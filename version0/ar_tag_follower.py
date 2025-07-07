import cv2
import numpy as np
from flask import Flask, Response
from gpiozero import Motor
import threading

# Motor setup
left_motor = Motor(forward=27, backward=17, enable=12)
right_motor = Motor(forward=22, backward=23, enable=13)

# Constants
DEAD_ZONE = 0.2
MAX_SPEED = 1.0

# ArUco dictionary setup (use a 4x4 dictionary for faster processing)
aruco_dict = cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_50)
parameters = cv2.aruco.DetectorParameters_create()

app = Flask(__name__)

# Global variables
frame = None
lock = threading.Lock()

def apply_dead_zone(value, dead_zone):
    if abs(value) < dead_zone:
        return 0
    return (value - dead_zone * (1 if value > 0 else -1)) / (1 - dead_zone)

def control_motors(throttle, steering):
    throttle = apply_dead_zone(throttle, DEAD_ZONE)
    steering = apply_dead_zone(steering, DEAD_ZONE)

    left_speed = throttle + steering
    right_speed = throttle - steering

    left_speed = max(-1, min(1, left_speed))
    right_speed = max(-1, min(1, right_speed))

    left_motor.value = left_speed
    right_motor.value = right_speed

    print(f"Left: {left_speed:.2f}, Right: {right_speed:.2f}")

def stop():
    left_motor.stop()
    right_motor.stop()

def process_frame(frame):
    global aruco_dict, parameters

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, rejected = cv2.aruco.detectMarkers(gray, aruco_dict, parameters=parameters)

    if ids is not None and 0 in ids:
        cv2.aruco.drawDetectedMarkers(frame, corners, ids)

        marker_center = np.mean(corners[0][0], axis=0)
        frame_center = frame.shape[1] / 2
        frame_bottom = frame.shape[0]

        steering = (marker_center[0] - frame_center) / (frame_center / 2)
        throttle = (frame_bottom - marker_center[1]) / (frame_bottom / 2)

        steering = np.clip(steering, -1, 1) * MAX_SPEED
        throttle = np.clip(throttle, -1, 1) * MAX_SPEED

        control_motors(throttle, steering)

        # Draw a box around the AR tag
        cv2.polylines(frame, [np.int32(corners[0][0])], True, (0, 255, 0), 2)
    else:
        stop()
        print("No AR tag detected")

    return frame

def generate_frames():
    global frame, lock

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    while True:
        success, frame = cap.read()
        if not success:
            break

        # Rotate the frame by 180 degrees
        frame = cv2.rotate(frame, cv2.ROTATE_180)

        with lock:
            frame = process_frame(frame)

        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

    cap.release()

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    return """
    <html>
    <head>
        <title>AR Tag Follower</title>
    </head>
    <body>
        <h1>AR Tag Follower</h1>
        <img src="/video_feed" width="640" height="480" />
    </body>
    </html>
    """

if __name__ == '__main__':
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)).start()
    generate_frames()

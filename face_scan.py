from flask import Flask, Response
import cv2
import time
import os
from gpiozero import Motor
import threading

app = Flask(__name__)

cascade_path = "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"

if not os.path.isfile(cascade_path):
    print(f"Error: Cascade file not found at {cascade_path}")
    exit()

face_cascade = cv2.CascadeClassifier(cascade_path)

camera = cv2.VideoCapture(0, cv2.CAP_V4L2)

if not camera.isOpened():
    print("Error: Could not open camera.")
    exit()

# Get and set FPS
max_fps = camera.get(cv2.CAP_PROP_FPS)
target_fps = max_fps * 0.9  # Set to 90% of max FPS
camera.set(cv2.CAP_PROP_FPS, target_fps)
actual_fps = camera.get(cv2.CAP_PROP_FPS)
print(f"Camera FPS set to: {actual_fps}")

# Set resolution
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# Initialize the head motor
head_motor = Motor(forward=5, backward=6, enable=26)

# Global variables for motor control
face_detected = False
motor_direction = 1  # 1 for forward, -1 for backward
interval_count = 0

def motor_control():
    global face_detected, motor_direction, interval_count
    while True:
        if not face_detected:
            if interval_count < 4:
                head_motor.value = 0.1 * motor_direction
                time.sleep(0.275)  # Rotate for 0.275 seconds
                head_motor.stop()
                time.sleep(0.825)  # Wait to make up the rest of 1.1 seconds
                interval_count += 1
            else:
                interval_count = 0
                motor_direction *= -1  # Reverse direction for next set of movements
        else:
            head_motor.stop()
        time.sleep(0.1)  # Small delay to prevent excessive CPU usage


def generate_frames():
    global face_detected
    while True:
        ret, frame = camera.read()
        if not ret:
            break
        
        frame = cv2.flip(frame, -1)  # Flip for upside-down camera
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        
        face_detected = len(faces) > 0
        
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
        
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    return """
    <html>
    <head>
        <title>Face Detection Stream</title>
    </head>
    <body>
        <h1>Face Detection Stream</h1>
        <img src="/video_feed" width="640" height="480" />
    </body>
    </html>
    """

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
    finally:
        head_motor.stop()
        camera.release()

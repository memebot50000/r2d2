from flask import Flask, Response
import cv2
import numpy as np
import time
import os
from gpiozero import Motor
import threading
import random

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

# Set resolution
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# Initialize the head motor
head_motor = Motor(forward=5, backward=6, enable=26)

# Parameters for random movement
TURN_RANGE = 30  # Degrees
TURN_SPEED = 0.1
current_angle = 0
target_angle = 0

# Parameters for optical flow
feature_params = dict(maxCorners=100, qualityLevel=0.3, minDistance=7, blockSize=7)
lk_params = dict(winSize=(15, 15), maxLevel=2, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))
color = np.random.randint(0, 255, (100, 3))

# Global variables
prev_frame = None
prev_points = None

def motor_control():
    global current_angle, target_angle
    while True:
        if abs(current_angle - target_angle) > 1:
            direction = 1 if target_angle > current_angle else -1
            head_motor.value = TURN_SPEED * direction
            time.sleep(0.05)
            current_angle += direction * 0.5  # Adjust this value to change turning speed
            head_motor.stop()
        else:
            target_angle = random.uniform(-TURN_RANGE, TURN_RANGE)
        time.sleep(0.1)

def generate_frames():
    global prev_frame, prev_points
    while True:
        ret, frame = camera.read()
        if not ret:
            break
        
        frame = cv2.flip(frame, -1)  # Flip for upside-down camera
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Face detection
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        
        if len(faces) > 0:
            for (x, y, w, h) in faces:
                # Draw rectangle around face
                cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
                
                # Draw markers at corners
                cv2.drawMarker(frame, (x, y), (0, 255, 0), cv2.MARKER_CROSS, 10, 2)
                cv2.drawMarker(frame, (x+w, y), (0, 255, 0), cv2.MARKER_CROSS, 10, 2)
                cv2.drawMarker(frame, (x, y+h), (0, 255, 0), cv2.MARKER_CROSS, 10, 2)
                cv2.drawMarker(frame, (x+w, y+h), (0, 255, 0), cv2.MARKER_CROSS, 10, 2)
            
            prev_points = None  # Reset optical flow points when face is detected
        else:
            # Optical flow
            if prev_frame is not None:
                if prev_points is None:
                    prev_points = cv2.goodFeaturesToTrack(prev_frame, mask=None, **feature_params)
                
                if prev_points is not None:
                    next_points, status, _ = cv2.calcOpticalFlowPyrLK(prev_frame, gray, prev_points, None, **lk_params)
                    
                    if next_points is not None:
                        good_new = next_points[status == 1]
                        good_old = prev_points[status == 1]
                        
                        for i, (new, old) in enumerate(zip(good_new, good_old)):
                            a, b = new.ravel()
                            c, d = old.ravel()
                            frame = cv2.line(frame, (int(a), int(b)), (int(c), int(d)), color[i].tolist(), 2)
                            frame = cv2.circle(frame, (int(a), int(b)), 5, color[i].tolist(), -1)
                    
                    prev_points = good_new.reshape(-1, 1, 2)
        
        prev_frame = gray
        
        # Display current and target angles
        cv2.putText(frame, f"Current angle: {current_angle:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(frame, f"Target angle: {target_angle:.2f}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    return """
    <html>
    <head>
        <title>Face Detection and Optical Flow Stream</title>
    </head>
    <body>
        <h1>Face Detection and Optical Flow Stream</h1>
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
        print("Initializing motor and starting thread")
        motor_thread = threading.Thread(target=motor_control, daemon=True)
        motor_thread.start()
        print("Motor thread started")
        app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
    finally:
        print("Stopping motor and releasing camera")
        head_motor.stop()
        camera.release()

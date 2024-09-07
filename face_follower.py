from flask import Flask, Response
import cv2
import numpy as np
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
face_position = 0  # 0 for center, negative for left, positive for right
last_known_face_position = 0
frames_without_face = 0
max_frames_without_face = 30  # Adjust this value to change how long to wait before returning

# Variables for optical flow
prev_frame = None
prev_points = None
flow_direction = 1  # 1 for right, -1 for left

# Parameters for ShiTomasi corner detection
feature_params = dict(maxCorners=100,
                      qualityLevel=0.3,
                      minDistance=7,
                      blockSize=7)

# Parameters for Lucas Kanade optical flow
lk_params = dict(winSize=(15, 15),
                 maxLevel=2,
                 criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))

# ... [previous imports and setup remain the same]

# Add this global variable for calibration
DIRECTION_CALIBRATION = -1  # Set to -1 to reverse the direction, 1 for original direction

# ... [other global variables remain the same]

def motor_control():
    global face_detected, face_position, last_known_face_position, frames_without_face, flow_direction
    print("Motor control thread started")
    while True:
        if face_detected:
            frames_without_face = 0
            if abs(face_position) > 30:  # Only move if face is significantly off-center
                # Use DIRECTION_CALIBRATION here
                head_motor.value = 0.1 * DIRECTION_CALIBRATION * flow_direction * (-1 if face_position < 0 else 1)
                time.sleep(0.05)  # Move for a shorter time
                head_motor.stop()
            else:
                head_motor.stop()
            last_known_face_position = face_position
        else:
            frames_without_face += 1
            if frames_without_face > max_frames_without_face:
                # Try to return to last known position
                if abs(last_known_face_position) > 10:  # Only move if last known position was off-center
                    # Use DIRECTION_CALIBRATION here as well
                    head_motor.value = 0.1 * DIRECTION_CALIBRATION * flow_direction * (-1 if last_known_face_position < 0 else 1)
                    time.sleep(0.05)
                    head_motor.stop()
                    last_known_face_position = last_known_face_position * 0.9  # Gradually reduce the target position
            else:
                head_motor.stop()
        time.sleep(0.1)  # Small delay to prevent excessive CPU usage

def generate_frames():
    global face_detected, face_position, last_known_face_position, frames_without_face, prev_frame, prev_points, flow_direction
    while True:
        ret, frame = camera.read()
        if not ret:
            break
        
        frame = cv2.flip(frame, -1)  # Flip for upside-down camera
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Optical flow
        if prev_frame is not None:
            if prev_points is None:
                prev_points = cv2.goodFeaturesToTrack(prev_frame, mask=None, **feature_params)
            
            if prev_points is not None and len(prev_points) > 0:
                next_points, status, _ = cv2.calcOpticalFlowPyrLK(prev_frame, gray, prev_points, None, **lk_params)
                
                if next_points is not None and len(next_points) > 0:
                    good_new = next_points[status == 1]
                    good_old = prev_points[status == 1]
                    
                    # Calculate overall flow direction
                    flow = good_new - good_old
                    avg_flow = np.mean(flow, axis=0)
                    if abs(avg_flow[0]) > 0.5:  # Threshold to avoid small movements
                        flow_direction = 1 if avg_flow[0] > 0 else -1
                    
                    # Draw flow vectors
                    for i, (new, old) in enumerate(zip(good_new, good_old)):
                        a, b = new.ravel()
                        c, d = old.ravel()
                        frame = cv2.line(frame, (int(a), int(b)), (int(c), int(d)), (0, 255, 0), 2)
                
                prev_points = good_new.reshape(-1, 1, 2)
        
        prev_frame = gray
        
        # Face detection
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        
        face_detected = len(faces) > 0
        
        if face_detected:
            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
                face_center_x = x + w // 2
                frame_center_x = frame.shape[1] // 2
                face_position = face_center_x - frame_center_x
                cv2.line(frame, (frame_center_x, 0), (frame_center_x, frame.shape[0]), (0, 255, 0), 1)
                cv2.line(frame, (face_center_x, 0), (face_center_x, frame.shape[0]), (0, 0, 255), 1)
        else:
            face_position = 0
        
        cv2.putText(frame, f"Face position: {face_position}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(frame, f"Last known: {last_known_face_position}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(frame, f"Frames without face: {frames_without_face}", (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(frame, f"Flow direction: {'Right' if flow_direction * DIRECTION_CALIBRATION > 0 else 'Left'}", (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# ... [rest of the code remains the same]

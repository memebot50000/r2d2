from flask import Flask, Response
import cv2
import time
import os

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

# Set resolution (adjust as needed)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

def generate_frames():
    while True:
        ret, frame = camera.read()
        if not ret:
            break
        
        frame = cv2.flip(frame, -1)  # Flip for upside-down camera
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors

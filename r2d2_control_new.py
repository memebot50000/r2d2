from gpiozero import Motor, Servo
import evdev
import time
import cv2
import numpy as np
import os
import threading
from flask import Flask, Response, render_template_string, request
import subprocess
import random

app = Flask(__name__)

# RC Car Control Constants
SPEKTRUM_VENDOR_ID = 0x0483
SPEKTRUM_PRODUCT_ID = 0x572b
DEAD_ZONE = 0.2  # 20% dead zone

# Face Detection and Optical Flow Constants
cascade_path = "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"
if not os.path.isfile(cascade_path):
    print(f"Error: Cascade file not found at {cascade_path}")
    exit()

face_cascade = cv2.CascadeClassifier(cascade_path)

camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
if not camera.isOpened():
    print("Error: Could not open camera.")
    exit()

camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# Motor Initialization
right_motor = Motor(forward=27, backward=17, enable=12)
left_motor = Motor(forward=22, backward=23, enable=13)
head_servo = Servo(12)  # New: servo on pin 12

# Optical Flow Parameters
feature_params = dict(maxCorners=100, qualityLevel=0.3, minDistance=7, blockSize=7)
lk_params = dict(winSize=(15, 15), maxLevel=2, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))
color = np.random.randint(0, 255, (100, 3))

# Global variables
prev_frame = None
prev_points = None
running = True
audio_lock = threading.Lock()
audio_process = None

# Motor and servo control state
left_motor_speed = 0
right_motor_speed = 0
servo_angle = 90  # degrees, 0-180

def normalize(value, min_val, max_val):
    return 2 * (value - min_val) / (max_val - min_val) - 1

def apply_dead_zone(value, dead_zone):
    if abs(value) < dead_zone:
        return 0
    return (value - dead_zone * (1 if value > 0 else -1)) / (1 - dead_zone)

def play_audio(file_path, duration=None):
    global audio_process
    with audio_lock:
        if audio_process:
            audio_process.terminate()
            audio_process.wait()
        if duration:
            start = random.uniform(0, max(0, 9 - duration))
            cmd = ["mpg123", "-a", "hw:1,0", "-q", "-k", str(int(start)), file_path]
        else:
            cmd = ["mpg123", "-a", "hw:1,0", "-q", file_path]
        audio_process = subprocess.Popen(cmd)
        if duration:
            time.sleep(duration)
            audio_process.terminate()
            audio_process.wait()

def update_motors():
    # Called after every slider update
    global left_motor_speed, right_motor_speed
    # Left motor
    if left_motor_speed > 0:
        left_motor.forward(left_motor_speed)
    elif left_motor_speed < 0:
        left_motor.backward(-left_motor_speed)
    else:
        left_motor.stop()
    # Right motor
    if right_motor_speed > 0:
        right_motor.forward(right_motor_speed)
    elif right_motor_speed < 0:
        right_motor.backward(-right_motor_speed)
    else:
        right_motor.stop()

def set_servo(angle):
    # Map 0-180 degrees to -1 to 1 for gpiozero Servo
    value = (angle / 90.0) - 1
    head_servo.value = max(-1, min(1, value))

def generate_frames():
    global prev_frame, prev_points
    while running:
        ret, frame = camera.read()
        if not ret:
            break
        frame = cv2.flip(frame, -1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        if len(faces) > 0:
            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
                cv2.drawMarker(frame, (x, y), (0, 255, 0), cv2.MARKER_CROSS, 10, 2)
                cv2.drawMarker(frame, (x+w, y), (0, 255, 0), cv2.MARKER_CROSS, 10, 2)
                cv2.drawMarker(frame, (x, y+h), (0, 255, 0), cv2.MARKER_CROSS, 10, 2)
                cv2.drawMarker(frame, (x+w, y+h), (0, 255, 0), cv2.MARKER_CROSS, 10, 2)
            prev_points = None
        else:
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
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

def play_random_segments():
    while running:
        play_audio("sound1.mp3", duration=2)
        time.sleep(random.uniform(5, 15))

@app.route('/')
def index():
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>R2D2 Control Panel</title>
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        <style>
            #controls {
                margin-top: 20px;
            }
            .slider-label {
                display: block;
                margin-top: 10px;
            }
            .slider {
                width: 300px;
            }
        </style>
    </head>
    <body>
        <h1>R2D2 Control Panel</h1>
        <img src="{{ url_for('video_feed') }}" width="640" height="480" />
        <div id="controls">
            <label class="slider-label">Left Motor Speed</label>
            <input type="range" min="-1" max="1" step="0.01" value="0" id="left_motor" class="slider">
            <span id="left_motor_val">0</span>
            <br>
            <label class="slider-label">Right Motor Speed</label>
            <input type="range" min="-1" max="1" step="0.01" value="0" id="right_motor" class="slider">
            <span id="right_motor_val">0</span>
            <br>
            <label class="slider-label">Head Servo Angle</label>
            <input type="range" min="0" max="180" step="1" value="90" id="servo_angle" class="slider">
            <span id="servo_angle_val">90</span>
        </div>
        <script>
            function sendControls() {
                $.post('/set_controls', {
                    left_motor: $('#left_motor').val(),
                    right_motor: $('#right_motor').val(),
                    servo_angle: $('#servo_angle').val()
                });
            }
            $('.slider').on('input change', function() {
                $('#left_motor_val').text($('#left_motor').val());
                $('#right_motor_val').text($('#right_motor').val());
                $('#servo_angle_val').text($('#servo_angle').val());
                sendControls();
            });
        </script>
    </body>
    </html>
    ''')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/set_controls', methods=['POST'])
def set_controls():
    global left_motor_speed, right_motor_speed, servo_angle
    try:
        left_motor_speed = float(request.form.get('left_motor', 0))
        right_motor_speed = float(request.form.get('right_motor', 0))
        servo_angle = int(request.form.get('servo_angle', 90))
        update_motors()
        set_servo(servo_angle)
        return 'OK'
    except Exception as e:
        return f'Error: {e}', 400

if __name__ == '__main__':
    try:
        print("Initializing motors and starting threads")
        random_sound_thread = threading.Thread(target=play_random_segments, daemon=True)
        random_sound_thread.start()
        print("Threads started")
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False, threaded=True)
    except KeyboardInterrupt:
        print("\nProgram interrupted by user. Exiting...")
    finally:
        running = False
        print("Stopping motors and releasing camera")
        left_motor.stop()
        right_motor.stop()
        head_servo.detach()
        camera.release()
        play_audio("sound2.mp3")
        if audio_process:
            audio_process.wait()
        print("Cleanup complete")

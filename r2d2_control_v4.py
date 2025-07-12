# Copy of v3, but with all depth perception code removed
import os
import time
import cv2
import numpy as np
import threading
from flask import Flask, Response, render_template_string, request
import subprocess
import random
import RPi.GPIO as GPIO
import urllib.request
from gpiozero import Motor

app = Flask(__name__)

# Motor Initialization
right_motor = Motor(forward=17, backward=27, enable=12)
left_motor = Motor(forward=23, backward=22, enable=13)

# Head Servo Initialization
SERVO_PIN = 18  # BCM numbering
GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)
pwm = GPIO.PWM(SERVO_PIN, 50)
pwm.start(0)

SERVO_POSITIONS = {
    'left': 20,
    'left-center': 50,
    'center': 80,
    'right-center': 110,
    'right': 140
}
current_servo_position = 'center'
servo_lock = threading.Lock()

# Camera Initialization
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
if not camera.isOpened():
    print("Error: Could not open camera.")
    exit()
# Zoom out: set a wider field of view if possible
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
# Try to set focus to auto (if supported)
try:
    camera.set(cv2.CAP_PROP_AUTOFOCUS, 1)
except Exception:
    pass

# Shared frame buffer for camera
shared_frame = None
shared_frame_lock = threading.Lock()

# Face detection setup
cascade_path = "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"
if not os.path.isfile(cascade_path):
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
face_cascade = cv2.CascadeClassifier(cascade_path)
print("Cascade loaded:", not face_cascade.empty())
if face_cascade.empty():
    print(f"Error: Could not load face cascade from {cascade_path}")
    exit(1)
face_detection_enabled = False
face_detection_lock = threading.Lock()

# Shared cache for async face detection
last_face_boxes = []
last_face_lock = threading.Lock()

# Camera reader thread
class CameraReaderThread(threading.Thread):
    def __init__(self, camera):
        super().__init__(daemon=True)
        self.camera = camera
        self.running = True
    def run(self):
        global shared_frame
        while self.running:
            ret, frame = self.camera.read()
            if not ret:
                time.sleep(0.01)
                continue
            with shared_frame_lock:
                shared_frame = frame.copy()
            time.sleep(0.01)

camera_reader_thread = CameraReaderThread(camera)
camera_reader_thread.start()

# Async face detection thread
class FaceThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.running = True
        self.frame_count = 0
    def run(self):
        global last_face_boxes
        while self.running:
            with shared_frame_lock:
                frame = shared_frame.copy() if shared_frame is not None else None
            if frame is None:
                time.sleep(0.01)
                continue
            self.frame_count += 1
            if self.frame_count % 3 != 0:
                time.sleep(0.01)
                continue
            small = cv2.resize(frame, (320, 180))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(20, 20))
            print(f"[FaceThread] Detected {len(faces)} faces")
            boxes = []
            for (x, y, w, h) in faces:
                fx = frame.shape[1] / 320
                fy = frame.shape[0] / 180
                boxes.append((int(x*fx), int(y*fy), int(w*fx), int(h*fy)))
            with last_face_lock:
                last_face_boxes = boxes
            time.sleep(0.03)

face_thread = FaceThread()
face_thread.start()

# Motor control state
current_throttle = 0.0
current_steering = 0.0
MOTOR_UPDATE_INTERVAL = 0.05  # seconds

# Deadzone logic
DEAD_ZONE = 0.2  # 20% dead zone
def apply_dead_zone(value, dead_zone):
    if abs(value) < dead_zone:
        return 0
    return (value - dead_zone * (1 if value > 0 else -1)) / (1 - dead_zone)

# Motor arming state
default_armed = False
motors_armed = default_armed
motors_armed_lock = threading.Lock()

# Audio process state
audio_lock = threading.Lock()
audio_process = None

# Global running flag for threads
running = True

# --- Utility Functions ---
def play_audio(file_path, duration=None):
    global audio_process
    with audio_lock:
        if audio_process:
            audio_process.terminate()
            audio_process.wait()
        cmd = ["mpg123", "-a", "hw:1,0", "-q", file_path]
        audio_process = subprocess.Popen(cmd)
        if duration:
            time.sleep(duration)
            audio_process.terminate()
            audio_process.wait()

def angle_to_duty(angle):
    return 2.5 + (angle / 180.0) * 10.0

def set_servo_position(position_name):
    global current_servo_position
    angle = SERVO_POSITIONS.get(position_name, 80)
    duty = angle_to_duty(angle)
    with servo_lock:
        pwm.ChangeDutyCycle(duty)
        time.sleep(0.3)
        pwm.ChangeDutyCycle(0)
    current_servo_position = position_name

def cleanup():
    global running
    running = False
    print("Stopping motors and releasing camera")
    try:
        left_motor.stop()
    except Exception:
        pass
    try:
        right_motor.stop()
    except Exception:
        pass
    try:
        pwm.stop()
        GPIO.cleanup()
    except Exception:
        pass
    try:
        camera.release()
    except Exception:
        pass
    try:
        play_audio("sound2.mp3")
    except Exception:
        pass
    if audio_process:
        try:
            audio_process.wait()
        except Exception:
            pass
    print("Cleanup complete")

# --- Threads ---
def head_servo_control():
    last_position = None
    while running:
        if current_servo_position != last_position:
            set_servo_position(current_servo_position)
            last_position = current_servo_position
        time.sleep(0.05)

def motor_control_loop():
    global current_throttle, current_steering, motors_armed
    while running:
        with motors_armed_lock:
            armed = motors_armed
        if not armed:
            left_motor.stop()
            right_motor.stop()
            time.sleep(MOTOR_UPDATE_INTERVAL)
            continue
        # Map joystick values to motor speeds
        throttle = current_throttle  # -1 to 1
        steering = current_steering  # -1 to 1
        left_speed = throttle + steering
        right_speed = throttle - steering
        left_speed = max(-1, min(1, left_speed))
        right_speed = max(-1, min(1, right_speed))
        if left_speed > 0:
            left_motor.forward(left_speed)
        elif left_speed < 0:
            left_motor.backward(-left_speed)
        else:
            left_motor.stop()
        if right_speed > 0:
            right_motor.forward(right_speed)
        elif right_speed < 0:
            right_motor.backward(-right_speed)
        else:
            right_motor.stop()
        time.sleep(MOTOR_UPDATE_INTERVAL)

def play_random_segments():
    while running:
        play_audio("sound1.mp3", duration=2)
        time.sleep(random.uniform(5, 15))

def generate_frames():
    while running:
        with shared_frame_lock:
            frame = shared_frame.copy() if shared_frame is not None else None
        if frame is None:
            time.sleep(0.01)
            continue
        frame = cv2.flip(frame, -1)
        # Face detection mode
        with face_detection_lock:
            detect_faces = face_detection_enabled
        if detect_faces:
            with last_face_lock:
                boxes = list(last_face_boxes)
            for (x, y, w, h) in boxes:
                cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 142, 72), 4)
                overlay = frame.copy()
                cv2.rectangle(overlay, (x, y), (x+w, y+h), (255, 142, 72), -1)
                alpha = 0.15
                cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

# --- Flask Endpoints ---
@app.route('/')
def index():
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>R2D2 Control Panel</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/nipplejs/0.9.0/nipplejs.min.js"></script>
        <style>
            html, body {
                height: 100%;
                margin: 0;
                padding: 0;
                background: #181a20;
                color: #f5f6fa;
                font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
                overflow: hidden;
            }
            body {
                display: flex;
                flex-direction: column;
                height: 100vh;
                width: 100vw;
            }
            #main-content {
                flex: 1 1 auto;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100vh;
                width: 100vw;
                overflow: hidden;
            }
            #camera-container {
                width: 100vw;
                height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                background: #111217;
                position: absolute;
                top: 0; left: 0; right: 0; bottom: 0;
                z-index: 1;
            }
            #camera-feed {
                width: 1280px;
                height: 720px;
                max-width: 95vw;
                max-height: 90vh;
                object-fit: contain;
                background: #000;
                display: block;
                border-radius: 18px;
                box-shadow: 0 4px 32px 0 #000a;
            }
            #joystick-container {
                position: absolute;
                top: 40px;
                left: 40px;
                z-index: 3;
                width: 140px;
                height: 140px;
                background: rgba(24,26,32,0.85);
                border-radius: 18px;
                box-shadow: 0 4px 32px 0 #000a;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            #arm-switch-container {
                position: absolute;
                top: 200px;
                left: 40px;
                z-index: 4;
                display: flex;
                align-items: center;
                gap: 16px;
                background: rgba(24,26,32,0.85);
                border-radius: 18px;
                box-shadow: 0 4px 32px 0 #000a;
                padding: 14px 24px;
            }
            .switch {
                position: relative;
                display: inline-block;
                width: 60px;
                height: 34px;
            }
            .switch input {display:none;}
            .slider {
                position: absolute;
                cursor: pointer;
                top: 0; left: 0; right: 0; bottom: 0;
                background: #232a3a;
                border-radius: 34px;
                transition: .4s;
            }
            .slider:before {
                position: absolute;
                content: "";
                height: 26px;
                width: 26px;
                left: 4px;
                bottom: 4px;
                background: #f5f6fa;
                border-radius: 50%;
                transition: .4s;
                box-shadow: 0 2px 8px 0 #0006;
            }
            input:checked + .slider {
                background: linear-gradient(90deg, #4e8cff 0%, #1e3c72 100%);
            }
            input:checked + .slider:before {
                transform: translateX(26px);
                background: #4e8cff;
            }
            #arm-label {
                font-size: 1.1rem;
                font-weight: 500;
                color: #f5f6fa;
                letter-spacing: 0.04em;
                margin-left: 8px;
            }
            #servo-controls {
                position: absolute;
                bottom: 40px;
                left: 50%;
                transform: translateX(-50%);
                z-index: 2;
                display: flex;
                gap: 18px;
                background: rgba(24,26,32,0.85);
                border-radius: 18px;
                box-shadow: 0 4px 32px 0 #000a;
                padding: 18px 32px;
            }
            .servo-btn {
                font-size: 1.2rem;
                font-weight: 500;
                color: #f5f6fa;
                background: linear-gradient(90deg, #23242a 0%, #232a3a 100%);
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                cursor: pointer;
                transition: background 0.2s, color 0.2s, box-shadow 0.2s;
                outline: none;
                box-shadow: 0 2px 8px 0 #0006;
                letter-spacing: 0.04em;
            }
            .servo-btn.selected, .servo-btn:hover {
                background: linear-gradient(90deg, #4e8cff 0%, #1e3c72 100%);
                color: #fff;
                box-shadow: 0 4px 16px 0 #4e8cff44;
            }
            #shutdown-btn {
                position: absolute;
                bottom: 40px;
                right: 40px;
                z-index: 3;
                background: linear-gradient(90deg, #ff3b3b 0%, #a80000 100%);
                color: #fff;
                font-size: 1.1rem;
                font-weight: 600;
                border: none;
                border-radius: 8px;
                padding: 16px 32px;
                cursor: pointer;
                box-shadow: 0 2px 12px 0 #a8000055;
                transition: background 0.2s, box-shadow 0.2s;
            }
            #shutdown-btn:hover {
                background: linear-gradient(90deg, #a80000 0%, #ff3b3b 100%);
                box-shadow: 0 4px 24px 0 #ff3b3b55;
            }
            #face-detect-switch-container {
                position: absolute;
                top: 260px;
                left: 40px;
                z-index: 4;
                display: flex;
                align-items: center;
                gap: 16px;
                background: rgba(24,26,32,0.85);
                border-radius: 18px;
                box-shadow: 0 4px 32px 0 #000a;
                padding: 14px 24px;
            }
            #face-detect-label {
                font-size: 1.1rem;
                font-weight: 500;
                color: #f5f6fa;
                letter-spacing: 0.04em;
                margin-left: 8px;
            }
            @media (max-width: 900px) {
                #servo-controls {
                    flex-direction: column;
                    bottom: 20px;
                    padding: 12px 10px;
                    gap: 10px;
                }
                .servo-btn {
                    font-size: 1rem;
                    padding: 10px 12px;
                }
                #shutdown-btn {
                    bottom: 10px;
                    right: 10px;
                    padding: 10px 18px;
                    font-size: 1rem;
                }
                #joystick-container {
                    top: 10px;
                    left: 10px;
                    width: 90px;
                    height: 90px;
                }
            }
        </style>
    </head>
    <body>
        <div id="main-content">
            <div id="camera-container">
                <img id="camera-feed" src="{{ url_for('video_feed') }}" alt="Camera Feed" />
            </div>
            <div id="joystick-container">
                <div id="joystick"></div>
            </div>
            <div id="arm-switch-container">
                <label class="switch">
                  <input type="checkbox" id="arm-switch">
                  <span class="slider"></span>
                </label>
                <span id="arm-label">Motors Disarmed</span>
            </div>
            <div id="face-detect-switch-container">
                <label class="switch">
                  <input type="checkbox" id="face-detect-switch">
                  <span class="slider"></span>
                </label>
                <span id="face-detect-label">Face Detection Off</span>
            </div>
            <div id="servo-controls">
                <button class="servo-btn" data-pos="left">Left</button>
                <button class="servo-btn" data-pos="left-center">Left-Center</button>
                <button class="servo-btn" data-pos="center">Center</button>
                <button class="servo-btn" data-pos="right-center">Right-Center</button>
                <button class="servo-btn" data-pos="right">Right</button>
            </div>
            <button id="shutdown-btn">Shutdown</button>
        </div>
        <script>
            // Joystick logic using nipplejs
            var throttle = 0.0;
            var steering = 0.0;
            var joystick = nipplejs.create({
                zone: document.getElementById('joystick'),
                mode: 'static',
                position: {left: '50%', top: '50%'},
                color: '#4e8cff',
                size: 90
            });
            function sendJoystick(throttle, steering) {
                $.post('/joystick', {throttle: throttle, steering: steering});
            }
            joystick.on('move', function(evt, data) {
                if (data && data.distance) {
                    var angle = data.angle ? data.angle.radian : 0;
                    var dist = Math.min(data.distance, 50);
                    var norm = dist / 50;
                    var x = Math.cos(angle) * norm;
                    var y = Math.sin(angle) * norm;
                    // y: up is -1, down is 1 (invert for throttle)
                    sendJoystick(-y, x);
                }
            });
            joystick.on('end', function() {
                sendJoystick(0, 0);
            });
            // Servo UI logic
            function setServoPosition(pos) {
                $.post('/set_servo', {position: pos}, function() {
                    $(".servo-btn").removeClass('selected');
                    $(`.servo-btn[data-pos='${pos}']`).addClass('selected');
                });
            }
            $('.servo-btn').click(function() {
                var pos = $(this).data('pos');
                setServoPosition(pos);
            });
            $(function() {
                setServoPosition('{{ current_servo_position }}');
            });
            // Arm/disarm switch logic
            var armSwitch = document.getElementById('arm-switch');
            var armLabel = document.getElementById('arm-label');
            function setArmState(armed) {
                $.post('/arm', {state: armed ? 'true' : 'false'});
                armLabel.textContent = armed ? 'Motors Armed' : 'Motors Disarmed';
                if (armed) {
                    armLabel.style.color = '#4e8cff';
                } else {
                    armLabel.style.color = '#f5f6fa';
                }
            }
            armSwitch.addEventListener('change', function() {
                setArmState(armSwitch.checked);
            });
            // Set initial state
            setArmState(
                {{ 'true' if motors_armed else 'false' }}
            );
            // Face detection switch logic
            var faceSwitch = document.getElementById('face-detect-switch');
            var faceLabel = document.getElementById('face-detect-label');
            function setFaceDetectionState(enabled) {
                $.post('/face_detection', {state: enabled ? 'true' : 'false'});
                faceLabel.textContent = enabled ? 'Face Detection On' : 'Face Detection Off';
                if (enabled) {
                    faceLabel.style.color = '#4e8cff';
                } else {
                    faceLabel.style.color = '#f5f6fa';
                }
            }
            faceSwitch.addEventListener('change', function() {
                setFaceDetectionState(faceSwitch.checked);
            });
            // Set initial state
            setFaceDetectionState(false);
            // Shutdown button logic
            $('#shutdown-btn').click(function() {
                if (confirm('Are you sure you want to shutdown the server?')) {
                    $.post('/shutdown', function() {
                        $('#shutdown-btn').text('Shutting down...').prop('disabled', true);
                    });
                }
            });
        </script>
    </body>
    </html>
    ''', current_servo_position=current_servo_position)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/set_servo', methods=['POST'])
def set_servo():
    global current_servo_position
    pos = request.form.get('position')
    if pos in SERVO_POSITIONS:
        current_servo_position = pos
    return 'OK'

@app.route('/joystick', methods=['POST'])
def joystick():
    global current_throttle, current_steering
    try:
        throttle = float(request.form.get('throttle', 0.0))
        steering = float(request.form.get('steering', 0.0))
        # Apply deadzone and clamp
        current_throttle = max(-1, min(1, apply_dead_zone(throttle, DEAD_ZONE)))
        current_steering = max(-1, min(1, apply_dead_zone(steering, DEAD_ZONE)))
    except Exception:
        current_throttle = 0.0
        current_steering = 0.0
    return 'OK'

@app.route('/arm', methods=['POST'])
def arm():
    global motors_armed
    state = request.form.get('state')
    with motors_armed_lock:
        if state == 'true':
            motors_armed = True
        else:
            motors_armed = False
    play_audio('sound3.mp3')
    return 'OK'

@app.route('/face_detection', methods=['POST'])
def face_detection():
    global face_detection_enabled
    state = request.form.get('state')
    with face_detection_lock:
        face_detection_enabled = (state == 'true')
    return 'OK'

@app.route('/shutdown', methods=['POST'])
def shutdown():
    cleanup()
    os._exit(0)

if __name__ == '__main__':
    try:
        print("Initializing motors and starting threads")
        head_servo_thread = threading.Thread(target=head_servo_control, daemon=True)
        motor_thread = threading.Thread(target=motor_control_loop, daemon=True)
        random_sound_thread = threading.Thread(target=play_random_segments, daemon=True)
        head_servo_thread.start()
        motor_thread.start()
        random_sound_thread.start()
        print("Threads started")
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False, threaded=True)
    except KeyboardInterrupt:
        print("\nProgram interrupted by user. Exiting...")
    finally:
        cleanup() 

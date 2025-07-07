import RPi.GPIO as GPIO
import time
from flask import Flask, Response, render_template_string, request
import threading
import cv2
import numpy as np
import os
from gpiozero import Motor
import subprocessimport RPi.GPIO as GPIO
import time
from flask import Flask, Response, render_template_string, request
import threading
import cv2
import numpy as np
import os
from gpiozero import Motor
import subprocess
import random

app = Flask(__name__)

# Camera and face detection setup
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

# Motor setup (gpiozero)
right_motor = Motor(forward=27, backward=17, enable=12)
left_motor = Motor(forward=22, backward=23, enable=13)

# Servo setup (RPi.GPIO, 100Hz)
SERVO_PIN = 12  # BOARD numbering (physical pin 12, GPIO 18)
GPIO.setmode(GPIO.BOARD)
GPIO.setup(SERVO_PIN, GPIO.OUT)
servo_lock = threading.Lock()

def AngleToDuty(pos):
    return float(pos)/10.+5.

def move_servo(angle):
    with servo_lock:
        pwm = GPIO.PWM(SERVO_PIN, 100)
        pwm.start(AngleToDuty(angle))
        time.sleep(0.4)
        pwm.stop()

# Motor and control state
throttle = 0
steering = 0

def update_motors():
    left_speed = throttle + steering
    right_speed = throttle - steering
    left_speed = max(-1, min(1, left_speed))
    right_speed = max(-1, min(1, right_speed))
    # Left motor
    if left_speed > 0:
        left_motor.forward(left_speed)
    elif left_speed < 0:
        left_motor.backward(-left_speed)
    else:
        left_motor.stop()
    # Right motor
    if right_speed > 0:
        right_motor.forward(right_speed)
    elif right_speed < 0:
        right_motor.backward(-right_speed)
    else:
        right_motor.stop()

def generate_frames():
    while True:
        ret, frame = camera.read()
        if not ret:
            break
        frame = cv2.flip(frame, -1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 200, 255), 2)
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# --- MP3 Sound Stuff ---
audio_lock = threading.Lock()
audio_process = None
running = True

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
        <link href="https://fonts.googleapis.com/css?family=Orbitron:700&display=swap" rel="stylesheet">
        <style>
            body {
                background: #181c25;
                color: #f0f0f0;
                font-family: 'Orbitron', Arial, sans-serif;
                margin: 0;
                padding: 0;
                overflow: hidden;
            }
            #container {
                display: flex;
                flex-direction: row;
                justify-content: center;
                align-items: flex-start;
                height: 100vh;
                width: 100vw;
                box-sizing: border-box;
            }
            #video {
                display: block;
                margin: 40px 0 40px 40px;
                border-radius: 20px;
                box-shadow: 0 0 30px #00eaff22;
                border: 3px solid #00eaff22;
                max-width: 60vw;
                max-height: 80vh;
            }
            #controls {
                background: #23283a;
                border-radius: 20px;
                padding: 40px 30px 40px 30px;
                box-shadow: 0 0 30px #00eaff22;
                margin: 40px 40px 40px 0;
                max-width: 400px;
                min-width: 320px;
                display: flex;
                flex-direction: column;
                align-items: center;
            }
            #joystick {
                width: 200px;
                height: 200px;
                background: linear-gradient(135deg, #23283a 60%, #00eaff22 100%);
                border-radius: 50%;
                position: relative;
                margin: 0 auto 15px auto;
                box-shadow: 0 0 20px #00eaff33;
                border: 2px solid #00eaff44;
                user-select: none;
                touch-action: none;
            }
            #stick {
                width: 60px;
                height: 60px;
                background: radial-gradient(circle, #00eaff 60%, #181c25 100%);
                border-radius: 50%;
                position: absolute;
                left: 70px;
                top: 70px;
                cursor: pointer;
                box-shadow: 0 0 20px #00eaff88;
                border: 2px solid #00eaff;
                touch-action: none;
                transition: box-shadow 0.2s;
            }
            #stick:active {
                box-shadow: 0 0 30px #00eaffcc;
            }
            .slider-label {
                display: block;
                margin: 30px 0 10px 0;
                font-size: 1.1em;
                color: #00eaff;
                letter-spacing: 2px;
            }
            .slider {
                width: 100%;
                max-width: 350px;
                margin: 0 auto;
                display: block;
                accent-color: #00eaff;
                background: #23283a;
                border-radius: 10px;
                height: 8px;
                box-shadow: 0 0 10px #00eaff44;
            }
            #servo_angle_val {
                margin-left: 12px;
                color: #00eaff;
                font-weight: bold;
                font-size: 1.1em;
            }
            .readout {
                display: inline-block;
                margin: 0 20px 0 0;
                font-size: 1.1em;
                color: #00eaff;
                font-weight: bold;
            }
            @media (max-width: 1200px) {
                #container { flex-direction: column; align-items: center; }
                #video { margin: 40px auto 0 auto; max-width: 90vw; }
                #controls { margin: 30px auto 0 auto; }
            }
        </style>
    </head>
    <body>
        <div id="container">
            <img id="video" src="{{ url_for('video_feed') }}" width="640" height="480" />
            <div id="controls">
                <label style="margin-bottom:10px;">Drive Joystick</label>
                <div id="joystick"><div id="stick"></div></div>
                <span class="readout">Throttle: <span id="throttle_val">0</span></span>
                <span class="readout">Steering: <span id="steering_val">0</span></span>
                <label class="slider-label">Head Servo Angle</label>
                <input type="range" min="0" max="180" step="1" value="90" id="servo_angle" class="slider">
                <span id="servo_angle_val">90</span>
            </div>
        </div>
        <script>
            // Joystick logic
            var joystick = document.getElementById('joystick');
            var stick = document.getElementById('stick');
            var dragging = false;
            var centerX = joystick.offsetWidth / 2;
            var centerY = joystick.offsetHeight / 2;
            var maxRadius = joystick.offsetWidth / 2 - stick.offsetWidth / 2;
            var throttle = 0, steering = 0;
            var last_servo_angle = 90;

            function sendControls() {
                $.post('/set_controls', {
                    throttle: throttle,
                    steering: steering
                });
            }

            function sendServo(angle) {
                $.post('/set_servo', {servo_angle: angle});
                last_servo_angle = angle;
            }

            function updateStick(x, y) {
                stick.style.left = (x - stick.offsetWidth / 2) + 'px';
                stick.style.top = (y - stick.offsetHeight / 2) + 'px';
            }

            function resetStick() {
                updateStick(centerX, centerY);
                throttle = 0;
                steering = 0;
                $('#throttle_val').text(throttle);
                $('#steering_val').text(steering);
                sendControls();
                // Reset servo to center when joystick released
                if (last_servo_angle !== 90) {
                    sendServo(90);
                }
            }

            stick.addEventListener('mousedown', function(e) { dragging = true; });
            document.addEventListener('mouseup', function(e) {
                if (dragging) { dragging = false; resetStick(); }
            });
            document.addEventListener('mousemove', function(e) {
                if (dragging) {
                    var rect = joystick.getBoundingClientRect();
                    var x = e.clientX - rect.left;
                    var y = e.clientY - rect.top;
                    var dx = x - centerX;
                    var dy = y - centerY;
                    var dist = Math.sqrt(dx*dx + dy*dy);
                    if (dist > maxRadius) {
                        dx = dx * maxRadius / dist;
                        dy = dy * maxRadius / dist;
                        x = centerX + dx;
                        y = centerY + dy;
                    }
                    updateStick(x, y);
                    steering = +(dx / maxRadius).toFixed(2);
                    throttle = +(-(dy / maxRadius)).toFixed(2);
                    $('#throttle_val').text(throttle);
                    $('#steering_val').text(steering);
                    sendControls();
                    // Move servo proportional to joystick X, map [-1,1] to [45,135]
                    var servoPos = Math.round(90 + steering * 45);
                    if (servoPos !== last_servo_angle) {
                        sendServo(servoPos);
                    }
                }
            });
            // Touch support
            stick.addEventListener('touchstart', function(e) { dragging = true; e.preventDefault(); });
            document.addEventListener('touchend', function(e) {
                if (dragging) { dragging = false; resetStick(); }
            });
            document.addEventListener('touchmove', function(e) {
                if (dragging && e.touches.length == 1) {
                    var rect = joystick.getBoundingClientRect();
                    var x = e.touches[0].clientX - rect.left;
                    var y = e.touches[0].clientY - rect.top;
                    var dx = x - centerX;
                    var dy = y - centerY;
                    var dist = Math.sqrt(dx*dx + dy*dy);
                    if (dist > maxRadius) {
                        dx = dx * maxRadius / dist;
                        dy = dy * maxRadius / dist;
                        x = centerX + dx;
                        y = centerY + dy;
                    }
                    updateStick(x, y);
                    steering = +(dx / maxRadius).toFixed(2);
                    throttle = +(-(dy / maxRadius)).toFixed(2);
                    $('#throttle_val').text(throttle);
                    $('#steering_val').text(steering);
                    sendControls();
                    var servoPos = Math.round(90 + steering * 45);
                    if (servoPos !== last_servo_angle) {
                        sendServo(servoPos);
                    }
                }
            });

            // Initialize stick
            resetStick();

            // Servo slider (only sends when changed)
            $('#servo_angle').on('input change', function() {
                $('#servo_angle_val').text($('#servo_angle').val());
                var angle = parseInt($('#servo_angle').val());
                sendServo(angle);
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
    global throttle, steering
    try:
        throttle = float(request.form.get('throttle', 0))
        steering = float(request.form.get('steering', 0))
        update_motors()
        return 'OK'
    except Exception as e:
        return f'Error: {e}', 400

@app.route('/set_servo', methods=['POST'])
def set_servo():
    try:
        angle = int(request.form.get('servo_angle', 90))
        threading.Thread(target=move_servo, args=(angle,), daemon=True).start()
        return 'OK'
    except Exception as e:
        return f'Error: {e}', 400

if __name__ == '__main__':
    try:
        # Start random sound thread
        random_sound_thread = threading.Thread(target=play_random_segments, daemon=True)
        random_sound_thread.start()
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False, threaded=True)
    finally:
        running = False
        left_motor.stop()
        right_motor.stop()
        GPIO.cleanup()
        camera.release()
        play_audio("sound2.mp3")
        if audio_process:
            audio_process.wait()

import random

app = Flask(__name__)

# Camera and face detection setup
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

# Motor setup (gpiozero)
right_motor = Motor(forward=27, backward=17, enable=12)
left_motor = Motor(forward=22, backward=23, enable=13)

# Servo setup (RPi.GPIO, 100Hz)
SERVO_PIN = 12  # BOARD numbering (physical pin 12, GPIO 18)
GPIO.setmode(GPIO.BOARD)
GPIO.setup(SERVO_PIN, GPIO.OUT)
servo_lock = threading.Lock()

def AngleToDuty(pos):
    return float(pos)/10.+5.

def move_servo(angle):
    with servo_lock:
        pwm = GPIO.PWM(SERVO_PIN, 100)
        pwm.start(AngleToDuty(angle))
        time.sleep(0.4)
        pwm.stop()

# Motor and control state
throttle = 0
steering = 0

def update_motors():
    left_speed = throttle + steering
    right_speed = throttle - steering
    left_speed = max(-1, min(1, left_speed))
    right_speed = max(-1, min(1, right_speed))
    # Left motor
    if left_speed > 0:
        left_motor.forward(left_speed)
    elif left_speed < 0:
        left_motor.backward(-left_speed)
    else:
        left_motor.stop()
    # Right motor
    if right_speed > 0:
        right_motor.forward(right_speed)
    elif right_speed < 0:
        right_motor.backward(-right_speed)
    else:
        right_motor.stop()

def generate_frames():
    while True:
        ret, frame = camera.read()
        if not ret:
            break
        frame = cv2.flip(frame, -1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 200, 255), 2)
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# --- MP3 Sound Stuff ---
audio_lock = threading.Lock()
audio_process = None
running = True

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
        <link href="https://fonts.googleapis.com/css?family=Orbitron:700&display=swap" rel="stylesheet">
        <style>
            body {
                background: #181c25;
                color: #f0f0f0;
                font-family: 'Orbitron', Arial, sans-serif;
                margin: 0;
                padding: 0;
                overflow: hidden;
            }
            #container {
                display: flex;
                flex-direction: row;
                justify-content: center;
                align-items: flex-start;
                height: 100vh;
                width: 100vw;
                box-sizing: border-box;
            }
            #video {
                display: block;
                margin: 40px 0 40px 40px;
                border-radius: 20px;
                box-shadow: 0 0 30px #00eaff22;
                border: 3px solid #00eaff22;
                max-width: 60vw;
                max-height: 80vh;
            }
            #controls {
                background: #23283a;
                border-radius: 20px;
                padding: 40px 30px 40px 30px;
                box-shadow: 0 0 30px #00eaff22;
                margin: 40px 40px 40px 0;
                max-width: 400px;
                min-width: 320px;
                display: flex;
                flex-direction: column;
                align-items: center;
            }
            #joystick {
                width: 200px;
                height: 200px;
                background: linear-gradient(135deg, #23283a 60%, #00eaff22 100%);
                border-radius: 50%;
                position: relative;
                margin: 0 auto 15px auto;
                box-shadow: 0 0 20px #00eaff33;
                border: 2px solid #00eaff44;
                user-select: none;
                touch-action: none;
            }
            #stick {
                width: 60px;
                height: 60px;
                background: radial-gradient(circle, #00eaff 60%, #181c25 100%);
                border-radius: 50%;
                position: absolute;
                left: 70px;
                top: 70px;
                cursor: pointer;
                box-shadow: 0 0 20px #00eaff88;
                border: 2px solid #00eaff;
                touch-action: none;
                transition: box-shadow 0.2s;
            }
            #stick:active {
                box-shadow: 0 0 30px #00eaffcc;
            }
            .slider-label {
                display: block;
                margin: 30px 0 10px 0;
                font-size: 1.1em;
                color: #00eaff;
                letter-spacing: 2px;
            }
            .slider {
                width: 100%;
                max-width: 350px;
                margin: 0 auto;
                display: block;
                accent-color: #00eaff;
                background: #23283a;
                border-radius: 10px;
                height: 8px;
                box-shadow: 0 0 10px #00eaff44;
            }
            #servo_angle_val {
                margin-left: 12px;
                color: #00eaff;
                font-weight: bold;
                font-size: 1.1em;
            }
            .readout {
                display: inline-block;
                margin: 0 20px 0 0;
                font-size: 1.1em;
                color: #00eaff;
                font-weight: bold;
            }
            @media (max-width: 1200px) {
                #container { flex-direction: column; align-items: center; }
                #video { margin: 40px auto 0 auto; max-width: 90vw; }
                #controls { margin: 30px auto 0 auto; }
            }
        </style>
    </head>
    <body>
        <div id="container">
            <img id="video" src="{{ url_for('video_feed') }}" width="640" height="480" />
            <div id="controls">
                <label style="margin-bottom:10px;">Drive Joystick</label>
                <div id="joystick"><div id="stick"></div></div>
                <span class="readout">Throttle: <span id="throttle_val">0</span></span>
                <span class="readout">Steering: <span id="steering_val">0</span></span>
                <label class="slider-label">Head Servo Angle</label>
                <input type="range" min="0" max="180" step="1" value="90" id="servo_angle" class="slider">
                <span id="servo_angle_val">90</span>
            </div>
        </div>
        <script>
            // Joystick logic
            var joystick = document.getElementById('joystick');
            var stick = document.getElementById('stick');
            var dragging = false;
            var centerX = joystick.offsetWidth / 2;
            var centerY = joystick.offsetHeight / 2;
            var maxRadius = joystick.offsetWidth / 2 - stick.offsetWidth / 2;
            var throttle = 0, steering = 0;
            var last_servo_angle = 90;

            function sendControls() {
                $.post('/set_controls', {
                    throttle: throttle,
                    steering: steering
                });
            }

            function sendServo(angle) {
                $.post('/set_servo', {servo_angle: angle});
                last_servo_angle = angle;
            }

            function updateStick(x, y) {
                stick.style.left = (x - stick.offsetWidth / 2) + 'px';
                stick.style.top = (y - stick.offsetHeight / 2) + 'px';
            }

            function resetStick() {
                updateStick(centerX, centerY);
                throttle = 0;
                steering = 0;
                $('#throttle_val').text(throttle);
                $('#steering_val').text(steering);
                sendControls();
                // Reset servo to center when joystick released
                if (last_servo_angle !== 90) {
                    sendServo(90);
                }
            }

            stick.addEventListener('mousedown', function(e) { dragging = true; });
            document.addEventListener('mouseup', function(e) {
                if (dragging) { dragging = false; resetStick(); }
            });
            document.addEventListener('mousemove', function(e) {
                if (dragging) {
                    var rect = joystick.getBoundingClientRect();
                    var x = e.clientX - rect.left;
                    var y = e.clientY - rect.top;
                    var dx = x - centerX;
                    var dy = y - centerY;
                    var dist = Math.sqrt(dx*dx + dy*dy);
                    if (dist > maxRadius) {
                        dx = dx * maxRadius / dist;
                        dy = dy * maxRadius / dist;
                        x = centerX + dx;
                        y = centerY + dy;
                    }
                    updateStick(x, y);
                    steering = +(dx / maxRadius).toFixed(2);
                    throttle = +(-(dy / maxRadius)).toFixed(2);
                    $('#throttle_val').text(throttle);
                    $('#steering_val').text(steering);
                    sendControls();
                    // Move servo proportional to joystick X, map [-1,1] to [45,135]
                    var servoPos = Math.round(90 + steering * 45);
                    if (servoPos !== last_servo_angle) {
                        sendServo(servoPos);
                    }
                }
            });
            // Touch support
            stick.addEventListener('touchstart', function(e) { dragging = true; e.preventDefault(); });
            document.addEventListener('touchend', function(e) {
                if (dragging) { dragging = false; resetStick(); }
            });
            document.addEventListener('touchmove', function(e) {
                if (dragging && e.touches.length == 1) {
                    var rect = joystick.getBoundingClientRect();
                    var x = e.touches[0].clientX - rect.left;
                    var y = e.touches[0].clientY - rect.top;
                    var dx = x - centerX;
                    var dy = y - centerY;
                    var dist = Math.sqrt(dx*dx + dy*dy);
                    if (dist > maxRadius) {
                        dx = dx * maxRadius / dist;
                        dy = dy * maxRadius / dist;
                        x = centerX + dx;
                        y = centerY + dy;
                    }
                    updateStick(x, y);
                    steering = +(dx / maxRadius).toFixed(2);
                    throttle = +(-(dy / maxRadius)).toFixed(2);
                    $('#throttle_val').text(throttle);
                    $('#steering_val').text(steering);
                    sendControls();
                    var servoPos = Math.round(90 + steering * 45);
                    if (servoPos !== last_servo_angle) {
                        sendServo(servoPos);
                    }
                }
            });

            // Initialize stick
            resetStick();

            // Servo slider (only sends when changed)
            $('#servo_angle').on('input change', function() {
                $('#servo_angle_val').text($('#servo_angle').val());
                var angle = parseInt($('#servo_angle').val());
                sendServo(angle);
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
    global throttle, steering
    try:
        throttle = float(request.form.get('throttle', 0))
        steering = float(request.form.get('steering', 0))
        update_motors()
        return 'OK'
    except Exception as e:
        return f'Error: {e}', 400

@app.route('/set_servo', methods=['POST'])
def set_servo():
    try:
        angle = int(request.form.get('servo_angle', 90))
        threading.Thread(target=move_servo, args=(angle,), daemon=True).start()
        return 'OK'
    except Exception as e:
        return f'Error: {e}', 400

if __name__ == '__main__':
    try:
        # Start random sound thread
        random_sound_thread = threading.Thread(target=play_random_segments, daemon=True)
        random_sound_thread.start()
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False, threaded=True)
    finally:
        running = False
        left_motor.stop()
        right_motor.stop()
        GPIO.cleanup()
        camera.release()
        play_audio("sound2.mp3")
        if audio_process:
            audio_process.wait()

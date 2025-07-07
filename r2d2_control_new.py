from gpiozero import Motor, AngularServo
import time
import cv2
import numpy as np
import os
import threading
from flask import Flask, Response, render_template_string, request
import subprocess
import random
import RPi.GPIO as GPIO

app = Flask(__name__)

# Face Detection Constants
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
# head_servo = AngularServo(18, min_angle=0, max_angle=180)  # GPIO 18, 0-180 degrees

# Global variables
running = True
audio_lock = threading.Lock()
audio_process = None

# Motor and servo control state
throttle = 0   # -1 (full reverse) to 1 (full forward)
steering = 0   # -1 (full left) to 1 (full right)
servo_angle = 80  # 20-140 center
last_servo_angle = 80

# Use RPi.GPIO for servo control
SERVO_PIN = 18  # BCM numbering
GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)
servo_pwm = GPIO.PWM(SERVO_PIN, 50)  # 50Hz
servo_pwm.start(0)
servo_lock = threading.Lock()

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
    # Convert throttle and steering to left/right motor speeds
    global throttle, steering
    left_speed = throttle + steering
    right_speed = throttle - steering
    # Clamp speeds to [-1, 1]
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

def angle_to_duty(angle):
    # Clamp angle to safe range
    angle = max(20, min(140, angle))
    return 2.5 + (angle / 180.0) * 10.0

def set_servo(angle):
    global last_servo_angle
    angle = max(20, min(140, angle))
    with servo_lock:
        duty = angle_to_duty(angle)
        servo_pwm.ChangeDutyCycle(duty)
        time.sleep(0.04)
        servo_pwm.ChangeDutyCycle(0)  # Reduce jitter
        last_servo_angle = angle

def generate_frames():
    while running:
        ret, frame = camera.read()
        if not ret:
            break
        frame = cv2.flip(frame, -1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
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
        <meta name="viewport" content="width=device-width, initial-scale=1">
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
                padding: 50px 40px 50px 40px;
                box-shadow: 0 0 30px #00eaff22;
                margin: 50px 50px 50px 0;
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
            #dial {
                margin: 30px 0 10px 0;
                width: 180px;
                height: 120px;
                display: block;
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
                <input type="range" min="20" max="140" step="1" value="80" id="servo_angle" class="slider">
                <span id="servo_angle_val">80</span>
                <svg id="dial" viewBox="0 0 180 120">
                    <path d="M20,100 A80,80 0 0,1 160,100" fill="none" stroke="#444" stroke-width="16"/>
                    <path id="dial-arc" d="M20,100 A80,80 0 0,1 160,100" fill="none" stroke="#00eaff" stroke-width="10"/>
                    <circle id="dial-knob" cx="90" cy="100" r="10" fill="#00eaff" stroke="#fff" stroke-width="3"/>
                </svg>
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
            var last_servo_angle = 80;
            var servo_min = 20, servo_max = 140;

            function sendControls() {
                $.post('/set_controls', {
                    throttle: throttle,
                    steering: steering,
                    servo_angle: last_servo_angle
                });
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
                if (last_servo_angle !== 80) {
                    setServo(80);
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
                }
            });
            document.addEventListener('mouseleave', function(e) {
                if (dragging) { dragging = false; resetStick(); }
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
                }
            });

            // Servo slider (only sends on release)
            function setServo(angle) {
                angle = Math.max(servo_min, Math.min(servo_max, angle));
                last_servo_angle = angle;
                $('#servo_angle_val').text(angle);
                updateDial(angle);
                $.post('/set_controls', {
                    throttle: throttle,
                    steering: steering,
                    servo_angle: angle
                });
            }
            $('#servo_angle').on('input', function() {
                var angle = parseInt($('#servo_angle').val());
                $('#servo_angle_val').text(angle);
                updateDial(angle);
            });
            $('#servo_angle').on('change', function() {
                var angle = parseInt($('#servo_angle').val());
                setServo(angle);
            });

            // Dial logic
            function updateDial(angle) {
                // Map angle [20,140] to [160deg, 20deg] (SVG arc)
                var a = (angle - servo_min) / (servo_max - servo_min);
                var theta = 160 - a * 140; // 160deg to 20deg
                var rad = theta * Math.PI / 180;
                var r = 80;
                var cx = 90, cy = 100;
                var x = cx + r * Math.cos(rad);
                var y = cy - r * Math.sin(rad);
                var arc = `M20,100 A80,80 0 0,1 160,100`;
                $("#dial-arc").attr("d", arc);
                $("#dial-knob").attr("cx", x).attr("cy", y);
            }
            // Initialize dial
            updateDial(80);
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
    global throttle, steering, servo_angle
    try:
        throttle = float(request.form.get('throttle', 0))
        steering = float(request.form.get('steering', 0))
        new_servo_angle = int(request.form.get('servo_angle', 80))
        update_motors()
        set_servo(new_servo_angle)
        return 'OK'
    except Exception as e:
        return f'Error: {e}', 400

if __name__ == '__main__':
    try:
        set_servo(80)
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
        # Remove or comment out: head_servo.detach()
        servo_pwm.stop()
        GPIO.cleanup()
        camera.release()
        play_audio("sound2.mp3")
        if audio_process:
            audio_process.wait()
        print("Cleanup complete")

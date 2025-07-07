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
servo_angle = 90  # 0-180 degrees
last_servo_angle = 90

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
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        <style>
            #controls {
                margin-top: 20px;
            }
            #joystick {
                width: 200px;
                height: 200px;
                background: #eee;
                border-radius: 50%;
                position: relative;
                margin-bottom: 20px;
                touch-action: none;
                user-select: none;
            }
            #stick {
                width: 60px;
                height: 60px;
                background: #888;
                border-radius: 50%;
                position: absolute;
                left: 70px;
                top: 70px;
                cursor: pointer;
                touch-action: none;
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
            <div>
                <label>Drive Joystick</label>
                <div id="joystick">
                    <div id="stick"></div>
                </div>
                <span>Throttle: <span id="throttle_val">0</span></span>
                <span>Steering: <span id="steering_val">0</span></span>
            </div>
            <label class="slider-label">Head Servo Angle</label>
            <input type="range" min="0" max="180" step="1" value="90" id="servo_angle" class="slider">
            <span id="servo_angle_val">90</span>
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

            function sendControls() {
                $.post('/set_controls', {
                    throttle: throttle,
                    steering: steering,
                    servo_angle: $('#servo_angle').val()
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
            }

            stick.addEventListener('mousedown', function(e) { dragging = true; });
            document.addEventListener('mouseup', function(e) {
                if (dragging) {
                    dragging = false;
                    resetStick();
                }
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
                    // Map to -1 to 1
                    steering = +(dx / maxRadius).toFixed(2);
                    throttle = +(-(dy / maxRadius)).toFixed(2);
                    $('#throttle_val').text(throttle);
                    $('#steering_val').text(steering);
                    sendControls();
                }
            });
            // Touch support
            stick.addEventListener('touchstart', function(e) { dragging = true; e.preventDefault(); });
            document.addEventListener('touchend', function(e) {
                if (dragging) {
                    dragging = false;
                    resetStick();
                }
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
                }
            });

            // Initialize stick
            resetStick();

            // Servo slider
            let last_servo_val = $('#servo_angle').val();
            $('#servo_angle').on('input change', function() {
                $('#servo_angle_val').text($('#servo_angle').val());
                if ($('#servo_angle').val() != last_servo_val) {
                    sendControls();
                    last_servo_val = $('#servo_angle').val();
                }
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
    global throttle, steering, servo_angle
    try:
        throttle = float(request.form.get('throttle', 0))
        steering = float(request.form.get('steering', 0))
        new_servo_angle = int(request.form.get('servo_angle', 90))
        update_motors()
        set_servo(new_servo_angle)
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
        # Remove or comment out: head_servo.detach()
        servo_pwm.stop()
        GPIO.cleanup()
        camera.release()
        play_audio("sound2.mp3")
        if audio_process:
            audio_process.wait()
        print("Cleanup complete")

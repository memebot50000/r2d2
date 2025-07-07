import RPi.GPIO as GPIO
import threading
import time
from flask import Flask, Response, render_template_string, request
from gpiozero import Motor
import cv2
import numpy as np
import os
import subprocess
import random
import signal
import sys

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

# Servo setup (RPi.GPIO, 50Hz, BCM numbering)
SERVO_PIN = 18  # BCM numbering (GPIO 18, physical pin 12)
GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)
servo_lock = threading.Lock()
servo_pwm = GPIO.PWM(SERVO_PIN, 50)  # 50Hz is standard for servos
servo_pwm.start(7.5)  # Center position (90 deg)

# Motor and control state
throttle = 0
steering = 0
motor_lock = threading.Lock()

# Helper to convert angle to duty cycle for 0-180 deg
# Most servos: 2.5% (0 deg) to 12.5% (180 deg)
def angle_to_duty(angle):
    angle = max(0, min(180, angle))
    return 2.5 + (angle / 180.0) * 10.0

# Ensure only one instance is running
try:
    import psutil
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        if proc.info['pid'] != current_pid and proc.info['cmdline']:
            if 'r2d2_control_new.py' in ' '.join(proc.info['cmdline']):
                print(f"Killing old instance with PID {proc.info['pid']}")
                os.kill(proc.info['pid'], signal.SIGTERM)
except ImportError:
    print("psutil not installed, cannot auto-kill old instances.")

def move_servo(angle):
    print(f"[DEBUG] move_servo called with angle={angle}")
    with servo_lock:
        duty = angle_to_duty(angle)
        servo_pwm.ChangeDutyCycle(duty)
        time.sleep(0.3)  # Allow servo to reach position
        servo_pwm.ChangeDutyCycle(0)  # Stop sending signal to avoid jitter

def update_motors():
    with motor_lock:
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

@app.route('/set_controls', methods=['POST'])
def set_controls():
    global throttle, steering
    try:
        with motor_lock:
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
        servo_pwm.stop()
        GPIO.cleanup()
        camera.release()
        play_audio("sound2.mp3")
        if audio_process:
            audio_process.wait() 

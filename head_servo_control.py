from gpiozero import Motor
import evdev
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

# Head Servo Initialization (replaces Motor-based head control)
SERVO_PIN = 18  # BCM numbering
GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)
pwm = GPIO.PWM(SERVO_PIN, 50)
pwm.start(0)

# Head servo positions (5 evenly spaced positions from 20 to 140 degrees)
SERVO_POSITIONS = {
    'left': 20,
    'left-center': 50,
    'center': 80,
    'right-center': 110,
    'right': 140
}
current_servo_position = 'center'
servo_lock = threading.Lock()

def angle_to_duty(angle):
    # Map 0-180 degrees to 2.5-12.5% duty cycle
    return 2.5 + (angle / 180.0) * 10.0

def set_servo_position(position_name):
    global current_servo_position
    angle = SERVO_POSITIONS.get(position_name, 80)  # Default to center if invalid
    duty = angle_to_duty(angle)
    with servo_lock:
        pwm.ChangeDutyCycle(duty)
        time.sleep(0.3)  # Allow servo to reach position
        pwm.ChangeDutyCycle(0)
    current_servo_position = position_name

# Head Movement Parameters
current_angle = 0
movement_command = None
movement_start_time = 0

# Global variables
running = True
audio_lock = threading.Lock()
audio_process = None

def normalize(value, min_val, max_val):
    return 2 * (value - min_val) / (max_val - min_val) - 1

def apply_dead_zone(value, dead_zone):
    if abs(value) < dead_zone:
        return 0
    return (value - dead_zone * (1 if value > 0 else -1)) / (1 - dead_zone)

def find_spektrum_device():
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    for device in devices:
        if device.info.vendor == SPEKTRUM_VENDOR_ID and device.info.product == SPEKTRUM_PRODUCT_ID:
            return device
    return None

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

def rc_car_control():
    joystick = find_spektrum_device()
    if not joystick:
        print("Spektrum receiver not found. Please make sure it's connected.")
        return

    print(f"Using device: {joystick.name}")

    def control_motors(throttle, steering):
        throttle = apply_dead_zone(throttle, DEAD_ZONE)
        steering = apply_dead_zone(steering, DEAD_ZONE)

        left_speed = throttle + steering
        right_speed = throttle - steering

        left_speed = max(-1, min(1, left_speed))
        right_speed = max(-1, min(1, right_speed))

        if abs(left_speed) > 0.7 or abs(right_speed) > 0.7:
            play_audio("sound3.mp3")

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

    print("RC Car Control Ready. Use the Spektrum controller to control the car.")

    absinfo_y = joystick.absinfo(evdev.ecodes.ABS_Y)
    absinfo_x = joystick.absinfo(evdev.ecodes.ABS_X)

    throttle = 0
    steering = 0

    try:
        for event in joystick.read_loop():
            if not running:
                break
            if event.type == evdev.ecodes.EV_ABS:
                if event.code == evdev.ecodes.ABS_Y:
                    throttle = normalize(event.value, absinfo_y.min, absinfo_y.max)
                elif event.code == evdev.ecodes.ABS_X:
                    steering = normalize(event.value, absinfo_x.min, absinfo_x.max)
                
                control_motors(throttle, steering)
    except Exception as e:
        print(f"An error occurred in RC car control: {e}")
    finally:
        left_motor.stop()
        right_motor.stop()

def head_servo_control():
    # This thread just keeps the servo at the requested position
    last_position = None
    while running:
        if current_servo_position != last_position:
            set_servo_position(current_servo_position)
            last_position = current_servo_position
        time.sleep(0.05)

def generate_frames():
    while running:
        ret, frame = camera.read()
        if not ret:
            break
        # Flip the frame by 180 degrees
        frame = cv2.rotate(frame, cv2.ROTATE_180)
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
    <html lang="en">
    <head>
        <title>R2D2 Control Panel</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
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
                width: 100vw;
                height: 100vh;
                object-fit: cover;
                background: #000;
                display: block;
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
            #dial-container {
                position: absolute;
                top: 40px;
                left: 50%;
                transform: translateX(-50%);
                z-index: 2;
                display: flex;
                flex-direction: column;
                align-items: center;
                background: rgba(24,26,32,0.85);
                border-radius: 18px;
                box-shadow: 0 4px 32px 0 #000a;
                padding: 18px 32px;
            }
            #dial-label {
                color: #f5f6fa;
                font-size: 1.1rem;
                margin-bottom: 8px;
                text-align: center;
                letter-spacing: 0.04em;
            }
            #dial {
                width: 120px;
                height: 60px;
                position: relative;
                margin-bottom: 0;
            }
            #dial-bg {
                width: 100%;
                height: 100%;
                border-radius: 60px 60px 0 0;
                background: linear-gradient(90deg, #23242a 0%, #232a3a 100%);
                border-bottom: 4px solid #4e8cff;
                position: absolute;
                left: 0; top: 0;
            }
            #dial-needle {
                width: 4px;
                height: 60px;
                background: #4e8cff;
                position: absolute;
                left: 50%;
                bottom: 0;
                transform: translateX(-50%) rotate(-80deg);
                transform-origin: bottom center;
                border-radius: 2px;
                box-shadow: 0 0 8px #4e8cff88;
                transition: transform 0.4s cubic-bezier(.4,2,.3,1);
            }
            #dial-ticks {
                position: absolute;
                width: 100%;
                height: 100%;
                left: 0; top: 0;
                pointer-events: none;
            }
            .dial-tick {
                position: absolute;
                width: 2px;
                height: 12px;
                background: #888;
                left: 50%;
                bottom: 0;
                transform-origin: bottom center;
            }
            .dial-tick-label {
                position: absolute;
                color: #aaa;
                font-size: 0.9rem;
                left: 50%;
                bottom: 12px;
                transform: translateX(-50%) translateY(0) rotate(0deg);
                white-space: nowrap;
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
                #dial-container {
                    top: 10px;
                    padding: 10px 8px;
                }
                #dial {
                    width: 80px;
                    height: 40px;
                }
            }
        </style>
    </head>
    <body>
        <div id="main-content">
            <div id="camera-container">
                <img id="camera-feed" src="{{ url_for('video_feed') }}" alt="Camera Feed" />
            </div>
            <div id="dial-container">
                <div id="dial-label">Head Position</div>
                <div id="dial">
                    <div id="dial-bg"></div>
                    <div id="dial-needle"></div>
                    <div id="dial-ticks"></div>
                </div>
            </div>
            <div id="servo-controls">
                <button class="servo-btn" data-pos="left">Left</button>
                <button class="servo-btn" data-pos="left-center">Left-Center</button>
                <button class="servo-btn" data-pos="center">Center</button>
                <button class="servo-btn" data-pos="right-center">Right-Center</button>
                <button class="servo-btn" data-pos="right">Right</button>
            </div>
        </div>
        <script>
            // Dial logic
            const SERVO_POSITIONS = {
                'left': 20,
                'left-center': 50,
                'center': 80,
                'right-center': 110,
                'right': 140
            };
            const DIAL_MIN = 20;
            const DIAL_MAX = 140;
            const DIAL_SWEEP = 160; // degrees for the dial arc
            const DIAL_START = -80; // leftmost angle
            function updateDial(posName) {
                const angle = SERVO_POSITIONS[posName] || 80;
                const rel = (angle - DIAL_MIN) / (DIAL_MAX - DIAL_MIN);
                const deg = DIAL_START + rel * DIAL_SWEEP;
                $("#dial-needle").css('transform', `translateX(-50%) rotate(${deg}deg)`);
                $(".servo-btn").removeClass('selected');
                $(`.servo-btn[data-pos='${posName}']`).addClass('selected');
            }
            // Draw dial ticks and labels
            function drawDialTicks() {
                const ticks = [
                    {pos: 'left', label: 'Left'},
                    {pos: 'left-center', label: 'L-C'},
                    {pos: 'center', label: 'Center'},
                    {pos: 'right-center', label: 'R-C'},
                    {pos: 'right', label: 'Right'}
                ];
                let html = '';
                for (let i = 0; i < ticks.length; ++i) {
                    const rel = i / (ticks.length - 1);
                    const deg = DIAL_START + rel * DIAL_SWEEP;
                    html += `<div class='dial-tick' style='transform:translateX(-50%) rotate(${deg}deg) translateY(-4px);height:16px;background:#4e8cff;'></div>`;
                    html += `<div class='dial-tick-label' style='transform:translateX(-50%) rotate(${deg}deg) translateY(-32px);'>${ticks[i].label}</div>`;
                }
                $("#dial-ticks").html(html);
            }
            drawDialTicks();
            // UI logic
            function setServoPosition(pos) {
                $.post('/set_servo', {position: pos}, function() {
                    updateDial(pos);
                });
            }
            $('.servo-btn').click(function() {
                var pos = $(this).data('pos');
                setServoPosition(pos);
            });
            // Highlight the current position on load
            $(function() {
                updateDial('{{ current_servo_position }}');
            });
        </script>
    </body>
    </html>
    ''', current_servo_position=current_servo_position)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/control', methods=['POST'])
def control():
    global movement_command, movement_start_time
    command = request.form.get('command')
    if command in ['left', 'right']:
        movement_command = command
        movement_start_time = time.time()
    return 'OK'

@app.route('/set_servo', methods=['POST'])
def set_servo():
    global current_servo_position
    pos = request.form.get('position')
    if pos in SERVO_POSITIONS:
        current_servo_position = pos
    return 'OK'

if __name__ == '__main__':
    try:
        print("Initializing motors and starting threads")
        rc_car_thread = threading.Thread(target=rc_car_control, daemon=True)
        head_servo_thread = threading.Thread(target=head_servo_control, daemon=True)
        random_sound_thread = threading.Thread(target=play_random_segments, daemon=True)
        rc_car_thread.start()
        head_servo_thread.start()
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
        pwm.stop()
        GPIO.cleanup()
        camera.release()
        play_audio("sound2.mp3")
        if audio_process:
            audio_process.wait()
        print("Cleanup complete") 

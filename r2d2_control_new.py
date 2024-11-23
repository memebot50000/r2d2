import time
import cv2
import numpy as np
import os
import threading
from flask import Flask, Response, render_template_string, request
import subprocess
import random
from gpiozero import Motor

app = Flask(__name__)

# Constants
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
head_motor = Motor(forward=6, backward=5, enable=26)

# Head Movement Parameters
TURN_SPEED = 0.1
current_angle = 0
movement_command = None
movement_start_time = 0

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

def head_motor_control():
    global current_angle, movement_command, movement_start_time
    while running:
        current_time = time.time()
        if movement_command and current_time - movement_start_time < 1:
            if movement_command == 'left':
                head_motor.value = -TURN_SPEED
            elif movement_command == 'right':
                head_motor.value = TURN_SPEED
        else:
            head_motor.stop()
            movement_command = None
        time.sleep(0.01)

def generate_frames():
    global prev_frame, prev_points
    while running:
        ret, frame = camera.read()
        if not ret:
            break
        frame = cv2.flip(frame, -1)  # Flip for upside-down camera
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

        cv2.putText(frame, f"Movement: {movement_command if movement_command else 'None'}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
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
        <script src="https://cdnjs.cloudflare.com/ajax/libs/nipplejs/0.9.0/nipplejs.min.js"></script>
        <style>
            #joystick {
                width: 200px;
                height: 200px;
                margin: 20px auto;
                border: 1px solid blue;
            }
            #controls {
                margin-top: 20px;
                text-align: center;
            }
            .arrow {
                font-size: 24px;
                margin: 0 10px;
                cursor: pointer;
            }
        </style>
    </head>
    <body>
        <h1>R2D2 Control Panel</h1>
        <img src="{{ url_for('video_feed') }}" width="640" height="480" />
        <div id="joystick"></div>
        <div id="controls">
            <span class="arrow" id="left">&#8592;</span>
            <span class="arrow" id="right">&#8594;</span>
        </div>
        <script>
            var joystick = nipplejs.create({
                zone: document.getElementById('joystick'),
                mode: 'static',
                position: { left: '50%', top: '50%' },
                color: 'blue',
                size: 150
            });

            joystick.on('move', function(evt, data) {
                var x = data.vector.x;
                var y = -data.vector.y;
                $.post('/control', {throttle: y, steering: x});
            });

            joystick.on('end', function() {
                $.post('/control', {throttle: 0, steering: 0});
            });

            function sendCommand(cmd) {
                $.post('/control', {command: cmd});
            }

            $('#left').click(function() { sendCommand('left'); });
            $('#right').click(function() { sendCommand('right'); });

            $(document).keydown(function(e) {
                switch(e.which) {
                    case 37: // left arrow
                        sendCommand('left');
                        break;
                    case 39: // right arrow
                        sendCommand('right');
                        break;
                    default: return;
                }
                e.preventDefault();
            });
        </script>
    </body>
    </html>
    ''')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/control', methods=['POST'])
def control():
    global movement_command, movement_start_time
    command = request.form.get('command')
    throttle = float(request.form.get('throttle', 0))
    steering = float(request.form.get('steering', 0))

    if command in ['left', 'right']:
        movement_command = command
        movement_start_time = time.time()
    else:
        control_motors(throttle, steering)

    return 'OK'

if __name__ == '__main__':
    try:
        print("Initializing motors and starting threads")
        head_motor_thread = threading.Thread(target=head_motor_control, daemon=True)
        random_sound_thread = threading.Thread(target=play_random_segments, daemon=True)
        head_motor_thread.start()
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
        head_motor.stop()
        camera.release()
        play_audio("sound2.mp3")
        if audio_process:
            audio_process.wait()
        print("Cleanup complete")

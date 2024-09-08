from gpiozero import Motor
import evdev
import time
import cv2
import numpy as np
import os
import threading
from flask import Flask, Response, render_template_string, request

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
        <div id="controls">
            <span class="arrow" id="left">&#8592;</span>
            <span class="arrow" id="right">&#8594;</span>
        </div>
        <script>
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

if __name__ == '__main__':
    try:
        print("Initializing motors and starting threads")
        rc_car_thread = threading.Thread(target=rc_car_control, daemon=True)
        head_motor_thread = threading.Thread(target=head_motor_control, daemon=True)
        rc_car_thread.start()
        head_motor_thread.start()
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
        print("Cleanup complete")

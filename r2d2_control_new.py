import os
import time
import cv2
import threading
from flask import Flask, Response, render_template_string, request
import pygame
from gpiozero import Motor

# Set up environment for Pygame to use ALSA or PulseAudio
os.environ['SDL_AUDIODRIVER'] = 'alsa'  # Change to 'pulse' if needed

app = Flask(__name__)

# Constants
DEAD_ZONE = 0.2  # 20% dead zone

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
head_motor = Motor(forward=6, backward=5, enable=26)

# Global variables
running = True
armed = False

# Initialize pygame for audio
pygame.mixer.init()
sounds = {
    'sound1': pygame.mixer.Sound("sound1.mp3"),
    'sound2': pygame.mixer.Sound("sound2.mp3"),
    'sound3': pygame.mixer.Sound("sound3.mp3")
}
current_sound = None

def apply_dead_zone(value, dead_zone):
    if abs(value) < dead_zone:
        return 0
    return (value - dead_zone * (1 if value > 0 else -1)) / (1 - dead_zone)

def play_sound(sound_name):
    global current_sound
    if current_sound:
        current_sound.stop()
    current_sound = sounds[sound_name]
    current_sound.play(-1)  # Loop indefinitely

def control_motors(throttle, steering):
    if not armed:
        left_motor.stop()
        right_motor.stop()
        return

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

def generate_frames():
    while running:
        ret, frame = camera.read()
        if not ret:
            break
        frame = cv2.flip(frame, -1)  # Flip for upside-down camera
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)

        cv2.putText(frame, f"Armed: {'Yes' if armed else 'No'}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
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
        <script src="https://cdnjs.cloudflare.com/ajax/libs/nipplejs/0.9.0/nipplejs.min.js"></script>
        <style>
            #joystick-container {
                width: 200px;
                height: 200px;
                margin: 20px auto;
                position: relative;
            }
            #joystick {
                width: 100%;
                height: 100%;
                border: 1px solid blue;
                position: absolute;
                top: 0;
                left: 0;
            }
            #controls {
                margin-top: 20px;
                text-align: center;
            }
            #armed-checkbox {
                margin-top: 20px;
                text-align: center;
            }
            #sound-controls {
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
        <div id="joystick-container">
            <div id="joystick"></div>
        </div>
        <div id="controls">
            <span class="arrow" id="left">&#8592;</span>
            <span class="arrow" id="right">&#8594;</span>
        </div>
        <div id="armed-checkbox">
            <label for="armed">Armed:</label>
            <input type="checkbox" id="armed" name="armed">
        </div>
        <div id="sound-controls">
            <button onclick="playSound('sound1')">Sound 1</button>
            <button onclick="playSound('sound2')">Sound 2</button>
            <button onclick="playSound('sound3')">Sound 3</button>
            <button onclick="stopSound()">Stop Sound</button>
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
                var y = -data.vector.y; // Invert Y-axis
                $.post('/control', {throttle: y, steering: x});
            });

            joystick.on('end', function() {
                $.post('/control', {throttle: 0, steering: 0});
            });

            $('#armed').change(function() {
                $.post('/arm', {armed: this.checked});
            });

            function playSound(sound) {
                $.post('/play_sound', {sound: sound});
            }

            function stopSound() {
                $.post('/stop_sound');
            }

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
    global movement_command
    command = request.form.get('command')
    
    if command in ['left', 'right']:
        movement_command = command
    else:
        throttle = float(request.form.get('throttle', 0))
        steering = float(request.form.get('steering', 0))
        control_motors(throttle, steering)

    return 'OK'

@app.route('/arm', methods=['POST'])
def arm():
    global armed
    armed = request.form.get('armed') == 'true'
    return 'OK'

@app.route('/play_sound', methods=['POST'])
def play_sound_route():
    sound_name = request.form.get('sound')
    
    if sound_name in sounds:
        play_sound(sound_name)
    
    return 'OK'

@app.route('/stop_sound', methods=['POST'])
def stop_sound():
    global current_sound
    
    if current_sound:
        current_sound.stop()
    
    return 'OK'

if __name__ == '__main__':
    try:
        print("Initializing motors and starting threads")
        
        head_motor_thread = threading.Thread(target=lambda : None) # Placeholder for head motor control thread if needed.
        
        head_motor_thread.start()
        
        print("Threads started")
        
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
        
    except KeyboardInterrupt:
        print("\nProgram interrupted by user. Exiting...")
    
finally:
   running = False 
   print("Stopping motors and releasing camera")
   left_motor.stop()
   right_motor.stop()
   head_motor.stop()
   camera.release()
   pygame.mixer.quit() 
   print("Cleanup complete")

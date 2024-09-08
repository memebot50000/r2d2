import subprocess
import threading
import time
import random
import os
import signal
from gpiozero import Motor

# Initialize motors with the correct pin numbers
left_motor = Motor(forward=27, backward=17, enable=12)
right_motor = Motor(forward=22, backward=23, enable=13)
head_motor_raw = Motor(forward=5, backward=6, enable=26)

# Flag to control the main loop
running = True

def play_sound(sound_file):
    subprocess.run(["mpg123", "-q", sound_file])

def play_random_segment():
    sound_length = 9  # Length of sound1.mp3 in seconds
    segment_length = 2  # Length of the segment to play in seconds

    while running:
        # Calculate the maximum starting point for the segment
        max_start = sound_length - segment_length
        start = random.uniform(0, max(max_start, 0))  # Ensure we don't exceed the length

        # Play the segment
        subprocess.run(["mpg123", "-q", "-k", str(int(start)), "-n", str(int(segment_length)), "sound1.mp3"])
        
        # Wait between 5 to 15 seconds before playing the next segment
        time.sleep(random.uniform(5, 15))

def monitor_motors():
    while running:
        if (abs(left_motor.value) > 0.7 or 
            abs(right_motor.value) > 0.7 or 
            abs(head_motor_raw.value) > 0.7):
            play_sound("sound3.mp3")
        time.sleep(0.1)  # Check every 0.1 seconds

def run_script(script_name):
    subprocess.run(["python3", script_name])

# Start the scripts
rc_car_thread = threading.Thread(target=run_script, args=("rc_car_control.py",))
face_thread = threading.Thread(target=run_script, args=("idle_face_optical.py",))
random_sound_thread = threading.Thread(target=play_random_segment)
motor_monitor_thread = threading.Thread(target=monitor_motors)

rc_car_thread.start()
face_thread.start()
random_sound_thread.start()
motor_monitor_thread.start()

# Function to handle termination
def terminate(signum, frame):
    global running
    running = False
    play_sound("sound2.mp3")
    time.sleep(2)  # Wait for sound2 to finish playing
    os._exit(0)

# Register the termination handler
signal.signal(signal.SIGINT, terminate)
signal.signal(signal.SIGTERM, terminate)

# Main loop
try:
    while running:
        time.sleep(1)
except KeyboardInterrupt:
    terminate(None, None)

# Wait for threads to finish
rc_car_thread.join()
face_thread.join()
random_sound_thread.join()
motor_monitor_thread.join()

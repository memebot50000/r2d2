import subprocess
import threading
import time
import random
import os
import signal
import pygame
from gpiozero import Motor

# Initialize pygame mixer
pygame.mixer.init()

# Load sound files
sound1 = pygame.mixer.Sound("sound1.mp3")
sound2 = pygame.mixer.Sound("sound2.mp3")
sound3 = pygame.mixer.Sound("sound3.mp3")

# Initialize motors with the correct pin numbers
left_motor = Motor(forward=27, backward=17, enable=12)
right_motor = Motor(forward=22, backward=23, enable=13)
head_motor_raw = Motor(forward=5, backward=6, enable=26)

# Flag to control the main loop
running = True

def play_random_segment():
    while running:
        if not pygame.mixer.get_busy():
            start = random.uniform(0, max(0, sound1.get_length() - 2))
            sound1.play(start=start, maxtime=2000)  # Play for 2 seconds
        time.sleep(random.uniform(5, 15))  # Wait between 5 to 15 seconds

def monitor_motors():
    while running:
        if (abs(left_motor.value) > 0.7 or 
            abs(right_motor.value) > 0.7 or 
            abs(head_motor_raw.value) > 0.7):
            if not pygame.mixer.get_busy():
                sound3.play()
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
    sound2.play()
    pygame.time.wait(int(sound2.get_length() * 1000))  # Wait for sound2 to finish playing
    pygame.mixer.quit()
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

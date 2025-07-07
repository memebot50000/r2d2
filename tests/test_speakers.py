import pygame
import time

# Initialize Pygame mixer
pygame.mixer.init()

# Load the MP3 file
audio_file = "sound1.mp3"
pygame.mixer.music.load(audio_file)

# Set the volume (optional)
pygame.mixer.music.set_volume(1.0)  # Adjust between 0.0 and 1.0

# Start playing the audio in an infinite loop
pygame.mixer.music.play(-1)  # -1 means loop indefinitely

# Keep the script running
while True:
    time.sleep(1)

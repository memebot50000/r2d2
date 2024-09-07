import board
import neopixel
import time
import random

# Initialize the NeoPixels
pixels = neopixel.NeoPixel(board.NEOPIXEL, 10, brightness=0.1, auto_write=False)

# Function to set red LEDs
def set_red_leds():
    for i in range(5):
        pixels[i] = (255, 0, 0)  # Bright red

# Function to set cyan LEDs with random flickering
def set_cyan_leds():
    for i in range(5, 10):
        if random.random() < 0.9:  # 90% chance to be on
            brightness = random.uniform(0.7, 1.0)  # Random brightness between 70% and 100%
            pixels[i] = (0, int(255 * brightness), int(255 * brightness))
        else:
            pixels[i] = (0, 0, 0)  # Off

# Main loop
while True:
    set_red_leds()  # Set red LEDs (they stay constant)
    set_cyan_leds()  # Set cyan LEDs with flickering
    pixels.show()
    time.sleep(0.1)  # Adjust this for faster or slower flickering

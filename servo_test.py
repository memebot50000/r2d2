import RPi.GPIO as GPIO
import time

# Basic Servo Test Script for Raspberry Pi
# Connect the servo signal wire to GPIO 18 (BCM numbering, physical pin 12)
# Connect servo power (red) to 5V, ground (brown/black) to GND
# Make sure your servo is powered from a supply that can handle its current draw!

SERVO_PIN = 18  # BCM numbering
GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)

# 50Hz is standard for most hobby servos
pwm = GPIO.PWM(SERVO_PIN, 50)
pwm.start(0)

def angle_to_duty(angle):
    # Map 0-180 degrees to 2.5-12.5% duty cycle
    return 2.5 + (angle / 180.0) * 10.0

try:
    print("Sweeping servo from 20 to 160 and back in 2 degree steps. Press Ctrl+C to exit.")
    while True:
        # Sweep up
        for angle in range(20, 161, 2):
            duty = angle_to_duty(angle)
            pwm.ChangeDutyCycle(duty)
            print(f"Angle: {angle} Duty: {duty:.2f}")
            time.sleep(0.03)
        # Sweep down
        for angle in range(160, 19, -2):
            duty = angle_to_duty(angle)
            pwm.ChangeDutyCycle(duty)
            print(f"Angle: {angle} Duty: {duty:.2f}")
            time.sleep(0.03)
except KeyboardInterrupt:
    print("\nExiting and cleaning up GPIO.")
finally:
    pwm.stop()
    GPIO.cleanup() 

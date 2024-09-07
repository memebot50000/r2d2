from gpiozero import Motor
import evdev
import time

SPEKTRUM_VENDOR_ID = 0x0483
SPEKTRUM_PRODUCT_ID = 0x572b

def find_spektrum_device():
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    for device in devices:
        if device.info.vendor == SPEKTRUM_VENDOR_ID and device.info.product == SPEKTRUM_PRODUCT_ID:
            return device
    return None

def normalize(value, min_val, max_val):
    return 2 * (value - min_val) / (max_val - min_val) - 1

def rc_car_control():
    right_motor = Motor(forward=27, backward=17, enable=12)
    left_motor = Motor(forward=22, backward=23, enable=13)

    joystick = find_spektrum_device()
    if not joystick:
        print("Spektrum receiver not found. Please make sure it's connected.")
        return

    print(f"Using device: {joystick.name}")

    def stop():
        left_motor.stop()
        right_motor.stop()

    def control_motors(throttle, steering):
        # Differential drive control
        left_speed = throttle + steering
        right_speed = throttle - steering

        # Clamp values between -1 and 1
        left_speed = max(-1, min(1, left_speed))
        right_speed = max(-1, min(1, right_speed))

        if left_speed == 0.1 or left_speed == -0.1:
            left_speed = 0
        if right_speed == 0.1 or right_speed == -0.1:
            right speed == 0

        # Control left motor
        if left_speed > 0:
            left_motor.forward(left_speed)
        elif left_speed < 0:
            left_motor.backward(-left_speed)
        else:
            left_motor.stop()

        # Control right motor
        if right_speed > 0:
            right_motor.forward(right_speed)
        elif right_speed < 0:
            right_motor.backward(-right_speed)
        else:
            right_motor.stop()

        print(f"Left: {left_speed:.2f}, Right: {right_speed:.2f}")  # Debug print

    print("RC Car Control Ready. Use the Spektrum controller to control the car. Press Ctrl+C to quit.")

    # Get initial values and capabilities
    absinfo_y = joystick.absinfo(evdev.ecodes.ABS_Y)
    absinfo_x = joystick.absinfo(evdev.ecodes.ABS_X)

    # Initialize throttle and steering
    throttle = 0
    steering = 0

    try:
        for event in joystick.read_loop():
            if event.type == evdev.ecodes.EV_ABS:
                if event.code == evdev.ecodes.ABS_Y:  # Throttle
                    throttle = normalize(event.value, absinfo_y.min, absinfo_y.max)
                elif event.code == evdev.ecodes.ABS_X:  # Steering
                    steering = normalize(event.value, absinfo_x.min, absinfo_x.max)
                
                control_motors(throttle, steering)

    except KeyboardInterrupt:
        print("\nProgram interrupted by user. Exiting...")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        stop()
        print("RC Car Control stopped.")

if __name__ == "__main__":
    rc_car_control()

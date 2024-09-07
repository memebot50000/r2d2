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
    return (value - min_val) / (max_val - min_val)

def rc_car_control():
    left_motor = Motor(forward=27, backward=17, enable=12)  # Swapped forward and backward
    right_motor = Motor(forward=22, backward=23, enable=13)
    head_motor = Motor(forward=5, backward=6, enable=26)

    joystick = find_spektrum_device()
    if not joystick:
        print("Spektrum receiver not found. Please make sure it's connected.")
        return

    print(f"Using device: {joystick.name}")

    def stop():
        left_motor.stop()
        right_motor.stop()
        head_motor.stop()

    def control_motors(throttle_value, steering_value, head_value):
        throttle = normalize(throttle_value, joystick.absinfo(evdev.ecodes.ABS_Y).min, joystick.absinfo(evdev.ecodes.ABS_Y).max)
        steering = normalize(steering_value, joystick.absinfo(evdev.ecodes.ABS_X).min, joystick.absinfo(evdev.ecodes.ABS_X).max)
        head = normalize(head_value, joystick.absinfo(evdev.ecodes.ABS_RZ).min, joystick.absinfo(evdev.ecodes.ABS_RZ).max)
        
        throttle = (throttle - 0.5) * 2
        steering = (steering - 0.5) * 2
        head = (head - 0.5) * 2

        print(f"Throttle: {throttle:.2f}, Steering: {steering:.2f}, Head: {head:.2f}")  # Debug print

        try:
            # Differential drive control
            left_speed = throttle + steering
            right_speed = throttle - steering

            # Clamp values between -1 and 1
            left_speed = max(-1, min(1, left_speed))
            right_speed = max(-1, min(1, right_speed))

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

        
        except ValueError as e:
            print(f"Error controlling motors: {e}")

    print("RC Car Control Ready. Use the Spektrum controller to control the car. Press Ctrl+C to quit.")

    throttle_value = 0
    steering_value = 0
    head_value = 0

    try:
        for event in joystick.read_loop():
            if event.type == evdev.ecodes.EV_ABS:
                if event.code == evdev.ecodes.ABS_Y:  # Throttle
                    throttle_value = event.value
                elif event.code == evdev.ecodes.ABS_X:  # Steering
                    steering_value = event.value
                

    except KeyboardInterrupt:
        print("\nProgram interrupted by user. Exiting...")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        stop()
        print("RC Car Control stopped.")

if __name__ == "__main__":
    rc_car_control()

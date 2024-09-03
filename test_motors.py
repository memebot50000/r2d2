from gpiozero import Motor
import time

def rc_car_control():
    left_motor = Motor(forward=27, backward=17, enable=12)
    right_motor = Motor(forward=22, backward=23, enable=13)
    head_motor = Motor(forward=5, backward=6, enable=26)

    def stop():
        left_motor.stop()
        right_motor.stop()
        head_motor.stop()

    def control_motor(motor, power, duration):
        if power > 0:
            motor.forward(power)
        elif power < 0:
            motor.backward(abs(power))
        else:
            motor.stop()
        
        time.sleep(duration)
        motor.stop()

    print("RC Car Control Ready. Enter commands in the following format:")
    print("motor_name power duration")
    print("motor_name can be 'left', 'right', or 'head'")
    print("power is a float between -1 and 1 (-1 for full reverse, 1 for full forward)")
    print("duration is the time in seconds")
    print("Enter 'quit' to exit the program")

    try:
        while True:
            command = input("Enter command: ").lower().split()
            
            if command[0] == 'quit':
                break
            
            if len(command) != 3:
                print("Invalid command format. Please try again.")
                continue
            
            motor_name, power, duration = command
            
            try:
                power = float(power)
                duration = float(duration)
                
                if power < -1 or power > 1:
                    print("Power must be between -1 and 1")
                    continue
                
                if duration < 0:
                    print("Duration must be positive")
                    continue
                
                if motor_name == 'left':
                    control_motor(left_motor, power, duration)
                elif motor_name == 'right':
                    control_motor(right_motor, power, duration)
                elif motor_name == 'head':
                    control_motor(head_motor, power, duration)
                else:
                    print("Invalid motor name. Use 'left', 'right', or 'head'")
            
            except ValueError:
                print("Invalid power or duration value. Please enter numbers.")

    except KeyboardInterrupt:
        print("\nProgram interrupted by user. Exiting...")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        stop()
        print("RC Car Control stopped.")

if __name__ == "__main__":
    rc_car_control()

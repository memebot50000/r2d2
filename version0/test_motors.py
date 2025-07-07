from gpiozero import Motor
import time

class ServoLikeMotor:
    def __init__(self, motor, max_power=1.0, travel_time=2.2):
        self.motor = motor
        self.max_power = max_power
        self.travel_time = travel_time
        self.current_position = 0.5  # Start at middle position
        self.target_position = 0.5

    def set_position(self, position):
        """Set target position (0 to 1)"""
        self.target_position = max(0, min(1, position))

    def update(self, duration):
        """Update motor position"""
        start_time = time.time()
        while time.time() - start_time < duration:
            if self.current_position != self.target_position:
                direction = 1 if self.target_position > self.current_position else -1
                speed = 0.1 * self.max_power * direction  # 1/10th of max power
                
                # Calculate position change
                time_step = 0.01  # Update every 10ms
                position_change = (time_step / self.travel_time) * direction
                
                self.current_position += position_change
                self.current_position = max(0, min(1, self.current_position))
                
                if direction > 0:
                    self.motor.forward(abs(speed))
                else:
                    self.motor.backward(abs(speed))
            else:
                self.motor.stop()
            
            time.sleep(0.01)
        
        self.motor.stop()

def rc_car_control():
    left_motor = Motor(forward=27, backward=17, enable=12)
    right_motor = Motor(forward=22, backward=23, enable=13)
    head_motor_raw = Motor(forward=5, backward=6, enable=26)
    head_motor = ServoLikeMotor(head_motor_raw)

    def stop():
        left_motor.stop()
        right_motor.stop()
        head_motor.motor.stop()

    def control_motor(motor, power, duration):
        if isinstance(motor, ServoLikeMotor):
            position = (power + 1) / 2  # Convert -1 to 1 range to 0 to 1 range
            motor.set_position(position)
            motor.update(duration)
        else:
            if power > 0:
                motor.forward(power)
            elif power < 0:
                motor.backward(abs(power))
            else:
                motor.stop()
            
            time.sleep(duration)
            motor.stop()

    print("Motor test ready. Enter commands in the following format:")
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
        print("Motor test stopped.")

if __name__ == "__main__":
    rc_car_control()

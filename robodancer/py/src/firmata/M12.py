import pyfirmata
import time

# Replace 'COM3' with your Arduino port (or '/dev/ttyACM0' for Linux, '/dev/cu.usbmodem1411' for Mac)
board = pyfirmata.Arduino('/dev/ttyUSB0')
print("Connection established")

# Start iterator thread to avoid buffer overflow
it = pyfirmata.util.Iterator(board)
it.start()

# Define motor pins for Shield V1
motor1_dir = board.get_pin('d:12:o')   # Direction pin for Motor 1
motor1_pwm = board.get_pin('d:3:p')    # PWM/Speed pin for Motor 1
motor1_brake = board.get_pin('d:9:o')  # Brake pin for Motor 1

motor2_dir = board.get_pin('d:13:o')   # Direction pin for Motor 2
motor2_pwm = board.get_pin('d:11:p')   # PWM/Speed pin for Motor 2
motor2_brake = board.get_pin('d:8:o')   # Brake pin for Motor 2

# Function to control motor 1
def control_motor1(speed, direction, brake=False):
    # Set brake
    motor1_brake.write(1 if brake else 0)
    
    if not brake:
        # Set direction (HIGH = clockwise, LOW = counter-clockwise)
        motor1_dir.write(1 if direction else 0)
        # Set speed (0-1.0)
        motor1_pwm.write(speed)
    else:
        motor1_pwm.write(0)  # No speed if brake is on

# Function to control motor 2
def control_motor2(speed, direction, brake=False):
    # Set brake
    motor2_brake.write(1 if brake else 0)
    
    if not brake:
        # Set direction (HIGH = clockwise, LOW = counter-clockwise)
        motor2_dir.write(1 if direction else 0)
        # Set speed (0-1.0)
        motor2_pwm.write(speed)
    else:
        motor2_pwm.write(0)  # No speed if brake is on

# Test motors
try:
    print("Motor 1 forward")
    control_motor1(0.5, True)  # 50% speed, clockwise, no brake
    time.sleep(2)
    
    print("Motor 1 stopped with brake")
    control_motor1(0, True, True)  # Apply brake
    time.sleep(1)
    
    print("Motor 1 reverse")
    control_motor1(0.3, False)  # 30% speed, counter-clockwise
    time.sleep(2)
    
    print("Motor 1 off")
    control_motor1(0, True)  # Stop without brake
    time.sleep(1)
    
    print("Motor 2 forward")
    control_motor2(0.5, True)  # 50% speed, clockwise
    time.sleep(2)
    
    print("Motor 2 off")
    control_motor2(0, True)  # Stop
    
finally:
    # Clean shutdown
    control_motor1(0, True)
    control_motor2(0, True)
    board.exit()

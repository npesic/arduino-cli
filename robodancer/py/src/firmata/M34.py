import pyfirmata
import time

# Replace 'COM3' with your Arduino port
board = pyfirmata.Arduino('/dev/ttyUSB0')
print("Connection established")

# Start iterator thread to avoid buffer overflow
it = pyfirmata.util.Iterator(board)
it.start()

# Define latch control pins (common for L293D shields with shift register)
# You may need to adjust these pins based on your specific shield
latch_data = board.get_pin('d:8:o')    # Data pin
latch_clock = board.get_pin('d:4:o')   # Clock pin  
latch_latch = board.get_pin('d:12:o')  # Latch pin
enable_pin = board.get_pin('d:7:o')    # Enable pin

# PWM pins for motor speed control
motor3_pwm = board.get_pin('d:6:p')    # PWM for motor 3
motor4_pwm = board.get_pin('d:5:p')    # PWM for motor 4

# Function to write data to the latch
def write_to_latch(data_byte):
    # Pull latch low to start data transfer
    latch_latch.write(0)
    
    # Shift out each bit of the byte
    for i in range(7, -1, -1):
        latch_clock.write(0)
        bit = (data_byte >> i) & 1
        latch_data.write(bit)
        latch_clock.write(1)
        time.sleep(0.001)  # Small delay for stability
        #latch_clock.write(0)
    
    # Pull latch high to latch the data
    latch_latch.write(1)

def control_motors(motor3_dir, motor4_dir):
    if 1!=1:
        return
    # Create control byte for L293D
    # Different shields may use different bit assignments
    # Common pattern:
    # Bit 0: Motor 1 Direction
    # Bit 1: Motor 2 Direction
    # Bit 2: Motor 3 Direction
    # Bit 3: Motor 4 Direction
    # Remaining bits: May control other features
    
    control_byte = 0
    if motor3_dir:
        #control_byte |= (1 << 2)  # Set bit 2 for motor 3 direction
        control_byte |= (1 << 5)  # Set bit 2 for motor 3 direction
    else:
        control_byte |= (1 << 7)  # Set bit 2 for motor 3 direction
    if motor4_dir:
        #control_byte |= (1 << 3)  # Set bit 3 for motor 4 direction
        control_byte |= (1 << 0)  # Set bit 3 for motor 4 direction
    else:
        control_byte |= (1 << 6)  # Set bit 3 for motor 4 direction
       
    print('ctrl byte=',control_byte) 
    # Write the control byte to the latch
    write_to_latch(control_byte)

def set_motor_speed(motor3_speed, motor4_speed):
    # Set PWM speed values (0.0-1.0)
    motor3_pwm.write(motor3_speed)
    motor4_pwm.write(motor4_speed)

# Initialize motors
enable_pin.write(0)  # Enable the motor driver

# Test routine for motors 3 and 4
try:
    print("Motors 3 & 4 forward")
    control_motors(True, True)  # Set directions
    #set_motor_speed(0.7, 0.7)   # Set speeds to 70%
    set_motor_speed(1, 1)   # Set speeds to 70%
    time.sleep(4)
    
    print("Motors 3 & 4 opposite directions")
    control_motors(True, False)  # Motor 3 forward, Motor 4 backward
    #set_motor_speed(0.5, 0.5)    # Set speeds to 50%
    set_motor_speed(1, 1)    # Set speeds to 50%
    time.sleep(4)
    
    print("Motors 3 & 4 reverse")
    control_motors(False, False)  # Both motors backward
    #set_motor_speed(0.3, 0.3)     # Set speeds to 30%
    set_motor_speed(1, 1)     # Set speeds to 30%
    time.sleep(4)
    
    print("Motors stopped")
    set_motor_speed(0, 0)  # Stop motors
    
finally:
    # Clean shutdown
    set_motor_speed(0, 0)  # Stop motors
    enable_pin.write(0)    # Disable motor driver
    board.exit()

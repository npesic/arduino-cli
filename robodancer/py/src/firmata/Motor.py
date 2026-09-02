#!/usr/bin/env python3
from pyfirmata import Arduino, util
from time import sleep

board = Arduino("/dev/ttyUSB0")  # Change to your port

it = util.Iterator(board)
it.start()

#pwmPinEA1 = board.get_pin("d:5:p")  # PWM Pin
#motorPinOne = board.get_pin("d:9:o")  # D9 pin : output
#motorPinTwo = board.get_pin("d:8:o")  # D8 pin : output
print("Starting to output PWM signal")

a_direction = board.get_pin("d:12:o")
a_pwm = board.get_pin("d:6:p")
a_break = board.get_pin("d:9:o")
enable_pin = board.get_pin('d:7:o')    # Enable pin

b_pwm = board.get_pin("d:5:p")

# Calculate expected PWM output voltage
#
#             timeOn
#         ----------------
#        (timeOff + timeOn)
#

timeOn = 0.00001
timeOff = 0.000
psuVoltage = 5

expectedOutputVoltage = (timeOn / (timeOn + timeOff)) * psuVoltage
motorPercentage = (expectedOutputVoltage / psuVoltage) * 100
print(f"{expectedOutputVoltage} volts")

enable_pin.write(0)
a_direction.write(0)
a_break.write(0)
a_pwm.write(1)
b_pwm.write(1)

#pwmPinEA1.write(10)
#motorPinOne.write(1)
#motorPinTwo.write(1)

sleep(5)

a_pwm.write(0)
b_pwm.write(0)

#pwmPinEA1.write(0)
#motorPinOne.write(0)
#motorPinTwo.write(0)




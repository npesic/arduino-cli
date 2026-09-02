#!/usr/bin/env python3
from pyfirmata import Arduino, util
from time import sleep

board = Arduino("/dev/ttyUSB0")  # Change to your port
pwmPinEA1 = board.get_pin("d:5:p")  # PWM Pin
motorPinOne = board.get_pin("d:9:o")  # DO pin
motorPinTwo = board.get_pin("d:8:o")  # DO pin
print("Starting to output PWM signal")


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


while True:
    pwmPinEA1.write(1)
    motorPinOne.write(1)
    motorPinTwo.write(0)
    # print(f"Motor One Forward at {int(motorPercentage)}% with output voltage of {int(expectedOutputVoltage)}V")
    # sleep(timeOn)

    sleep(5)
    # pwmPinEA1.write(0)
    # print(f"Off time is {timeOff} seconds")
    # sleep(timeOff)
    motorPinOne.write(0)
    motorPinTwo.write(1)

    sleep(5)

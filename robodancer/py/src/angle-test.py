#!/usr/bin/python
import time
import RPi.GPIO as GPIO
from PCA9685 import PCA9685
import traceback
import sys

pwm = PCA9685()
try:
    if len(sys.argv) < 3:
        print ("Arg 0 - Channel 0 angle, Arg 1 - Channel 1 angle")
        exit()
    ch0Angle = int(sys.argv[1])
    ch1Angle = int(sys.argv[2])
    print ("This is an PCA9685 routine")
    pwm.setPWMFreq(50)
    #pwm.setServoPulse(1,500) 
    pwm.setRotationAngle(1, ch1Angle) # left/right
    pwm.setRotationAngle(0, ch0Angle) # up/down
    print ("Changel 0, angle = "+ str(ch0Angle))
    print ("Changel 1, angle = "+ str(ch1Angle))
except:
    traceback.print_exc()
    pwm.exit_PCA9685()
    print ("\nProgram end")
    exit()

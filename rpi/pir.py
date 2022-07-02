import RPi.GPIO as GPIO
import time

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)
GPIO.setup(11, GPIO.IN)

while True:
    i = GPIO.input(11)
    if i==1:
        print "Nothing", i
        time.sleep(0.1)
    elif i==0:
        print "Detected",i
        time.sleep(0.1)

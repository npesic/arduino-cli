import RPi.GPIO as GPIO
import time

PIR_PIN = 13
IR_PIN = 11

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)
GPIO.setup(IR_PIN, GPIO.IN)
GPIO.setup(PIR_PIN, GPIO.IN)

while True:
    #ir (infra red) is opposite: 1 - high signal indicates sensor is on, 0 - low signal indicates detected movement
    ir = GPIO.input(IR_PIN)
    pir = GPIO.input(PIR_PIN) # pir (passive ir) 1 - movement detected (stayes on for some cool off time), 0 - no movement
    if ir==1:
        print "Nothing", ir, pir
        time.sleep(0.1)
    elif ir==0:
        print "Detected",ir, pir
        time.sleep(0.1)

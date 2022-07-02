import RPi.GPIO as GPIO
import time
import requests

PIR_PIN = 13
IR_PIN = 11

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)
GPIO.setup(IR_PIN, GPIO.IN)
GPIO.setup(PIR_PIN, GPIO.IN)

url = 'http://head2toes.asuscomm.com/sub/example/printQueue.json'
payload = {"text":"Hi from Py!","x":200,"y":200}
cnt = 0

while True:
    cnt=cnt+1
    #ir (infra red) is opposite: 1 - high signal indicates sensor is on, 0 - low signal indicates detected movement
    ir = GPIO.input(IR_PIN)
    pir = GPIO.input(PIR_PIN) # pir (passive ir) 1 - movement detected (stayes on for some cool off time), 0 - no movement
    if ir==1:
        #print ("Nothing", ir, pir)
        payload['text'] = "Nothing. ir=" + str(ir) + " pir=" + str(pir)
        res = requests.put(url, json=payload)
        print(payload)
        time.sleep(0.5)
    elif ir==0:
        #print ("Detected",ir, pir)
        payload['text'] = "Detected. ir=" + str(ir) + " pir=" + str(pir)
        res = requests.put(url, json=payload)
        print(payload)
        time.sleep(0.5)

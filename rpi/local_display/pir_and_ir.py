#import RPi.GPIO as GPIO
import time
import requests
import board
import digitalio
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306

oled_reset = digitalio.DigitalInOut(board.D4)
WID = 128
HEI = 64
i2c = board.I2C()
oled = adafruit_ssd1306.SSD1306_I2C( WID, HEI, i2c, addr=0x3C, reset=oled_reset)

def clear ():
    oled.fill(0)
    oled.show()

def drawText(txt, x, y):
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((x,y),text=txt,font=font,fill=255)
    oled.image(image)
    oled.show()


PIR_PIN = 13
IR_PIN = 11

#GPIO.setwarnings(False)
#GPIO.setmode(GPIO.BOARD)
#GPIO.setup(IR_PIN, GPIO.IN)
#GPIO.setup(PIR_PIN, GPIO.IN)
pir = digitalio.DigitalInOut(board.D22)
pir.direction = digitalio.Direction.INPUT
ir = digitalio.DigitalInOut(board.D17)
ir.direction = digitalio.Direction.INPUT

url = 'http://head2toes.asuscomm.com/sub/example/printQueue.json'
payload = {"text":"Hi from Py!","x":200,"y":200}
cnt = 0

while True:
    cnt=cnt+1
    #ir (infra red) is opposite: 1 - high signal indicates sensor is on, 0 - low signal indicates detected movement
    #ir = GPIO.input(IR_PIN)
    #pir = #GPIO.input(PIR_PIN) # pir (passive ir) 1 - movement detected (stayes on for some cool off time), 0 - no movement
    if ir.value:
        #print ("Nothing", ir, pir)
        payload['text'] = "Nothing. ir=" + str(ir.value) + " pir=" + str(pir.value)
        #res = requests.put(url, json=payload)
        print(payload)
        drawText("Nothing",0,0)
        time.sleep(0.5)
    else:
        #print ("Detected",ir, pir)
        payload['text'] = "Detected. ir=" + str(ir.value) + " pir=" + str(pir.value)
        #res = requests.put(url, json=payload)
        print(payload)
        drawText("Detected",0,16)
        time.sleep(0.5)

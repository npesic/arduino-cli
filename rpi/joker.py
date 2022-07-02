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


image = Image.new("1", (oled.width, oled.height))
draw = ImageDraw.Draw(image)

def clear ():
    draw = ImageDraw.Draw(image)
    draw = draw.rectangle(((0, 0), (oled.width, oled.height)), fill=0)
    oled.fill(0)
    oled.show()

def drawText(txt, x, y):
    font = ImageFont.load_default()
    draw.text((x,y),text=txt,font=font,fill=255)
    oled.image(image)
    oled.show()


#pin15 = digitalio.DigitalInOut(board.D22) #15
#pin15.direction = digitalio.Direction.INPUT
pin11 = digitalio.DigitalInOut(board.D17) #11
pin11.direction = digitalio.Direction.INPUT

cnt = 0;
tosay=["Hi", "Hello!", "Knock, knock", "Who's there?", "Hello, hello!", "Welcome back", "Hello beautiful!", " :-) "]

while True:
    if pin11.value:
        cnt=cnt+1
        if cnt>3:
            cnt = 0
            clear();
        index=int(time.time() % len(tosay))
        drawText(tosay[index],0,cnt*16)
        time.sleep(3)
#    if pin15.value:
#        drawText("Hi, p15!",0,16)
#        time.sleep(0.5)

    #if pin15.value == 0 and pin11.value == 0:
    if pin11.value == 0:
        clear()
    time.sleep(0.5)

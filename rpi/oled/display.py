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

clear()
drawText("Hey, Hi!",0,0)
drawText("How you doing?",0,16)


/**************************************************************************
 This is an example for our Monochrome OLEDs based on SSD1306 drivers
 Pick one up today in the adafruit shop!
 ------> http://www.adafruit.com/category/63_98
 This example is for a 128x64 pixel display using I2C to communicate
 3 pins are required to interface (two I2C and one reset).
 Adafruit invests time and resources providing this open
 source code, please support Adafruit and open-source
 hardware by purchasing products from Adafruit!
 Written by Limor Fried/Ladyada for Adafruit Industries,
 with contributions from the open source community.
 BSD license, check license.txt for more information
 All text above, and the splash screen below must be
 included in any redistribution.
 **************************************************************************/

#include <SPI.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define SCREEN_WIDTH 128 // OLED display width, in pixels
#define SCREEN_HEIGHT 64 // OLED display height, in pixels

// Declaration for an SSD1306 display connected to I2C (SDA, SCL pins)
// The pins for I2C are defined by the Wire-library. 
// On an arduino UNO:       A4(SDA), A5(SCL)
// On an arduino MEGA 2560: 20(SDA), 21(SCL)
// On an arduino LEONARDO:   2(SDA),  3(SCL), ...
#define OLED_RESET     -1 // Reset pin # (or -1 if sharing Arduino reset pin)
#define SCREEN_ADDRESS 0x3C ///< See datasheet for Address; 0x3D for 128x64, 0x3C for 128x32
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

#define NUMFLAKES     10 // Number of snowflakes in the animation example

#define LOGO_HEIGHT   16
#define LOGO_WIDTH    16
static const unsigned char PROGMEM logo_bmp[] =
{ 0b00000000, 0b11000000,
  0b00000001, 0b11000000,
  0b00000001, 0b11000000,
  0b00000011, 0b11100000,
  0b11110011, 0b11100000,
  0b11111110, 0b11111000,
  0b01111110, 0b11111111,
  0b00110011, 0b10011111,
  0b00011111, 0b11111100,
  0b00001101, 0b01110000,
  0b00011011, 0b10100000,
  0b00111111, 0b11100000,
  0b00111111, 0b11110000,
  0b01111100, 0b11110000,
  0b01110000, 0b01110000,
  0b00000000, 0b00110000 };
#define PIR 14 //GPIO14 - D5
#define PIN 12 //GPIO12 - D6
#define BTTN 13 //GPIO13 - D7
int pirState;

void setup() {
    pinMode(BTTN, INPUT);
    pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(9600);

  // SSD1306_SWITCHCAPVCC = generate display voltage from 3.3V internally
  if(!display.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS)) {
    Serial.println(F("SSD1306 allocation failed"));
    for(;;); // Don't proceed, loop forever
  }

  // Show initial display buffer contents on the screen --
  // the library initializes this with an Adafruit splash screen.
  display.display();
  delay(1000); // Pause for 1 seconds

  // Clear the buffer
  display.clearDisplay();
  display.display();
  }

int clockState = 0;

void loop() {
    pirState = digitalRead(BTTN);
    if (pirState == 1){
    digitalWrite(LED_BUILTIN, HIGH);
    delay(1000);
    } else {
    digitalWrite(LED_BUILTIN, LOW);
    delay(1000);
    }

    if (clockState == 0 && pirState == 1){
      runClock();
    }

}

void runClock(){

clockState = 1;

  display.clearDisplay();
  int16_t sec, minute;
  while (minute<20){
    while (sec<60){
	sec++;
	showSec(sec);
  	display.display();
	delay(1000);

    	pirState = digitalRead(BTTN);
	if (pirState == 1){
		display.clearDisplay();
		display.display();
		clockState=0;
		delay(5000);
		return;
	}
    }
    sec=0;
    showMin(minute);
    minute++;
  display.display();
  }
  delay(5000);

clockState = 0;

  display.clearDisplay();
  display.display();

}

void showSec(int16_t sec){
int16_t x=sec*2;
display.drawLine(x,0,x,8, SSD1306_INVERSE);
}

void showMin(int16_t minute){
int16_t x=minute*6;
if (minute<10){
display.fillRect(x,20, 4, 30, SSD1306_WHITE);
} else {
display.fillRect(x,30, 4, 20, SSD1306_WHITE);
}
}

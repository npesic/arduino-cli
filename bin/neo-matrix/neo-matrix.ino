// the setup function runs once when you press reset or power the board

#include <Adafruit_SPITFT_Macros.h>
#include <Adafruit_SPITFT.h>
#include <Adafruit_GFX.h>
#include <Adafruit_NeoMatrix.h>
#include <Adafruit_NeoPixel.h>

#ifndef PSTR
#define PSTR //make Arduino Due happy
#endif // !PSTR

#define PIN 12 //GPIO12 - D6
#define PIR 14 //GPIO14 - D5

int pirState;
#define timeSeconds 2

// Timer: Auxiliary variables
unsigned long now = millis();
unsigned long lastTrigger = 0;
boolean startTimer = false;

// Checks if motion was detected, sets LED HIGH and starts a timer
ICACHE_RAM_ATTR void detectsMovement() {
  digitalWrite(LED_BUILTIN, LOW);
  startTimer = true;
  lastTrigger = millis();
}


Adafruit_NeoMatrix matrix = Adafruit_NeoMatrix(32, 8, PIN, NEO_MATRIX_TOP + NEO_MATRIX_LEFT + NEO_MATRIX_COLUMNS + NEO_MATRIX_ZIGZAG, NEO_GRB + NEO_KHZ800);

const uint16_t colors[] = {
matrix.Color(0,200,0), matrix.Color(230,115,0),matrix.Color(0,179,179) };

void setup() {
    pinMode(PIR, INPUT);
    //pinMode(PIR, INPUT_PULLUP);
    pinMode(LED_BUILTIN, OUTPUT);
    //attachInterrupt(digitalPinToInterrupt(PIR), detectsMovement, RISING);


matrix.begin();
matrix.setTextWrap(false);
matrix.setBrightness(4);
matrix.setTextColor(colors[0]);

}

int x = matrix.width();
int pass = 0;

void loop() {
  // Current time
  now = millis();
pirState = digitalRead(PIR);
if (pirState == 1){
	startTimer = true;
	lastTrigger = now;
    digitalWrite(LED_BUILTIN, LOW);
}
  // Turn off the LED after the number of seconds defined in the timeSeconds variable
 if(startTimer == true && (now - lastTrigger > (timeSeconds*1000))) {
    startTimer = false;
    digitalWrite(LED_BUILTIN, HIGH);
 }

 if (startTimer == true && pass == 0){
    //digitalWrite(LED_BUILTIN, LOW);
    startTimer = false;
    onePass();
    digitalWrite(LED_BUILTIN, HIGH);
    startTimer = false;
  }
}

void onePass(){
char scrollText[] = "welcome to the matrix";
int scrollLen = strlen(scrollText) *- 6;
while (1==1){
matrix.fillScreen(0);
matrix.setCursor(x, 0);
matrix.print(scrollText);
if (--x < scrollLen) {
x = matrix.width();
if (++pass >= 3){
  pass = 0;
  matrix.setTextColor(colors[0]);
  return;
}
matrix.setTextColor(colors[pass]);
}
matrix.show();
delay(20);
}
}

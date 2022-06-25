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


Adafruit_NeoMatrix matrix = Adafruit_NeoMatrix(32, 8, PIN, NEO_MATRIX_TOP + NEO_MATRIX_LEFT + NEO_MATRIX_COLUMNS + NEO_MATRIX_ZIGZAG, NEO_GRB + NEO_KHZ800);

const uint16_t colors[] = {
matrix.Color(0,200,60), matrix.Color(230,115,0),matrix.Color(0,179,179) };

void setup() {
    pinMode(PIR, INPUT);
    pinMode(LED_BUILTIN, OUTPUT);

matrix.begin();
matrix.setTextWrap(false);
matrix.setBrightness(4);
matrix.setTextColor(colors[0]);

}

int x = matrix.width();
int pass = 0;

// the loop function runs over and over again until power down or reset
void loop() {
    pirState = digitalRead(PIR);
    if (pirState == 0){
    digitalWrite(LED_BUILTIN, HIGH);
    onePass();
    delay(500);
    } else {
    digitalWrite(LED_BUILTIN, LOW);
//    onePass();
    delay(1000);
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
  return;
}
matrix.setTextColor(colors[pass]);
}
matrix.show();
delay(20);
}
}

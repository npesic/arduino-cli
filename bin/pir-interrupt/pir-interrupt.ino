#define PIN 12 //GPIO12 - D6
#define PIR 14 //GPIO14 - D5
int pirState;
unsigned long now = millis();
unsigned long lastTrigger = 0;

ICACHE_RAM_ATTR void detectsMovement() {
  digitalWrite(LED_BUILTIN, LOW);
  pirState = 1;
  lastTrigger = millis();
}


void setup() {
    pinMode(PIR, INPUT_PULLUP);
    pinMode(LED_BUILTIN, OUTPUT);
    attachInterrupt(digitalPinToInterrupt(PIR), detectsMovement, RISING);


}

void loop() {
    now = millis();
    if (pirState == 1 && (now-lastTrigger)>2000){
    	digitalWrite(LED_BUILTIN, HIGH);
	pirState = 0;
    }
}

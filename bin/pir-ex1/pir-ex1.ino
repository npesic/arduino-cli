#define PIN 12 //GPIO12 - D6
#define PIR 14 //GPIO14 - D5
int pirState;

void setup() {
    pinMode(PIR, INPUT);
    pinMode(LED_BUILTIN, OUTPUT);
}

void loop() {
    pirState = digitalRead(PIR);
    if (pirState == 0){
    digitalWrite(LED_BUILTIN, HIGH);
    delay(1000);
    } else {
    digitalWrite(LED_BUILTIN, LOW);
    delay(1000);
    }
}

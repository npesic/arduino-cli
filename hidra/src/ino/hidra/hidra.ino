#include <WiFi.h>
#include <ESPAsyncWebServer.h>
#include <M5StickCPlus.h>
#include <BleKeyboard.h>
  
const char* ssid = "<REPLACE>";
const char* password =  "<REPLACE>";
  
BleKeyboard bleKeyboard("HIDRA");

AsyncWebServer server(80);
AsyncWebSocket ws("/ws");
 
char scrollText[160] = " ";
boolean ready = false;

void handleWebSocketMessage(void *arg, uint8_t *data, size_t len) {
  AwsFrameInfo *info = (AwsFrameInfo*)arg;
  if (info->final && info->index == 0 && info->len == len && info->opcode == WS_TEXT) {
    data[len] = 0;

    if (len<160 && !ready){
        memset(scrollText, '\0', sizeof(scrollText));
        strcpy(scrollText,(char*)data);
    }
    ready = true;
  }
}


 
void onWsEvent(AsyncWebSocket * server, AsyncWebSocketClient * client, AwsEventType type, void * arg, uint8_t *data, size_t len){
  
  if(type == WS_EVT_CONNECT){
  
    Serial.println("Websocket client connection received");
     
   } else if(type == WS_EVT_DATA){
 
     handleWebSocketMessage(arg, data, len);
  
   } else if(type == WS_EVT_DISCONNECT){
 
    Serial.println("Client disconnected");
  
  }
}
  
void setup(){
  M5.begin();
  M5.Lcd.setTextSize(2);  
  M5.Lcd.setRotation(3);
    M5.Lcd.println("WS BLE HID");
  Serial.begin(9600);
  
  WiFi.begin(ssid, password);
  M5.lcd.print("Connecting");
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.println("Connecting to WiFi..");
    M5.lcd.print(".");
  }

  Serial.println("Starting BLE work!");
  bleKeyboard.begin();

  Serial.println(WiFi.localIP());
  M5.lcd.println(".");
  M5.lcd.println(WiFi.localIP());

  ws.onEvent(onWsEvent);
  server.addHandler(&ws);
  
  server.begin();
}
  
void loop(){

  boolean ctr = false;
  boolean alt = false;
 
  if (ready){
    ws.textAll(scrollText);
    ready = false;
    if (strcmp((char*)scrollText, "esc") == 0) {
      bleKeyboard.write(KEY_ESC);
    } else if (strcmp(scrollText, "tab") == 0) {
      bleKeyboard.write(KEY_TAB);
    } else if (strcmp(scrollText, "up") == 0) {
      bleKeyboard.write(KEY_UP_ARROW);
    } else if (strcmp(scrollText, "down") == 0) {
      bleKeyboard.write(KEY_DOWN_ARROW);
    } else if (strcmp(scrollText, "left") == 0) {
      bleKeyboard.write(KEY_LEFT_ARROW);
    } else if (strcmp(scrollText, "right") == 0) {
      bleKeyboard.write(KEY_RIGHT_ARROW);
    } else if (strcmp(scrollText, "ctr") == 0) {
      bleKeyboard.press(KEY_LEFT_CTRL);
      ctr = true;
    } else if (strcmp(scrollText, "alt") == 0) {
      bleKeyboard.press(KEY_LEFT_ALT);
      alt = true;
    } else {
        M5.lcd.fillScreen(BLACK);
        M5.lcd.setCursor(0,10);
        bleKeyboard.print(scrollText);
        bleKeyboard.releaseAll();
        alt = false;
        ctr = false;
    }
    M5.lcd.print(scrollText);
  }
 
}

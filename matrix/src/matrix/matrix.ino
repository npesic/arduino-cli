/*********
  Arduino App Matrix - ESP8266 NodeMCU

  Based on the WebSocket server example by Rui Santos
  https://RandomNerdTutorials.com/esp8266-nodemcu-websocket-server-arduino/

  Modules:
    * WS2812 LED matrix panel (32x8)   - D6 / GPIO12
    * SSD1306 OLED display (I2C)       - D1 (SCL) / D2 (SDA)
    * PIR motion sensor                - D5 / GPIO14
    * Capacitive touch button (TTP223) - D7 / GPIO13

  Features:
    * Wi-Fi credentials manager (AP setup page -> LittleFS -> STA mode)
    * HTTP + WebSocket server for setting the scrolling banner
    * NTP time sync, local time kept in sync in the background
    * PIR / touch driven display logic (see handleInputs())
*********/

#include <ESP8266WiFi.h>
#include <ESPAsyncTCP.h>
#include <ESPAsyncWebServer.h>
#include <DNSServer.h>
#include <LittleFS.h>
#include <time.h>
#include <TZ.h>

#include <SPI.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_NeoMatrix.h>
#include <Adafruit_NeoPixel.h>

// ---------------------------------------------------------------- pins/config

#define PIN         12  // GPIO12 - D6, LED matrix data
#define PIR         14  // GPIO14 - D5, PIR sensor
#define TOUCH       13  // GPIO13 - D7, touch button (active HIGH)

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET   -1
#define SCREEN_ADDRESS 0x3C

#define SCROLL_PASSES     3      // how many times the banner is scrolled
#define SCROLL_STEP_MS    60     // one pixel step of the scroll
#define CLOCK_MS          10000  // how long the clock stays on the matrix
#define INPUT_COOLDOWN_MS 1000   // ignore repeated triggers within this window

#define NIGHT_START_HOUR  22     // night (sleep) time starts at 22:00
#define NIGHT_END_HOUR    7      // ...and ends at 07:00

#define AP_SSID     "Matrix-Setup"
#define AP_PASSWORD "matrix1234"   // >= 8 chars, or "" for an open AP
#define WIFI_FILE   "/wifi.cfg"
#define WIFI_CONNECT_TIMEOUT_MS 20000

#define MY_TZ  TZ_America_Los_Angeles  // PST/PDT, see TZ.h for other zones
#define NTP_SERVER_1 "pool.ntp.org"
#define NTP_SERVER_2 "time.nist.gov"

// ---------------------------------------------------------------- hardware

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

Adafruit_NeoMatrix matrix = Adafruit_NeoMatrix(32, 8, PIN,
  NEO_MATRIX_TOP + NEO_MATRIX_LEFT + NEO_MATRIX_COLUMNS + NEO_MATRIX_ZIGZAG,
  NEO_GRB + NEO_KHZ800);

const uint16_t colors[] = {
  matrix.Color(0, 200, 0), matrix.Color(230, 115, 0),
  matrix.Color(0, 0, 179), matrix.Color(120, 120, 179) };
uint16_t nightColor;  // set in setup(), matrix.Color() is not constexpr

// ---------------------------------------------------------------- state

AsyncWebServer server(80);
AsyncWebSocket ws("/ws");
DNSServer dnsServer;

bool apMode = false;              // true while running the credentials portal
String wifiSsid;
String wifiPass;

bool ledState = 0;                // motion display enabled (toggled from the page)
const int ledPin = LED_BUILTIN;

char scrollText[160] = "welcome to the matrix";
char scrollBuffer[200];           // banner + appended time/date, what is shown
int scrollLen = 0;                // negative, x position where a pass ends
int x = 0;
int pass = 0;
unsigned long lastScrollStep = 0;

enum Mode { MODE_IDLE, MODE_SCROLL, MODE_CLOCK };
Mode mode = MODE_IDLE;
unsigned long modeStart = 0;
unsigned long lastTrigger = 0;
int lastTouch = LOW;

bool timeSynced = false;
unsigned long lastOled = 0;

// ---------------------------------------------------------------- pages

const char setup_html[] PROGMEM = R"rawliteral(
<!DOCTYPE HTML><html>
<head>
  <title>Matrix Wi-Fi Setup</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <style>
    html { font-family: Arial, Helvetica, sans-serif; text-align: center; }
    body { margin: 0; }
    h1 { font-size: 1.8rem; color: white; }
    .topnav { overflow: hidden; background-color: #143642; }
    .content { padding: 30px; max-width: 600px; margin: 0 auto; }
    .card { background-color: #F8F7F9; box-shadow: 2px 2px 12px 1px rgba(140,140,140,.5);
            padding: 10px 20px 20px 20px; }
    input { font-size: 1.2rem; padding: 8px; width: 90%; margin: 6px 0; }
    .button { padding: 15px 50px; font-size: 24px; color: #fff;
              background-color: #0f8b8d; border: none; border-radius: 5px; }
  </style>
</head>
<body>
  <div class="topnav"><h1>Matrix Wi-Fi Setup</h1></div>
  <div class="content"><div class="card">
    <h2>Wi-Fi credentials</h2>
    <form action="/save" method="POST">
      <p><input type="text" name="ssid" placeholder="SSID" maxlength="32" required></p>
      <p><input type="password" name="pass" placeholder="password" maxlength="63"></p>
      <p><button type="submit" class="button">Save</button></p>
    </form>
  </div></div>
</body></html>
)rawliteral";

const char saved_html[] PROGMEM = R"rawliteral(
<!DOCTYPE HTML><html>
<head><title>Saved</title><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,"></head>
<body style="font-family:Arial;text-align:center;padding-top:40px">
  <h2>Credentials saved</h2>
  <p>Restarting and connecting to the network...</p>
  <p>If the connection fails the setup access point comes back.</p>
</body></html>
)rawliteral";

const char index_html[] PROGMEM = R"rawliteral(
<!DOCTYPE HTML><html>
<head>
  <title>Matrix</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <style>
    html { font-family: Arial, Helvetica, sans-serif; text-align: center; }
    body { margin: 0; }
    h1 { font-size: 1.8rem; color: white; }
    h2 { font-size: 1.5rem; font-weight: bold; color: #143642; }
    .topnav { overflow: hidden; background-color: #143642; }
    .content { padding: 30px; max-width: 600px; margin: 0 auto; }
    .card { background-color: #F8F7F9; box-shadow: 2px 2px 12px 1px rgba(140,140,140,.5);
            padding-top: 10px; padding-bottom: 20px; margin-bottom: 20px; }
    .button { padding: 15px 50px; font-size: 24px; text-align: center; outline: none;
              color: #fff; background-color: #0f8b8d; border: none; border-radius: 5px;
              -webkit-touch-callout: none; user-select: none;
              -webkit-tap-highlight-color: rgba(0,0,0,0); }
    .button:active { background-color: #0f8b8d; transform: translateY(2px); }
    .danger { background-color: #b03a2e; font-size: 18px; padding: 10px 30px; }
    .state { font-size: 1.5rem; color: #8c8c8c; font-weight: bold; }
  </style>
</head>
<body>
  <div class="topnav"><h1>ESP WebSocket Server</h1></div>
  <div class="content">
    <div class="card">
      <h2>Motion display</h2>
      <p class="state">state: <span id="state">OFF</span></p>
      <p><button id="button" class="button">Toggle</button></p>
    </div>
    <div class="card">
      <h2>Banner</h2>
      <p class="state"><input id="bannerText" type="text"></p>
      <p><button id="banner" class="button">Set</button></p>
    </div>
    <div class="card">
      <h2>Clock</h2>
      <p class="state"><span id="clock">--:--</span></p>
      <p><button id="show" class="button">Show on matrix</button></p>
    </div>
    <div class="card">
      <h2>Wi-Fi</h2>
      <p class="state"><span id="ssid"></span></p>
      <p><button id="forget" class="button danger">Forget network</button></p>
    </div>
  </div>
<script>
  var gateway = `ws://${window.location.hostname}/ws`;
  var websocket;
  window.addEventListener('load', onLoad);
  function initWebSocket() {
    websocket = new WebSocket(gateway);
    websocket.onopen    = onOpen;
    websocket.onclose   = onClose;
    websocket.onmessage = onMessage;
  }
  function onOpen(event) { websocket.send('status'); }
  function onClose(event) { setTimeout(initWebSocket, 2000); }
  function onMessage(event) {
    var msg = event.data;
    if (msg.charAt(0) == '{') {
      var s = JSON.parse(msg);
      document.getElementById('state').innerHTML = s.led ? 'ON' : 'OFF';
      document.getElementById('clock').innerHTML = s.time;
      document.getElementById('ssid').innerHTML = s.ssid;
      document.getElementById('bannerText').placeholder = s.banner;
      return;
    }
    document.getElementById('state').innerHTML = (msg == "1") ? "ON" : "OFF";
  }
  function onLoad(event) { initWebSocket(); initButtons(); setInterval(poll, 5000); }
  function initButtons() {
    document.getElementById('button').addEventListener('click', toggle);
    document.getElementById('banner').addEventListener('click', setBanner);
    document.getElementById('show').addEventListener('click', showClock);
    document.getElementById('forget').addEventListener('click', forget);
  }
  function poll() { if (websocket.readyState == 1) websocket.send('status'); }
  function toggle() { websocket.send('toggle'); }
  function showClock() { websocket.send('clock'); }
  function setBanner() { websocket.send(document.getElementById('bannerText').value); }
  function forget() {
    if (confirm('Erase the stored Wi-Fi credentials and restart in setup mode?')) {
      fetch('/forget', {method: 'POST'});
    }
  }
</script>
</body></html>
)rawliteral";

// ---------------------------------------------------------------- time

bool haveTime() {
  return time(nullptr) > 1600000000;  // sane epoch => SNTP has answered
}

struct tm localNow() {
  time_t now = time(nullptr);
  struct tm t;
  localtime_r(&now, &t);
  return t;
}

String timeString() {
  if (!haveTime()) return String("--:--");
  struct tm t = localNow();
  char buf[8];
  snprintf(buf, sizeof(buf), "%02d:%02d", t.tm_hour, t.tm_min);
  return String(buf);
}

String dateString() {
  if (!haveTime()) return String("--.--.");
  struct tm t = localNow();
  char buf[12];
  snprintf(buf, sizeof(buf), "%02d.%02d.", t.tm_mday, t.tm_mon + 1);
  return String(buf);
}

String dateTimeString() {
  if (!haveTime()) return String("--:-- --.--.----");
  struct tm t = localNow();
  char buf[24];
  snprintf(buf, sizeof(buf), "%02d:%02d %02d.%02d.%04d",
           t.tm_hour, t.tm_min, t.tm_mday, t.tm_mon + 1, t.tm_year + 1900);
  return String(buf);
}

// Night time is the window reserved for sleep, it may wrap around midnight.
bool isNightTime() {
  if (!haveTime()) return false;
  int h = localNow().tm_hour;
  if (NIGHT_START_HOUR == NIGHT_END_HOUR) return false;
  if (NIGHT_START_HOUR < NIGHT_END_HOUR) {
    return h >= NIGHT_START_HOUR && h < NIGHT_END_HOUR;
  }
  return h >= NIGHT_START_HOUR || h < NIGHT_END_HOUR;
}

void initTime() {
  configTime(MY_TZ, NTP_SERVER_1, NTP_SERVER_2);  // SNTP keeps polling on its own
}

// ---------------------------------------------------------------- credentials

bool loadCredentials() {
  if (!LittleFS.exists(WIFI_FILE)) return false;
  File f = LittleFS.open(WIFI_FILE, "r");
  if (!f) return false;
  wifiSsid = f.readStringUntil('\n');
  wifiPass = f.readStringUntil('\n');
  f.close();
  wifiSsid.trim();
  wifiPass.trim();
  return wifiSsid.length() > 0;
}

bool saveCredentials(const String& ssid, const String& pass) {
  File f = LittleFS.open(WIFI_FILE, "w");
  if (!f) return false;
  f.println(ssid);
  f.println(pass);
  f.close();
  return true;
}

void clearCredentials() {
  LittleFS.remove(WIFI_FILE);
}

// ---------------------------------------------------------------- OLED

void oledLines(const String& l1, const String& l2 = "", const String& l3 = "") {
  display.clearDisplay();
  display.setCursor(0, 0);
  display.println(l1);
  if (l2.length()) display.println(l2);
  if (l3.length()) display.println(l3);
  display.display();
}

void updateOled() {
  if (millis() - lastOled < 1000) return;
  lastOled = millis();
  display.clearDisplay();
  display.setCursor(0, 0);
  if (apMode) {
    display.println(F("Wi-Fi setup mode"));
    display.println(String("AP: ") + AP_SSID);
    display.println(WiFi.softAPIP().toString());
    display.display();
    return;
  }
  display.println(timeString() + " " + dateString());
  display.println(WiFi.localIP().toString());
  display.println(String("motion: ") + (ledState ? "on" : "off"));
  display.println(isNightTime() ? F("night mode") : F("day mode"));
  if (!haveTime()) display.println(F("time not synced"));
  display.display();
}

// ---------------------------------------------------------------- matrix

void matrixClear() {
  matrix.fillScreen(0);
  matrix.show();
}

void startScroll() {
  // banner + the current time and date appended at the end
  snprintf(scrollBuffer, sizeof(scrollBuffer), "%s   %s",
           scrollText, dateTimeString().c_str());
  scrollLen = (int)strlen(scrollBuffer) * -6;
  x = matrix.width();
  pass = SCROLL_PASSES;
  matrix.setBrightness(4);
  matrix.setTextColor(colors[0]);
  mode = MODE_SCROLL;
  modeStart = millis();
  lastScrollStep = 0;
}

void startClock() {
  matrix.setBrightness(isNightTime() ? 2 : 4);
  mode = MODE_CLOCK;
  modeStart = millis();
}

void stopDisplay() {
  mode = MODE_IDLE;
  pass = 0;
  matrixClear();
}

void doScroll() {
  unsigned long now = millis();
  if (now - lastScrollStep < SCROLL_STEP_MS) return;
  lastScrollStep = now;

  if (--x < scrollLen) {
    x = matrix.width();
    pass--;
    if (pass <= 0) {
      matrix.setTextColor(colors[0]);
      stopDisplay();
      return;
    }
    matrix.setTextColor(colors[pass]);
  }
  matrix.fillScreen(0);
  matrix.setCursor(x, 0);
  matrix.print(scrollBuffer);
  matrix.show();
}

// The 32x8 panel fits 5 characters of the default font, so the static clock
// alternates between the time and the day/month every two seconds.
void doClock() {
  unsigned long elapsed = millis() - modeStart;
  if (elapsed >= CLOCK_MS) {
    stopDisplay();
    return;
  }
  String text = ((elapsed / 2000) % 2 == 0) ? timeString() : dateString();
  matrix.fillScreen(0);
  matrix.setTextColor(nightColor);
  matrix.setCursor(1, 0);
  matrix.print(text);
  matrix.show();
}

// ---------------------------------------------------------------- websocket

String statusJson() {
  String json = "{\"led\":";
  json += ledState ? "1" : "0";
  json += ",\"time\":\"" + dateTimeString() + "\"";
  json += ",\"ssid\":\"" + (WiFi.isConnected() ? WiFi.SSID() : String("-")) + "\"";
  json += ",\"banner\":\"" + String(scrollText) + "\"}";
  return json;
}

void notifyClients() {
  ws.textAll(String(ledState));
}

void handleWebSocketMessage(void *arg, uint8_t *data, size_t len) {
  AwsFrameInfo *info = (AwsFrameInfo*)arg;
  if (!(info->final && info->index == 0 && info->len == len && info->opcode == WS_TEXT)) return;
  data[len] = 0;

  if (strcmp((char*)data, "toggle") == 0) {
    ledState = !ledState;
    notifyClients();
    return;
  }
  if (strcmp((char*)data, "status") == 0) {
    ws.textAll(statusJson());
    return;
  }
  if (strcmp((char*)data, "clock") == 0) {
    startClock();
    return;
  }
  if (len > 0 && len < sizeof(scrollText)) {
    memset(scrollText, '\0', sizeof(scrollText));
    strcpy(scrollText, (char*)data);
  }
}

void onEvent(AsyncWebSocket *server, AsyncWebSocketClient *client, AwsEventType type,
             void *arg, uint8_t *data, size_t len) {
  switch (type) {
    case WS_EVT_CONNECT:
      Serial.printf("WebSocket client #%u connected from %s\n",
                    client->id(), client->remoteIP().toString().c_str());
      client->text(statusJson());
      break;
    case WS_EVT_DISCONNECT:
      Serial.printf("WebSocket client #%u disconnected\n", client->id());
      break;
    case WS_EVT_DATA:
      handleWebSocketMessage(arg, data, len);
      break;
    case WS_EVT_PONG:
    case WS_EVT_ERROR:
      break;
  }
}

// ---------------------------------------------------------------- servers

void startSetupPortal() {
  apMode = true;
  Serial.println(F("Starting Wi-Fi setup access point"));

  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, strlen(AP_PASSWORD) >= 8 ? AP_PASSWORD : NULL);
  IPAddress apIP = WiFi.softAPIP();
  Serial.println(apIP);

  dnsServer.setErrorReplyCode(DNSReplyCode::NoError);
  dnsServer.start(53, "*", apIP);  // captive portal: every name resolves to us

  server.on("/", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send_P(200, "text/html", setup_html);
  });
  server.on("/save", HTTP_POST, [](AsyncWebServerRequest *request) {
    String ssid = request->hasParam("ssid", true) ? request->getParam("ssid", true)->value() : "";
    String pass = request->hasParam("pass", true) ? request->getParam("pass", true)->value() : "";
    if (ssid.length() == 0) {
      request->send(400, "text/plain", "SSID is required");
      return;
    }
    if (!saveCredentials(ssid, pass)) {
      request->send(500, "text/plain", "Could not write the credentials");
      return;
    }
    request->send_P(200, "text/html", saved_html);
    Serial.println("Credentials for '" + ssid + "' saved, restarting");
    delay(500);
    ESP.restart();
  });
  server.onNotFound([](AsyncWebServerRequest *request) {
    request->redirect("/");
  });
  server.begin();

  oledLines(F("Wi-Fi setup mode"), String("AP: ") + AP_SSID, apIP.toString());
}

void startAppServer() {
  ws.onEvent(onEvent);
  server.addHandler(&ws);

  server.on("/", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send_P(200, "text/html", index_html);
  });
  server.on("/status", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send(200, "application/json", statusJson());
  });
  server.on("/forget", HTTP_POST, [](AsyncWebServerRequest *request) {
    clearCredentials();
    request->send(200, "text/plain", "Credentials erased, restarting in setup mode");
    delay(500);
    ESP.restart();
  });
  server.begin();
}

// Returns true when the stored credentials got us onto the network.
bool connectStation() {
  Serial.println("Connecting to '" + wifiSsid + "'");
  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());

  unsigned long start = millis();
  int cnt = 0;
  while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_CONNECT_TIMEOUT_MS) {
    delay(500);
    Serial.print(".");
    if (++cnt % 4 == 0) {
      display.println(F("Connecting..."));
      display.display();
      if (cnt > 32) { cnt = 0; display.clearDisplay(); display.setCursor(0, 0); }
    }
  }
  Serial.println();
  return WiFi.status() == WL_CONNECTED;
}

// ---------------------------------------------------------------- inputs

void handleInputs() {
  unsigned long now = millis();

  int touch = digitalRead(TOUCH);
  bool touched = (touch == HIGH && lastTouch == LOW);
  lastTouch = touch;

  bool motion = digitalRead(PIR) == HIGH;

  // The touch button always shows the time and date, whatever the hour is.
  if (touched && now - lastTrigger > INPUT_COOLDOWN_MS) {
    lastTrigger = now;
    startClock();
    return;
  }

  if (!motion || !ledState) return;
  if (mode != MODE_IDLE) return;
  if (now - lastTrigger <= INPUT_COOLDOWN_MS) return;
  lastTrigger = now;

  if (isNightTime()) {
    startClock();     // night: only the clock, red, no scrolling
  } else {
    startScroll();    // day: the banner with the time and date appended
  }
}

// ---------------------------------------------------------------- setup/loop

void setup() {
  Serial.begin(9600);
  Serial.println();

  pinMode(ledPin, OUTPUT);
  digitalWrite(ledPin, HIGH);   // built-in LED is active LOW
  pinMode(PIR, INPUT);
  pinMode(TOUCH, INPUT);

  if (!display.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS)) {
    Serial.println(F("SSD1306 allocation failed"));
    for (;;);
  }
  display.display();
  delay(1000);
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(F("Hey, Hi!"));
  display.display();

  matrix.begin();
  matrix.setTextWrap(false);
  matrix.setBrightness(4);
  matrix.setTextColor(colors[0]);
  nightColor = matrix.Color(255, 0, 0);
  matrixClear();

  if (!LittleFS.begin()) {
    Serial.println(F("LittleFS mount failed, formatting"));
    LittleFS.format();
    LittleFS.begin();
  }

  if (loadCredentials() && connectStation()) {
    Serial.println(WiFi.localIP());
    oledLines(F("Connected"), WiFi.SSID(), WiFi.localIP().toString());
    initTime();
    startAppServer();
  } else {
    // no credentials yet, or the stored ones do not work: back to setup mode
    startSetupPortal();
  }
}

void loop() {
  if (apMode) {
    dnsServer.processNextRequest();
    updateOled();
    return;
  }

  ws.cleanupClients();
  digitalWrite(ledPin, ledState ? LOW : HIGH);

  if (!timeSynced && haveTime()) {
    timeSynced = true;
    Serial.println("Time synced: " + dateTimeString());
  }

  handleInputs();

  switch (mode) {
    case MODE_SCROLL: doScroll(); break;
    case MODE_CLOCK:  doClock();  break;
    case MODE_IDLE:   break;
  }

  updateOled();
}

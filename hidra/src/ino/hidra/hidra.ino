// HIDRA — Phase 1, Architecture D (PLAN.md Appendix C)
//
//   Tablet A ──WiFi (this device's SoftAP) + WebSocket──> M5StickC Plus ──BLE HID──> Tablet B
//
// No WiFi credentials in source: the ESP32 *is* the access point, and its passphrase is
// generated on first boot, persisted in NVS, and shown on the LCD as text and as a QR code.
//
// Protocol (PLAN.md §4) — newline-terminated ASCII over the WebSocket:
//   A->ESP   V1                 handshake
//            D <usage> <mods>   key down, HID usage id (decimal)
//            U <usage> <mods>   key up
//            T <text>           type a literal string
//            R                  release everything
//            P                  ping
//   ESP->A   OK V1  |  S ble=<0|1> batt=<pct>  |  !  |  E <msg>
//
// Usages 0xE0..0xE7 are the modifier keys and maintain the modifier bitmask themselves, so a
// client can just send them as ordinary key events. The <mods> field is honoured only when
// <usage> is 0, i.e. "D 0 <mods>" sets the modifier state outright.
//
// Buttons: A cycles the LCD screens. B (hold 1.5 s) regenerates the WiFi passphrase.

#include <M5StickCPlus.h>
#include <WiFi.h>
#include <DNSServer.h>
#include <ESPAsyncWebServer.h>
#include <BleKeyboard.h>
#include <Preferences.h>
#include <esp_system.h>
#if __has_include(<esp_random.h>)
#include <esp_random.h>   // moved out of esp_system.h in newer IDF revisions
#endif

#include "page.h"

// ---------------------------------------------------------------- configuration
static const char *AP_SSID       = "HIDRA";
static const char *BLE_NAME      = "HIDRA";
static const uint8_t AP_CHANNEL  = 6;
static const uint8_t AP_MAX_CONN = 2;
static const uint32_t IDLE_RELEASE_MS = 3000;   // release stuck keys if the client goes quiet
static const uint32_t STATUS_MS       = 2000;
static const uint32_t BTN_HOLD_MS     = 1500;

// Flip to 0 if your M5 library revision has no M5.Lcd.qrcode().
#define USE_QR 1

// ---------------------------------------------------------------- globals
BleKeyboard bleKeyboard(BLE_NAME, "HIDRA", 100);
AsyncWebServer server(80);
AsyncWebSocket ws("/ws");
DNSServer dns;
Preferences prefs;

String apPass;

// The HID report we own. BleKeyboard::sendReport() lets us drive real usage ids directly,
// which is what makes held modifiers and press-and-hold work (the old sketch only had write()).
KeyReport report = {0, 0, {0, 0, 0, 0, 0, 0}};

// Messages are parsed on the AsyncTCP task but *acted on* in loop(): BLE calls from the async
// task run on a small stack and have bitten people before.
struct Msg { char text[96]; };
QueueHandle_t msgq;

uint32_t lastClientMs = 0;
uint32_t lastStatusMs = 0;
uint32_t btnBDownMs = 0;
uint8_t  screenIdx = 0;
bool     lastBleState = false;

// ---------------------------------------------------------------- credentials
static String makePassphrase() {
  // No 0/O/1/l/I — this gets read off a 135 px screen.
  static const char alphabet[] = "abcdefghijkmnpqrstuvwxyz23456789";
  String s;
  for (int i = 0; i < 10; i++) s += alphabet[esp_random() % (sizeof(alphabet) - 1)];
  return s;
}

static void loadOrCreatePassphrase(bool forceNew) {
  prefs.begin("hidra", false);
  apPass = prefs.getString("appass", "");
  if (forceNew || apPass.length() < 8) {
    apPass = makePassphrase();
    prefs.putString("appass", apPass);
  }
  prefs.end();
}

// ---------------------------------------------------------------- HID plumbing
static bool isModifier(uint8_t usage) { return usage >= 0xE0 && usage <= 0xE7; }

static void pushReport() {
  if (bleKeyboard.isConnected()) bleKeyboard.sendReport(&report);
}

static bool anythingHeld() {
  if (report.modifiers) return true;
  for (uint8_t i = 0; i < 6; i++) if (report.keys[i]) return true;
  return false;
}

static void keyDown(uint8_t usage, uint8_t mods) {
  if (usage == 0) { report.modifiers = mods; pushReport(); return; }
  if (isModifier(usage)) {
    report.modifiers |= (1 << (usage - 0xE0));
  } else {
    for (uint8_t i = 0; i < 6; i++) if (report.keys[i] == usage) { pushReport(); return; }
    for (uint8_t i = 0; i < 6; i++) if (report.keys[i] == 0) { report.keys[i] = usage; break; }
    // 6 keys already held: silently drop, matching real keyboard rollover behaviour.
  }
  pushReport();
}

static void keyUp(uint8_t usage, uint8_t mods) {
  if (usage == 0) { report.modifiers = mods; pushReport(); return; }
  if (isModifier(usage)) {
    report.modifiers &= ~(1 << (usage - 0xE0));
  } else {
    for (uint8_t i = 0; i < 6; i++) if (report.keys[i] == usage) report.keys[i] = 0;
  }
  pushReport();
}

static void releaseAll() {
  report.modifiers = 0;
  memset(report.keys, 0, sizeof(report.keys));
  pushReport();
}

// ---------------------------------------------------------------- protocol
static void reply(const char *s) { ws.textAll(s); }

static void handleLine(char *line) {
  while (*line == ' ' || *line == '\r') line++;
  if (!*line) return;

  const char cmd = *line;
  char *arg = line + 1;
  while (*arg == ' ') arg++;

  switch (cmd) {
    case 'V':
      reply("OK V1");
      break;

    case 'D':
    case 'U': {
      char *end;
      long usage = strtol(arg, &end, 10);
      long mods  = strtol(end, nullptr, 10);
      if (usage < 0 || usage > 255 || mods < 0 || mods > 255) { reply("E range"); break; }
      if (cmd == 'D') keyDown((uint8_t)usage, (uint8_t)mods);
      else            keyUp((uint8_t)usage, (uint8_t)mods);
      break;
    }

    case 'T':
      if (bleKeyboard.isConnected()) {
        bleKeyboard.print(arg);
        pushReport();          // print() clobbers the report; restore whatever is still held
      }
      break;

    case 'R':
      releaseAll();
      break;

    case 'P':
      reply("!");
      break;

    default:
      reply("E cmd");
      break;
  }
}

// Split a frame into lines and queue them. Runs on the AsyncTCP task — no BLE calls here.
static void enqueue(const char *data, size_t len) {
  Msg m;
  size_t n = 0;
  for (size_t i = 0; i <= len; i++) {
    const char c = (i < len) ? data[i] : '\n';
    if (c == '\n' || n == sizeof(m.text) - 1) {
      m.text[n] = '\0';
      if (n) xQueueSend(msgq, &m, 0);
      n = 0;
      if (c != '\n') i--;   // line was truncated; resume mid-line rather than dropping the tail
    } else {
      m.text[n++] = c;
    }
  }
}

static void onWsEvent(AsyncWebSocket *, AsyncWebSocketClient *client, AwsEventType type,
                      void *arg, uint8_t *data, size_t len) {
  if (type == WS_EVT_DATA) {
    AwsFrameInfo *info = (AwsFrameInfo *)arg;
    if (info->final && info->index == 0 && info->len == len && info->opcode == WS_TEXT) {
      enqueue((const char *)data, len);
    }
  } else if (type == WS_EVT_DISCONNECT) {
    Msg m;                                  // drop every key the departing client was holding
    strcpy(m.text, "R");
    xQueueSend(msgq, &m, 0);
  }
}

// ---------------------------------------------------------------- LCD
static int batteryPct() {
  const float v = M5.Axp.GetBatVoltage();
  int pct = (int)((v - 3.0f) / (4.07f - 3.0f) * 100.0f);
  return constrain(pct, 0, 100);
}

static String joinQrPayload() {
  return "WIFI:S:" + String(AP_SSID) + ";T:WPA;P:" + apPass + ";;";
}

static void drawScreen() {
  M5.Lcd.fillScreen(BLACK);
  M5.Lcd.setTextSize(1);
  M5.Lcd.setCursor(0, 0);

  const bool ble = bleKeyboard.isConnected();

  if (screenIdx == 0) {                       // join the AP
#if USE_QR
    M5.Lcd.qrcode(joinQrPayload(), 0, 8, 118, 6);
#endif
    M5.Lcd.setCursor(124, 10);  M5.Lcd.print("JOIN WIFI");
    M5.Lcd.setCursor(124, 30);  M5.Lcd.print("ssid:");
    M5.Lcd.setCursor(124, 42);  M5.Lcd.setTextSize(2); M5.Lcd.print(AP_SSID);
    M5.Lcd.setTextSize(1);
    M5.Lcd.setCursor(124, 66);  M5.Lcd.print("pass:");
    M5.Lcd.setCursor(124, 78);  M5.Lcd.setTextSize(2); M5.Lcd.print(apPass);
    M5.Lcd.setTextSize(1);
    M5.Lcd.setCursor(124, 104); M5.Lcd.print(ble ? "BLE: paired" : "BLE: waiting");
  } else if (screenIdx == 1) {                // open the keyboard
#if USE_QR
    M5.Lcd.qrcode("http://192.168.4.1/", 0, 8, 118, 3);
#endif
    M5.Lcd.setCursor(124, 10);  M5.Lcd.print("OPEN PAGE");
    M5.Lcd.setCursor(124, 34);  M5.Lcd.setTextSize(2); M5.Lcd.print("192.168");
    M5.Lcd.setCursor(124, 54);  M5.Lcd.print(".4.1");
    M5.Lcd.setTextSize(1);
    M5.Lcd.setCursor(124, 84);  M5.Lcd.print("after joining");
    M5.Lcd.setCursor(124, 96);  M5.Lcd.print("the HIDRA AP");
  } else {                                    // status
    M5.Lcd.setTextSize(2);
    M5.Lcd.setCursor(4, 6);   M5.Lcd.print("HIDRA");
    M5.Lcd.setTextSize(1);
    M5.Lcd.setCursor(4, 34);  M5.Lcd.printf("BLE     : %s", ble ? "paired" : "waiting");
    M5.Lcd.setCursor(4, 48);  M5.Lcd.printf("wifi cli: %d", WiFi.softAPgetStationNum());
    M5.Lcd.setCursor(4, 62);  M5.Lcd.printf("ws cli  : %d", ws.count());
    M5.Lcd.setCursor(4, 76);  M5.Lcd.printf("battery : %d%%", batteryPct());
    M5.Lcd.setCursor(4, 90);  M5.Lcd.printf("mods=%02X keys=%02X %02X %02X",
                                            report.modifiers, report.keys[0],
                                            report.keys[1], report.keys[2]);
    M5.Lcd.setCursor(4, 112); M5.Lcd.print("A: screens  B(hold): new pass");
  }
}

// ---------------------------------------------------------------- setup / loop
void setup() {
  M5.begin();
  M5.Lcd.setRotation(3);
  M5.Lcd.fillScreen(BLACK);
  M5.Lcd.setTextSize(2);
  M5.Lcd.println("HIDRA booting");

  Serial.begin(115200);

  msgq = xQueueCreate(16, sizeof(Msg));

  loadOrCreatePassphrase(false);

  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, apPass.c_str(), AP_CHANNEL, /*hidden=*/0, AP_MAX_CONN);
  Serial.printf("AP %s / %s at %s\n", AP_SSID, apPass.c_str(),
                WiFi.softAPIP().toString().c_str());

  // Any hostname resolves here, so a mistyped URL still lands on the keyboard.
  dns.start(53, "*", WiFi.softAPIP());

  server.on("/", HTTP_GET, [](AsyncWebServerRequest *r) {
    r->send_P(200, "text/html", INDEX_HTML);
  });
  // Answer the connectivity probes with "all good" so Fire OS stops nagging about, and
  // deprioritising, an internet-less network.
  server.on("/generate_204", HTTP_GET, [](AsyncWebServerRequest *r) { r->send(204); });
  server.on("/gen_204", HTTP_GET, [](AsyncWebServerRequest *r) { r->send(204); });
  // DNS points every hostname here, so anything else the browser asks for gets the keyboard.
  server.onNotFound([](AsyncWebServerRequest *r) {
    r->send_P(200, "text/html", INDEX_HTML);
  });

  ws.onEvent(onWsEvent);
  server.addHandler(&ws);
  server.begin();

  bleKeyboard.begin();

  lastClientMs = millis();
  drawScreen();
}

void loop() {
  M5.update();
  dns.processNextRequest();

  Msg m;
  while (xQueueReceive(msgq, &m, 0) == pdTRUE) {
    lastClientMs = millis();
    handleLine(m.text);
  }

  // Nothing from the client for a while and keys are still down: let go, or tablet B ends up
  // with a wedged modifier and an infinite key repeat.
  if (anythingHeld() && millis() - lastClientMs > IDLE_RELEASE_MS) {
    releaseAll();
    Serial.println("watchdog: released all keys");
  }

  if (millis() - lastStatusMs > STATUS_MS) {
    lastStatusMs = millis();
    char buf[48];
    snprintf(buf, sizeof(buf), "S ble=%d batt=%d",
             bleKeyboard.isConnected() ? 1 : 0, batteryPct());
    ws.textAll(buf);
    ws.cleanupClients();
    // Only the status screen has live numbers. Redrawing a QR code twice a minute would just
    // burn cycles and make the panel flicker.
    if (screenIdx == 2) drawScreen();
  }

  if (bleKeyboard.isConnected() != lastBleState) {
    lastBleState = bleKeyboard.isConnected();
    drawScreen();
  }

  if (M5.BtnA.wasPressed()) {
    screenIdx = (screenIdx + 1) % 3;
    drawScreen();
  }

  if (M5.BtnB.isPressed()) {
    if (btnBDownMs == 0) btnBDownMs = millis();
    if (millis() - btnBDownMs > BTN_HOLD_MS) {
      btnBDownMs = 0;
      loadOrCreatePassphrase(true);
      M5.Lcd.fillScreen(BLACK);
      M5.Lcd.setCursor(4, 40);
      M5.Lcd.setTextSize(2);
      M5.Lcd.print("new passphrase\n rebooting...");
      delay(1200);
      ESP.restart();          // simplest way to re-arm the AP with new credentials
    }
  } else {
    btnBDownMs = 0;
  }
}

# Howto: build, deploy, use

## Wiring (ESP8266 NodeMCU)

| Module                  | Pin        |
|-------------------------|------------|
| WS2812 matrix 32x8 data | D6 / GPIO12|
| PIR sensor out          | D5 / GPIO14|
| Touch button (TTP223)   | D7 / GPIO13|
| OLED SSD1306 SCL/SDA    | D1 / D2    |

## Libraries

* ESPAsyncTCP, ESPAsyncWebServer
* Adafruit GFX, Adafruit SSD1306, Adafruit NeoPixel, Adafruit NeoMatrix
* LittleFS and TZ.h come with the ESP8266 core

```
~/arduino-cli core install esp8266:esp8266
~/arduino-cli lib install "Adafruit GFX Library" "Adafruit SSD1306" "Adafruit NeoPixel" "Adafruit NeoMatrix"
```

ESPAsyncTCP / ESPAsyncWebServer are not in the index, install them from git into
`~/Arduino/libraries`.

## Compile

```
~/arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 -e matrix/src/matrix
```

## Deploy

```
~/arduino-cli upload --fqbn esp8266:esp8266:nodemcuv2 -p /dev/ttyUSB0 matrix/src/matrix
```

## First run: Wi-Fi setup

1. With no credentials stored (or when the stored ones fail) the board starts an
   access point `Matrix-Setup`, password `matrix1234`. The OLED shows the AP name
   and IP (192.168.4.1).
2. Join it, open <http://192.168.4.1> (a captive portal redirect brings any
   address there), enter SSID and password, submit.
3. Credentials are written to LittleFS (`/wifi.cfg`) and the board restarts in
   client mode. A failed connection (20 s timeout) sends it back to the AP.
4. "Forget network" on the main page erases `/wifi.cfg` and restarts in AP mode.

## Behaviour

* Time is synced over NTP (`pool.ntp.org`, zone `TZ_Europe_Belgrade` in the sketch).
* Night time (22:00-07:00 by default): motion shows only the time and date in
  red, static, for 10 s.
* Day time: motion scrolls the banner with the current time and date appended,
  three passes - only while "Motion display" is toggled on, as before.
* The touch button always shows the time and date for 10 s, day or night.
* The panel fits five characters, so the static clock alternates `HH:MM` and
  `DD.MM.` every two seconds.

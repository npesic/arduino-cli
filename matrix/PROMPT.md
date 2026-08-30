# Intructions for Arduino App Matrix

The Arduino App Matrix is utilization of:

* App executes on ESP8266 Node MCU with attached modules
  * LED matrix panel
  * OLED display
  * PIR sensor
  * Touch button

# Current implementation

* existing implementation: `/src/ws-ex3/ws-ex3.ino`
* it starts the HTTP and WS (websocket) server
* it serves an HTTP page with the code that offer reading/setting up the text that will be scrolled over on the LED matrix panel

# Improvements and new feature

* implement wi-fi password manager
  * goal is to avoid hardcoding the wi-fi ssid and pass
  * instead current wi-fi mode start in AP mode with page that accepts wi-fi credentials
  * after credentials are entered saved them in local file system
  * restart with wi-fi in client mode that uses the stored credentials from file system
    * if connection fails restart back in AP mode
* starts the HTTP and WS server (as in current implementation)
* (NEW) introduce the current time and date variable and start polling of the network time server for reading/syncing local time
* change the logic for handling PIR events and touch button
  * if the current time is night time reserved for sleep
    * show only current time and date in red color with no scroll and for 10s
  * else 
    * use the current logic for scrolling text message
    * add the current time and date on the end of the scrolling text
  * touch button should always bring the time and date for 10s



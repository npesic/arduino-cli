# HIDRA - HID keyboard implementaion for esp32 over BLE

HID stands for Human Interface Device
BLE stands for Bluetooth Low Energy
esp32 is a family of low-cost, energy-efficient microcontrollers developed by Espressif Systems that integrate Wi-Fi and Bluetooth connectivity

# Objective

* Develop the arduino code (Arduino sketch file) that can execute in esp32 controller.
* Target device is M5StrickC-Plus.

# Tools

* arduino-cli that is executed in Raspberry Pi 4
* Compile example: `./arduino-cli compile --fqbn esp32:esp32:m5stick-c -e`
* Deployment example: `esptool.py --port /dev/ttyUSB0 write_flash 0x10000 MPU6886/build/esp32.esp32.m5stick-c/MPU6886.ino.bin`

# Implementation consideration

* Start with example implementation in: `src/ino/hidra/hidra.ino`
  * This example is starting BLE HID and WebSocket servers
  * It listens to the WebSocket client input that is the HTML implementation of keyboard keys. On key press the key code is sent over the WS connection
  * Incoming WS key codes are then passed to the BLE HID
* Implement similar functionality with following differences:
  * Remove the WS server and replace it with serial connection listener: the key codes are now coming in from serial connection.
  * Implement the keyboard in HTML 5 that will be executed in browser. This implementaion should use browser API to connect over serial interface to the esp32 device.
* The end result would be:
  * esp32 device that can connect on USB C port to tablet A that will run the HTML 5 implementation of the keyboard (as PWA preferably)
  * esp32 device connected over USB to tablet A will allow bluetooth paired tablet B to connect to tablet A as BLE HID keyboard
  * after table B connecting, table A can be used as regular BLE HID keyboard for tablet B

# Phased approach

* start with laying out detail plan and fisability checking

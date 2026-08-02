# Howto: Build, deploy, etc.

## Compile
```
~/arduino-cli compile --fqbn esp32:esp32:m5stick-c -e
```

## Deploy
```
esptool.py --port /dev/ttyUSB0 write_flash 0x10000 build/esp32.esp32.m5stick-c/hidra.ino.bin
```

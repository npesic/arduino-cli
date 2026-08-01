# Results

Base:
```
secure context (HTTPS)	YES
navigator.bluetooth (Web Bluetooth)	YES
navigator.usb (WebUSB)	YES
navigator.serial (Web Serial)	YES
navigator.hid (WebHID)	NO
service worker (PWA offline)	YES
userAgent	Mozilla/5.0 (Linux; Android 9; KFTRWI) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.7204.244 Safari/537.36

```

BLE:
```
—
userAgent: Mozilla/5.0 (Linux; Android 9; KFTRWI) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.7204.244 Safari/537.36
BT error: NotFoundError User cancelled the requestDevice() chooser.
USB error: NotFoundError Failed to execute 'requestDevice' on 'USB': No device selected.
Serial error: NotFoundError Failed to execute 'requestPort' on 'Serial': No port selected by the user.
USB picked: Hades2001 M5stack vid=0x403 pid=0x6001
USB opened, configuration: 1
  iface 0 class=255 sub=255 proto=255
  iface 0 CLAIMED
Serial picked: {"bluetoothServiceClassId":"00001101-0000-1000-8000-00805f9b34fb"}
Serial error: NetworkError Failed to execute 'open' on 'SerialPort': Failed to open serial port.
BT picked: ESP32-WS-BLE uyoacirrCO+tS6XX+Gagew==
BT GATT connected: true
```

USB:
```
—
userAgent: Mozilla/5.0 (Linux; Android 9; KFTRWI) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.7204.244 Safari/537.36
BT error: NotFoundError User cancelled the requestDevice() chooser.
USB error: NotFoundError Failed to execute 'requestDevice' on 'USB': No device selected.
Serial error: NotFoundError Failed to execute 'requestPort' on 'Serial': No port selected by the user.
USB picked: Hades2001 M5stack vid=0x403 pid=0x6001
USB opened, configuration: 1
  iface 0 class=255 sub=255 proto=255
  iface 0 CLAIMED
```

Serial:
```
—
userAgent: Mozilla/5.0 (Linux; Android 9; KFTRWI) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.7204.244 Safari/537.36
BT error: NotFoundError User cancelled the requestDevice() chooser.
USB error: NotFoundError Failed to execute 'requestDevice' on 'USB': No device selected.
Serial error: NotFoundError Failed to execute 'requestPort' on 'Serial': No port selected by the user.
USB picked: Hades2001 M5stack vid=0x403 pid=0x6001
USB opened, configuration: 1
  iface 0 class=255 sub=255 proto=255
  iface 0 CLAIMED
Serial picked: {"bluetoothServiceClassId":"00001101-0000-1000-8000-00805f9b34fb"}
Serial error: NetworkError Failed to execute 'open' on 'SerialPort': Failed to open serial port.
```

# Specs
```
IC type :WS2812B IC Built-in
Color order : G R B（NOT RGB）
Gray level: 256
View angle: 120°
Input voltage:DC5V Do not use DC12V or DC24V
FPCB: Flexible
Color: full color 24-bit
FPCB board color: Black
Power:0.1W~0.3W/LED Total 25W~75W (The value will change depending on the effect.)
Recommended power supply：DC5V10A(50w) or DC5V20A (100W)
Pixel Qty: 32pixels x 8 pixels Total 256 Pixels
Operating Temperature: -20 ~ +50°C
Length xWidthx Height：32cmx8cmx0.2cm
Waterproof level: IP30 non-waterproof
When you light up 1 color（red or green or blue） , 0.1W/LED . If you light up 2 colors (red+green) ,0.2W/LED , when you light up 3 colors (red+green+blue=white light), 0.3W/LED
Note: All white light, power is 75W, wires generate a lot of heat, Do not recommended to light all white light, it will reduce the LED life and it will be very harsh
```

# Wiring
- 5V (with brightness set to 4 on scale 0-255 can be taken from esp8266 board VIN)
- GND
- DIN (can connect to esp8266 digital pin directly)

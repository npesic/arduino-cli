# Robodancer

Arduino, python and PWA apps to allow dron (arduino with motor hat and two motors to power wheels + pizero with pan-tilt hat and cam) to be controlled from PWA app with gamepad API and bluetooth game pad controller to move around dron and stream video from the cam.

# Review Existing Code

* Example cam streamer: `py/src/streamer.py`
* Example py code server for pan-tilt: `py/src/server.py` and `py/src/robo.py`
* Example py code for firmata API for motor hat: `py/src/firmata/Motor.py`
* Example HTML and JS code for gamepad API: `web/joy/index.html`

# Review implementation instructions and develop a plan first

* The python server code should unite pan-tilt API, arduino firmata API (for wheel motors control) and cam streaming. Server should expose the HTTP API similar to one existing now
* PWA app should use the HTTP API python server exposing and use the gamepad API to:
  * Left analog stick
    * split the speed difference assigned between the left and right wheel based on the left right angle of the stick: middle stick position - equal speed for left and right, stick full left position - left full assigned speed, right speed 0, stick full right - left speed 0
    * assign the absolute speed value based upon the up/down angle of the stick: middle stick position - 0 speed, full up - max speed forward, full down - max speed backward
  * digital arrows
    * left arrow: circle spin left - left wheel spins backwards and right spins forwards
    * right arrow: circle spin right - left wheel spins forwards and right spins backwards
    * up arrow: forward spin - left wheel spins forwards and right spins forwards
    * down arrow: backward spin - left wheel spins backward and right spins backward
  * Right analog stick
    * Controls pan-tilt positioning for the cam

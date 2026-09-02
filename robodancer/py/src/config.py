import socket

class config:

    sqlite_file = "../../abcd.robo.py.db"
    ip = "0.0.0.0"
    callsign = "green 1"

    def __init__ (self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        self.ip = s.getsockname()[0]
        s.close()
        print(self.ip)
        print(self.ip.split('.'))
        self.setCallsign()

    def setCallsign (self):
        ipnum = self.ip.split('.')
        d = int(ipnum[3])
        prefix = 'Yellow '
        if d > 50 and d < 150:
            prefix = 'Green '
        elif d >= 150:
            prefix = 'Robo '
        
        pos = 1
        dstr = ipnum[3]
        suf = dstr[0]
        while pos < len(dstr):
            suf = suf + '-' + dstr[pos]
            pos = pos + 1
        cs = prefix + suf
        print (cs)
        self.callsign = cs
            



# ---------------------------------------------------------------------------
# Wheel drive tuning (L293D shift-register shield, motors M3 + M4).
#
# Calibrated on the hardware and confirmed with dirtest.py:
#   byte 192 (M3 bit7 + M4 bit6) = forward
#   byte  33 (M3 bit5 + M4 bit0) = backward
#   byte 129 (M3 bit7 + M4 bit0) = spin right
#   byte  96 (M3 bit5 + M4 bit6) = spin left
# Re-run caltest.py if the shield, wiring or motors change.
# ---------------------------------------------------------------------------

SERIAL_PORT = '/dev/ttyUSB0'

# Shift-register (74HC595) control pins.
PIN_LATCH_DATA  = 'd:8:o'
PIN_LATCH_CLOCK = 'd:4:o'
PIN_LATCH_LATCH = 'd:12:o'
PIN_ENABLE      = 'd:7:o'   # active LOW: write(0) enables the drivers

# Motor PWM pins. M34.py drives motor 3 on d:6 and motor 4 on d:5.
PIN_PWM_M3 = 'd:6:p'
PIN_PWM_M4 = 'd:5:p'

# Which physical motor is the left wheel: 3 or 4.
LEFT_MOTOR = 3

# Control-byte bits, per motor, for forward and reverse.
M3_BIT_FORWARD = 7
M3_BIT_REVERSE = 5
M4_BIT_FORWARD = 6
M4_BIT_REVERSE = 0

# Set True if a wheel spins the wrong way once LEFT_MOTOR is correct.
INVERT_LEFT  = False
INVERT_RIGHT = False

# Delay between shift-register clock edges. 0.001 is what M34.py used and is
# known to work; lower it only if direction changes feel laggy.
LATCH_BIT_DELAY = 0.001

# Speed shaping. Below DEADZONE the motors are cut entirely; at and above it
# the magnitude is remapped onto [MIN_DUTY, MAX_DUTY], because brushed motors
# just buzz and heat up below MIN_DUTY instead of turning.
DEADZONE = 0.08
MIN_DUTY = 0.50
MAX_DUTY = 1.0

# Motors stop if no command arrives within this many seconds.
DEADMAN_TIMEOUT = 0.4


# ---------------------------------------------------------------------------
# Pan-tilt tuning (PCA9685 servo driver).
#
# Channel assignment matches robo.py and angle-test.py.
# ---------------------------------------------------------------------------

CH_PAN  = 1        # left/right
CH_TILT = 0        # up/down

PAN_CENTER  = 90
TILT_CENTER = 90

# Travel limits. robo.py's macros stayed inside 20..160; going further risks
# the servo hitting its mechanical stop and stalling.
PAN_MIN,  PAN_MAX  = 20, 160
TILT_MIN, TILT_MAX = 20, 160

# Set True if the right stick moves the camera the wrong way.
INVERT_PAN  = False
INVERT_TILT = False

# Right-stick sensitivity, in degrees per second at full deflection.
PAN_RATE  = 70.0
TILT_RATE = 50.0

# Stick magnitude below which the camera holds still.
PANTILT_DEADZONE = 0.12

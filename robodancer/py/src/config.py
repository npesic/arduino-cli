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
# The direction bits and the left/right assignment below are GUESSES carried
# over from firmata/M34.py. Run caltest.py on the hardware and replace them
# with what it prints.
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

# Control-byte bits, per motor, for forward and reverse. From M34.py.
M3_BIT_FORWARD = 5
M3_BIT_REVERSE = 7
M4_BIT_FORWARD = 0
M4_BIT_REVERSE = 6

# Set True if a wheel spins the wrong way once LEFT_MOTOR is correct.
INVERT_LEFT  = False
INVERT_RIGHT = False

# Delay between shift-register clock edges. 0.001 is what M34.py used and is
# known to work; lower it only if direction changes feel laggy.
LATCH_BIT_DELAY = 0.001

# Speed shaping. Below DEADZONE the motors are cut entirely; at and above it
# the magnitude is remapped onto [MIN_DUTY, MAX_DUTY], because brushed motors
# just buzz and heat up below roughly 0.3 duty instead of turning.
DEADZONE = 0.08
MIN_DUTY = 0.35
MAX_DUTY = 1.0

# Motors stop if no command arrives within this many seconds.
DEADMAN_TIMEOUT = 0.4

#!/usr/bin/python3
"""Two-wheel drive over an L293D shift-register motor shield via Firmata.

Direction for each motor is a bit in a control byte shifted out to the
shield's 74HC595; speed is a PWM pin. Shifting the byte out costs eight
Firmata round-trips plus LATCH_BIT_DELAY per bit, so the latched byte is
cached and only re-sent when a direction actually flips. Driving in a
straight line at varying speed re-latches zero times.

pyfirmata is imported lazily so the speed/direction math can be imported and
tested on a machine with no Arduino attached (see --selftest).
"""

import logging
import threading
import time

import config

log = logging.getLogger(__name__)


def clamp(value, low, high):
    return max(low, min(high, value))


class Wheels:
    def __init__(self, board=None, port=None):
        """If `board` is given it is reused (and not closed by this class),
        otherwise a connection is opened to `port`."""
        self._lock = threading.RLock()
        self._latched = None
        self._board = board
        self._owns_board = board is None
        self._port = port or config.SERIAL_PORT
        self._connected = False
        self._pins = {}

    # -- hardware -----------------------------------------------------------

    def connect(self):
        import pyfirmata

        with self._lock:
            if self._connected:
                return self
            if self._board is None:
                log.info('Connecting to Arduino on %s', self._port)
                self._board = pyfirmata.Arduino(self._port)
                it = pyfirmata.util.Iterator(self._board)
                it.start()
                # The board resets when the serial port opens; Firmata is not
                # ready to accept pin config until its boot completes.
                time.sleep(2)

            g = self._board.get_pin
            self._pins = {
                'data':   g(config.PIN_LATCH_DATA),
                'clock':  g(config.PIN_LATCH_CLOCK),
                'latch':  g(config.PIN_LATCH_LATCH),
                'enable': g(config.PIN_ENABLE),
                'pwm3':   g(config.PIN_PWM_M3),
                'pwm4':   g(config.PIN_PWM_M4),
            }
            self._pins['enable'].write(0)   # active low: 0 enables the drivers
            self._pins['pwm3'].write(0)
            self._pins['pwm4'].write(0)
            self._connected = True
            log.info('Wheels ready (left motor = M%d)', config.LEFT_MOTOR)
            return self

    def _write_latch(self, data_byte):
        """Shift `data_byte` MSB-first into the 74HC595."""
        p = self._pins
        p['latch'].write(0)
        for i in range(7, -1, -1):
            p['clock'].write(0)
            p['data'].write((data_byte >> i) & 1)
            p['clock'].write(1)
            time.sleep(config.LATCH_BIT_DELAY)
        p['latch'].write(1)

    # -- math (no hardware needed) ------------------------------------------

    @staticmethod
    def dir_byte(m3_forward, m4_forward):
        """Control byte placing each motor in forward or reverse."""
        byte = 0
        byte |= 1 << (config.M3_BIT_FORWARD if m3_forward else config.M3_BIT_REVERSE)
        byte |= 1 << (config.M4_BIT_FORWARD if m4_forward else config.M4_BIT_REVERSE)
        return byte

    @staticmethod
    def duty(magnitude):
        """Map a 0..1 stick magnitude onto the usable PWM range.

        Below DEADZONE the motor is cut; at DEADZONE it jumps straight to
        MIN_DUTY, since anything less makes the motor buzz without turning.
        """
        magnitude = clamp(abs(magnitude), 0.0, 1.0)
        if magnitude < config.DEADZONE:
            return 0.0
        span = 1.0 - config.DEADZONE
        if span <= 0:
            return config.MAX_DUTY
        scaled = (magnitude - config.DEADZONE) / span
        return config.MIN_DUTY + (config.MAX_DUTY - config.MIN_DUTY) * scaled

    @staticmethod
    def to_motors(left, right):
        """Left/right wheel speeds -> (m3_speed, m4_speed), applying the
        LEFT_MOTOR assignment and the per-side inversions."""
        if config.INVERT_LEFT:
            left = -left
        if config.INVERT_RIGHT:
            right = -right
        if config.LEFT_MOTOR == 3:
            return left, right
        return right, left

    # -- driving ------------------------------------------------------------

    def set(self, left, right):
        """Drive the wheels. `left` and `right` are -1.0..1.0, sign = direction."""
        m3, m4 = self.to_motors(clamp(left, -1.0, 1.0), clamp(right, -1.0, 1.0))
        with self._lock:
            if not self._connected:
                raise RuntimeError('Wheels.connect() not called')
            byte = self.dir_byte(m3 >= 0, m4 >= 0)
            if byte != self._latched:
                self._write_latch(byte)
                self._latched = byte
            self._pins['pwm3'].write(self.duty(m3))
            self._pins['pwm4'].write(self.duty(m4))

    def raw(self, m3_forward, m4_forward, pwm3, pwm4):
        """Direct control for calibration: explicit direction bits and raw PWM.

        Bypasses duty(), to_motors() and the INVERT_* flags, because caltest.py
        exists to work out what those should be.
        """
        with self._lock:
            if not self._connected:
                raise RuntimeError('Wheels.connect() not called')
            byte = self.dir_byte(m3_forward, m4_forward)
            if byte != self._latched:
                self._write_latch(byte)
                self._latched = byte
            self._pins['pwm3'].write(clamp(pwm3, 0.0, 1.0))
            self._pins['pwm4'].write(clamp(pwm4, 0.0, 1.0))

    def stop(self):
        with self._lock:
            if not self._connected:
                return
            self._pins['pwm3'].write(0)
            self._pins['pwm4'].write(0)

    def close(self):
        with self._lock:
            if not self._connected:
                return
            try:
                self.stop()
                self._pins['enable'].write(1)   # disable the drivers
            finally:
                self._connected = False
                if self._owns_board and self._board is not None:
                    self._board.exit()
                    self._board = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc):
        self.close()


def _selftest():
    """Exercise the math with no hardware attached."""
    ok = True

    def check(label, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        print('%-42s %-22s %s' % (label, got, 'ok' if good else 'FAIL want %s' % (want,)))

    print('-- dir_byte (M3 fwd bit %d/rev %d, M4 fwd bit %d/rev %d)' % (
        config.M3_BIT_FORWARD, config.M3_BIT_REVERSE,
        config.M4_BIT_FORWARD, config.M4_BIT_REVERSE))
    check('both forward', bin(Wheels.dir_byte(True, True)),
          bin((1 << config.M3_BIT_FORWARD) | (1 << config.M4_BIT_FORWARD)))
    check('both reverse', bin(Wheels.dir_byte(False, False)),
          bin((1 << config.M3_BIT_REVERSE) | (1 << config.M4_BIT_REVERSE)))
    check('spin (m3 fwd, m4 rev)', bin(Wheels.dir_byte(True, False)),
          bin((1 << config.M3_BIT_FORWARD) | (1 << config.M4_BIT_REVERSE)))

    print('-- duty (deadzone %.2f, range %.2f..%.2f)' % (
        config.DEADZONE, config.MIN_DUTY, config.MAX_DUTY))
    check('0.0 -> cut', Wheels.duty(0.0), 0.0)
    check('below deadzone -> cut', Wheels.duty(config.DEADZONE / 2), 0.0)
    check('at deadzone -> MIN_DUTY', round(Wheels.duty(config.DEADZONE), 6), config.MIN_DUTY)
    check('1.0 -> MAX_DUTY', round(Wheels.duty(1.0), 6), config.MAX_DUTY)
    check('negative uses magnitude', Wheels.duty(-1.0), Wheels.duty(1.0))
    mid = Wheels.duty(0.5)
    check('0.5 inside range', config.MIN_DUTY < mid < config.MAX_DUTY, True)
    check('monotonic', Wheels.duty(0.3) < Wheels.duty(0.6) < Wheels.duty(0.9), True)

    print('-- to_motors (LEFT_MOTOR = M%d)' % config.LEFT_MOTOR)
    check('left/right -> m3/m4', Wheels.to_motors(0.4, -0.8),
          (0.4, -0.8) if config.LEFT_MOTOR == 3 else (-0.8, 0.4))

    print('\n%s' % ('ALL PASS' if ok else 'FAILURES ABOVE'))
    return 0 if ok else 1


if __name__ == '__main__':
    import sys
    if '--selftest' in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
    print('Run with --selftest to check the math without hardware.')

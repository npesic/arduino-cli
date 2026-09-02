#!/usr/bin/python3
"""Applies control commands to the hardware, and stops the drone when they stop.

Sits between transports (WebSocket, HTTP) and the drivers, so the deadman
timer covers every command source rather than being a property of one of them.

The deadman is the point: a wheeled robot that keeps its last throttle setting
after the link drops keeps going until it hits something. If no command has
arrived within DEADMAN_TIMEOUT the wheels are cut.
"""

import logging
import threading
import time

import config
import mixing

log = logging.getLogger(__name__)

# A stalled link then a late message would otherwise integrate one huge camera
# step; cap the slice any single message can advance the pan-tilt by.
MAX_DT = 0.25


class Pilot:
    def __init__(self, wheels=None, pantilt=None, timeout=None):
        self.wheels = wheels
        self.pantilt = pantilt
        self.timeout = config.DEADMAN_TIMEOUT if timeout is None else timeout

        self._lock = threading.Lock()
        self._last_command = None      # monotonic time, None = idle
        self._last_gamepad = None
        self._moving = False
        self._speeds = (0.0, 0.0)
        self._watchdog = None
        self._running = False
        self.deadman_trips = 0

    # -- lifecycle ----------------------------------------------------------

    def start(self):
        self._running = True
        self._watchdog = threading.Thread(target=self._watch, name='deadman',
                                          daemon=True)
        self._watchdog.start()
        return self

    def close(self):
        self._running = False
        if self._watchdog is not None:
            self._watchdog.join(timeout=2.0)
            self._watchdog = None
        self.stop('shutdown')

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()

    # -- commands -----------------------------------------------------------

    def drive(self, left, right):
        """Set wheel speeds and refresh the deadman."""
        left = mixing.clamp(float(left), -1.0, 1.0)
        right = mixing.clamp(float(right), -1.0, 1.0)
        with self._lock:
            self._last_command = time.monotonic()
            self._speeds = (left, right)
            moving = left != 0.0 or right != 0.0
            self._moving = moving
            if self.wheels is not None:
                self.wheels.set(left, right)
        return left, right

    def gamepad(self, axes, buttons, now=None):
        """Apply one gamepad sample: wheels from the left stick or d-pad,
        camera from the right stick."""
        now = time.monotonic() if now is None else now
        axes = list(axes or [])
        buttons = list(buttons or [])

        with self._lock:
            previous = self._last_gamepad
            self._last_gamepad = now
        dt = MAX_DT if previous is None else min(now - previous, MAX_DT)

        left, right = mixing.mix(axes, buttons)
        self.drive(left, right)

        if self.pantilt is not None and dt > 0:
            axis_pan, axis_tilt = mixing.look(axes)
            self.pantilt.nudge(axis_pan, axis_tilt, dt)
        return left, right

    def stop(self, reason='stop'):
        with self._lock:
            was_moving = self._moving
            self._moving = False
            self._speeds = (0.0, 0.0)
            self._last_command = None
            if self.wheels is not None:
                self.wheels.stop()
        if was_moving:
            log.info('Wheels stopped (%s)', reason)
        return was_moving

    # -- deadman ------------------------------------------------------------

    def _watch(self):
        interval = max(0.02, self.timeout / 4.0)
        while self._running:
            time.sleep(interval)
            with self._lock:
                last = self._last_command
                moving = self._moving
            if moving and last is not None and time.monotonic() - last > self.timeout:
                self.deadman_trips += 1
                log.warning('Deadman: no command for %.2fs', self.timeout)
                self.stop('deadman')

    @property
    def state(self):
        with self._lock:
            speeds = self._speeds
            moving = self._moving
        pan = tilt = None
        if self.pantilt is not None:
            pan, tilt = self.pantilt.position
        return {
            'left': speeds[0], 'right': speeds[1], 'moving': moving,
            'pan': pan, 'tilt': tilt,
            'deadman_trips': self.deadman_trips,
        }


class _FakeWheels:
    def __init__(self):
        self.calls = []
        self.stops = 0

    def set(self, left, right):
        self.calls.append((round(left, 3), round(right, 3)))

    def stop(self):
        self.stops += 1


class _FakePanTilt:
    def __init__(self):
        self.nudges = []
        self.macros = []
        self._pos = (70.0, 50.0)

    def macro(self, name):
        self.macros.append(name)
        return True

    def nudge(self, pan, tilt, dt):
        self.nudges.append((pan, tilt, round(dt, 3)))
        return self._pos

    @property
    def position(self):
        return self._pos


def _selftest():
    ok = True

    def check(label, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        print('%-50s %-16s %s' % (label, got, 'ok' if good else 'FAIL want %s' % (want,)))

    print('-- drive')
    w = _FakeWheels()
    p = Pilot(wheels=w, pantilt=_FakePanTilt(), timeout=0.2)
    check('drive passes speeds through', p.drive(0.5, -0.5), (0.5, -0.5))
    check('wheels received them', w.calls[-1], (0.5, -0.5))
    check('out-of-range clamped', p.drive(9.0, -9.0), (1.0, -1.0))
    check('moving flag set', p.state['moving'], True)
    check('stop cuts the wheels', p.stop(), True)
    check('stop is idempotent', p.stop(), False)

    print('-- gamepad')
    w = _FakeWheels()
    pt = _FakePanTilt()
    p = Pilot(wheels=w, pantilt=pt, timeout=0.2)
    p.gamepad([0.0, -1.0, 0.0, 0.0], [], now=1.0)
    check('full forward stick drives both wheels', w.calls[-1], (1.0, 1.0))
    p.gamepad([0.0, 0.0, 0.0, 0.0], [config.BTN_LEFT], now=1.1)
    check('d-pad left spins', w.calls[-1],
          (-config.SPIN_SPEED, config.SPIN_SPEED))
    check('dt measured between samples', pt.nudges[-1][2], 0.1)
    p.gamepad([0.0, 0.0, 1.0, 0.0], [], now=99.0)
    check('long gap clamps dt to MAX_DT', pt.nudges[-1][2], MAX_DT)
    check('right stick reaches pan-tilt', pt.nudges[-1][0], 1.0)

    print('-- deadman (timeout 0.2s)')
    w = _FakeWheels()
    p = Pilot(wheels=w, timeout=0.2).start()
    try:
        p.drive(1.0, 1.0)
        time.sleep(0.1)
        check('still driving before timeout', p.state['moving'], True)
        time.sleep(0.45)
        check('deadman stopped the wheels', p.state['moving'], False)
        check('deadman tripped once', p.deadman_trips, 1)
        before = w.stops
        time.sleep(0.3)
        check('does not re-trip while idle', w.stops, before)
        p.drive(1.0, 1.0)
        check('driving resumes after a new command', p.state['moving'], True)
    finally:
        p.close()
    check('close stops the wheels', p.state['moving'], False)

    print('\n%s' % ('ALL PASS' if ok else 'FAILURES ABOVE'))
    return 0 if ok else 1


if __name__ == '__main__':
    import sys
    if '--selftest' in sys.argv:
        logging.basicConfig(level=logging.WARNING, format='  %(levelname)s: %(message)s')
        sys.exit(_selftest())
    print(__doc__)
    print('Run with --selftest to exercise mixing, dt clamping and the deadman.')

#!/usr/bin/python3
"""Pan-tilt camera head on a PCA9685.

Replaces robo.py's blocking macros. Two changes matter:

  * Macros are generators of (channel, angle, delay) steps run on a worker
    thread, so `search` no longer blocks an HTTP handler for five seconds and
    can be cancelled between any two steps.
  * Position is a setpoint the caller moves, so the right stick can drive the
    head continuously via nudge() instead of replaying canned sequences.

Any manual move cancels a running macro -- the operator wins.

PCA9685 is imported lazily so the geometry can be tested without an I2C bus
(see --selftest).
"""

import logging
import threading
import time

import config

log = logging.getLogger(__name__)


def clamp(value, low, high):
    return max(low, min(high, value))


class PanTilt:
    def __init__(self, pwm=None):
        self._lock = threading.RLock()      # guards the I2C bus
        self._pwm = pwm
        self._connected = pwm is not None
        self._pan = float(config.PAN_CENTER)
        self._tilt = float(config.TILT_CENTER)

        self._cancel = threading.Event()
        self._pending = None                # one-slot macro queue
        self._pending_cv = threading.Condition()
        self._worker = None
        self._running = False

    # -- hardware -----------------------------------------------------------

    def connect(self):
        with self._lock:
            if not self._connected:
                from PCA9685 import PCA9685
                log.info('Opening PCA9685')
                self._pwm = PCA9685()
                self._pwm.setPWMFreq(50)
                self._connected = True
            self._apply(config.CH_PAN, self._pan)
            self._apply(config.CH_TILT, self._tilt)

        self._running = True
        self._worker = threading.Thread(target=self._run, name='pantilt',
                                        daemon=True)
        self._worker.start()
        return self

    def _apply(self, channel, angle):
        """Write one servo angle. Caller holds the lock."""
        self._pwm.setRotationAngle(channel, int(round(angle)))

    # -- geometry (no hardware needed) --------------------------------------

    @staticmethod
    def limits():
        return ((config.PAN_MIN, config.PAN_MAX),
                (config.TILT_MIN, config.TILT_MAX))

    @staticmethod
    def clamp_pan(angle):
        return clamp(angle, config.PAN_MIN, config.PAN_MAX)

    @staticmethod
    def clamp_tilt(angle):
        return clamp(angle, config.TILT_MIN, config.TILT_MAX)

    @staticmethod
    def step(pan, tilt, axis_pan, axis_tilt, dt):
        """Integrate stick deflection into new pan/tilt angles.

        The stick is a velocity control, not a position: letting go holds the
        current aim instead of snapping back to centre.

        Sign convention, which the caller must honour: positive `axis_pan`
        aims the camera RIGHT, positive `axis_tilt` aims it UP. Whether that
        means a rising or falling servo angle is hardware-dependent -- run
        `pantilt.py --check` and set INVERT_PAN / INVERT_TILT accordingly.
        """
        def rate(axis, deg_per_sec, invert):
            if abs(axis) < config.PANTILT_DEADZONE:
                return 0.0
            if invert:
                axis = -axis
            return axis * deg_per_sec * dt

        pan = PanTilt.clamp_pan(pan + rate(axis_pan, config.PAN_RATE,
                                           config.INVERT_PAN))
        tilt = PanTilt.clamp_tilt(tilt + rate(axis_tilt, config.TILT_RATE,
                                              config.INVERT_TILT))
        return pan, tilt

    # -- manual control -----------------------------------------------------

    @property
    def position(self):
        with self._lock:
            return self._pan, self._tilt

    def set(self, pan=None, tilt=None, cancel_macro=True):
        """Move to absolute angles. Values outside the limits are clamped."""
        if cancel_macro:
            self._cancel.set()
        with self._lock:
            if pan is not None:
                self._pan = self.clamp_pan(float(pan))
                self._apply(config.CH_PAN, self._pan)
            if tilt is not None:
                self._tilt = self.clamp_tilt(float(tilt))
                self._apply(config.CH_TILT, self._tilt)
            return self._pan, self._tilt

    def nudge(self, axis_pan, axis_tilt, dt):
        """Advance the setpoint from right-stick axes. Returns the new position,
        and writes nothing if the stick is inside the deadzone."""
        with self._lock:
            pan, tilt = self.step(self._pan, self._tilt, axis_pan, axis_tilt, dt)
            if pan == self._pan and tilt == self._tilt:
                return self._pan, self._tilt
        return self.set(pan, tilt)

    def center(self):
        return self.set(config.PAN_CENTER, config.TILT_CENTER)

    # -- macros -------------------------------------------------------------

    def _sweep(self, channel, start, stop, step, delay=0.05):
        for angle in range(start, stop, step):
            yield (channel, angle, delay)

    def _m_center(self):
        yield (config.CH_PAN, config.PAN_CENTER, 0)
        yield (config.CH_TILT, config.TILT_CENTER, 0)

    def _m_node_no(self):
        for item in self._m_center():
            yield item
        for item in self._sweep(config.CH_PAN, 90, 60, -3):
            yield item
        for item in self._sweep(config.CH_PAN, 60, 120, 3):
            yield item
        for item in self._sweep(config.CH_PAN, 120, 90, -3):
            yield item

    def _m_node_yes(self):
        for item in self._m_center():
            yield item
        for item in self._sweep(config.CH_TILT, 90, 60, -3):
            yield item
        for item in self._sweep(config.CH_TILT, 60, 120, 3):
            yield item
        for item in self._sweep(config.CH_TILT, 120, 90, -3):
            yield item

    def _m_head_up(self):
        for item in self._m_center():
            yield item
        for item in self._sweep(config.CH_TILT, 90, 20, -3):
            yield item

    def _m_head_down(self):
        for item in self._m_center():
            yield item
        for item in self._sweep(config.CH_TILT, 90, 160, 3):
            yield item

    def _m_roll_eyes(self):
        for item in self._m_center():
            yield item
        for angle in range(90, 20, -3):
            yield (config.CH_PAN, angle, 0)
            yield (config.CH_TILT, 180 - angle, 0.05)
        # robo.py had range(160, 20, 3) here, which is empty and silently
        # skipped this phase; the step has to be negative to count down.
        for item in self._sweep(config.CH_TILT, 160, 20, -3):
            yield item
        for item in self._sweep(config.CH_PAN, 20, 160, 3):
            yield item
        for angle in range(160, 90, -3):
            yield (config.CH_PAN, angle, 0)
            yield (config.CH_TILT, angle, 0.05)

    def _m_search(self):
        corners = [(90, 90), (40, 90), (40, 40), (90, 40), (130, 40),
                   (130, 90), (130, 130), (90, 130), (90, 90), (40, 90),
                   (90, 90)]
        for pan, tilt in corners:
            yield (config.CH_PAN, pan, 0)
            yield (config.CH_TILT, tilt, 0.5)

    MACROS = {
        'center':    '_m_center',
        'node_no':   '_m_node_no',
        'node_yes':  '_m_node_yes',
        'head_up':   '_m_head_up',
        'head_down': '_m_head_down',
        'roll_eyes': '_m_roll_eyes',
        'search':    '_m_search',
    }

    def macro(self, name):
        """Queue a macro, replacing any running or pending one. Returns False
        if the name is unknown."""
        if name not in self.MACROS:
            return False
        self._cancel.set()
        with self._pending_cv:
            self._pending = name
            self._pending_cv.notify()
        return True

    def cancel(self):
        self._cancel.set()

    def _run(self):
        while self._running:
            with self._pending_cv:
                while self._running and self._pending is None:
                    self._pending_cv.wait(0.25)
                name = self._pending
                self._pending = None
            if not self._running or name is None:
                continue

            self._cancel.clear()
            log.info('Running macro %s', name)
            try:
                for channel, angle, delay in getattr(self, self.MACROS[name])():
                    if self._cancel.is_set() or self._pending is not None:
                        log.info('Macro %s cancelled', name)
                        break
                    with self._lock:
                        if channel == config.CH_PAN:
                            self._pan = self.clamp_pan(angle)
                            self._apply(channel, self._pan)
                        else:
                            self._tilt = self.clamp_tilt(angle)
                            self._apply(channel, self._tilt)
                    if delay:
                        time.sleep(delay)
            except Exception:
                log.exception('Macro %s failed', name)

    # -- back-compat with robo.py -------------------------------------------

    def dispatch(self, path, params):
        """Handle a /robo/<name> path the way robo.dispatch() did, plus
        /robo/pantilt?pan=&tilt= for absolute positioning."""
        name = path.split('?')[0].rstrip('/').rsplit('/', 1)[-1]
        if name == 'pantilt':
            pan = params.get('pan', [None])[0]
            tilt = params.get('tilt', [None])[0]
            self.set(pan if pan is None else float(pan),
                     tilt if tilt is None else float(tilt))
            return True
        return self.macro(name)

    # -- lifecycle ----------------------------------------------------------

    def close(self):
        self._running = False
        self._cancel.set()
        with self._pending_cv:
            self._pending = None
            self._pending_cv.notify()
        if self._worker is not None:
            self._worker.join(timeout=2.0)
            self._worker = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc):
        self.close()


def _selftest():
    ok = True

    def check(label, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        print('%-44s %-20s %s' % (label, got, 'ok' if good else 'FAIL want %s' % (want,)))

    print('-- clamping (pan %d..%d, tilt %d..%d)' % (
        config.PAN_MIN, config.PAN_MAX, config.TILT_MIN, config.TILT_MAX))
    check('pan below min', PanTilt.clamp_pan(-30), config.PAN_MIN)
    check('pan above max', PanTilt.clamp_pan(999), config.PAN_MAX)
    check('tilt in range', PanTilt.clamp_tilt(90), 90)

    print('-- stick integration (pan %.0f deg/s, deadzone %.2f)' % (
        config.PAN_RATE, config.PANTILT_DEADZONE))
    check('deadzone holds still', PanTilt.step(90, 90, 0.05, 0.0, 1.0), (90, 90))
    pan, _ = PanTilt.step(90, 90, 1.0, 0.0, 1.0)
    check('full deflection for 1s', round(pan - 90, 1), round(config.PAN_RATE, 1))
    pan, _ = PanTilt.step(90, 90, -1.0, 0.0, 10.0)
    check('long push clamps at min', pan, config.PAN_MIN)
    _, tilt = PanTilt.step(90, 90, 0.0, 1.0, 10.0)
    check('tilt clamps at max', tilt, config.TILT_MAX)

    print('-- macros')
    pt = PanTilt(pwm=object())
    for name in sorted(PanTilt.MACROS):
        steps = list(getattr(pt, PanTilt.MACROS[name])())
        in_range = all(
            (config.PAN_MIN <= a <= config.PAN_MAX) if c == config.CH_PAN
            else (config.TILT_MIN <= a <= config.TILT_MAX)
            for c, a, _ in steps)
        check('%s: non-empty and within limits' % name,
              (len(steps) > 0, in_range), (True, True))
    check('unknown macro rejected', pt.macro('nope'), False)

    rolled = list(pt._m_roll_eyes())
    tilt_down = [a for c, a, _ in rolled if c == config.CH_TILT]
    check('roll_eyes descending phase present',
          any(x > y for x, y in zip(tilt_down, tilt_down[1:])), True)

    print('\n%s' % ('ALL PASS' if ok else 'FAILURES ABOVE'))
    return 0 if ok else 1


def _ask(prompt, valid):
    options = '/'.join(valid)
    while True:
        try:
            answer = input('%s [%s] ' % (prompt, options)).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            raise SystemExit('Aborted.')
        if answer in valid:
            return answer
        print('  answer one of: %s' % options)


def _check():
    """On-hardware check: servo directions, and proof the macros do not block."""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    print('Pan-tilt check. The camera head will move through its full travel.')
    print('Make sure nothing is in its way.\n')
    if _ask('Ready?', ['y', 'n']) != 'y':
        return 1

    offset = 40
    with PanTilt() as pt:
        print('\nCentring...')
        pt.center()
        time.sleep(1.0)

        print('Increasing PAN angle by %d degrees.' % offset)
        pt.set(pan=config.PAN_CENTER + offset)
        time.sleep(1.0)
        invert_pan = _ask('Camera is now aimed which way?', ['r', 'l']) == 'l'

        pt.center()
        time.sleep(1.0)
        print('Increasing TILT angle by %d degrees.' % offset)
        pt.set(tilt=config.TILT_CENTER + offset)
        time.sleep(1.0)
        invert_tilt = _ask('Camera is now aimed which way?', ['u', 'd']) == 'd'

        pt.center()
        time.sleep(1.0)

        # The whole point of the refactor: queuing a macro must return at once.
        print('\nQueuing the `search` macro (robo.py blocked ~5.5s here)...')
        started = time.time()
        pt.macro('search')
        queued = time.time() - started
        print('  macro() returned in %.1f ms' % (queued * 1000))
        print('  ...letting it run for 2s, then interrupting with a manual move.')
        time.sleep(2.0)
        pt.set(pan=config.PAN_CENTER, tilt=config.TILT_CENTER)
        time.sleep(1.0)
        moved = pt.position
        print('  position after interrupt: pan=%.0f tilt=%.0f' % moved)

    print('\n' + '=' * 62)
    print('Paste into config.py:')
    print('=' * 62)
    print('INVERT_PAN  = %s' % invert_pan)
    print('INVERT_TILT = %s' % invert_tilt)
    print('=' * 62)
    if queued > 0.05:
        print('WARNING: macro() took %.0f ms -- it should be near-instant.' % (queued * 1000))
    if moved != (float(config.PAN_CENTER), float(config.TILT_CENTER)):
        print('WARNING: manual move did not win over the running macro.')
    return 0


if __name__ == '__main__':
    import sys
    if '--selftest' in sys.argv:
        sys.exit(_selftest())
    if '--check' in sys.argv:
        sys.exit(_check())
    print(__doc__)
    print('  --selftest   geometry checks, no hardware needed')
    print('  --check      servo direction + non-blocking check, on the Pi')

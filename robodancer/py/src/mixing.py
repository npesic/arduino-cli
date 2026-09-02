#!/usr/bin/python3
"""Gamepad -> wheel speeds. Pure functions, no hardware, no I/O.

Implements the control scheme from PROMPT.md:

  left stick   up/down    sets the speed magnitude, forward and backward
               left/right splits that speed between the wheels
  d-pad        up/down    both wheels the same way
               left/right counter-rotating spin

The d-pad wins when anything on it is pressed, because a digital spin request
is unambiguous and should not fight a stick resting slightly off-centre.
"""

import config


def clamp(value, low, high):
    return max(low, min(high, value))


def stick_mix(axis_x, axis_y):
    """Left stick -> (left, right), each -1..1.

    PROMPT.md: centre is equal speed; full left is "left full assigned speed,
    right zero"; full right is the mirror. Note that this rotates the drone
    the opposite way to most conventions -- see INVERT_STEERING.
    """
    # Gamepad Y is negative upward, and up means forward.
    speed = -axis_y
    if abs(speed) < config.DRIVE_DEADZONE:
        return 0.0, 0.0

    x = clamp(axis_x, -1.0, 1.0)
    if abs(x) < config.DRIVE_DEADZONE:
        x = 0.0
    if config.INVERT_STEERING:
        x = -x

    left = speed * (1.0 if x <= 0 else 1.0 - x)
    right = speed * (1.0 if x >= 0 else 1.0 + x)
    return clamp(left, -1.0, 1.0), clamp(right, -1.0, 1.0)


def dpad_mix(pressed, speed=None):
    """D-pad button indices -> (left, right), or None if nothing is pressed."""
    speed = config.SPIN_SPEED if speed is None else speed
    pressed = set(pressed)
    up = config.BTN_UP in pressed
    down = config.BTN_DOWN in pressed
    left = config.BTN_LEFT in pressed
    right = config.BTN_RIGHT in pressed

    # Opposing presses cancel rather than picking a winner arbitrarily.
    if up and down:
        up = down = False
    if left and right:
        left = right = False

    if left:
        return -speed, speed        # spin left: left back, right forward
    if right:
        return speed, -speed        # spin right: left forward, right back
    if up:
        return speed, speed
    if down:
        return -speed, -speed
    return None


def mix(axes, buttons):
    """Full gamepad state -> (left, right). `buttons` is a list of pressed
    button indices; `axes` is the raw axis array."""
    spin = dpad_mix(buttons)
    if spin is not None:
        return spin
    if len(axes) <= max(config.AXIS_LX, config.AXIS_LY):
        return 0.0, 0.0
    return stick_mix(axes[config.AXIS_LX], axes[config.AXIS_LY])


def look(axes):
    """Right stick -> (axis_pan, axis_tilt) in PanTilt's sign convention:
    positive pan aims right, positive tilt aims up."""
    if len(axes) <= max(config.AXIS_RX, config.AXIS_RY):
        return 0.0, 0.0
    # Gamepad Y is negative upward; PanTilt wants positive = up.
    return axes[config.AXIS_RX], -axes[config.AXIS_RY]


def _selftest():
    ok = True

    def check(label, got, want):
        nonlocal ok
        if isinstance(got, tuple) and isinstance(want, tuple):
            good = all(abs(g - w) < 1e-9 for g, w in zip(got, want)) and len(got) == len(want)
            got = tuple(round(v, 3) for v in got)
        else:
            good = got == want
        ok = ok and good
        print('%-48s %-18s %s' % (label, got, 'ok' if good else 'FAIL want %s' % (want,)))

    F = -1.0   # full forward on a gamepad Y axis
    print('-- left stick, per PROMPT.md (deadzone %.2f)' % config.DRIVE_DEADZONE)
    check('centred -> stopped', stick_mix(0.0, 0.0), (0.0, 0.0))
    check('full up, centred -> equal speed', stick_mix(0.0, F), (1.0, 1.0))
    check('full up, full left -> left full, right zero',
          stick_mix(-1.0, F), (1.0, 0.0))
    check('full up, full right -> left zero, right full',
          stick_mix(1.0, F), (0.0, 1.0))
    check('full down -> both reversed', stick_mix(0.0, 1.0), (-1.0, -1.0))
    check('half up -> half speed both', stick_mix(0.0, -0.5), (0.5, 0.5))
    check('half right -> right keeps speed, left halved',
          stick_mix(0.5, F), (0.5, 1.0))
    check('y inside deadzone -> stopped', stick_mix(1.0, -0.05), (0.0, 0.0))
    check('x inside deadzone -> straight', stick_mix(0.05, F), (1.0, 1.0))
    check('reverse steers the same way', stick_mix(-1.0, 1.0), (-1.0, 0.0))

    print('-- d-pad (spin speed %.2f)' % config.SPIN_SPEED)
    s = config.SPIN_SPEED
    check('nothing pressed -> None', dpad_mix([]), None)
    check('up -> both forward', dpad_mix([config.BTN_UP]), (s, s))
    check('down -> both back', dpad_mix([config.BTN_DOWN]), (-s, -s))
    check('left -> left back, right fwd', dpad_mix([config.BTN_LEFT]), (-s, s))
    check('right -> left fwd, right back', dpad_mix([config.BTN_RIGHT]), (s, -s))
    check('left+right cancel', dpad_mix([config.BTN_LEFT, config.BTN_RIGHT]), None)
    check('up+down cancel', dpad_mix([config.BTN_UP, config.BTN_DOWN]), None)

    print('-- combined')
    axes = [0.0, F, 0.0, 0.0]
    check('stick used when d-pad idle', mix(axes, []), (1.0, 1.0))
    check('d-pad overrides the stick', mix(axes, [config.BTN_LEFT]), (-s, s))
    check('short axis array is safe', mix([], []), (0.0, 0.0))

    print('-- right stick -> pan/tilt convention')
    check('push right -> positive pan', look([0, 0, 1.0, 0])[0], 1.0)
    check('push up -> positive tilt', look([0, 0, 0, -1.0])[1], 1.0)
    check('short axis array is safe', look([0, 0]), (0.0, 0.0))

    print('\n%s' % ('ALL PASS' if ok else 'FAILURES ABOVE'))
    return 0 if ok else 1


if __name__ == '__main__':
    import sys
    if '--selftest' in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
    print('Run with --selftest to check the mixing.')

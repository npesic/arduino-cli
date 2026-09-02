#!/usr/bin/python3
"""Interactive calibration for the wheel drive.

Works out the four things wheels.py cannot know from the code alone:

  * which physical motor (M3 or M4) is the left wheel
  * which control-byte bit means "forward" for each motor
  * the lowest PWM duty that actually turns the wheels

Prints a config.py block at the end. Nothing is written automatically.

    python3 caltest.py                      # guided wizard
    python3 caltest.py --motor 3 --rev --duty 0.6 --secs 2   # single pulse

*** PUT THE DRONE ON A STAND. The wheels will spin. ***
"""

import argparse
import logging
import sys
import time

import config
from wheels import Wheels

PULSE = 1.5          # seconds each test pulse runs
RAMP = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60, 0.70, 0.85, 1.00]


def ask(prompt, valid):
    """Prompt until the answer is one of `valid`; 'q' aborts."""
    options = '/'.join(valid)
    while True:
        try:
            answer = input('%s [%s] (q=quit) ' % (prompt, options)).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            raise SystemExit('Aborted.')
        if answer == 'q':
            raise SystemExit('Aborted.')
        if answer in valid:
            return answer
        print('  please answer one of: %s' % options)


def pulse(w, motor, forward, duty, secs=PULSE):
    """Run one motor for `secs`, leaving the other stopped."""
    m3 = duty if motor == 3 else 0.0
    m4 = duty if motor == 4 else 0.0
    # The idle motor's direction bit is irrelevant at zero PWM.
    w.raw(forward if motor == 3 else True,
          forward if motor == 4 else True, m3, m4)
    time.sleep(secs)
    w.stop()
    time.sleep(0.3)


def find_left_motor(w, duty):
    print('\n=== Step 1/3: which motor is the left wheel? ===')
    print('Running M3 alone.')
    input('Press Enter to pulse M3... ')
    pulse(w, 3, True, duty)
    side = ask('Which wheel turned?', ['l', 'r', 'n'])
    if side == 'n':
        print('\nNo movement. Raise --duty (currently %.2f) and rerun, or check' % duty)
        print('wiring, the enable pin, and that motor power is actually connected.')
        raise SystemExit(1)
    left_motor = 3 if side == 'l' else 4
    print('  -> LEFT_MOTOR = %d' % left_motor)
    return left_motor


def find_directions(w, duty):
    print('\n=== Step 2/3: which bit is forward? ===')
    result = {}
    for motor in (3, 4):
        print('\nRunning M%d with the FORWARD bit set.' % motor)
        input('Press Enter to pulse M%d... ' % motor)
        pulse(w, motor, True, duty)
        got = ask('Did that wheel drive the drone forward or backward?', ['f', 'b'])
        result[motor] = (got == 'f')
        print('  -> M%d forward bit is %s' % (
            motor, 'correct' if result[motor] else 'INVERTED'))
    return result


def find_min_duty(w, left_motor):
    print('\n=== Step 3/3: minimum duty that turns the wheels ===')
    print('Both motors will run at rising duty. Say yes at the first step where')
    print('BOTH wheels turn steadily (not just buzz or stutter).')
    for duty in RAMP:
        input('\nPress Enter to try duty %.2f... ' % duty)
        w.raw(True, True, duty, duty)
        time.sleep(PULSE)
        w.stop()
        time.sleep(0.3)
        if ask('  Did both wheels turn steadily at %.2f?' % duty, ['y', 'n']) == 'y':
            print('  -> MIN_DUTY = %.2f' % duty)
            return duty
    print('\nNothing turned steadily even at full duty. Check the battery voltage')
    print('and the motor wiring before going further.')
    raise SystemExit(1)


def report(left_motor, directions, min_duty):
    # A wheel that ran backward is corrected by swapping that motor's bits,
    # which keeps INVERT_* free for later per-side tweaks.
    m3_fwd, m3_rev = config.M3_BIT_FORWARD, config.M3_BIT_REVERSE
    m4_fwd, m4_rev = config.M4_BIT_FORWARD, config.M4_BIT_REVERSE
    if not directions[3]:
        m3_fwd, m3_rev = m3_rev, m3_fwd
    if not directions[4]:
        m4_fwd, m4_rev = m4_rev, m4_fwd

    print('\n' + '=' * 66)
    print('Paste this into config.py, replacing the matching lines:')
    print('=' * 66)
    print('LEFT_MOTOR = %d' % left_motor)
    print()
    print('M3_BIT_FORWARD = %d' % m3_fwd)
    print('M3_BIT_REVERSE = %d' % m3_rev)
    print('M4_BIT_FORWARD = %d' % m4_fwd)
    print('M4_BIT_REVERSE = %d' % m4_rev)
    print()
    print('MIN_DUTY = %.2f' % min_duty)
    print('=' * 66)
    changed = []
    if left_motor != config.LEFT_MOTOR:
        changed.append('LEFT_MOTOR %d -> %d' % (config.LEFT_MOTOR, left_motor))
    if not directions[3]:
        changed.append('M3 direction bits swapped')
    if not directions[4]:
        changed.append('M4 direction bits swapped')
    if abs(min_duty - config.MIN_DUTY) > 1e-9:
        changed.append('MIN_DUTY %.2f -> %.2f' % (config.MIN_DUTY, min_duty))
    print('Changes from current config: %s' % (', '.join(changed) if changed
                                               else 'none, config was already correct'))


def wizard(w, duty):
    left_motor = find_left_motor(w, duty)
    directions = find_directions(w, duty)
    min_duty = find_min_duty(w, left_motor)
    report(left_motor, directions, min_duty)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--motor', type=int, choices=(3, 4),
                    help='single-pulse mode: which motor to run')
    ap.add_argument('--rev', action='store_true', help='single-pulse mode: reverse bit')
    ap.add_argument('--duty', type=float, default=0.7,
                    help='PWM duty for pulses (default 0.7)')
    ap.add_argument('--secs', type=float, default=PULSE,
                    help='single-pulse duration (default %.1f)' % PULSE)
    ap.add_argument('--port', default=None, help='serial port (default %s)' % config.SERIAL_PORT)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    print(__doc__)
    if ask('Wheels are off the ground and free to spin?', ['y', 'n']) != 'y':
        raise SystemExit('Put it on a stand first.')

    with Wheels(port=args.port) as w:
        try:
            if args.motor:
                print('Pulsing M%d %s at duty %.2f for %.1fs' % (
                    args.motor, 'reverse' if args.rev else 'forward',
                    args.duty, args.secs))
                pulse(w, args.motor, not args.rev, args.duty, args.secs)
            else:
                wizard(w, args.duty)
        finally:
            w.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/python3
"""Ground-truth direction test: prints the exact control byte behind every
movement, so an observation can be tied to a byte rather than to an assumption.

Also prints which config.py is actually loaded and its checksum, because a
stale copy on the Pi looks exactly like a driver bug.

    python3 dirtest.py            # all four direction combos
    python3 dirtest.py --duty 0.9

*** WHEELS OFF THE GROUND ***
"""

import argparse
import hashlib
import os
import sys
import time

import config
import wheels
from wheels import Wheels


def provenance():
    print('=' * 66)
    print('CONFIG ACTUALLY LOADED')
    print('=' * 66)
    for module in (config, wheels):
        path = os.path.abspath(module.__file__)
        digest = hashlib.sha256(open(path, 'rb').read()).hexdigest()[:12]
        print('  %-10s %s' % (module.__name__, path))
        print('  %-10s sha256:%s  mtime:%s' % (
            '', digest,
            time.strftime('%Y-%m-%d %H:%M:%S',
                          time.localtime(os.path.getmtime(path)))))
    print()
    print('  LEFT_MOTOR     = %d' % config.LEFT_MOTOR)
    print('  M3 fwd/rev bit = %d/%d' % (config.M3_BIT_FORWARD, config.M3_BIT_REVERSE))
    print('  M4 fwd/rev bit = %d/%d' % (config.M4_BIT_FORWARD, config.M4_BIT_REVERSE))
    print('  INVERT L/R     = %s/%s' % (config.INVERT_LEFT, config.INVERT_RIGHT))
    print('  DEADZONE       = %.2f    MIN_DUTY = %.2f' % (config.DEADZONE, config.MIN_DUTY))
    print('=' * 66)


CASES = [
    ('both motors FORWARD bit',  True,  True),
    ('both motors REVERSE bit',  False, False),
    ('M3 forward, M4 reverse',   True,  False),
    ('M3 reverse, M4 forward',   False, True),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--duty', type=float, default=0.8)
    ap.add_argument('--secs', type=float, default=1.5)
    ap.add_argument('--port', default=None)
    args = ap.parse_args()

    provenance()
    print(__doc__)
    if input('Wheels off the ground? [y/N] ').strip().lower() != 'y':
        return 1

    observed = []
    with Wheels(port=args.port) as w:
        try:
            for label, m3_fwd, m4_fwd in CASES:
                byte = Wheels.dir_byte(m3_fwd, m4_fwd)
                print('\n--- %s' % label)
                print('    control byte = %d (0b%08d)' % (byte, int(bin(byte)[2:])))
                input('    Press Enter to run... ')
                # Force a re-latch every time so no cached state can hide a
                # byte that never reached the shift register.
                w._latched = None
                w.raw_byte(byte, args.duty, args.duty)
                time.sleep(args.secs)
                w.stop()
                time.sleep(0.4)
                got = input('    What happened? (f=forward b=backward '
                            'l=spin left r=spin right n=nothing) ').strip().lower()
                observed.append((label, byte, got))
        finally:
            w.stop()

    print('\n' + '=' * 66)
    print('%-26s %-8s %s' % ('CASE', 'BYTE', 'OBSERVED'))
    print('=' * 66)
    for label, byte, got in observed:
        print('%-26s %-8d %s' % (label, byte, got))
    print('=' * 66)
    print('Send this table back. If the two single-direction cases show the')
    print('same result, the latch is not reaching the shield at all.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

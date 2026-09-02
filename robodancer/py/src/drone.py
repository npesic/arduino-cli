#!/usr/bin/python3
"""Robodancer entry point: camera, pan-tilt and the HTTPS server in one process.

    python3 drone.py                 # everything
    python3 drone.py --no-camera     # control only, useful when debugging
    python3 drone.py --no-tls        # plain HTTP; the gamepad API will NOT work

Ctrl-C shuts down in reverse order so the camera is released and the servo
worker is joined rather than killed mid-move.
"""

import argparse
import logging
import signal
import socket
import sys
import threading

import config
import httpsrv

log = logging.getLogger('drone')


def local_ip():
    """Best-effort LAN address, for printing a reachable URL."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except OSError:
        return '127.0.0.1'
    finally:
        s.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', type=int, default=config.HTTP_PORT)
    ap.add_argument('--no-camera', action='store_true')
    ap.add_argument('--no-pantilt', action='store_true')
    ap.add_argument('--no-tls', action='store_true',
                    help='serve plain HTTP (gamepad API will not work)')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s %(levelname)-7s %(name)s: %(message)s')

    camera = None
    pantilt = None
    httpd = None
    shutdown = threading.Event()

    try:
        if not args.no_pantilt:
            from pantilt import PanTilt
            pantilt = PanTilt().connect()
            log.info('Pan-tilt centred at %s', pantilt.position)

        if not args.no_camera:
            from camera import Camera
            camera = Camera().start()

        httpd = httpsrv.create(camera=camera, pantilt=pantilt,
                               port=args.port, tls=not args.no_tls)

        scheme = 'http' if args.no_tls else 'https'
        log.info('Serving on %s://%s:%d/', scheme, local_ip(), args.port)
        log.info('  stream: %s://%s:%d/stream.mjpg', scheme, local_ip(), args.port)
        log.info('  status: %s://%s:%d/api/status', scheme, local_ip(), args.port)
        if args.no_tls:
            log.warning('TLS disabled -- the Gamepad API needs a secure context')

        def on_signal(signum, frame):
            log.info('Signal %d, shutting down', signum)
            shutdown.set()
            threading.Thread(target=httpd.shutdown, daemon=True).start()

        signal.signal(signal.SIGINT, on_signal)
        signal.signal(signal.SIGTERM, on_signal)

        httpd.serve_forever()

    except KeyboardInterrupt:
        log.info('Interrupted')
    finally:
        log.info('Cleaning up')
        if httpd is not None:
            httpd.server_close()
        if camera is not None:
            camera.stop()
        if pantilt is not None:
            pantilt.close()
        log.info('Stopped')
    return 0


if __name__ == '__main__':
    sys.exit(main())

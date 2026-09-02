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
    ap.add_argument('--no-wheels', action='store_true')
    ap.add_argument('--no-ws', action='store_true',
                    help='skip the WebSocket server (no live driving)')
    ap.add_argument('--no-tls', action='store_true',
                    help='serve plain HTTP (gamepad API will not work)')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s %(levelname)-7s %(name)s: %(message)s')

    camera = None
    pantilt = None
    wheels = None
    pilot = None
    wssrv = None
    httpd = None
    shutdown = threading.Event()

    try:
        if not args.no_pantilt:
            from pantilt import PanTilt
            pantilt = PanTilt().connect()
            log.info('Pan-tilt centred at %s', pantilt.position)

        if not args.no_wheels:
            from wheels import Wheels
            wheels = Wheels().connect()

        # The pilot owns the deadman, so it starts with the wheels rather than
        # with any particular transport.
        from pilot import Pilot
        pilot = Pilot(wheels=wheels, pantilt=pantilt).start()
        log.info('Deadman armed at %.2fs', pilot.timeout)

        if not args.no_camera:
            from camera import Camera
            camera = Camera().start()

        if not args.no_ws:
            from wssrv import WSServer
            ws_ssl = None if args.no_tls else httpsrv.ssl_context()
            wssrv = WSServer(pilot, ssl_ctx=ws_ssl).start()

        httpd = httpsrv.create(camera=camera, pantilt=pantilt, pilot=pilot,
                               port=args.port, tls=not args.no_tls)

        scheme = 'http' if args.no_tls else 'https'
        log.info('Serving on %s://%s:%d/', scheme, local_ip(), args.port)
        log.info('  stream: %s://%s:%d/stream.mjpg', scheme, local_ip(), args.port)
        log.info('  status: %s://%s:%d/api/status', scheme, local_ip(), args.port)
        if not args.no_ws:
            log.info('  driving: %s://%s:%d',
                     'ws' if args.no_tls else 'wss', local_ip(), config.WS_PORT)
        if args.no_tls:
            log.warning('TLS disabled -- the Gamepad API needs a secure context')
        if wheels is None:
            log.warning('Wheels disabled -- drive commands will be accepted '
                        'and ignored')

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
        # Reverse order, wheels first: whatever else fails on the way down,
        # the drone should not still be driving.
        log.info('Cleaning up')
        if pilot is not None:
            pilot.stop('shutdown')
        if wssrv is not None:
            wssrv.stop()
        if httpd is not None:
            httpd.server_close()
        if camera is not None:
            camera.stop()
        if pilot is not None:
            pilot.close()
        if wheels is not None:
            wheels.close()
        if pantilt is not None:
            pantilt.close()
        log.info('Stopped')
    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/python3
"""HTTPS server: PWA static files, the /robo/* control API, and the MJPEG stream.

Threaded, because the MJPEG response never returns -- a single-threaded server
would be permanently occupied by the first viewer.

TLS is mandatory rather than decorative: the Gamepad API is gated on a secure
context, and a page served over HTTPS cannot fetch an HTTP API without being
blocked as mixed content. Run gencert.sh once to create the certificate.
"""

import json
import logging
import mimetypes
import os
import posixpath
import socketserver
import ssl
from http import server
from urllib.parse import urlparse, parse_qs, unquote

import config

log = logging.getLogger(__name__)

BOUNDARY = b'FRAME'


class Handler(server.BaseHTTPRequestHandler):
    server_version = 'robodancer/1.0'
    protocol_version = 'HTTP/1.1'

    # -- helpers ------------------------------------------------------------

    def end_headers(self):
        # Matches server.py's behaviour so existing clients keep working.
        self.send_header('Access-Control-Allow-Origin', '*')
        server.BaseHTTPRequestHandler.end_headers(self)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def log_message(self, fmt, *args):
        log.info('%s %s', self.address_string(), fmt % args)

    def _json(self, obj, status=200):
        body = json.dumps(obj, indent=2).encode('utf8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- routes -------------------------------------------------------------

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        try:
            if path == '/stream.mjpg':
                self._stream()
            elif path == '/api/status':
                self._status()
            elif path.startswith('/robo/'):
                self._robo(path, params)
            else:
                self._static(path)
        except (BrokenPipeError, ConnectionResetError):
            log.info('Client %s went away', self.client_address)
        except Exception:
            log.exception('Error handling %s', self.path)
            try:
                self.send_error(500, 'Internal error')
            except Exception:
                pass

    def _status(self):
        cam = self.server.camera
        pt = self.server.pantilt
        pilot = self.server.pilot
        self._json({
            'ok': True,
            'camera': None if cam is None else {
                'resolution': config.CAM_RESOLUTION,
                'framerate': config.CAM_FRAMERATE,
                'failed': cam.failure is not None,
            },
            'pantilt': None if pt is None else {
                'pan': pt.position[0], 'tilt': pt.position[1]},
            'macros': [] if pt is None else sorted(pt.MACROS),
            'drive': None if pilot is None else pilot.state,
            'ws_port': config.WS_PORT,
            # Served rather than duplicated in JS, so the browser and the
            # drone can never disagree about deadzones or button indices.
            'tuning': {
                'drive_deadzone': config.DRIVE_DEADZONE,
                'spin_speed': config.SPIN_SPEED,
                'invert_steering': config.INVERT_STEERING,
                'pantilt_deadzone': config.PANTILT_DEADZONE,
                'deadman_timeout': config.DEADMAN_TIMEOUT,
                'axes': {'lx': config.AXIS_LX, 'ly': config.AXIS_LY,
                         'rx': config.AXIS_RX, 'ry': config.AXIS_RY},
                'buttons': {'up': config.BTN_UP, 'down': config.BTN_DOWN,
                            'left': config.BTN_LEFT, 'right': config.BTN_RIGHT},
            },
        })

    def _robo(self, path, params):
        name = path.rstrip('/').rsplit('/', 1)[-1]
        # An emergency stop must not depend on the WebSocket being healthy.
        if name == 'stop':
            if self.server.pilot is None:
                self._json({'ok': False, 'error': 'drive not running'}, 503)
            else:
                self.server.pilot.stop('http request')
                self._json({'ok': True, 'path': path, 'stopped': True})
            return
        if name == 'drive':
            if self.server.pilot is None:
                self._json({'ok': False, 'error': 'drive not running'}, 503)
                return
            left = float(params.get('left', [0])[0])
            right = float(params.get('right', [0])[0])
            self.server.pilot.drive(left, right)
            self._json({'ok': True, 'path': path, 'left': left, 'right': right})
            return
        if self.server.pantilt is None:
            self._json({'ok': False, 'error': 'pantilt not running'}, 503)
            return
        handled = self.server.pantilt.dispatch(path, params)
        if not handled:
            self._json({'ok': False, 'path': path, 'error': 'unknown command'}, 404)
            return
        pan, tilt = self.server.pantilt.position
        self._json({'ok': True, 'path': path, 'pan': pan, 'tilt': tilt})

    def _stream(self):
        camera = self.server.camera
        if camera is None:
            self._json({'ok': False, 'error': 'camera not running'}, 503)
            return
        self.send_response(200)
        self.send_header('Age', '0')
        self.send_header('Cache-Control', 'no-cache, private')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Content-Type',
                         'multipart/x-mixed-replace; boundary=%s'
                         % BOUNDARY.decode())
        self.end_headers()
        try:
            for frame in camera.frames():
                self.wfile.write(b'--' + BOUNDARY + b'\r\n')
                self.wfile.write(b'Content-Type: image/jpeg\r\n')
                self.wfile.write(b'Content-Length: %d\r\n\r\n' % len(frame))
                self.wfile.write(frame)
                self.wfile.write(b'\r\n')
        except (BrokenPipeError, ConnectionResetError):
            log.info('Stream client %s disconnected', self.client_address)
        finally:
            self.close_connection = True

    def _resolve(self, path):
        """Map a URL path to a file under WEB_ROOT, or None if it escapes."""
        path = unquote(urlparse(path).path)
        path = posixpath.normpath(path)
        parts = [p for p in path.split('/') if p and p not in ('.', '..')]
        target = os.path.join(config.WEB_ROOT, *parts)
        target = os.path.abspath(target)
        root = os.path.abspath(config.WEB_ROOT)
        if target != root and not target.startswith(root + os.sep):
            return None
        # Directory requests get index.html. Decided from the URL rather than
        # os.path.isdir so it behaves the same before the files exist.
        if not parts or path.endswith('/') or os.path.isdir(target):
            target = os.path.join(target, 'index.html')
        return target

    def _static(self, path):
        target = self._resolve(path)
        if target is None:
            self.send_error(403, 'Forbidden')
            return
        if not os.path.isfile(target):
            self.send_error(404, 'Not found: %s' % path)
            return
        ctype, _ = mimetypes.guess_type(target)
        with open(target, 'rb') as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header('Content-Type', ctype or 'application/octet-stream')
        self.send_header('Content-Length', str(len(body)))
        # The PWA is edited constantly during bring-up; caching just confuses.
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(body)


class DroneHTTPServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, camera=None, pantilt=None, pilot=None):
        super().__init__(address, Handler)
        self.camera = camera
        self.pantilt = pantilt
        self.pilot = pilot


def ssl_context(cert_file=None, key_file=None):
    cert_file = cert_file or config.CERT_FILE
    key_file = key_file or config.KEY_FILE
    for path in (cert_file, key_file):
        if not os.path.isfile(path):
            raise SystemExit(
                'Missing %s -- run ./gencert.sh first.' % path)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_file, key_file)
    return ctx


def create(camera=None, pantilt=None, pilot=None, port=None, tls=True):
    port = port or config.HTTP_PORT
    httpd = DroneHTTPServer(('', port), camera=camera, pantilt=pantilt,
                            pilot=pilot)
    if tls:
        httpd.socket = ssl_context().wrap_socket(httpd.socket, server_side=True)
    return httpd


def _selftest():
    """Path resolution only -- the traversal guard is the part worth testing."""
    ok = True

    def check(label, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        print('%-46s %-22s %s' % (label, got, 'ok' if good else 'FAIL want %s' % (want,)))

    class Fake(Handler):
        def __init__(self):
            pass

    h = Fake()
    root = os.path.abspath(config.WEB_ROOT)
    check('/ -> index.html', h._resolve('/'), os.path.join(root, 'index.html'))
    check('/app.js', h._resolve('/app.js'), os.path.join(root, 'app.js'))
    check('query string ignored', h._resolve('/app.js?v=2'),
          os.path.join(root, 'app.js'))
    check('../ escape blocked', h._resolve('/../../config.py'),
          os.path.join(root, 'config.py'))
    check('encoded ../ blocked', h._resolve('/%2e%2e/%2e%2e/config.py'),
          os.path.join(root, 'config.py'))
    check('deep escape blocked', h._resolve('/a/../../../../etc/passwd'),
          os.path.join(root, 'etc', 'passwd'))

    print('\n%s' % ('ALL PASS' if ok else 'FAILURES ABOVE'))
    return 0 if ok else 1


if __name__ == '__main__':
    import sys
    if '--selftest' in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
    print('Run via drone.py; --selftest checks static path resolution.')

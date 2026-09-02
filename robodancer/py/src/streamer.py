#!/usr/bin/python3

import io
import logging
import os
import socketserver
import threading
import picamera
from threading import Condition
from http import server

# Tuning knobs. On a Pi Zero W (armv6, 512MB) 640x480@24 is close to the
# ceiling for WiFi throughput; drop FRAMERATE to 10-15 if the stream stalls.
RESOLUTION = '640x480'
FRAMERATE = 24

# If no new frame arrives within this many seconds the camera has stalled,
# so drop the client instead of blocking its thread forever.
FRAME_TIMEOUT = 5.0

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(threadName)s: %(message)s')


class StreamingOutput:
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def write(self, buf):
        if buf.startswith(b'\xff\xd8'):
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)


class StreamingHandler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/stream.mjpg')
            self.end_headers()
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        if not output.condition.wait(timeout=FRAME_TIMEOUT):
                            logging.warning(
                                'No frame for %ss, dropping client %s',
                                FRAME_TIMEOUT, self.client_address)
                            return
                        frame = output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))
        else:
            # send_error() emits its own headers and body; calling
            # end_headers() again here corrupts the response.
            self.send_error(404)


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def watch_encoder(camera, httpd):
    """Surface exceptions raised on picamera's background encoder thread.

    picamera stores them and only re-raises on wait_recording(); without this
    a dead encoder just means the stream silently stops with no error.
    """
    try:
        while True:
            camera.wait_recording(1)
    except Exception:
        logging.exception('Encoder failed, shutting down')
        threading.Thread(target=httpd.shutdown, daemon=True).start()


with picamera.PiCamera(resolution=RESOLUTION, framerate=FRAMERATE) as camera:
    output = StreamingOutput()
    camera.start_recording(output, format='mjpeg')
    httpd = None
    try:
        address = ('', 8000)
        httpd = StreamingServer(address, StreamingHandler)
        threading.Thread(
            target=watch_encoder, args=(camera, httpd),
            name='encoder-watchdog', daemon=True).start()
        logging.info('Serving on port %d (pid %d)', address[1], os.getpid())
        httpd.serve_forever()
    except KeyboardInterrupt:
        logging.info('Interrupted')
    finally:
        if httpd is not None:
            httpd.server_close()
        camera.stop_recording()

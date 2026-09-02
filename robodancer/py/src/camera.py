#!/usr/bin/python3
"""MJPEG camera source, extracted from streamer.py.

Keeps the parts of streamer.py that earned their place: the JPEG-boundary
frame splitter, and the encoder watchdog. picamera stores exceptions raised on
its background encoder thread and only re-raises them from wait_recording(),
so without the watchdog a dead encoder looks like a stream that quietly stops.

picamera is imported lazily so this module can be imported off the Pi.
"""

import io
import logging
import threading

import config

log = logging.getLogger(__name__)


class StreamingOutput:
    """File-like sink that splits the MJPEG stream into whole frames.

    picamera writes the encoder output in arbitrary chunks; a new frame starts
    at the JPEG SOI marker (0xFFD8), which is where the previous frame is
    published to waiting clients.
    """

    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = threading.Condition()

    def write(self, buf):
        if buf.startswith(b'\xff\xd8'):
            self.buffer.truncate()
            data = self.buffer.getvalue()
            # The very first chunk carries an SOI with nothing before it;
            # streamer.py published that empty buffer as a 0-byte frame.
            if data:
                with self.condition:
                    self.frame = data
                    self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)

    def wait_frame(self, timeout=None):
        """Block until the next frame. Returns None if `timeout` elapses."""
        with self.condition:
            if not self.condition.wait(timeout=timeout):
                return None
            return self.frame


class Camera:
    def __init__(self, resolution=None, framerate=None):
        self.output = StreamingOutput()
        self._resolution = resolution or config.CAM_RESOLUTION
        self._framerate = framerate or config.CAM_FRAMERATE
        self._camera = None
        self._watchdog = None
        self._running = False
        self.failure = None

    def start(self):
        import picamera

        log.info('Starting camera %s @ %dfps', self._resolution, self._framerate)
        self._camera = picamera.PiCamera(resolution=self._resolution,
                                         framerate=self._framerate)
        self._camera.start_recording(self.output, format='mjpeg')
        self._running = True
        self._watchdog = threading.Thread(target=self._watch, name='cam-watchdog',
                                          daemon=True)
        self._watchdog.start()
        return self

    def _watch(self):
        """Surface encoder-thread exceptions; see the module docstring."""
        while self._running:
            try:
                self._camera.wait_recording(1)
            except Exception as exc:
                if self._running:
                    log.exception('Camera encoder failed')
                    self.failure = exc
                return

    def frames(self, timeout=None):
        """Yield JPEG frames until the client goes away or the camera stalls."""
        timeout = timeout or config.CAM_FRAME_TIMEOUT
        while True:
            frame = self.output.wait_frame(timeout)
            if frame is None:
                log.warning('No frame for %ss, ending stream', timeout)
                return
            yield frame

    def stop(self):
        self._running = False
        if self._camera is not None:
            try:
                self._camera.stop_recording()
            except Exception:
                log.exception('stop_recording failed')
            finally:
                self._camera.close()
                self._camera = None
        if self._watchdog is not None:
            self._watchdog.join(timeout=2.0)
            self._watchdog = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


def _selftest():
    """Exercise the frame splitter with synthetic encoder chunks."""
    ok = True

    def check(label, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        print('%-46s %-18s %s' % (label, got, 'ok' if good else 'FAIL want %s' % (want,)))

    out = StreamingOutput()
    check('no frame before any SOI', out.frame, None)

    # One whole frame, delivered in two chunks, then the start of the next.
    out.write(b'\xff\xd8aaa')
    out.write(b'bbb')
    check('frame not published mid-frame', out.frame, None)
    out.write(b'\xff\xd8ccc')
    check('previous frame published on next SOI', out.frame, b'\xff\xd8aaabbb')

    out.write(b'\xff\xd8d')
    check('frames do not accumulate', out.frame, b'\xff\xd8ccc')

    check('wait_frame times out cleanly', out.wait_frame(timeout=0.05), None)

    published = []
    def consumer():
        published.append(out.wait_frame(timeout=2.0))
    t = threading.Thread(target=consumer)
    t.start()
    import time
    time.sleep(0.1)
    out.write(b'\xff\xd8zzz')          # publishes b'\xff\xd8d'
    t.join(timeout=2.0)
    check('waiter woken by a new frame', published, [b'\xff\xd8d'])

    print('\n%s' % ('ALL PASS' if ok else 'FAILURES ABOVE'))
    return 0 if ok else 1


if __name__ == '__main__':
    import sys
    if '--selftest' in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
    print('Run with --selftest to check frame splitting without a camera.')

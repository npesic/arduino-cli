#!/usr/bin/python3
"""WebSocket transport for live driving commands.

HTTP request-per-update would mean a new request every 50ms on a single-core
armv6; a persistent socket costs a frame. It also gives the deadman a second,
faster signal: the socket closing means the operator is gone, so the wheels
stop immediately rather than after the timeout.

Runs its own asyncio loop on a background thread, since the rest of the
process is threaded and blocking.

Message format, JSON, client to server:

    {"t": "gamepad", "axes": [...], "buttons": [12, 15]}
    {"t": "drive", "left": 0.5, "right": -0.5}
    {"t": "macro", "name": "center"}
    {"t": "stop"}
    {"t": "ping"}

Server to client: {"t": "state", ...} periodically, and {"t": "pong"}.
"""

import asyncio
import json
import logging
import threading

import config

log = logging.getLogger(__name__)

try:
    import websockets
    HAVE_WEBSOCKETS = True
except ImportError:                                  # pragma: no cover
    websockets = None
    HAVE_WEBSOCKETS = False


class WSServer:
    def __init__(self, pilot, port=None, ssl_ctx=None, status_interval=0.5):
        if not HAVE_WEBSOCKETS:
            raise SystemExit(
                "The websockets package is missing. On Buster/python3.7:\n"
                "    pip3 install 'websockets==10.4'\n"
                "(newer releases dropped python 3.7)")
        self.pilot = pilot
        self.port = config.WS_PORT if port is None else port
        self.ssl_ctx = ssl_ctx
        self.status_interval = status_interval

        self._clients = set()
        self._loop = None
        self._thread = None
        self._server = None
        self._state_task = None
        self._ready = threading.Event()

    # -- lifecycle ----------------------------------------------------------

    def start(self):
        self._thread = threading.Thread(target=self._run, name='wssrv',
                                        daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=10.0):
            raise RuntimeError('WebSocket server failed to start')
        return self

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
            self._loop.run_forever()
        finally:
            self._loop.close()

    async def _serve(self):
        self._server = await websockets.serve(
            self._handler, '', self.port, ssl=self.ssl_ctx,
            ping_interval=5, ping_timeout=10)
        self._state_task = self._loop.create_task(self._broadcast_state())
        scheme = 'ws' if self.ssl_ctx is None else 'wss'
        log.info('WebSocket listening on %s://0.0.0.0:%d', scheme, self.port)
        self._ready.set()

    async def _shutdown(self):
        """Unwind inside the loop, so the close coroutines actually complete.

        Stopping the loop outright leaves websockets' own _close() task pending
        and prints 'Task was destroyed but it is pending' on the way out.
        """
        if self._state_task is not None:
            self._state_task.cancel()
            try:
                await self._state_task
            except asyncio.CancelledError:
                pass
        for ws in list(self._clients):
            try:
                await ws.close()
            except Exception:
                pass
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        self._loop.stop()

    def stop(self):
        if self._loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop).result(3.0)
        except Exception:
            # The loop stops as part of _shutdown, so the future often never
            # resolves; the join below is what actually confirms shutdown.
            pass
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    # -- connection ---------------------------------------------------------

    async def _handler(self, ws, path=None):
        peer = getattr(ws, 'remote_address', None)
        self._clients.add(ws)
        log.info('Client connected: %s (%d total)', peer, len(self._clients))
        try:
            async for raw in ws:
                await self._on_message(ws, raw)
        except Exception as exc:
            log.info('Client %s ended: %s', peer, exc)
        finally:
            self._clients.discard(ws)
            log.info('Client gone: %s (%d left)', peer, len(self._clients))
            # The socket closing is itself a deadman signal -- do not wait for
            # the timer when we already know the operator is gone.
            if not self._clients:
                self.pilot.stop('client disconnected')

    async def _on_message(self, ws, raw):
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            log.warning('Dropping unparseable message')
            return
        if not isinstance(msg, dict):
            return

        kind = msg.get('t')
        try:
            if kind == 'gamepad':
                self.pilot.gamepad(msg.get('axes') or [], msg.get('buttons') or [])
            elif kind == 'drive':
                self.pilot.drive(msg.get('left', 0.0), msg.get('right', 0.0))
            elif kind == 'stop':
                self.pilot.stop('client request')
            elif kind == 'macro':
                pt = self.pilot.pantilt
                if pt is not None:
                    pt.macro(msg.get('name', ''))
            elif kind == 'ping':
                await ws.send(json.dumps({'t': 'pong'}))
            else:
                log.warning('Unknown message type %r', kind)
        except Exception:
            log.exception('Failed to handle %r', kind)

    async def _broadcast_state(self):
        try:
            await self._broadcast_loop()
        except asyncio.CancelledError:
            pass

    async def _broadcast_loop(self):
        while True:
            await asyncio.sleep(self.status_interval)
            if not self._clients:
                continue
            payload = json.dumps(dict(self.pilot.state, t='state'))
            for ws in list(self._clients):
                try:
                    await ws.send(payload)
                except Exception:
                    self._clients.discard(ws)


def _selftest():
    """Loopback test against a real server, with a fake wheel driver."""
    import time
    from pilot import Pilot, _FakeWheels, _FakePanTilt

    ok = True

    def check(label, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        print('%-50s %-16s %s' % (label, got, 'ok' if good else 'FAIL want %s' % (want,)))

    wheels = _FakeWheels()
    pantilt = _FakePanTilt()
    # Long timeout: this test is about transport, and pilot.py already
    # covers the deadman. A short one would trip during these sleeps.
    pilot = Pilot(wheels=wheels, pantilt=pantilt, timeout=2.0).start()
    srv = WSServer(pilot, port=9401, status_interval=0.1).start()

    async def client():
        uri = 'ws://127.0.0.1:%d' % srv.port
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({'t': 'ping'}))
            pong = json.loads(await asyncio.wait_for(ws.recv(), 3))
            check('ping answered', pong.get('t'), 'pong')

            await ws.send(json.dumps({'t': 'gamepad',
                                      'axes': [0.0, -1.0, 0.0, 0.0],
                                      'buttons': []}))
            await asyncio.sleep(0.2)
            check('gamepad drove the wheels', wheels.calls[-1], (1.0, 1.0))

            await ws.send(json.dumps({'t': 'drive', 'left': -0.4, 'right': 0.4}))
            await asyncio.sleep(0.2)
            check('drive message applied', wheels.calls[-1], (-0.4, 0.4))

            await ws.send(json.dumps({'t': 'macro', 'name': 'center'}))
            await ws.send('this is not json')
            await ws.send(json.dumps({'t': 'nonsense'}))
            await asyncio.sleep(0.2)
            check('server survived junk', pilot.state['moving'], True)
            check('macro forwarded to pan-tilt', pantilt.macros, ['center'])

            deadline = time.monotonic() + 3
            state = None
            while time.monotonic() < deadline:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 3))
                if msg.get('t') == 'state':
                    state = msg
                    break
            check('state broadcast received', state is not None, True)

            await ws.send(json.dumps({'t': 'stop'}))
            await asyncio.sleep(0.2)
            check('stop message cut the wheels', pilot.state['moving'], False)

            await ws.send(json.dumps({'t': 'drive', 'left': 1.0, 'right': 1.0}))
            await asyncio.sleep(0.2)
            check('driving again before disconnect', pilot.state['moving'], True)

    try:
        asyncio.new_event_loop().run_until_complete(client())
        time.sleep(0.5)
        check('disconnect stopped the wheels', pilot.state['moving'], False)
        check('stopped by disconnect, not the timer', pilot.deadman_trips, 0)
    finally:
        srv.stop()
        pilot.close()

    print('\n%s' % ('ALL PASS' if ok else 'FAILURES ABOVE'))
    return 0 if ok else 1


if __name__ == '__main__':
    import sys
    if '--selftest' in sys.argv:
        logging.basicConfig(level=logging.WARNING, format='  %(levelname)s: %(message)s')
        sys.exit(_selftest())
    print(__doc__)
    print('Run with --selftest for a loopback test (needs the websockets package).')

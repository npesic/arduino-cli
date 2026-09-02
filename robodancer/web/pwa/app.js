// Robodancer PWA: gamepad -> WebSocket, video, HUD.

import { DEFAULT_TUNING, mix, look, readPad, changed } from './gamepad.js';

const SEND_INTERVAL = 50;    // ms; 20 Hz is well inside the deadman window
const PING_INTERVAL = 2000;
const RECONNECT_MIN = 500;
const RECONNECT_MAX = 5000;

const el = (id) => document.getElementById(id);
const ui = {
  link: el('link'), pad: el('pad'), rtt: el('rtt'),
  leftFill: el('left-fill'), rightFill: el('right-fill'),
  leftVal: el('left-val'), rightVal: el('right-val'),
  pan: el('pan'), tilt: el('tilt'), trips: el('trips'), padId: el('pad-id'),
  macros: el('macros'), estop: el('estop'), cam: el('cam'),
};

let tuning = DEFAULT_TUNING;
let wsPort = 9082;
let ws = null;
let retryDelay = RECONNECT_MIN;
let lastSent = 0;
let lastSample = null;
let lastPing = 0;
let pingSentAt = 0;

function pill(node, cls, text) {
  node.className = 'pill ' + cls;
  node.lastElementChild.textContent = text;
}

// -- wheel meters: bar grows from the centre, colour marks reverse ---------

function setMeter(fill, valNode, value) {
  const pct = Math.min(Math.abs(value), 1) * 50;
  fill.style.left = value >= 0 ? '50%' : (50 - pct) + '%';
  fill.style.width = pct + '%';
  fill.classList.toggle('rev', value < 0);
  valNode.textContent = value.toFixed(2);
}

// -- websocket -------------------------------------------------------------

function connect() {
  const url = `wss://${location.hostname}:${wsPort}`;
  pill(ui.link, 'wait', 'connecting');
  ws = new WebSocket(url);

  ws.onopen = () => {
    retryDelay = RECONNECT_MIN;
    pill(ui.link, 'on', 'linked');
  };

  ws.onclose = () => {
    pill(ui.link, 'off', 'disconnected');
    ws = null;
    // The drone stops itself when the socket drops; this just gets us back.
    setTimeout(connect, retryDelay);
    retryDelay = Math.min(retryDelay * 2, RECONNECT_MAX);
  };

  ws.onerror = () => { if (ws) ws.close(); };

  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    if (msg.t === 'pong') {
      ui.rtt.textContent = Math.round(performance.now() - pingSentAt) + ' ms';
    } else if (msg.t === 'state') {
      // Server truth wins over the local preview.
      setMeter(ui.leftFill, ui.leftVal, msg.left);
      setMeter(ui.rightFill, ui.rightVal, msg.right);
      ui.pan.textContent = msg.pan == null ? '--' : Math.round(msg.pan) + '°';
      ui.tilt.textContent = msg.tilt == null ? '--' : Math.round(msg.tilt) + '°';
      ui.trips.textContent = msg.deadman_trips;
    }
  };
}

const send = (obj) => {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
};

// -- control loop ----------------------------------------------------------

function loop() {
  const now = performance.now();
  const sample = readPad();

  if (!sample) {
    pill(ui.pad, 'off', 'no gamepad');
    ui.padId.textContent = '--';
  } else {
    pill(ui.pad, 'on', 'gamepad');
    ui.padId.textContent = sample.id.slice(0, 34);

    const [left, right] = mix(sample.axes, sample.buttons, tuning);
    const [lookX, lookY] = look(sample.axes, tuning);
    setMeter(ui.leftFill, ui.leftVal, left);
    setMeter(ui.rightFill, ui.rightVal, right);

    const moving = left !== 0 || right !== 0;
    const looking = Math.abs(lookX) > tuning.pantilt_deadzone ||
                    Math.abs(lookY) > tuning.pantilt_deadzone;
    // Resend while moving even if nothing changed, or the deadman trips on a
    // perfectly steady stick.
    if (now - lastSent >= SEND_INTERVAL &&
        (moving || looking || changed(sample, lastSample))) {
      send({ t: 'gamepad', axes: sample.axes, buttons: sample.buttons });
      lastSent = now;
      lastSample = sample;
    }
  }

  if (now - lastPing >= PING_INTERVAL) {
    lastPing = now;
    pingSentAt = now;
    send({ t: 'ping' });
  }

  requestAnimationFrame(loop);
}

// -- setup -----------------------------------------------------------------

function stop() {
  send({ t: 'stop' });
  setMeter(ui.leftFill, ui.leftVal, 0);
  setMeter(ui.rightFill, ui.rightVal, 0);
}

async function init() {
  ui.estop.addEventListener('click', stop);
  window.addEventListener('keydown', (e) => {
    if (e.code === 'Space' || e.code === 'Escape') { e.preventDefault(); stop(); }
  });
  // Losing focus means the gamepad stops being read, so stop moving too.
  window.addEventListener('blur', stop);
  window.addEventListener('gamepadconnected', (e) =>
    console.log('gamepad connected:', e.gamepad.id));

  try {
    const status = await (await fetch('/api/status')).json();
    if (status.tuning) tuning = status.tuning;
    if (status.ws_port) wsPort = status.ws_port;
    for (const name of status.macros || []) {
      const b = document.createElement('button');
      b.textContent = name;
      b.onclick = () => send({ t: 'macro', name });
      ui.macros.appendChild(b);
    }
  } catch (err) {
    console.warn('status fetch failed, using defaults', err);
  }

  ui.cam.src = '/stream.mjpg';
  connect();
  requestAnimationFrame(loop);

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(
      (e) => console.warn('sw registration failed', e));
  }
}

init();

// Phase 1 test/console page, served from flash at http://192.168.4.1/
// Deliberately minimal: it exists to exercise the §4 protocol end to end.
// The real on-screen keyboard is Phase 2 (src/web/).
#pragma once
#include <pgmspace.h>

const char INDEX_HTML[] PROGMEM = R"HTMLDOC(
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>HIDRA</title>
<style>
  :root { color-scheme: dark; }
  body { font: 15px/1.4 system-ui, sans-serif; margin: 0; padding: .6rem;
         background: #15171a; color: #e8e8e8; }
  #bar { display: flex; gap: .5rem; align-items: center; margin-bottom: .5rem; font-size: 13px; }
  .pill { padding: .15rem .5rem; border-radius: 1rem; background: #333; }
  .ok { background: #1a6b32; } .bad { background: #7a1f1f; }
  #cap { border: 2px dashed #555; border-radius: .4rem; padding: .8rem; text-align: center;
         color: #999; margin-bottom: .5rem; }
  #cap:focus { border-color: #4a9; color: #4a9; outline: none; }
  .grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: .3rem; margin-bottom: .5rem; }
  button { padding: .7rem .2rem; font-size: 14px; background: #2a2d33; color: #e8e8e8;
           border: 1px solid #3a3f47; border-radius: .3rem; }
  button:active { background: #4a9; color: #000; }
  button.on { background: #4a9; color: #000; }
  .row { display: flex; gap: .3rem; margin-bottom: .5rem; }
  input { flex: 1; padding: .6rem; background: #2a2d33; color: #e8e8e8;
          border: 1px solid #3a3f47; border-radius: .3rem; }
  #log { white-space: pre-wrap; font: 12px monospace; background: #0e1013; padding: .5rem;
         border-radius: .3rem; height: 8rem; overflow-y: auto; }
</style>
</head>
<body>

<div id="bar">
  <span class="pill" id="ws">ws…</span>
  <span class="pill" id="ble">ble?</span>
  <span class="pill" id="bat">—</span>
</div>

<div id="cap" tabindex="0">tap here, then type on a physical keyboard</div>

<div class="grid" id="keys"></div>

<div class="row">
  <input id="txt" placeholder="literal text (T command)" autocapitalize="off" autocomplete="off">
  <button id="send" style="flex:0 0 5rem">Send</button>
</div>
<div class="row">
  <button id="panic">Release all</button>
  <button id="ping">Ping</button>
</div>

<div id="log"></div>

<script>
const $ = id => document.getElementById(id);
const log = m => { const l = $('log'); l.textContent += m + '\n'; l.scrollTop = l.scrollHeight; };

// ---- HID usage table (KeyboardEvent.code -> HID usage id) ----
const U = {
  Enter:0x28, Escape:0x29, Backspace:0x2A, Tab:0x2B, Space:0x2C, Minus:0x2D, Equal:0x2E,
  BracketLeft:0x2F, BracketRight:0x30, Backslash:0x31, Semicolon:0x33, Quote:0x34,
  Backquote:0x35, Comma:0x36, Period:0x37, Slash:0x38, CapsLock:0x39,
  PrintScreen:0x46, ScrollLock:0x47, Pause:0x48, Insert:0x49, Home:0x4A, PageUp:0x4B,
  Delete:0x4C, End:0x4D, PageDown:0x4E,
  ArrowRight:0x4F, ArrowLeft:0x50, ArrowDown:0x51, ArrowUp:0x52,
  ControlLeft:0xE0, ShiftLeft:0xE1, AltLeft:0xE2, MetaLeft:0xE3,
  ControlRight:0xE4, ShiftRight:0xE5, AltRight:0xE6, MetaRight:0xE7,
};
for (let i = 0; i < 26; i++) U['Key' + String.fromCharCode(65 + i)] = 0x04 + i;
for (let i = 1; i <= 9; i++) U['Digit' + i] = 0x1D + i;
U.Digit0 = 0x27;
for (let i = 1; i <= 12; i++) U['F' + i] = 0x39 + i;

// ---- transport (Phase 3 swaps this for a GATT characteristic) ----
let sock, alive = false;
function connect() {
  sock = new WebSocket('ws://' + location.host + '/ws');
  sock.onopen = () => {
    alive = true; $('ws').textContent = 'ws up'; $('ws').className = 'pill ok';
    send('V1');
  };
  sock.onclose = () => {
    alive = false; $('ws').textContent = 'ws down'; $('ws').className = 'pill bad';
    setTimeout(connect, 1000);
  };
  sock.onmessage = e => {
    const m = e.data.trim();
    if (m.startsWith('S ')) {
      const ble = /ble=1/.test(m);
      $('ble').textContent = ble ? 'BLE paired' : 'BLE waiting';
      $('ble').className = 'pill ' + (ble ? 'ok' : 'bad');
      const b = m.match(/batt=(\d+)/);
      if (b) $('bat').textContent = b[1] + '%';
    } else { log('< ' + m); }
  };
}
function send(line) {
  if (alive) sock.send(line); else log('! dropped: ' + line);
}

// ---- key state ----
const held = new Set();
const down = u => { if (u) { held.add(u); send('D ' + u + ' 0'); } };
const up   = u => { if (u) { held.delete(u); send('U ' + u + ' 0'); } };

$('cap').addEventListener('keydown', e => {
  e.preventDefault();
  if (e.repeat) return;
  const u = U[e.code];
  if (!u) return log('? unmapped ' + e.code);
  down(u);
});
$('cap').addEventListener('keyup', e => { e.preventDefault(); up(U[e.code]); });

// ---- on-screen keys ----
const PLAIN = [['Esc','Escape'],['Tab','Tab'],['↑','ArrowUp'],['↓','ArrowDown'],
               ['←','ArrowLeft'],['→','ArrowRight'],['Enter','Enter'],['Bksp','Backspace'],
               ['Del','Delete'],['Home','Home'],['End','End'],['Space','Space']];
const STICKY = [['Ctrl','ControlLeft'],['Shift','ShiftLeft'],['Alt','AltLeft'],['Win','MetaLeft']];

for (const [label, code] of PLAIN) {
  const b = document.createElement('button');
  b.textContent = label;
  b.onpointerdown = ev => { ev.preventDefault(); down(U[code]); };
  b.onpointerup = b.onpointerleave = () => up(U[code]);
  $('keys').append(b);
}
for (const [label, code] of STICKY) {   // latching, so Ctrl+C is possible on a touchscreen
  const b = document.createElement('button');
  b.textContent = label;
  b.onclick = () => {
    const u = U[code];
    if (held.has(u)) { up(u); b.classList.remove('on'); }
    else { down(u); b.classList.add('on'); }
  };
  $('keys').append(b);
}

$('send').onclick = () => {
  const v = $('txt').value;
  if (v) { send('T ' + v); $('txt').value = ''; }
};
$('txt').addEventListener('keydown', e => { if (e.key === 'Enter') $('send').click(); });
$('panic').onclick = () => {
  held.clear(); send('R');
  document.querySelectorAll('button.on').forEach(b => b.classList.remove('on'));
};
$('ping').onclick = () => send('P');

// keep the watchdog fed while the page is open but idle
setInterval(() => { if (alive) send('P'); }, 1500);

connect();
$('cap').focus();
</script>
</body>
</html>
)HTMLDOC";

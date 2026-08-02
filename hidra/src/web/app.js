// HIDRA keyboard — Phase 2.
// Sends explicit key down/up so tablet B does its own shifting, its own key repeat, and sees
// real held modifiers. Nothing here interprets characters.

(() => {
  const { U, MODIFIERS, FN_ROW, MAIN_ROWS } = HIDRA_KEYMAP;
  const $ = (id) => document.getElementById(id);

  const link = new WebSocketTransport('ws://' + location.host + '/ws');

  // ---------------------------------------------------------------- key state
  const held = new Set();          // usage ids currently down
  // Modifier latch state per code: 0 = off, 1 = one-shot (armed), 2 = locked.
  // Tapping cycles off -> one-shot -> locked -> off, the pattern every touch keyboard uses.
  const latch = new Map();
  const buttons = new Map();       // code -> element

  const OFF = 0, ONESHOT = 1, LOCKED = 2;

  function down(code) {
    const u = U[code];
    if (!u || held.has(u)) return;
    held.add(u);
    link.send('D ' + u + ' 0');
    paint(code, true);
  }

  function up(code) {
    const u = U[code];
    if (!u || !held.has(u)) return;
    held.delete(u);
    link.send('U ' + u + ' 0');
    paint(code, false);
  }

  function paint(code, isDown) {
    const el = buttons.get(code);
    if (el) el.classList.toggle('down', isDown);
  }

  function setLatch(code, state) {
    latch.set(code, state);
    const el = buttons.get(code);
    if (el) {
      el.classList.toggle('armed', state === ONESHOT);
      el.classList.toggle('locked', state === LOCKED);
    }
    if (state === OFF) up(code); else down(code);
    reflectShift();
  }

  function cycleLatch(code) {
    const s = latch.get(code) || OFF;
    setLatch(code, s === OFF ? ONESHOT : s === ONESHOT ? LOCKED : OFF);
  }

  // After a normal key is released, drop any one-shot modifiers — that is what makes a single
  // Shift tap capitalise exactly one letter.
  function consumeOneShots() {
    for (const [code, state] of latch) {
      if (state === ONESHOT) setLatch(code, OFF);
    }
  }

  function reflectShift() {
    const shifted = ['ShiftLeft', 'ShiftRight'].some((c) => (latch.get(c) || OFF) !== OFF)
                 || held.has(U.ShiftLeft) || held.has(U.ShiftRight);
    document.body.classList.toggle('shifted', shifted);
  }

  function releaseAll() {
    held.clear();
    latch.clear();
    link.send('R');
    document.querySelectorAll('.key').forEach((el) => {
      el.classList.remove('down', 'armed', 'locked');
    });
    reflectShift();
  }

  // ---------------------------------------------------------------- build the keyboard
  function makeKey(spec) {
    const el = document.createElement('button');
    el.className = 'key';
    el.style.flexGrow = spec.w;
    el.style.flexBasis = 0;
    el.dataset.code = spec.code;
    if (MODIFIERS.has(spec.code)) el.classList.add('mod');
    if (spec.code === 'Space') el.classList.add('space');

    if (spec.shifted) {
      el.innerHTML = '<span class="lbl base"></span><span class="lbl alt"></span>';
      el.querySelector('.base').textContent = spec.label;
      el.querySelector('.alt').textContent = spec.shifted;
    } else {
      el.textContent = spec.label;
      if (spec.label.length > 1) el.classList.add('wide-label');
    }

    // Pointer events, not touch/mouse: one code path, and multi-touch works, so chords like
    // Shift+letter can be pressed with two fingers at once.
    el.addEventListener('pointerdown', (ev) => {
      ev.preventDefault();
      el.setPointerCapture(ev.pointerId);
      if (MODIFIERS.has(spec.code)) cycleLatch(spec.code);
      else down(spec.code);
    });

    const release = (ev) => {
      if (MODIFIERS.has(spec.code)) return;   // modifiers are latched, not momentary
      ev.preventDefault();
      up(spec.code);
      consumeOneShots();
    };
    el.addEventListener('pointerup', release);
    el.addEventListener('pointercancel', release);

    el.addEventListener('contextmenu', (ev) => ev.preventDefault());
    return el;
  }

  function buildRow(specs, cls) {
    const row = document.createElement('div');
    row.className = 'row' + (cls ? ' ' + cls : '');
    for (const spec of specs) {
      const el = makeKey(spec);
      row.append(el);
      // Shift and Ctrl appear twice; the map keeps the first, which is all `paint` needs.
      if (!buttons.has(spec.code)) buttons.set(spec.code, el);
    }
    return row;
  }

  const board = $('board');
  board.append(buildRow(FN_ROW, 'fnrow'));
  for (const r of MAIN_ROWS) board.append(buildRow(r));

  // ---------------------------------------------------------------- physical keyboard
  let capture = false;

  function setCapture(on) {
    capture = on;
    $('capture').classList.toggle('on', on);
    $('capture').textContent = on ? 'capture: on' : 'capture: off';
  }

  document.addEventListener('keydown', (e) => {
    if (!capture) return;
    e.preventDefault();
    if (e.repeat) return;           // tablet B generates its own repeat from the held key
    if (U[e.code]) down(e.code);
  });

  document.addEventListener('keyup', (e) => {
    if (!capture) return;
    e.preventDefault();
    if (U[e.code]) up(e.code);
    reflectShift();
  });

  $('capture').onclick = () => setCapture(!capture);
  $('panic').onclick = releaseAll;

  // ---------------------------------------------------------------- link status
  link.onStatus = (up_) => {
    $('ws').textContent = up_ ? 'linked' : 'no link';
    $('ws').className = 'pill ' + (up_ ? 'ok' : 'bad');
    document.body.classList.toggle('offline', !up_);
    if (!up_) {
      // The firmware watchdog will release these anyway; clear the UI so it does not lie.
      held.clear();
      latch.clear();
      document.querySelectorAll('.key').forEach((el) =>
        el.classList.remove('down', 'armed', 'locked'));
      reflectShift();
    }
  };

  link.onLine = (line) => {
    if (line.startsWith('S ')) {
      const ble = /ble=1/.test(line);
      $('ble').textContent = ble ? 'paired' : 'waiting for tablet';
      $('ble').className = 'pill ' + (ble ? 'ok' : 'bad');
      const b = line.match(/batt=(\d+)/);
      if (b) {
        $('bat').textContent = b[1] + '%';
        $('bat').className = 'pill' + (Number(b[1]) < 20 ? ' bad' : '');
      }
    }
  };

  // Feed the firmware's idle watchdog while the page sits open with nothing pressed.
  setInterval(() => link.send('P'), 1500);

  // Backgrounding the tab stops our events but not tablet B's key repeat — let go first.
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) releaseAll();
  });
  window.addEventListener('pagehide', releaseAll);

  // Stop the browser turning long-presses and two-finger taps into selections and zooms.
  document.addEventListener('contextmenu', (e) => {
    if (e.target.closest('.key')) e.preventDefault();
  });
  document.addEventListener('dblclick', (e) => e.preventDefault());

  setCapture(false);

  if (location.host) {
    link.start();
  } else {
    // Opened as a file:// URL — there is no device to talk to. Render anyway so the layout can
    // be eyeballed without flashing anything.
    $('ws').textContent = 'preview (no device)';
  }
})();

// HIDRA transport, Android build.
//
// Shadows src/web/transport.js — same class name, same three members app.js uses (send,
// onStatus, onLine, start), but the far end is a Kotlin bridge in this process rather than a
// WebSocket to an ESP32. app.js, keymap.js, style.css and index.html are copied from src/web/
// verbatim at build time and must stay untouched: the ESP32 firmware serves the same files.
//
// The line protocol is kept exactly as it was ("D 4 0", "U 4 0", "R", "P") even though both
// ends are now in one process. It costs nothing, it keeps app.js identical across both builds,
// and the protocol is already documented and proven.

(() => {
  let instance = null;

  class AndroidTransport {
    constructor(_url) {
      this.onStatus = null;
      this.onLine = null;
      instance = this;
    }

    start() {
      decorate();
      HidraNative.ready();
    }

    send(line) {
      HidraNative.send(line);
    }
  }

  // app.js does `new WebSocketTransport(...)`, so this has to answer to that name.
  window.WebSocketTransport = AndroidTransport;

  // Kotlin calls into these.
  window.HIDRA_ANDROID = {
    status(up) { if (instance && instance.onStatus) instance.onStatus(up); },
    line(s) { if (instance && instance.onLine) instance.onLine(s); }
  };

  // --------------------------------------------------------------- Android-only adjustments
  //
  // Anything the phone needs that the tablet build does not goes here, so src/web/ never has to
  // learn which host it is running on.
  function decorate() {
    const style = document.createElement('style');
    style.textContent = `
      /* The veil means "no device is accepting keys", not "the network dropped". */
      body.offline::after { content: "waiting for a device…"; }

      /* A phone in landscape is not a 10-inch tablet. The function row is reference material
         more than a typing target (see style.css), so on short screens it folds away and the
         remaining rows get the height back. */
      body.compact .row.fnrow { display: none; }
    `;
    document.head.append(style);

    const bar = document.getElementById('bar');
    const toggle = document.createElement('button');
    toggle.id = 'fnrow';

    // Default to hidden wherever the keys would otherwise be uncomfortably short. 450 CSS px
    // of height is about where a phone in landscape stops having room for seven rows.
    setCompact(window.innerHeight < 450);

    function setCompact(on) {
      document.body.classList.toggle('compact', on);
      toggle.textContent = on ? 'fn row: off' : 'fn row: on';
      toggle.classList.toggle('on', !on);
    }

    toggle.onclick = () => setCompact(!document.body.classList.contains('compact'));
    bar.insertBefore(toggle, document.getElementById('capture'));
  }
})();

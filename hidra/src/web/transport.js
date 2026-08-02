// Transport seam. Everything above this file speaks the PLAN.md §4 line protocol and knows
// nothing about how the bytes travel — which is the whole point: Phase 3 adds a BleTransport
// with the same four members (start, send, onStatus, onLine) and app.js is untouched.

class WebSocketTransport {
  constructor(url) {
    this.url = url;
    this.sock = null;
    this.up = false;
    this.onStatus = () => {};    // (up: boolean) => void
    this.onLine = () => {};      // (line: string) => void
    this.retryMs = 500;
  }

  start() {
    this.sock = new WebSocket(this.url);

    this.sock.onopen = () => {
      this.up = true;
      this.retryMs = 500;
      this.onStatus(true);
      this.send('V1');
    };

    this.sock.onclose = () => {
      if (this.up) this.onStatus(false);
      this.up = false;
      // Back off gently: the stick reboots in a couple of seconds, a tablet waking from sleep
      // can take longer, and hammering it helps nobody.
      setTimeout(() => this.start(), this.retryMs);
      this.retryMs = Math.min(this.retryMs * 1.6, 5000);
    };

    this.sock.onerror = () => this.sock.close();

    this.sock.onmessage = (e) => {
      for (const line of String(e.data).split('\n')) {
        const t = line.trim();
        if (t) this.onLine(t);
      }
    };
  }

  send(line) {
    if (!this.up) return false;
    try {
      this.sock.send(line);
      return true;
    } catch (_) {
      return false;
    }
  }
}

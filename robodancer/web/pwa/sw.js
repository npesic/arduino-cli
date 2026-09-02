// Service worker: enough to make the app installable and survive a brief
// dropout, without ever serving stale code.
//
// Network-first deliberately. Cache-first would mean editing a file on the Pi
// and still being served the old one from the browser -- the same class of
// stale-code confusion that is painful to debug on this project.

const CACHE = 'robodancer-v1';
const SHELL = [
  '/', '/index.html', '/style.css', '/app.js', '/gamepad.js',
  '/manifest.json', '/icon-192.png', '/icon-512.png',
];

// Never cache: the MJPEG stream never completes, and live state must be live.
const NEVER = ['/stream.mjpg', '/api/'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== location.origin) return;
  if (NEVER.some((p) => url.pathname.startsWith(p))) return;

  event.respondWith(
    fetch(event.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(event.request, copy)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(event.request).then(
        (hit) => hit || caches.match('/index.html'))));
});

// Carrot panel service worker: PWA shell + Web Push delivery.
// Network-first for API and documents (device data must be fresh), cache-first
// fallback for same-origin static assets so the shell still opens offline.
const SHELL_CACHE = 'carrot-shell-v1';

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((cache) => cache.addAll(['/'])));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== SHELL_CACHE).map((k) => caches.delete(k)))),
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET' || new URL(request.url).origin !== self.location.origin) {
    return;
  }
  if (new URL(request.url).pathname.startsWith('/api/') || request.mode === 'navigate') {
    // Network-first; fall back to the cached shell when the device is unreachable.
    event.respondWith(
      fetch(request).catch(() =>
        caches.match(request).then((hit) => hit || caches.match('/'))),
    );
    return;
  }
  event.respondWith(
    caches.match(request).then((hit) => hit || fetch(request).then((response) => {
      const copy = response.clone();
      caches.open(SHELL_CACHE).then((cache) => cache.put(request, copy));
      return response;
    })),
  );
});

self.addEventListener('push', (event) => {
  let title = 'carrot';
  let body = 'device event';
  try {
    const data = event.data ? event.data.json() : {};
    title = data.title || title;
    body = data.body || body;
  } catch (error) {
    body = event.data ? event.data.text() : body;
  }
  event.waitUntil(self.registration.showNotification(title, {
    body,
    icon: '/shared-assets/img_spinner_comma.png',
    badge: '/shared-assets/img_spinner_comma.png',
    tag: 'carrot-device',
    renotify: true,
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ('focus' in client) return client.focus();
      }
      return self.clients.openWindow('/');
    }),
  );
});

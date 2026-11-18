const CACHE = 'civia-admin-offline-v1';
const OFFLINE = '/admin/offline.html';
const OFFLINE_REQUEST = new Request(OFFLINE, { credentials: 'omit', cache: 'reload' });

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.add(OFFLINE_REQUEST)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys().then((names) => Promise.all(names
    .filter((name) => name.startsWith('civia-admin-offline-') && name !== CACHE)
    .map((name) => caches.delete(name)))).then(() => self.clients.claim()));
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== 'GET' || request.mode !== 'navigate' ||
      url.origin !== self.location.origin || !url.pathname.startsWith('/admin/')) return;

  event.respondWith(fetch(request).catch(async () =>
    (await caches.match(OFFLINE_REQUEST, { cacheName: CACHE })) || Response.error()
  ));
});

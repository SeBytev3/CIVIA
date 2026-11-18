const CACHE = 'civia-admin-offline-v1';
const OFFLINE = '/admin/offline.html';
const OFFLINE_REQUEST = new Request(OFFLINE, { credentials: 'omit', cache: 'reload' });

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const response = await fetch(OFFLINE_REQUEST, { redirect: 'error' });
    if (response.status !== 200 || response.type !== 'basic' || !response.headers.get('Content-Type')?.startsWith('text/html')) {
      throw new Error('Aviso administrativo no disponible.');
    }
    const cache = await caches.open(CACHE);
    await cache.put(OFFLINE_REQUEST, response);
    await self.skipWaiting();
  })());
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
      !['http:', 'https:'].includes(url.protocol) || url.origin !== self.location.origin ||
      !['/admin/', '/admin/index.html'].includes(url.pathname)) return;

  event.respondWith(fetch(request).catch(async () =>
    (await caches.match(OFFLINE_REQUEST, { cacheName: CACHE })) || Response.error()
  ));
});

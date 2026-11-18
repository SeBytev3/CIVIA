self.addEventListener('install', (event) => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    await Promise.allSettled([self.clients.claim(), caches.delete('civia-pwa-v1')]);
    await self.registration.unregister();
  })());
});

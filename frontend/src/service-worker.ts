export async function retireLegacyWorker() {
  if (!('serviceWorker' in navigator)) return;
  try {
    const regs = await navigator.serviceWorker.getRegistrations();
    await Promise.all(regs.filter((reg) => reg.scope === new URL('/', location.origin).href &&
      [reg.active, reg.waiting, reg.installing].some((worker) => worker && new URL(worker.scriptURL).pathname === '/sw.js'))
      .map((legacy) => legacy.unregister()));
    await window.caches?.delete('civia-pwa-v1');
  } catch {
    // The app still works without service workers.
  }
}

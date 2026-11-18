export async function retireLegacyWorker() {
  if (!('serviceWorker' in navigator)) return;
  try {
    const regs = await navigator.serviceWorker.getRegistrations();
    const root = regs.find((reg) => reg.scope === new URL('/', location.origin).href &&
      [reg.active, reg.waiting, reg.installing].some((worker) => worker && new URL(worker.scriptURL).pathname === '/sw.js'));
    // Updating runs the retirement worker even when an older worker still controls this tab.
    if (root) await root.update();
    else await window.caches?.delete('civia-pwa-v1');
  } catch {
    // The app still works without service workers.
  }
}

export async function registerScopedWorker(scope: '/app/' | '/admin/') {
  if (!window.isSecureContext || !('serviceWorker' in navigator)) return;
  void retireLegacyWorker();
  try { await navigator.serviceWorker.register(`${scope}sw.js`, { scope, updateViaCache: 'none' }); }
  catch { /* The experience remains available online. */ }
}

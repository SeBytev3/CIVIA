const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const base = process.env.TARGET_URL || 'http://localhost:5174';
const sample = {
  id: '2d859c01-e59a-4b35-b3eb-d1d3ad9772df', title: 'Calle con hueco',
  description: 'Registro sintético con evidencia', tracking_code: 'CIV-LOCAL-001',
  status: 'PENDING_ANALYSIS', analysis_status: 'PENDING',
  created_at: '2026-01-01T00:00:00Z', latitude: 3.437, longitude: -76.52,
};
const stats = { total: 1, total_reports: 1, by_category: {}, by_status: { PENDING_ANALYSIS: 1 }, by_comuna: {} };

async function setup(context, role, handleSubmit = async (route) => route.fulfill({ status: 201, json: sample })) {
  await context.route('https://*.tile.openstreetmap.org/**', (route) => route.abort());
  await context.route('**/api/**', async (route) => {
    const { pathname } = new URL(route.request().url());
    const session = { user: { id: 'owner', email: 'demo@example.invalid', name: 'Usuario sintético', role, active: true }, csrf_token: 'synthetic-test-csrf' };
    if (pathname === '/api/auth/session') {
      return route.fulfill(role ? { json: session } : { status: 401, json: {} });
    }
    if (pathname.endsWith('/stats')) return route.fulfill({ json: stats });
    if (pathname === '/api/reports' && route.request().method() === 'POST') return handleSubmit(route);
    if (pathname === '/api/reports') return route.fulfill({ json: { items: [sample], limit: 10, offset: 0, total: 1 } });
    return route.fulfill({ json: { items: [], limit: 10, offset: 0, total: 0 } });
  });
}

async function run() {
  const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'msedge' });
  const failures = [];
  const runCase = async (name, test) => {
    try { await test(); console.log('PASS', name); }
    catch (error) { failures.push(error); console.error('FAIL', name, error.message.split('\n')[0]); }
  };
  try {
    await runCase('la solicitud ciudadana de escritorio queda bloqueada y sin manifest', async () => {
      const context = await browser.newContext();
      try {
        await setup(context, 'CITIZEN');
        const page = await context.newPage();
        await page.goto(base);
        await page.getByRole('button', { name: 'Reportar', exact: true }).first().click({ timeout: 3000 });
        await page.getByText('Para registrar un reporte, utiliza CIVIA desde tu dispositivo móvil.', { exact: true }).waitFor({ timeout: 3000 });
        assert.equal(await page.locator('link[rel=manifest]').count(), 0);
        assert.equal(await page.getByLabel('Título').count(), 0);
      } finally { await context.close(); }
    });
    await runCase('solo Administración tiene manifest y CASE_ADMIN no ve controles de sistema', async () => {
      const context = await browser.newContext();
      try {
        await setup(context, 'CASE_ADMIN');
        const page = await context.newPage();
        await page.goto(new URL('/admin/', base).href);
        await page.getByRole('button', { name: 'Bandeja de casos', exact: true }).waitFor({ timeout: 3000 });
        assert.equal(await page.locator('link[rel=manifest]').getAttribute('href'), '/admin/manifest.webmanifest');
        for (const label of ['Reportar', 'Usuarios y roles', 'Observabilidad', 'Trabajos fallidos']) {
          assert.equal(await page.getByRole('button', { name: label, exact: true }).count(), 0, label);
        }
      } finally { await context.close(); }
    });
    await runCase('el portal rechaza una sesión ciudadana', async () => {
      const context = await browser.newContext();
      try {
        await setup(context, 'CITIZEN');
        const page = await context.newPage();
        await page.goto(new URL('/admin/', base).href);
        await page.getByText('Este portal requiere una cuenta administrativa.', { exact: true }).waitFor({ timeout: 3000 });
        assert.equal(await page.getByRole('button', { name: 'Bandeja de casos', exact: true }).count(), 0);
      } finally { await context.close(); }
    });
    await runCase('la PWA administrativa solo almacena su aviso sin conexión', async () => {
      const context = await browser.newContext();
      try {
        await setup(context, 'CASE_ADMIN');
        const page = await context.newPage();
        await page.goto(new URL('/admin/', base).href);
        await page.getByRole('heading', { name: 'Dashboard operativo' }).waitFor();
        await page.waitForFunction(() => navigator.serviceWorker.controller?.scriptURL.endsWith('/admin/sw.js'));
        assert.deepEqual(await page.evaluate(async () => {
          const registrations = await navigator.serviceWorker.getRegistrations();
          return registrations.map((registration) => new URL(registration.scope).pathname);
        }), ['/admin/']);
        assert.deepEqual(await page.evaluate(async () => {
          const cached = await caches.open('civia-admin-offline-v1');
          return (await cached.keys()).map((request) => new URL(request.url).pathname);
        }), ['/admin/offline.html']);
        await context.setOffline(true);
        await page.reload();
        await page.getByText('El portal administrativo necesita conexión para consultar o guardar datos.').waitFor();
        assert.equal(await page.getByRole('button', { name: 'Bandeja de casos' }).count(), 0);
        await context.setOffline(false);
        await page.goto(base);
        assert.equal(await page.evaluate(() => navigator.serviceWorker.controller), null);
      } finally { await context.close(); }
    });
    await runCase('un segundo ciudadano no carga el borrador del primer ciudadano', async () => {
      const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
      try {
        await setup(context, 'CITIZEN');
        const page = await context.newPage();
        await page.goto(base);
        await page.getByRole('button', { name: 'Reportar', exact: true }).first().click();
        await page.getByLabel('Título').fill('Borrador de otra cuenta');
        await page.waitForFunction(() => new Promise((resolve) => {
          const req = indexedDB.open('civia-drafts', 1);
          req.onsuccess = () => {
            const db = req.result;
            const read = db.transaction('reports').objectStore('reports').get('owner');
            read.onsuccess = () => { db.close(); resolve(read.result?.title === 'Borrador de otra cuenta'); };
          };
        }));
        await context.route('**/api/auth/session', (route) => route.fulfill({ json: {
          user: { id: 'other-owner', email: 'otra@example.invalid', name: 'Otra cuenta', role: 'CITIZEN', active: true },
          csrf_token: 'synthetic-other-csrf',
        } }));
        await page.reload();
        await page.getByLabel('Título').waitFor();
        assert.equal(await page.getByLabel('Título').inputValue(), '');
      } finally { await context.close(); }
    });
    await runCase('la recepción móvil conserva evidencia y clave después de un envío perdido y recarga', async () => {
      const context = await browser.newContext({
        viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true,
        permissions: ['geolocation'], geolocation: { latitude: 3.437, longitude: -76.52 },
      });
      try {
        const attempts = [];
        await setup(context, 'CITIZEN', async (route) => {
          const headers = route.request().headers();
          attempts.push({ key: headers['idempotency-key'], csrf: headers['x-csrf-token'], hasPhoto: route.request().postDataBuffer().includes(Buffer.from('evidence.jpg')) });
          return attempts.length === 1 ? route.abort('connectionreset') : route.fulfill({ status: 201, json: sample });
        });
        const page = await context.newPage();
        await page.goto(base);
        await page.getByRole('button', { name: 'Reportar', exact: true }).first().click({ timeout: 3000 });
        await page.getByLabel('Título').fill('Cambio de superficie');
        await page.getByLabel('Descripción').fill('Registro sintético con evidencia');
        await page.getByRole('button', { name: 'Usar mi ubicación' }).click();
        await page.getByText('3.437000, -76.520000', { exact: true }).waitFor();
        await page.getByLabel('Seleccionar foto').setInputFiles({
          name: 'evidence.jpg', mimeType: 'image/jpeg', buffer: Buffer.from([255, 216, 255, 217]),
        });
        await page.getByRole('button', { name: 'Enviar reporte' }).click();
        await page.getByText('Tu reporte está guardado en este dispositivo y pendiente de envío. Podrás enviarlo cuando recuperes la conexión.', { exact: true }).waitFor();
        assert.equal(await page.getByText(sample.tracking_code, { exact: true }).count(), 0);
        await page.reload();
        await page.getByRole('button', { name: 'Reportar', exact: true }).first().click();
        assert.equal(await page.getByLabel('Título').inputValue(), 'Cambio de superficie');
        await page.getByRole('button', { name: 'Reintentar envío' }).click();
        await page.getByText('Tu reporte fue recibido correctamente.', { exact: true }).waitFor();
        await page.getByText(sample.tracking_code, { exact: true }).waitFor();
        assert.ok(attempts[0].key);
        assert.deepEqual(attempts[0], attempts[1]);
        assert.equal(attempts[0].csrf, 'synthetic-test-csrf');
        assert.ok(attempts[0].hasPhoto);
      } finally { await context.close(); }
    });
  } finally { await browser.close(); }
  if (failures.length) process.exitCode = 1;
}

run().catch((error) => { console.error(error); process.exitCode = 1; });

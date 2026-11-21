const assert = require('node:assert/strict');
const { mkdtempSync, readFileSync, rmSync } = require('node:fs');
const { createServer } = require('node:http');
const { tmpdir } = require('node:os');
const { dirname, join, resolve } = require('node:path');
const { chromium } = require('playwright');

const base = process.env.TARGET_URL || 'http://localhost:5174';
const channel = process.env.BROWSER_CHANNEL || 'msedge';
const sample = {
  id: '2d859c01-e59a-4b35-b3eb-d1d3ad9772df', title: 'Calle con hueco',
  description: 'Registro sintético con evidencia', tracking_code: `CIV-LOCAL-${'1234567890'.repeat(5)}`,
  status: 'PENDING_ANALYSIS', analysis_status: 'PENDING',
  created_at: '2026-01-01T00:00:00Z', latitude: 3.437, longitude: -76.52,
};
const viewports = [[320, 568], [360, 800], [375, 667], [390, 844], [412, 915], [768, 1024], [1366, 768], [1920, 1080], [800, 360]];
const stats = { total: 1, total_reports: 1, by_category: {}, by_status: { PENDING_ANALYSIS: 1 }, by_comuna: {} };
const citizen = { id: 'owner', email: 'demo@example.invalid', name: 'NombreSintético'.repeat(8), role: 'CITIZEN', active: true };
const installation = { installation_id: '73d37868-959d-4c7b-81bf-eea7d081e72c', version: require('../package.json').version, commit: 'test', protocol: 1 };
const photo = readFileSync(join(__dirname, '..', 'public', 'demo_evidence', 'sample_hueco.jpg'));
const browserErrors = [];

function wav() {
  const frames = 8_000;
  const file = Buffer.alloc(44 + frames * 2);
  file.write('RIFF', 0);
  file.writeUInt32LE(file.length - 8, 4);
  file.write('WAVEfmt ', 8);
  file.writeUInt32LE(16, 16);
  file.writeUInt16LE(1, 20);
  file.writeUInt16LE(1, 22);
  file.writeUInt32LE(frames, 24);
  file.writeUInt32LE(frames * 2, 28);
  file.writeUInt16LE(2, 32);
  file.writeUInt16LE(16, 34);
  file.write('data', 36);
  file.writeUInt32LE(file.length - 44, 40);
  return file;
}

async function setup(context, role, handleSubmit = async (route) => route.fulfill({ status: 201, json: sample })) {
  context.on('page', (page) => page.on('pageerror', (error) => browserErrors.push(error.message)));
  await context.route(/^https:\/\/(?:[abc]\.)?tile\.openstreetmap\.org\//, (route) => route.abort());
  await context.route('**/api/**', async (route) => {
    const { pathname } = new URL(route.request().url());
    const session = { user: { ...citizen, role }, csrf_token: 'synthetic-test-csrf' };
    if (pathname === '/api/meta') return route.fulfill({ json: installation });
    if (pathname === '/api/auth/session') {
      return route.fulfill(role ? { json: session } : { status: 401, json: {} });
    }
    if (pathname === '/api/auth/register' || pathname === '/api/auth/login') {
      return route.fulfill({ json: { ...session, user: citizen } });
    }
    if (pathname.endsWith('/stats')) return route.fulfill({ json: stats });
    if (pathname === '/api/reports' && route.request().method() === 'POST') return handleSubmit(route);
    if (pathname === '/api/reports') {
      const items = role === 'WEB_ADMIN' ? Array.from({ length: 20 }, (_, index) => ({
        ...sample, id: String(index), title: 'DescripciónSintéticaExtensa'.repeat(8),
      })) : [sample];
      return route.fulfill({ json: { items, limit: 20, offset: 0, total: items.length } });
    }
    if (pathname === '/api/admin/observability') return route.fulfill({ json: {
      provider_chain: [], circuits: [], recent_calls: [], metrics: [],
    } });
    return route.fulfill({ json: { items: [], limit: 10, offset: 0, total: 0 } });
  });
}

async function legacyOrigin() {
  const worker = readFileSync(join(__dirname, 'fixtures', 'legacy-sw.js'));
  let deployed = false;
  const server = createServer(async (request, response) => {
    response.setHeader('Cache-Control', 'no-store');
    if (!deployed) {
      const isWorker = request.url === '/sw.js';
      response.setHeader('Content-Type', isWorker ? 'application/javascript' : 'text/html');
      response.end(isWorker ? worker : '<!doctype html><title>CIVIA 1.0</title><h1>CIVIA 1.0</h1>');
      return;
    }
    try {
      const upstream = await fetch(new URL(request.url, base));
      response.statusCode = upstream.status;
      response.setHeader('Content-Type', upstream.headers.get('content-type') || 'application/octet-stream');
      response.end(Buffer.from(await upstream.arrayBuffer()));
    } catch {
      response.writeHead(502);
      response.end();
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return {
    url: `http://127.0.0.1:${server.address().port}/`,
    deploy: () => { deployed = true; },
    close: () => new Promise((resolve) => { server.close(resolve); server.closeAllConnections(); }),
  };
}

async function checkBounds(page) {
  assert.deepEqual(await page.evaluate(() => {
    const issues = [];
    const viewport = Math.min(innerWidth, document.documentElement.clientWidth);
    if (document.documentElement.scrollWidth > viewport + 1) issues.push('Desborde del documento');
    for (const control of document.querySelectorAll('button, input, select, textarea, summary, a[href]')) {
      if (!control.getClientRects().length || getComputedStyle(control).visibility !== 'visible') continue;
      const scroller = control.closest('.table-scroll, .markdown-table-wrapper, .leaflet-pane');
      if (scroller) continue;
      const container = control.closest('fieldset, .login-panel, .civia-map-shell, .citizen-nav, .admin-sidebar');
      const rect = control.getBoundingClientRect();
      const left = container ? Math.max(0, container.getBoundingClientRect().left) : 0;
      const right = container ? Math.min(viewport, container.getBoundingClientRect().right) : viewport;
      if (rect.left < left - 1 || rect.right > right + 1) issues.push(control.outerHTML.slice(0, 150));
    }
    return issues;
  }), []);
}

async function waitForSavedTitle(page, title) {
  await page.waitForFunction(({ key, expected }) => new Promise((resolve) => {
    const request = indexedDB.open('civia-drafts', 1);
    request.onerror = () => resolve(false);
    request.onsuccess = () => {
      const db = request.result;
      const stored = db.transaction('reports').objectStore('reports').get(key);
      stored.onsuccess = () => { db.close(); resolve(stored.result?.title === expected); };
      stored.onerror = () => { db.close(); resolve(false); };
    };
  }), { key: `${installation.installation_id}:${citizen.id}`, expected: title });
}

async function run() {
  const browser = await chromium.launch({ channel, args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] });
  const failures = [];
  const runCase = async (name, test) => {
    try { await test(); console.log('PASS', name); }
    catch (error) { failures.push(error); console.error('FAIL', name, error.message); }
  };
  try {
    await runCase('la cámara web captura una foto y libera el dispositivo', async () => {
      const context = await browser.newContext();
      try {
        await setup(context, 'CITIZEN');
        await context.addInitScript(() => {
          const devices = navigator.mediaDevices;
          if (!devices?.getUserMedia) return;
          const getUserMedia = devices.getUserMedia.bind(devices);
          devices.getUserMedia = async (constraints) => {
            const stream = await getUserMedia(constraints);
            window.civiaTestCamera = stream;
            return stream;
          };
        });
        const page = await context.newPage();
        page.setDefaultTimeout(5000);
        await page.goto(base);
        await page.getByRole('button', { name: 'Abrir cámara' }).click();
        await page.getByRole('button', { name: 'Tomar foto' }).click();
        await page.getByRole('img', { name: 'Evidencia seleccionada' }).waitFor();
        await page.waitForFunction(() => window.civiaTestCamera.getVideoTracks()[0].readyState === 'ended');
        assert.equal(await page.getByLabel('Seleccionar foto').getAttribute('type'), 'file');
        await page.evaluate(() => {
          navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Denied in test', 'NotAllowedError'); };
        });
        await page.getByRole('button', { name: 'Abrir cámara' }).click();
        await page.getByText('Permite el acceso a la cámara en el navegador o selecciona una foto.').waitFor();
        assert.equal(await page.getByRole('button', { name: 'Cerrar cámara' }).count(), 0);
        assert.equal(await page.getByLabel('Seleccionar foto').isEnabled(), true);
      } finally { await context.close(); }
    });
    await runCase('la raíz es exclusivamente de radicación en todas las resoluciones', async () => {
      const context = await browser.newContext();
      try {
        await setup(context, 'CITIZEN');
        const tileRequests = [];
        await context.route(/^https:\/\/(?:[abc]\.)?tile\.openstreetmap\.org\//, async (route) => {
          tileRequests.push({ url: route.request().url(), referer: await route.request().headerValue('referer') });
          await route.fulfill({ status: 403 });
        });
        const page = await context.newPage();
        page.setDefaultTimeout(8000);
        await page.goto(new URL('/#asistente', base).href);
        await page.getByLabel('Título').waitFor({ timeout: 3000 });
        await page.getByLabel('Título').fill('TítuloSintéticoLargo'.repeat(8));
        await page.getByLabel('Descripción').fill('Descripción sintética larga para verificar el trazado. '.repeat(25));
        await Promise.all([
          page.waitForResponse((response) => response.status() === 403 && /tile\.openstreetmap\.org/.test(response.url())),
          page.getByRole('button', { name: 'Elegir en el mapa' }).click(),
        ]);
        assert.ok(tileRequests.length > 0);
        for (const { url, referer } of tileRequests) {
          assert.equal(new URL(url).hostname, 'tile.openstreetmap.org');
          assert.equal(referer, `${new URL(base).origin}/`);
        }
        await page.getByText('El mapa base no está disponible.', { exact: false }).waitFor();
        await page.getByRole('button', { name: 'Usar centro del mapa' }).click();
        await page.getByText(/^3\.\d{6}, -76\.\d{6}$/).waitFor();
        await page.getByLabel('Seleccionar foto').setInputFiles({
          name: `${'EvidenciaSintetica'.repeat(12)}.jpg`, mimeType: 'image/jpeg', buffer: photo,
        });
        await page.getByRole('img', { name: 'Evidencia seleccionada' }).waitFor();
        assert.equal(await page.locator('link[rel=manifest]').count(), 0);
        assert.equal(await page.getByRole('navigation').count(), 0);
        assert.equal(await page.getByRole('contentinfo').count(), 1);
        assert.equal(await page.getByText('Mapa ciudadano', { exact: true }).count(), 0);
        assert.equal(await page.getByText('Asistente ciudadano', { exact: true }).count(), 0);
        for (const [width, height] of viewports) {
          await page.setViewportSize({ width, height });
          await checkBounds(page);
          if (process.env.CIVIA_SCREENSHOTS) await page.screenshot({ path: `${process.env.CIVIA_SCREENSHOTS}/web-${width}x${height}.png`, fullPage: true });
        }
        await page.setViewportSize({ width: 680, height: 384 });
        await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
        await checkBounds(page);
      } finally { await context.close(); }
    });
    await runCase('la ruta ciudadana anuncia instalación y navega con scope independiente', async () => {
      const tempRoot = resolve(tmpdir());
      const testProfile = mkdtempSync(join(tempRoot, 'civia-pwa-'));
      const context = await chromium.launchPersistentContext(testProfile, { channel });
      try {
        await setup(context, 'CITIZEN');
        const page = await context.newPage();
        await page.goto(base);
        await page.getByRole('link', { name: 'Instalar CIVIA' }).click({ timeout: 3000 });
        await page.getByRole('heading', { name: 'Instalar CIVIA' }).waitFor({ timeout: 3000 });
        assert.equal(await page.locator('link[rel=manifest]').getAttribute('href'), '/app/manifest.webmanifest');
        const manifest = await (await page.request.get(new URL('/app/manifest.webmanifest', base).href)).json();
        assert.equal(manifest.id, '/app/');
        assert.equal(manifest.start_url, '/app/');
        assert.equal(manifest.scope, '/app/');
        assert.equal(manifest.display, 'standalone');
        for (const size of [192, 512]) {
          for (const purpose of ['any', 'maskable']) {
            const icon = manifest.icons.find((item) => item.sizes === `${size}x${size}` && item.purpose === purpose);
            assert.ok(icon);
            const response = await page.request.get(new URL(icon.src, base).href);
            const png = await response.body();
            assert.equal(png.readUInt32BE(16), size);
            assert.equal(png.readUInt32BE(20), size);
          }
        }
        await page.getByRole('navigation', { name: 'Navegación ciudadana' }).getByRole('button', { name: 'Reportar' }).click();
        await page.getByLabel('Título').waitFor();
        await page.getByLabel('Título').fill('Borrador de CIVIA Ciudadano');
        await waitForSavedTitle(page, 'Borrador de CIVIA Ciudadano');
        await page.waitForFunction(() => navigator.serviceWorker.controller?.scriptURL.endsWith('/app/sw.js'));
        const cdp = await context.newCDPSession(page);
        const { installabilityErrors } = await cdp.send('Page.getInstallabilityErrors');
        assert.deepEqual(installabilityErrors, []);
        assert.deepEqual(await page.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).map(
          (registration) => new URL(registration.scope).pathname,
        )), ['/app/']);
        await context.setOffline(true);
        await page.reload();
        await page.getByText('CIVIA necesita conexión para acceder a tu cuenta o enviar reportes.').waitFor();
        assert.deepEqual(await page.evaluate(async () => {
          const cache = await caches.open('civia-citizen-offline-v1');
          return (await cache.keys()).map((request) => new URL(request.url).pathname);
        }), ['/app/offline.html']);
        await context.setOffline(false);
        await page.reload();
        await page.getByLabel('Título').waitFor();
        assert.equal(await page.getByLabel('Título').inputValue(), 'Borrador de CIVIA Ciudadano');
        await page.goto(new URL('/admin/', base).href);
        await page.waitForFunction(() => navigator.serviceWorker.controller?.scriptURL.endsWith('/admin/sw.js'));
        assert.deepEqual(await page.evaluate(async () => (await navigator.serviceWorker.getRegistrations())
          .map((registration) => new URL(registration.scope).pathname).sort()), ['/admin/', '/app/']);
        await page.goto(base);
        assert.equal(await page.evaluate(() => navigator.serviceWorker.controller), null);
      } finally {
        await context.close();
        if (dirname(testProfile) === tempRoot) rmSync(testProfile, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
      }
    });
    await runCase('la apertura standalone oculta la instalación y conserva las secciones al cambiar de ancho', async () => {
      const context = await browser.newContext();
      try {
        await setup(context, 'CITIZEN');
        await context.addInitScript(() => {
          const realMatch = window.matchMedia;
          window.matchMedia = (query) => {
            const list = realMatch.call(window, query);
            if (query === '(display-mode: standalone)') Object.defineProperty(list, 'matches', { value: true });
            return list;
          };
        });
        const page = await context.newPage();
        await page.goto(new URL('/app/#perfil', base).href);
        await page.getByRole('heading', { name: 'Perfil' }).waitFor();
        const nav = page.getByRole('navigation', { name: 'Navegación ciudadana' });
        for (const [tab, heading] of [
          ['Inicio', 'Reportes ciudadanos'], ['Reportar', 'Nuevo reporte'], ['Mis reportes', 'Mis reportes'],
          ['Asistente', 'Asistente ciudadano'], ['Perfil', 'Perfil'],
        ]) {
          await nav.getByRole('button', { name: tab, exact: true }).click();
          await page.getByRole('heading', { name: heading, exact: true }).waitFor();
          for (const [width, height] of viewports) {
            await page.setViewportSize({ width, height });
            await checkBounds(page);
            if (process.env.CIVIA_SCREENSHOTS) await page.screenshot({ path: `${process.env.CIVIA_SCREENSHOTS}/pwa-${tab.replaceAll(' ', '-')}-${width}x${height}.png`, fullPage: true });
          }
        }
        assert.equal(await page.getByRole('heading', { name: 'Instalar CIVIA' }).count(), 0);
      } finally { await context.close(); }
    });
    await runCase('el trabajador histórico actualiza la raíz sin eliminar borradores ni cachés ajenas', async () => {
      const site = await legacyOrigin();
      const context = await browser.newContext();
      try {
        await setup(context, 'CITIZEN');
        let page = await context.newPage();
        await page.goto(site.url);
        await page.evaluate(() => navigator.serviceWorker.register('/sw.js'));
        await page.waitForFunction(() => navigator.serviceWorker.controller?.scriptURL.endsWith('/sw.js'));
        await page.evaluate(async () => {
          const preserved = await caches.open('fixture-caché-ajena');
          await preserved.put('/preserved', new Response('fixture'));
          await new Promise((resolve, reject) => {
            const request = indexedDB.open('legacy-draft-fixture', 1);
            request.onupgradeneeded = () => request.result.createObjectStore('drafts');
            request.onerror = () => reject(request.error);
            request.onsuccess = () => {
              const db = request.result;
              const tx = db.transaction('drafts', 'readwrite');
              tx.objectStore('drafts').put('pendiente', 'report');
              tx.oncomplete = () => { db.close(); resolve(); };
            };
          });
        });
        site.deploy();
        await page.reload();
        await page.getByRole('heading', { name: 'Nuevo reporte' }).waitFor();
        await page.waitForFunction(async () =>
          !(await navigator.serviceWorker.getRegistrations()).some((registration) => new URL(registration.scope).pathname === '/'),
        );
        await page.close();
        page = await context.newPage();
        await page.goto(site.url);
        assert.equal(await page.evaluate(() => navigator.serviceWorker.controller), null);
        assert.deepEqual(await page.evaluate(() => caches.keys()), ['fixture-caché-ajena']);
        assert.equal(await page.evaluate(async () => {
          const db = await new Promise((resolve, reject) => {
            const request = indexedDB.open('legacy-draft-fixture', 1);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
          return new Promise((resolve) => {
            const request = db.transaction('drafts').objectStore('drafts').get('report');
            request.onsuccess = () => { db.close(); resolve(request.result); };
          });
        }), 'pendiente');
      } finally { await context.close(); await site.close(); }
    });
    await runCase('registro e inicio de sesión conducen al formulario web', async () => {
      for (const register of [false, true]) {
        const context = await browser.newContext();
        try {
          await setup(context, null);
          const page = await context.newPage();
          await page.goto(base);
          const form = page.getByRole('main');
          if (register) {
            await form.getByRole('button', { name: 'Crear cuenta ciudadana' }).click();
            await form.getByLabel('Nombre').fill('Registro sintético');
          }
          await form.getByLabel('Correo electrónico').fill('demo@example.invalid');
          await form.getByLabel('Contraseña').fill('password-sintetica-para-ui');
          await form.getByRole('button', { name: register ? 'Registrarme' : 'Entrar', exact: true }).click();
          await form.getByLabel('Título').waitFor();
        } finally { await context.close(); }
      }
    });
    await runCase('Administración tiene su propio manifest y CASE_ADMIN no ve controles de sistema', async () => {
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
    await runCase('WEB_ADMIN tiene controles propios y la tabla ancha se desplaza dentro del portal', async () => {
      const context = await browser.newContext();
      try {
        await setup(context, 'WEB_ADMIN');
        const page = await context.newPage();
        await page.goto(new URL('/admin/', base).href);
        for (const label of ['Usuarios y roles', 'Observabilidad', 'Trabajos fallidos']) {
          await page.getByRole('button', { name: label, exact: true }).waitFor();
        }
        await page.getByRole('button', { name: 'Bandeja de casos' }).click();
        await page.getByRole('heading', { name: 'Bandeja de casos' }).waitFor();
        await page.locator('tbody tr').last().waitFor();
        assert.equal(await page.locator('tbody tr').count(), 20);
        for (const [width, height] of viewports) {
          await page.setViewportSize({ width, height });
          await checkBounds(page);
          if (process.env.CIVIA_SCREENSHOTS) await page.screenshot({ path: `${process.env.CIVIA_SCREENSHOTS}/admin-${width}x${height}.png`, fullPage: true });
        }
        await page.setViewportSize({ width: 360, height: 800 });
        assert.equal(await page.locator('.table-scroll').evaluate((table) => table.scrollWidth > table.clientWidth), true);
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
        await page.getByLabel('Título').fill('Borrador de otra cuenta');
        await waitForSavedTitle(page, 'Borrador de otra cuenta');
        await page.reload();
        await page.getByLabel('Título').waitFor();
        assert.equal(await page.getByLabel('Título').inputValue(), 'Borrador de otra cuenta');
        await context.route('**/api/auth/session', (route) => route.fulfill({ json: {
          user: { id: 'other-owner', email: 'otra@example.invalid', name: 'Otra cuenta', role: 'CITIZEN', active: true },
          csrf_token: 'synthetic-other-csrf',
        } }));
        await page.reload();
        await page.getByLabel('Título').waitFor();
        assert.equal(await page.getByLabel('Título').inputValue(), '');
      } finally { await context.close(); }
    });
    await runCase('la actualización recupera un borrador anterior solo al pedirlo y conserva su clave', async () => {
      const context = await browser.newContext();
      try {
        const key = '4255209a-ad84-4e96-8b22-f30fb2e52f87';
        const sent = [];
        await setup(context, 'CITIZEN', (route) => {
          sent.push(route.request().headers()['idempotency-key']);
          return route.fulfill({ status: 201, json: sample });
        });
        const page = await context.newPage();
        await page.goto(base);
        await page.getByLabel('Título').waitFor();
        await page.evaluate(async ({ key, bytes }) => {
          const db = await new Promise((resolve, reject) => {
            const request = indexedDB.open('civia-drafts', 1);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
          await new Promise((resolve, reject) => {
            const tx = db.transaction('reports', 'readwrite');
            tx.objectStore('reports').put({
              key, title: 'Borrador anterior', description: 'Descripción sintética del borrador anterior',
              latitude: 3.437, longitude: -76.52,
              photo: new File([new Uint8Array(bytes)], 'conservada.jpg', { type: 'image/jpeg' }), pending: true,
            }, 'owner');
            tx.oncomplete = () => { db.close(); resolve(); };
            tx.onabort = () => { db.close(); reject(tx.error); };
          });
        }, { key, bytes: [...photo] });
        await page.reload();
        await page.getByLabel('Título').waitFor();
        assert.equal(await page.getByLabel('Título').inputValue(), '');
        await page.getByRole('button', { name: 'Recuperar borrador anterior' }).click({ timeout: 3000 });
        await page.getByRole('img', { name: 'Evidencia seleccionada' }).waitFor();
        assert.equal(await page.getByLabel('Título').inputValue(), 'Borrador anterior');
        assert.deepEqual(sent, []);
        await page.getByRole('button', { name: 'Enviar reporte', exact: true }).click();
        await page.getByText(sample.tracking_code, { exact: true }).waitFor();
        assert.deepEqual(sent, [key]);
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
          const bytes = route.request().postDataBuffer();
          attempts.push({ key: headers['idempotency-key'], csrf: headers['x-csrf-token'], hasPhoto: bytes.includes(photo), hasAudio: bytes.includes(wav()) });
          return attempts.length === 1 ? route.abort('connectionreset') : route.fulfill({ status: 201, json: sample });
        });
        const page = await context.newPage();
        await page.goto(base);
        await page.getByLabel('Título').fill('Cambio de superficie');
        await page.getByLabel('Descripción').fill('Registro sintético con evidencia');
        await page.getByRole('button', { name: 'Usar mi ubicación' }).click();
        await page.getByText('3.437000, -76.520000', { exact: true }).waitFor();
        await page.getByLabel('Seleccionar foto').setInputFiles({
          name: 'evidence.jpg', mimeType: 'image/jpeg', buffer: photo,
        });
        await page.getByLabel('Adjuntar audio').setInputFiles({ name: 'nota-sintetica.wav', mimeType: 'audio/wav', buffer: wav() });
        await page.locator('audio').waitFor();
        await page.getByRole('button', { name: 'Enviar reporte' }).click();
        await page.getByText('Tu reporte está guardado en este dispositivo y pendiente de envío. Podrás enviarlo cuando recuperes la conexión.', { exact: true }).waitFor();
        assert.equal(await page.getByText(sample.tracking_code, { exact: true }).count(), 0);
        await page.reload();
        await page.getByLabel('Título').waitFor();
        assert.equal(await page.getByLabel('Título').inputValue(), 'Cambio de superficie');
        await page.getByRole('button', { name: 'Reintentar envío' }).click();
        await page.getByText('Tu reporte fue recibido correctamente.', { exact: true }).waitFor();
        await page.getByText(sample.tracking_code, { exact: true }).waitFor();
        assert.ok(attempts[0].key);
        assert.deepEqual(attempts[0], attempts[1]);
        assert.equal(attempts[0].csrf, 'synthetic-test-csrf');
        assert.ok(attempts[0].hasPhoto);
        assert.ok(attempts[0].hasAudio);
        await checkBounds(page);
        await page.getByRole('button', { name: 'Registrar otro reporte' }).click();
        await page.getByLabel('Título').waitFor();
        assert.equal(await page.getByLabel('Título').inputValue(), '');
      } finally { await context.close(); }
    });
    await runCase('el recorrido de navegador termina sin excepciones JavaScript no gestionadas', async () => {
      assert.deepEqual(browserErrors, []);
    });
  } finally { await browser.close(); }
  if (failures.length) process.exitCode = 1;
}

run().catch((error) => { console.error(error); process.exitCode = 1; });

const assert = require('node:assert/strict');
const { mkdir, writeFile } = require('node:fs/promises');
const { join } = require('node:path');
const { setTimeout: delay } = require('node:timers/promises');
const { chromium } = require('playwright');

const app = new URL('/app/', process.env.TARGET_URL || 'http://localhost:5174').href;

function pageCommands(browserSession, sessionId) {
  let sequence = 0;
  return (method, params) => new Promise((resolve, reject) => {
    const id = ++sequence;
    function finish(error, value) {
      clearTimeout(timer);
      browserSession.off('Target.receivedMessageFromTarget', receive);
      if (error) reject(error);
      else resolve(value);
    }
    function receive({ sessionId: source, message }) {
      if (source !== sessionId) return;
      const reply = JSON.parse(message);
      if (reply.id !== id) return;
      finish(reply.error && new Error(reply.error.message), reply.result);
    }
    const timer = setTimeout(() => finish(new Error(`CDP: ${method} agotó el tiempo de espera`)), 7000);
    browserSession.on('Target.receivedMessageFromTarget', receive);
    browserSession.send('Target.sendMessageToTarget', {
      sessionId, message: JSON.stringify({ id, method, params }),
    }).catch(finish);
  });
}

async function run() {
  const browser = await chromium.launch({
    channel: 'chromium',
    headless: false,
    args: ['--disable-default-apps', '--start-minimized'],
  });
  const session = await browser.newBrowserCDPSession();
  let installed = false;
  try {
    await session.send('Target.createTarget', { url: app });
    await session.send('PWA.install', { manifestId: app, installUrlOrBundleUrl: app });
    installed = true;
    await session.send('PWA.changeAppUserSettings', { manifestId: app, displayMode: 'standalone' });
    const existing = new Set((await session.send('Target.getTargets')).targetInfos.map((target) => target.targetId));
    await session.send('PWA.launch', { manifestId: app });

    let appPage;
    for (let attempt = 0; attempt < 50 && !appPage; attempt += 1) {
      const { targetInfos } = await session.send('Target.getTargets');
      appPage = targetInfos.find((target) => target.type === 'page' && target.url === app && !existing.has(target.targetId));
      if (!appPage) await delay(100);
    }
    assert.ok(appPage, 'Chromium debe abrir una página al lanzar la PWA');
    const { sessionId } = await session.send('Target.attachToTarget', { targetId: appPage.targetId, flatten: false });
    const page = pageCommands(session, sessionId);

    let state;
    const expression = `({
      standalone: matchMedia('(display-mode: standalone)').matches,
      navigation: !!document.querySelector('.citizen-nav'),
      installPanel: !!document.querySelector('.install-panel'),
    })`;
    for (let attempt = 0; attempt < 50; attempt += 1) {
      try {
        state = (await page('Runtime.evaluate', { expression, returnByValue: true })).result.value;
        if (state.navigation) break;
      } catch (error) {
        if (!error.message.includes('Execution context was destroyed')) throw error;
      }
      await delay(100);
    }
    assert.deepEqual(state, { standalone: true, navigation: true, installPanel: false });
    if (process.env.CIVIA_SCREENSHOTS) {
      const { data } = await page('Page.captureScreenshot', { format: 'png' });
      await mkdir(process.env.CIVIA_SCREENSHOTS, { recursive: true });
      await writeFile(join(process.env.CIVIA_SCREENSHOTS, 'chromium-pwa-standalone.png'), Buffer.from(data, 'base64'));
    }
    console.log(`PASS Instalación y lanzamiento standalone de CIVIA Ciudadano en Chromium ${browser.version()}`);
  } finally {
    try {
      if (installed) await session.send('PWA.uninstall', { manifestId: app });
    } finally {
      await browser.close();
    }
  }
}

run().catch((error) => { console.error(error); process.exitCode = 1; });

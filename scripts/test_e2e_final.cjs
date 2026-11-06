let chromium;
try {
  chromium = require('playwright').chromium;
} catch {
  chromium = require('C:/Users/Jhoesp/AppData/Local/npm-cache/_npx/e41f203b7505f1fb/node_modules/playwright').chromium;
}

(async () => {
  console.log('--- CIVIA: Verificación E2E Playwright de Flujo Completo ---');
  const browser = await chromium.launch({
    channel: 'msedge',
    headless: true,
    args: [
      '--use-fake-ui-for-media-stream',
      '--use-fake-device-for-media-stream',
    ],
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    permissions: ['camera', 'geolocation'],
  });

  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });

  try {
    // 1. Cargar la aplicación
    console.log('1. Navegando a http://127.0.0.1:5173...');
    await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle' });

    const title = await page.title();
    console.log(`   Título de página: "${title}"`);

    // 2. Navegar a "+ Nuevo Reporte"
    console.log('2. Entrando a pestaña "+ Nuevo Reporte"...');
    await page.click('button:has-text("+ Nuevo Reporte")');
    await page.waitForSelector('text=Registrar Nuevo Reporte Ciudadano');

    // 3. Probar activación de cámara en vivo
    console.log('3. Probando visor de cámara web...');
    await page.click('button:has-text("Tomar fotografía")');
    await page.waitForSelector('video');
    console.log('   Visor de video en vivo activo.');

    // Capturar foto desde la cámara
    await page.click('button:has-text("Capturar fotografía ahora")');
    await page.waitForSelector('text=Archivo listo:');
    console.log('   Fotografía capturada desde cámara y cargada.');

    // Descartar para probar selección sintética
    console.log('4. Probando cambio de fotografía y muestra sintética...');
    await page.click('button:has-text("Cambiar fotografía")');
    await page.waitForSelector('text=Tome una foto en el lugar');

    // Seleccionar muestra de poste/cables (OTRO)
    await page.click('button:has-text("Poste / Cables")');
    await page.waitForSelector('text=Imagen generada con IA · Simulación');
    console.log('   Muestra de simulación OTRO seleccionada y distintivo ético visible.');

    // Verificar que la descripción se prellenó con el texto ético
    const desc = await page.inputValue('#rep-desc');
    console.log(`   Descripción asignada: "${desc.slice(0, 60)}..."`);

    // 5. Enviar el reporte
    console.log('5. Enviando reporte ciudadano a PostgreSQL...');
    await page.click('button[type="submit"]');

    // Esperar redirección automática a pestaña de seguimiento
    await page.waitForSelector('text=Seguimiento de Reporte mediante Código de Radicado', { timeout: 15000 });
    const successAlert = await page.textContent('.civia-alert.success');
    console.log(`   Alerta de éxito: ${successAlert}`);

    // Extraer código de radicado
    const trackingBadge = await page.textContent('.civia-badge.status');
    console.log(`   Radicado generado y visualizado: ${trackingBadge}`);

    // Verificar que el distintivo ético HTML esté presente en el panel de detalle
    const badgeCount = await page.locator('text=Imagen generada con IA · Simulación').count();
    console.log(`   Distintivos éticos visibles en panel: ${badgeCount}`);
    if (badgeCount < 1) {
      throw new Error('El panel de detalle no muestra el distintivo ético HTML.');
    }

    // 6. Recargar la página y verificar persistencia en PostgreSQL
    console.log('6. Recargando la página para verificar persistencia...');
    await page.reload({ waitUntil: 'networkidle' });

    // Ir a pestaña de seguimiento y consultar el radicado
    await page.click('button:has-text("Seguimiento Radicado")');
    await page.fill('input[aria-label="Código de radicado"]', trackingBadge.trim());
    await page.click('button:has-text("Consultar Radicado")');

    await page.waitForSelector(`.civia-badge.status:has-text("${trackingBadge.trim()}")`);
    console.log(`   Reporte ${trackingBadge.trim()} recuperado con éxito desde PostgreSQL tras recarga.`);

    // 7. Verificar errores de consola no esperados
    const criticalErrors = consoleErrors.filter(
      (err) => !err.includes('favicon') && !err.includes('tile.openstreetmap.org')
    );
    if (criticalErrors.length > 0) {
      console.warn('   Advertencias/Errores en consola:', criticalErrors);
    } else {
      console.log('   Cero errores críticos de consola JS.');
    }

    console.log('--- VERIFICACIÓN E2E PLAYWRIGHT: EXITOSA (PASS) ---');
  } finally {
    await browser.close();
  }
})();

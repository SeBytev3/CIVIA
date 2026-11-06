/**
 * CIVIA - Suite E2E de Verificación en Navegador (Playwright)
 * 
 * Ejecuta dos pruebas independientes:
 * 1. Flujo con Cámara Real en Vivo: captura de cuadro web, envío de fotografía,
 *    persistencia en PostgreSQL, radicado, descarga de imagen y verificación is_synthetic=false.
 * 2. Flujo con Muestra Sintética Oficial: selección de activo de catálogo, distintivo ético,
 *    persistencia en PostgreSQL, radicado, visualización contain e is_synthetic=true.
 * 
 * Totalmente portable: sin rutas absolutas y compatible con Chromium estándar, Chrome o Edge.
 */

const path = require('path');

let playwright;
try {
  playwright = require('playwright');
} catch {
  try {
    playwright = require(path.join(__dirname, '..', 'frontend', 'node_modules', 'playwright'));
  } catch {
    console.error('Playwright no se encuentra instalado.');
    console.error('Para ejecutar los tests E2E desde el host, ejecute:');
    console.error('  cd frontend && npm install && npx playwright install chromium');
    process.exit(1);
  }
}

const { chromium } = playwright;

async function launchBrowser() {
  const commonArgs = [
    '--use-fake-ui-for-media-stream',
    '--use-fake-device-for-media-stream',
  ];

  const channelOverride = process.env.PLAYWRIGHT_CHANNEL;
  if (channelOverride) {
    return await chromium.launch({ channel: channelOverride, headless: true, args: commonArgs });
  }

  // 1. Intentar Chromium estándar de Playwright
  try {
    return await chromium.launch({ headless: true, args: commonArgs });
  } catch (err) {
    // 2. Si Chromium no está descargado, probar canales del sistema (Edge o Chrome)
    try {
      return await chromium.launch({ channel: 'msedge', headless: true, args: commonArgs });
    } catch {
      return await chromium.launch({ channel: 'chrome', headless: true, args: commonArgs });
    }
  }
}

(async () => {
  console.log('================================================================');
  console.log(' CIVIA - Verificación E2E de Flujo Ciudadano y Muestras Demo');
  console.log('================================================================\n');

  const browser = await launchBrowser();
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    permissions: ['camera', 'geolocation'],
  });

  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  const baseUrl = process.env.CIVIA_FRONTEND_URL || 'http://127.0.0.1:5173';

  try {
    // =========================================================================
    // PRUEBA 1: Flujo con Cámara Real en Vivo (Fotografía Ciudadana Genuina)
    // =========================================================================
    console.log('[TEST 1/2] Iniciando prueba con Cámara en Vivo (Fotografía Ciudadana)...');
    await page.goto(baseUrl, { waitUntil: 'networkidle' });

    // Navegar a "+ Nuevo Reporte"
    await page.click('button:has-text("+ Nuevo Reporte")');
    await page.waitForSelector('text=Registrar Nuevo Reporte Ciudadano');

    // Activar cámara
    console.log('  1.1 Activando visor de cámara web...');
    await page.click('button:has-text("Tomar fotografía")');
    await page.waitForSelector('video');

    // Disparar captura
    console.log('  1.2 Capturando fotografía desde la cámara...');
    await page.click('button:has-text("Capturar fotografía ahora")');
    await page.waitForSelector('text=Archivo listo:');

    // Ingresar descripción ciudadana
    const realCitizenDesc = `Reporte ciudadano con captura directa de cámara en vivo sobre calzada de Cali [TEST-${Date.now()}].`;
    await page.fill('#rep-desc', realCitizenDesc);

    // Enviar formulario conservando la foto de la cámara
    console.log('  1.3 Enviando reporte con fotografía de cámara a PostgreSQL...');
    await page.click('button[type="submit"]');

    // Esperar transición a pestaña de seguimiento
    await page.waitForSelector('text=Seguimiento de Reporte mediante Código de Radicado', { timeout: 30000 });
    const realTrackingCode = (await page.textContent('.civia-badge.status')).trim();
    console.log(`  1.4 Reporte creado con radicado: ${realTrackingCode}`);

    // Verificar en la respuesta que is_synthetic es false para la foto real de la cámara
    const badgeText = await page.locator('.civia-badge-row').textContent();
    if (badgeText.includes('DATO SINTÉTICO') || badgeText.includes('DEMO SINTÉTICO')) {
      throw new Error(`Error: la fotografía de la cámara se marcó indebidamente como sintética en ${realTrackingCode}`);
    }
    console.log('  1.5 Verificado: La fotografía ciudadana real NO tiene marca sintética (is_synthetic=false).');

    // Recuperar la imagen almacenada a través del endpoint HTTP
    const photoImg = page.locator('img[alt^="Evidencia fotográfica"]');
    await photoImg.waitFor();
    const photoUrl = await photoImg.getAttribute('src');
    const fullPhotoUrl = new URL(photoUrl, baseUrl).toString();
    console.log(`  1.6 URL de la imagen en servidor: ${fullPhotoUrl}`);

    const photoResponse = await page.request.get(fullPhotoUrl);
    if (photoResponse.status() !== 200) {
      throw new Error(`Fallo al descargar la foto almacenada: HTTP ${photoResponse.status()}`);
    }
    const photoBytes = await photoResponse.body();
    if (photoBytes.length < 5000) {
      throw new Error(`La fotografía almacenada está vacía o truncada (${photoBytes.length} bytes).`);
    }
    console.log(`  1.7 Imagen almacenada descargada exitosamente (${photoBytes.length} bytes, HTTP 200).`);

    // Recargar página y comprobar persistencia tras recarga
    console.log('  1.8 Recargando página para verificar persistencia en PostgreSQL...');
    await page.reload({ waitUntil: 'networkidle' });
    await page.click('button:has-text("Seguimiento Radicado")');
    await page.fill('input[aria-label="Código de radicado"]', realTrackingCode);
    await page.click('button:has-text("Consultar Radicado")');
    await page.waitForSelector(`.civia-badge.status:has-text("${realTrackingCode}")`);
    console.log(`  1.9 Persistencia confirmada tras recarga para radicado ${realTrackingCode}.`);
    console.log('-> [TEST 1/2] EXITOSO (PASS)\n');

    // =========================================================================
    // PRUEBA 2: Flujo con Muestra Sintética Oficial (Demostración y Evaluación)
    // =========================================================================
    console.log('[TEST 2/2] Iniciando prueba con Muestra Sintética Oficial de Catálogo...');
    await page.click('button:has-text("+ Nuevo Reporte")');
    await page.waitForSelector('text=Registrar Nuevo Reporte Ciudadano');

    // Seleccionar muestra oficial de Poste / Cables (OTRO)
    console.log('  2.1 Seleccionando muestra sintética oficial (Poste / Cables)...');
    const demoSummary = page.locator('summary:has-text("Opciones de prueba")');
    if (await demoSummary.count() > 0) {
      await demoSummary.click();
      await page.waitForTimeout(200);
    }
    await page.click('button:has-text("Poste / Cables")');
    await page.waitForSelector('text=Imagen generada con IA · Simulación');

    // Verificar distintivo ético en la vista previa del formulario
    const previewBadgeCount = await page.locator('text=Imagen generada con IA · Simulación').count();
    if (previewBadgeCount < 1) {
      throw new Error('La vista previa del formulario no muestra el distintivo ético HTML.');
    }
    console.log('  2.2 Distintivo ético HTML visible en vista previa.');

    // Enviar el reporte
    console.log('  2.3 Enviando reporte sintético...');
    await page.click('button[type="submit"]');

    // Esperar transición a seguimiento
    await page.waitForSelector('text=Seguimiento de Reporte mediante Código de Radicado', { timeout: 30000 });
    const demoTrackingCode = (await page.textContent('.civia-badge.status')).trim();
    console.log(`  2.4 Reporte sintético creado con radicado: ${demoTrackingCode}`);

    // Verificar que is_synthetic es true (distintivo presente)
    const demoBadgeText = await page.locator('.civia-badge-row').textContent();
    if (!demoBadgeText.includes('DATO SINTÉTICO') && !demoBadgeText.includes('DEMO SINTÉTICO')) {
      throw new Error(`Error: la muestra oficial no se marcó como sintética en ${demoTrackingCode}`);
    }
    console.log('  2.5 Verificado: Muestra oficial tiene procedencia sintética certificada (is_synthetic=true).');

    // Verificar estilo objectFit: contain en la imagen de detalle
    const demoImg = page.locator('img[alt^="Evidencia fotográfica"]');
    await demoImg.waitFor();
    const objectFitValue = await demoImg.evaluate((el) => window.getComputedStyle(el).objectFit);
    if (objectFitValue !== 'contain') {
      throw new Error(`Error: estilo de imagen en detalle es '${objectFitValue}', esperado 'contain' para no recortar la franja ética.`);
    }
    console.log(`  2.6 Verificado: objectFit es '${objectFitValue}' (preserva la franja ética sin recorte).`);

    // Recargar página y comprobar persistencia
    console.log('  2.7 Recargando página para verificar persistencia...');
    await page.reload({ waitUntil: 'networkidle' });
    await page.click('button:has-text("Seguimiento Radicado")');
    await page.fill('input[aria-label="Código de radicado"]', demoTrackingCode);
    await page.click('button:has-text("Consultar Radicado")');
    await page.waitForSelector(`.civia-badge.status:has-text("${demoTrackingCode}")`);
    console.log(`  2.8 Persistencia de reporte sintético confirmada tras recarga.`);
    console.log('-> [TEST 2/2] EXITOSO (PASS)\n');

    console.log('================================================================');
    console.log(' RESUMEN: Ambas pruebas E2E (Cámara real + Muestra) superadas.');
    console.log('================================================================');
  } finally {
    await browser.close();
  }
})();

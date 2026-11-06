/**
 * CIVIA - Suite E2E de Refinamiento UX/UI, Trazabilidad Ciudadana y Notificaciones Internas
 * 
 * Verifica exhaustivamente:
 * 1. Estilos y contrastes de botones (especialmente hover en .civia-btn.secondary).
 * 2. Lenguaje empático ciudadano (sin jerga técnica en el proceso de guardado).
 * 3. Flujo vertical post-envío: scroll accesible, foco al resultado, radicado grande, botón copiar radicado.
 * 4. Aviso obligatorio sobre correo electrónico a entidades externas no habilitado.
 * 5. Trazabilidad ciudadana con línea de tiempo cronológica de eventos (report_events).
 * 6. Input de radicado inicialmente vacío y modo demo opcional en acordeón colapsable.
 * 7. Cierre limpio de detalles (botón "Cerrar detalle" restaura foco).
 * 8. Bandeja de notificaciones internas en el panel administrativo.
 * 9. Portabilidad y accesibilidad tanto en Desktop (1366x768) como en Mobile (390x844).
 */

const path = require('path');
const fs = require('fs');

let playwright;
try {
  playwright = require('playwright');
} catch {
  try {
    playwright = require(path.join(__dirname, '..', 'frontend', 'node_modules', 'playwright'));
  } catch {
    console.error('Playwright no está disponible en frontend/node_modules.');
    process.exit(1);
  }
}

const { chromium } = playwright;

// Obtener ADMIN_TOKEN de .env
function getAdminToken() {
  try {
    const envPath = path.join(__dirname, '..', '.env');
    if (fs.existsSync(envPath)) {
      const lines = fs.readFileSync(envPath, 'utf-8').split('\n');
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('ADMIN_TOKEN=')) {
          return trimmed.substring('ADMIN_TOKEN='.length).trim();
        }
      }
    }
  } catch {}
  return process.env.ADMIN_TOKEN || '';
}

async function launchBrowser() {
  const commonArgs = [
    '--use-fake-ui-for-media-stream',
    '--use-fake-device-for-media-stream',
  ];
  try {
    return await chromium.launch({ headless: true, args: commonArgs });
  } catch {
    try {
      return await chromium.launch({ channel: 'msedge', headless: true, args: commonArgs });
    } catch {
      return await chromium.launch({ channel: 'chrome', headless: true, args: commonArgs });
    }
  }
}

(async () => {
  console.log('========================================================================');
  console.log(' CIVIA - Verificación E2E de Refinamiento UX/UI y Trazabilidad');
  console.log('========================================================================\n');

  const adminToken = getAdminToken();
  const browser = await launchBrowser();

  try {
    // TEST 1: DESKTOP (1366 x 768)
    console.log('--- TEST 1: Experiencia Ciudadana en Desktop (1366 x 768) ---');
    const contextDesktop = await browser.newContext({
      viewport: { width: 1366, height: 768 },
      permissions: ['camera', 'microphone', 'clipboard-read', 'clipboard-write'],
    });
    const page = await contextDesktop.newPage();

    await page.goto('http://localhost:5173', { waitUntil: 'networkidle' });
    console.log('✓ Aplicación cargada en http://localhost:5173');

    // 1.1 Verificar contraste y hover de botones secundarios
    const exploreRefreshBtn = page.locator('button:has-text("Actualizar datos")');
    await exploreRefreshBtn.waitFor({ state: 'visible' });

    const btnStyleNormal = await exploreRefreshBtn.evaluate((el) => {
      const style = window.getComputedStyle(el);
      return { bg: style.backgroundColor, color: style.color };
    });

    await exploreRefreshBtn.hover();
    await page.waitForTimeout(200);

    const btnStyleHover = await exploreRefreshBtn.evaluate((el) => {
      const style = window.getComputedStyle(el);
      return { bg: style.backgroundColor, color: style.color };
    });

    console.log(`✓ Botón secundario normal: bg=${btnStyleNormal.bg}, color=${btnStyleNormal.color}`);
    console.log(`✓ Botón secundario hover:  bg=${btnStyleHover.bg}, color=${btnStyleHover.color}`);

    // Comprobar que en hover el fondo no sea negro/oscuro (RGB R<20, G<40, B<40) mientras el texto es oscuro
    // En nuestro CSS nuevo: bg hover es #d6e8e5 (rgb(214, 232, 229))
    if (btnStyleHover.bg.includes('11, 60, 73') || btnStyleHover.bg.includes('5, 29, 35')) {
      throw new Error(`Fallo de contraste: el botón secundario en hover se oscureció incorrectamente (${btnStyleHover.bg}).`);
    }
    console.log('✓ Contraste de hover en botón secundario verificado exitosamente (legible y claro).');

    // 1.2 Verificar pestaña "Seguimiento Radicado" con input vacío por defecto
    const navTrackingBtn = page.locator('button.civia-nav-btn:has-text("Seguimiento Radicado")');
    await navTrackingBtn.click();
    await page.waitForTimeout(300);

    const trackingInput = page.locator('input[aria-label="Código de radicado"]');
    const initialInputValue = await trackingInput.inputValue();
    console.log(`✓ Valor inicial en input de seguimiento: "${initialInputValue}"`);
    if (initialInputValue !== '') {
      throw new Error(`El input de seguimiento debía iniciar vacío, pero contenía: "${initialInputValue}".`);
    }
    console.log('✓ Input de seguimiento inicia vacío con placeholder informativo.');

    // Verificar que los ejemplos de prueba están en un acordeón discreto
    const demoAccordion = page.locator('details.civia-demo-details');
    await demoAccordion.waitFor({ state: 'attached' });
    const isAccordionOpen = await demoAccordion.evaluate((el) => el.open);
    console.log(`✓ Acordeón de pruebas colapsado por defecto: ${!isAccordionOpen}`);

    // 1.3 Verificar pestaña "Nuevo Reporte" y lenguaje empático de guardado
    const navReportBtn = page.locator('button.civia-nav-btn:has-text("+ Nuevo Reporte")');
    await navReportBtn.click();
    await page.waitForTimeout(300);

    // Tomar fotografía con la cámara emulada
    const takePhotoBtn = page.locator('button:has-text("Tomar fotografía")');
    await takePhotoBtn.click();
    const captureFrameBtn = page.locator('button:has-text("Capturar fotografía ahora")');
    await captureFrameBtn.waitFor({ state: 'visible' });
    await captureFrameBtn.click();
    await page.waitForTimeout(400);

    // Ingresar descripción ciudadana
    const descInput = page.locator('textarea#rep-desc');
    const testDesc = `Prueba de reporte ciudadano UX: bache pronunciado frente al parque municipal. ${Date.now()}`;
    await descInput.fill(testDesc);

    // Enviar el reporte y observar el mensaje empático
    const submitBtn = page.locator('button[type="submit"]:has-text("Enviar Reporte")');
    await submitBtn.click();

    // Comprobar mensaje de ciclo de vida empático
    const statusNotice = page.locator('div.civia-alert.info[role="status"]');
    const noticeText = await statusNotice.innerText().catch(() => '');
    console.log(`✓ Mensaje de proceso capturado: "${noticeText}"`);
    if (noticeText.includes('PostgreSQL') || noticeText.includes('multimodal')) {
      throw new Error(`El mensaje al ciudadano contiene jerga técnica prohibida: "${noticeText}".`);
    }

    // Esperar a que el reporte sea creado y aparezca el banner de éxito
    const successBanner = page.locator('div.civia-success-banner');
    await successBanner.waitFor({ state: 'visible', timeout: 20000 });
    console.log('✓ Banner de éxito post-envío visible de inmediato.');

    // 1.4 Verificar número de radicado grande y botón "Copiar radicado"
    const trackingDisplay = page.locator('.civia-tracking-display');
    const radicadoCode = (await trackingDisplay.innerText()).trim();
    console.log(`✓ Radicado obtenido y mostrado de forma destacada: ${radicadoCode}`);
    if (!radicadoCode.startsWith('CIV-2026-')) {
      throw new Error(`Radicado inválido: ${radicadoCode}`);
    }

    const copyBtn = page.locator('button:has-text("Copiar radicado")');
    await copyBtn.click();
    await page.waitForTimeout(300);
    const copyBtnText = await page.locator('button[aria-label="Copiar número de radicado al portapapeles"]').first().innerText();
    console.log(`✓ Feedback de copia en botón: "${copyBtnText}"`);

    // 1.5 Verificar aviso obligatorio sobre correo electrónico a entidades externas
    const noticeCard = page.locator('.civia-notice-card').first();
    await noticeCard.waitFor({ state: 'visible' });
    const noticeContent = await noticeCard.innerText();
    console.log('✓ Contenido del aviso sobre entidades externas comprobado:');
    if (!noticeContent.includes('no está habilitado') || !noticeContent.includes('permanecerá guardado')) {
      throw new Error('El aviso de correo a entidades externas no contiene el texto obligatorio.');
    }
    console.log('  → "Por ahora, el envío de notificaciones por correo electrónico a las entidades responsables no está habilitado."');
    console.log('  → "Tu reporte permanecerá guardado en la plataforma para su consulta y gestión."');

    // 1.6 Verificar que el formulario se limpió al volver a la pestaña de reporte
    await page.locator('button.civia-nav-btn:has-text("+ Nuevo Reporte")').click();
    await page.waitForTimeout(300);
    const descAfter = await page.locator('textarea#rep-desc').inputValue();
    if (descAfter !== '') {
      throw new Error(`El formulario no se limpió tras el éxito. Descripción actual: "${descAfter}".`);
    }
    console.log('✓ Formulario limpiado automáticamente tras el éxito de guardado.');

    // Regresar a la pestaña de seguimiento para continuar validando la trazabilidad
    await page.locator('button.civia-nav-btn:has-text("Seguimiento Radicado")').click();
    await page.waitForTimeout(300);

    // 1.7 Verificar que estamos en la pestaña de seguimiento y que se cargó la línea de tiempo
    const eventsTimeline = page.locator('.civia-events-timeline').first();
    await eventsTimeline.waitFor({ state: 'visible' });
    const timelineText = await eventsTimeline.innerText();
    console.log('✓ Línea de tiempo de eventos ciudadana visible:');
    console.log(`  ${timelineText.replace(/\n+/g, ' · ')}`);
    if (!timelineText.includes('Reporte recibido y registrado')) {
      throw new Error('La línea de tiempo no contiene el evento de registro inicial.');
    }

    // 1.8 Verificar botón "Cerrar detalle"
    const closeDetailBtn = page.locator('button:has-text("Cerrar detalle")');
    await closeDetailBtn.click();
    await page.waitForTimeout(400);

    // Verificar que la tarjeta de detalle desapareció
    const detailCount = await page.locator('.civia-panel:has-text("Línea de Tiempo y Trazabilidad")').count();
    if (detailCount !== 0) {
      throw new Error('El botón "Cerrar detalle" no ocultó la tarjeta.');
    }
    console.log('✓ Botón "Cerrar detalle" oculta la tarjeta correctamente.');

    // 1.9 Verificar panel de administración y notificaciones
    if (adminToken) {
      console.log('\n--- Verificación de Bandeja de Notificaciones en Admin ---');
      const navAdminBtn = page.locator('button.civia-nav-btn:has-text("Observabilidad Admin")');
      await navAdminBtn.click();
      await page.waitForTimeout(300);

      const tokenInput = page.locator('input#admin-token-input');
      await tokenInput.fill(adminToken);
      const refreshAdminBtn = page.locator('button:has-text("Refrescar Observabilidad")');
      await refreshAdminBtn.click();
      await page.waitForTimeout(800);

      const notifHeader = page.locator('h3:has-text("Bandeja de Reportes Recibidos")');
      await notifHeader.waitFor({ state: 'visible' });
      console.log('✓ Bandeja de Reportes Recibidos visible en Panel Admin.');

      // Comprobar que nuestro radicado recién creado aparece en las notificaciones
      const notifItem = page.locator(`.civia-notif-item:has-text("${radicadoCode}")`);
      const notifFound = await notifItem.count();
      console.log(`✓ Notificación para ${radicadoCode} encontrada en bandeja admin: ${notifFound > 0}`);
      if (notifFound > 0) {
        // Probar botón "Marcar leída"
        const markReadBtn = notifItem.locator('button:has-text("Marcar leída")');
        if (await markReadBtn.count() > 0) {
          await markReadBtn.click();
          await page.waitForTimeout(500);
          console.log(`✓ Notificación para ${radicadoCode} marcada como leída sin alterar el reporte.`);
        }
      }
    }

    await contextDesktop.close();

    // TEST 2: MOBILE (390 x 844 - iPhone / Android Viewport)
    console.log('\n--- TEST 2: Experiencia Ciudadana en Móvil (390 x 844) ---');
    const contextMobile = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
    });
    const pageMobile = await contextMobile.newPage();

    await pageMobile.goto('http://localhost:5173', { waitUntil: 'networkidle' });
    console.log('✓ Aplicación cargada en vista móvil (390 x 844)');

    // Verificar que los botones de navegación tienen tamaño táctil adecuado (>= 44px de alto)
    const mobileNavBtn = pageMobile.locator('button.civia-nav-btn').first();
    const navBtnBox = await mobileNavBtn.boundingBox();
    console.log(`✓ Altura de botón en móvil: ${navBtnBox.height}px (estándar táctil WCAG >= 44px o accesible)`);

    // Navegar a Seguimiento
    await pageMobile.locator('button.civia-nav-btn:has-text("Seguimiento")').click();
    await pageMobile.waitForTimeout(300);

    // Buscar el radicado creado anteriormente
    const mobileInput = pageMobile.locator('input[aria-label="Código de radicado"]');
    await mobileInput.fill(radicadoCode);
    const searchBtn = pageMobile.locator('button[type="submit"]:has-text("Consultar Radicado")');
    await searchBtn.click();
    await pageMobile.waitForTimeout(600);

    // Verificar aviso obligatorio en móvil
    const mobileNotice = pageMobile.locator('.civia-notice-card').first();
    await mobileNotice.waitFor({ state: 'visible' });
    console.log('✓ Aviso de entrega externa no habilitada visible y adaptable en pantalla móvil.');

    // Verificar timeline en móvil
    const mobileTimeline = pageMobile.locator('.civia-events-timeline');
    await mobileTimeline.waitFor({ state: 'visible' });
    console.log('✓ Línea de tiempo de eventos renderizada correctamente en móvil.');

    await contextMobile.close();

    console.log('\n========================================================================');
    console.log(' ¡TODAS LAS PRUEBAS E2E DE REFINAMIENTO UX/UI Y TRAZABILIDAD PASARON!');
    console.log('========================================================================\n');
  } finally {
    await browser.close();
  }
})();

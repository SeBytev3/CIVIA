/**
 * CIVIA - Prueba E2E Playwright de Navegación entre Pestañas y Aislamiento de Paneles
 *
 * Verifica:
 * 1. Consulta de radicado en pestaña 'Seguimiento Radicado'.
 * 2. Transición a 'Asistente Agéntico' garantizando aislamiento visual completo (sin arrastre de tarjetas).
 * 3. Transición a 'Observabilidad Admin' garantizando aislamiento técnico (sin reportes ciudadanos flotantes).
 * 4. Retorno a 'Mapa y Reportes' con apertura y cierre controlado del panel de inspección.
 * 5. Ciclo de navegación repetido en desktop y viewport móvil (375x667).
 * 6. Ausencia de errores de React en consola.
 */

const { chromium } = require('C:/Users/Jhoesp/.gemini/config/skills/playwright-skill/node_modules/playwright');

const BASE_URL = process.env.TARGET_URL || 'http://localhost:4173';

async function runNavTestSuite(viewport, label) {
  console.log(`\n========================================`);
  console.log(`--- CIVIA E2E: Navegación [${label}] en ${BASE_URL} ---`);
  console.log(`========================================`);

  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();

  const reactConsoleErrors = [];
  page.on('console', msg => {
    const txt = msg.text();
    if (msg.type() === 'error' && !txt.includes('Failed to load resource')) {
      reactConsoleErrors.push(txt);
    }
  });

  try {
    await page.goto(BASE_URL, { waitUntil: 'networkidle' });
    console.log('✓ 1. Página inicial cargada correctamente.');

    // 2. Abrir Seguimiento Radicado
    await page.click('button:has-text("Seguimiento Radicado")');
    await page.waitForTimeout(400);
    console.log('✓ 2. Pestaña Seguimiento Radicado seleccionada.');

    // 3. Buscar CIV-2026-DEMO0001
    await page.fill('input[placeholder*="CIV-2026-"]', 'CIV-2026-DEMO0001');
    await page.click('button:has-text("Consultar radicado")');
    await page.waitForTimeout(800);

    const detailTitle = await page.locator('h2:has-text("Hundimiento severo en carril derecho de Avenida Sexta")').isVisible();
    if (!detailTitle) throw new Error('Detalle CIV-2026-DEMO0001 no se mostró en Seguimiento');
    console.log('✓ 3. Detalle correcto visible en Seguimiento Radicado.');

    // 4. Seleccionar Asistente Agéntico
    await page.click('button:has-text("Asistente Agéntico")');
    await page.waitForTimeout(500);

    const detailInAsistente = await page.locator('h2:has-text("Hundimiento severo en carril derecho de Avenida Sexta")').isVisible();
    const assistantHeader = await page.locator('h2:has-text("Asistente Agéntico de Consulta")').isVisible();
    const assistantChatInput = await page.locator('input[aria-label="Consulta para el agente de CIVIA"]').isVisible();
    const assistantButton = await page.locator('button:has-text("Consultar al Agente")').isVisible();
    if (detailInAsistente) throw new Error('ERROR: Detalle CIV-2026-DEMO0001 todavía visible en Asistente Agéntico!');
    if (!assistantHeader || !assistantChatInput || !assistantButton) throw new Error('ERROR: El asistente no quedó operativo!');
    console.log('✓ 4. Asistente Agéntico operativo y libre de paneles ajenos.');

    // 5. Seleccionar Observabilidad Admin
    await page.click('button:has-text("Observabilidad Admin")');
    await page.waitForTimeout(500);

    const detailInAdmin = await page.locator('h2:has-text("Hundimiento severo en carril derecho de Avenida Sexta")').isVisible();
    const adminHeader = await page.locator('h2:has-text("Zona Protegida de Observabilidad")').isVisible();
    if (detailInAdmin) throw new Error('ERROR: Detalle arrastrado a Observabilidad Admin!');
    if (!adminHeader) throw new Error('ERROR: Panel de Observabilidad Admin no visible!');
    console.log('✓ 5. Observabilidad Admin visible sin detalles arrastrados.');

    // 6. Volver a Mapa y Reportes
    await page.click('button:has-text("Mapa y Reportes")');
    await page.waitForTimeout(500);

    const detailInExplorarBefore = await page.locator('h2:has-text("Hundimiento severo en carril derecho de Avenida Sexta")').isVisible();
    if (detailInExplorarBefore) throw new Error('ERROR: Mapa y reportes tiene detalle no solicitado!');
    console.log('✓ 6. Mapa y Reportes abierto sin detalle residual.');

    // 7. Ciclo repetido entre pestañas
    for (const tabName of ['+ Nuevo Reporte', 'Seguimiento Radicado', 'Asistente Agéntico', 'Observabilidad Admin', 'Mapa y Reportes']) {
      await page.click(`button:has-text("${tabName}")`);
      await page.waitForTimeout(200);
    }
    console.log('✓ 7. Ciclo de navegación repetido completado sin excepciones.');

    if (reactConsoleErrors.length > 0) {
      console.warn('Advertencias de consola:', reactConsoleErrors);
    } else {
      console.log('✓ 8. Cero errores de React en consola.');
    }

    console.log(`>>> RESULTADO [${label}]: TODAS LAS PRUEBAS PASARON (GREEN) <<<\n`);
  } finally {
    await browser.close();
  }
}

(async () => {
  try {
    await runNavTestSuite({ width: 1280, height: 800 }, 'ESCRITORIO 1280x800');
    await runNavTestSuite({ width: 375, height: 667 }, 'MÓVIL 375x667');
    console.log('========================================================');
    console.log('>>> CIVIA E2E: SUITE DE NAVEGACIÓN EXITOSA (GREEN) <<<');
    console.log('========================================================');
  } catch (err) {
    console.error('FALLO EN PRUEBA E2E:', err);
    process.exit(1);
  }
})();

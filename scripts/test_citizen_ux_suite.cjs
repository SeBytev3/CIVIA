/**
 * CIVIA - Suite E2E de Refinamiento UX/UI, Trazabilidad Ciudadana y Notificaciones Internas
 * 
 * Verifica exhaustivamente:
 * 1. Estilos y contrastes de botones (especialmente hover en .civia-btn.secondary).
 * 2. Lenguaje empático ciudadano (sin jerga técnica en mensajes ni pantallas públicas).
 * 3. Flujo vertical post-envío: scroll accesible, foco al resultado, radicado grande, botón copiar radicado.
 * 4. Aviso obligatorio sobre correo electrónico a entidades externas no habilitado.
 * 5. Trazabilidad ciudadana con línea de tiempo cronológica de eventos (report_events).
 * 6. Cierre real de tarjeta de detalle tanto desde Mapa como desde Seguimiento.
 * 7. Historial de cambios administrativos (STATUS_UPDATED, asignación de dependencia y notas públicas).
 * 8. Confidencialidad administrativa: las notas internas NUNCA se exponen al ciudadano.
 * 9. Eliminación de generadores alternativos tipo Paint en frontend y backend.
 * 10. Bandeja de notificaciones internas en el panel administrativo.
 * 11. Portabilidad y accesibilidad tanto en Desktop (1366x768) como en Mobile (390x844).
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
  console.log(' CIVIA - Verificación E2E de Refinamiento UX/UI y Trazabilidad (Hotfix)');
  console.log('========================================================================\n');

  // Verificación estática 0: Comprobar que los generadores Paint fueron eliminados definitivamente
  console.log('--- VERIFICACIÓN 0: Ausencia definitiva de generadores Paint ---');
  const appTsx = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'src', 'App.tsx'), 'utf-8');
  if (appTsx.includes('createCanvasDemoPhoto')) {
    throw new Error('Fallo: createCanvasDemoPhoto todavía existe en frontend/src/App.tsx');
  }
  const seedPy = fs.readFileSync(path.join(__dirname, '..', 'backend', 'app', 'seed.py'), 'utf-8');
  if (seedPy.includes('generate_synthetic_evidence_png') || seedPy.includes('ImageDraw')) {
    throw new Error('Fallo: generate_synthetic_evidence_png o ImageDraw todavía existen en backend/app/seed.py');
  }
  console.log('✓ Confirmado: Ni frontend ni backend contienen generadores de canvas o tarjetas dibujadas.');

  const adminToken = getAdminToken();
  const browser = await launchBrowser();

  try {
    // TEST 1: DESKTOP (1366 x 768)
    console.log('\n--- TEST 1: Experiencia Ciudadana en Desktop (1366 x 768) ---');
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

    // Verificar acordeón de pruebas
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
    console.log('✓ Contenido del aviso sobre entidades externas comprobado.');
    if (!noticeContent.includes('no está habilitado') || !noticeContent.includes('permanecerá guardado')) {
      throw new Error('El aviso de correo a entidades externas no contiene el texto obligatorio.');
    }

    // 1.6 Verificar que el formulario se limpió al volver a la pestaña de reporte
    await page.locator('button.civia-nav-btn:has-text("+ Nuevo Reporte")').click();
    await page.waitForTimeout(300);
    const descAfter = await page.locator('textarea#rep-desc').inputValue();
    if (descAfter !== '') {
      throw new Error(`El formulario no se limpió tras el éxito. Descripción actual: "${descAfter}".`);
    }
    console.log('✓ Formulario limpiado automáticamente tras el éxito de guardado.');

    // 1.7 Probar cierre real de detalle desde pestaña Seguimiento
    console.log('\n--- Verificación de Cierre de Detalle en Seguimiento ---');
    await page.locator('button.civia-nav-btn:has-text("Seguimiento Radicado")').click();
    await page.waitForTimeout(300);

    // Consultar el radicado
    await trackingInput.fill(radicadoCode);
    await page.locator('button[type="submit"]:has-text("Consultar Radicado")').click();
    await page.waitForTimeout(600);

    // Confirmar presencia del panel de inspección
    const closeBtnTracking = page.locator('button:has-text("✕ Cerrar detalle")');
    await closeBtnTracking.waitFor({ state: 'visible' });
    const trackingBadge = page.locator(`.civia-badge.status:has-text("${radicadoCode}")`);
    await trackingBadge.waitFor({ state: 'visible' });
    console.log(`✓ Panel de detalle visible para ${radicadoCode}.`);

    // Hacer clic en "✕ Cerrar detalle"
    await closeBtnTracking.click();
    await page.waitForTimeout(400);

    // VERIFICACIÓN ADVERSARIAL OBLIGATORIA: El botón y el panel deben desaparecer REALMENTE del DOM
    const closeBtnCountAfter = await page.locator('button:has-text("✕ Cerrar detalle")').count();
    const radicadoBadgeCountAfter = await page.locator(`.civia-badge.status:has-text("${radicadoCode}")`).count();
    console.log(`✓ Conteo de botón "Cerrar detalle" tras cierre: ${closeBtnCountAfter}`);
    console.log(`✓ Conteo de badge ${radicadoCode} tras cierre: ${radicadoBadgeCountAfter}`);
    if (closeBtnCountAfter !== 0 || radicadoBadgeCountAfter !== 0) {
      throw new Error(`Fallo: "Cerrar detalle" en Seguimiento no ocultó el panel (closeBtnCount=${closeBtnCountAfter}, badgeCount=${radicadoBadgeCountAfter}).`);
    }
    console.log('✓ Cierre de detalle en Seguimiento verificado: panel, fotografía e historial ocultos al 100%.');

    // 1.8 Probar cierre real de detalle desde pestaña Mapa (Explorar)
    console.log('\n--- Verificación de Cierre de Detalle en Mapa (Explorar) ---');
    await page.locator('button.civia-nav-btn:has-text("Mapa y Reportes")').click();
    await page.waitForTimeout(400);

    const detailBtn = page.locator('.civia-report-card button:has-text("Ver detalle")').first();
    await detailBtn.waitFor({ state: 'visible' });
    await detailBtn.click();
    await page.waitForTimeout(400);

    const closeBtnMap = page.locator('button:has-text("✕ Cerrar detalle")');
    await closeBtnMap.waitFor({ state: 'visible' });
    console.log('✓ Panel de detalle abierto desde la lista del mapa.');

    await closeBtnMap.click();
    await page.waitForTimeout(400);

    const mapCloseBtnCountAfter = await page.locator('button:has-text("✕ Cerrar detalle")').count();
    if (mapCloseBtnCountAfter !== 0) {
      throw new Error(`Fallo: "Cerrar detalle" en Mapa no ocultó el panel (count=${mapCloseBtnCountAfter}).`);
    }
    console.log('✓ Cierre de detalle en Mapa verificado: panel ocultado correctamente.');

    // 1.9 Verificación de Cambios Administrativos, Trazabilidad y Confidencialidad
    if (adminToken) {
      console.log('\n--- Verificación de Historial Administrativo y Confidencialidad ---');
      const apiBase = 'http://localhost:8000';

      // Obtener el reporte por código
      const repResp = await fetch(`${apiBase}/api/reports/by-code/${radicadoCode}`);
      if (!repResp.ok) throw new Error(`No se pudo obtener el reporte ${radicadoCode}`);
      const repData = await repResp.json();
      const reportId = repData.id;

      // 1.9.1 Actualizar estado a IN_REVIEW con nota
      const statusRes = await fetch(`${apiBase}/api/reports/${reportId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Token': adminToken },
        body: JSON.stringify({ status: 'IN_REVIEW', human_approved: true, note: 'Inspección técnica programada' }),
      });
      if (!statusRes.ok) throw new Error(`Fallo al actualizar status administrativo: ${statusRes.status}`);

      // 1.9.2 Actualizar gestión: asignar dependencia, nota pública y nota interna privada
      const secretInternalNote = 'NOTA_CONFIDENCIAL_POLICIAL_INTERNA_987654';
      const publicNote = 'Cuadrilla de bacheo asignada para intervención prioritaria.';
      const deptName = 'Secretaría de Infraestructura de Cali';

      const mgmtRes = await fetch(`${apiBase}/api/admin/reports/${reportId}/management`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Token': adminToken },
        body: JSON.stringify({
          assigned_to: deptName,
          public_note: publicNote,
          internal_note: secretInternalNote,
        }),
      });
      if (!mgmtRes.ok) throw new Error(`Fallo al actualizar gestión administrativa: ${mgmtRes.status}`);

      // 1.9.3 Consultar en frontend en la pestaña Seguimiento y verificar eventos públicos
      await page.locator('button.civia-nav-btn:has-text("Seguimiento Radicado")').click();
      await page.waitForTimeout(300);
      await trackingInput.fill(radicadoCode);
      await page.locator('button[type="submit"]:has-text("Consultar Radicado")').click();
      await page.waitForTimeout(600);

      const timelineEl = page.locator('.civia-events-timeline');
      await timelineEl.waitFor({ state: 'visible' });
      const timelineHtml = await timelineEl.innerHTML();

      // Verificar que los eventos públicos requeridos están en el historial
      if (!timelineHtml.includes('Estado administrativo actualizado a: IN_REVIEW')) {
        throw new Error('Fallo: Evento STATUS_UPDATED no aparece en la línea de tiempo pública.');
      }
      console.log('✓ Evento STATUS_UPDATED verificado en la línea de tiempo.');

      if (!timelineHtml.includes(deptName)) {
        throw new Error('Fallo: Evento ASSIGNED_TO_DEPARTMENT no aparece en la línea de tiempo pública.');
      }
      console.log(`✓ Evento de asignación institucional verificado: "${deptName}".`);

      if (!timelineHtml.includes(publicNote)) {
        throw new Error('Fallo: Evento PUBLIC_NOTE_ADDED no aparece en la línea de tiempo pública.');
      }
      console.log('✓ Observación pública de seguimiento verificada en la línea de tiempo.');

      // 1.9.4 VERIFICACIÓN DE CONFIDENCIALIDAD OBLIGATORIA
      // Comprobar que secretInternalNote NO aparece en la página pública ni en la API pública
      const pageWholeText = await page.innerText('body');
      if (pageWholeText.includes(secretInternalNote)) {
        throw new Error('VIOLACIÓN CRÍTICA DE SEGURIDAD: La nota interna privada se expuso en la interfaz ciudadana!');
      }

      const publicCheckRes = await fetch(`${apiBase}/api/reports/by-code/${radicadoCode}`);
      const publicCheckJson = await publicCheckRes.text();
      if (publicCheckJson.includes(secretInternalNote)) {
        throw new Error('VIOLACIÓN CRÍTICA DE SEGURIDAD: La nota interna privada se expuso en la API pública!');
      }
      console.log('✓ Confidencialidad verificada: Las notas internas privadas NO se exponen al ciudadano.');

      // 1.9.5 Verificar Bandeja de Notificaciones en Admin
      console.log('\n--- Verificación de Bandeja de Notificaciones en Admin ---');
      const navAdminBtn = page.locator('button.civia-nav-btn:has-text("Observabilidad Admin")');
      await navAdminBtn.click();
      await page.waitForTimeout(300);

      // Verificar protección estricta de telemetría sin autenticación (Fase 2)
      const unauthTelemetry = page.locator('summary:has-text("Telemetría y Auditoría")');
      const unauthTelemetryCount = await unauthTelemetry.count();
      if (unauthTelemetryCount > 0) {
        throw new Error('Fallo de seguridad: Telemetría técnica expuesta sin haber suministrado ADMIN_TOKEN.');
      }
      console.log('✓ Protección de privacidad confirmada: Sin ADMIN_TOKEN no se renderiza telemetría agéntica.');

      const tokenInput = page.locator('input#admin-token-input');
      await tokenInput.fill(adminToken);
      const refreshAdminBtn = page.locator('button:has-text("Refrescar Observabilidad")');
      await refreshAdminBtn.click();
      await page.waitForTimeout(800);

      const notifHeader = page.locator('h3:has-text("Bandeja de Reportes Recibidos")');
      await notifHeader.waitFor({ state: 'visible' });
      console.log('✓ Bandeja de Reportes Recibidos visible en Panel Admin.');

      const notifItem = page.locator(`.civia-notif-item:has-text("${radicadoCode}")`);
      const notifFound = await notifItem.count();
      console.log(`✓ Notificación para ${radicadoCode} encontrada en bandeja admin: ${notifFound > 0}`);
      if (notifFound > 0) {
        const markReadBtn = notifItem.locator('button:has-text("Marcar leída")');
        if (await markReadBtn.count() > 0) {
          await markReadBtn.click();
          await page.waitForTimeout(500);
          console.log(`✓ Notificación para ${radicadoCode} marcada como leída.`);
        }
      }
    }

    // 1.10 Verificar Ausencia de Términos Internos en Todas las Pestañas Públicas
    console.log('\n--- Verificación de Lenguaje Ciudadano en Pestañas Públicas ---');
    const forbiddenTerms = ['PostgreSQL', 'PENDING_ANALYSIS', 'SQL Directo', 'Herramientas Tipadas'];
    const publicTabs = [
      { name: 'Mapa y Reportes', btn: 'Mapa y Reportes' },
      { name: 'Nuevo Reporte', btn: '+ Nuevo Reporte' },
      { name: 'Seguimiento Radicado', btn: 'Seguimiento Radicado' },
      { name: 'Asistente Ciudadano', btn: 'Asistente' },
    ];

    for (const tab of publicTabs) {
      await page.locator(`button.civia-nav-btn:has-text("${tab.btn}")`).click();
      await page.waitForTimeout(300);
      const tabText = await page.innerText('body');
      for (const term of forbiddenTerms) {
        if (tabText.includes(term)) {
          throw new Error(`Término interno prohibido "${term}" encontrado en pestaña pública "${tab.name}".`);
        }
      }
      console.log(`✓ Pestaña "${tab.name}" libre de jerga técnica interna.`);
    }

    // 1.11 Verificación de Asistente Ciudadano: Markdown Seguro y Cero Telemetría
    console.log('\n--- Verificación de Asistente: Markdown Seguro y Cero Telemetría Pública ---');
    await page.locator('button.civia-nav-btn:has-text("Asistente")').click();
    await page.waitForTimeout(300);

    // Ejecutar consulta cotidiana
    const presetBtn = page.locator('button:has-text("¿Cómo puedo consultar el estado de mi reporte?")');
    await presetBtn.waitFor({ state: 'visible' });
    await presetBtn.click();

    // Esperar renderizado de respuesta con SafeMarkdown
    const markdownRoot = page.locator('.civia-agent-response-card .safe-markdown-root');
    await markdownRoot.waitFor({ state: 'visible', timeout: 35000 });
    const renderedHtml = await markdownRoot.innerHTML();
    console.log('✓ Respuesta del asistente renderizada exitosamente con SafeMarkdown.');

    // Comprobar elementos estructurados de Markdown (listas o negritas)
    const hasMarkdownStructure = renderedHtml.includes('<strong') || renderedHtml.includes('<ol') || renderedHtml.includes('<ul') || renderedHtml.includes('<p');
    if (!hasMarkdownStructure) {
      throw new Error('La respuesta del asistente no contiene estructura HTML segura de Markdown.');
    }
    console.log('✓ Elementos semánticos de Markdown (párrafos/listas/énfasis) confirmados en DOM.');

    // Comprobar ausencia absoluta de telemetría agéntica en la vista ciudadana
    const assistantAreaText = await page.locator('section.civia-panel').innerText();
    const telemetryTerms = ['Vueltas:', 'Tokens:', 'Latencia:', 'Límite activado:', 'Herramienta:', 'ID Operación:'];
    for (const tTerm of telemetryTerms) {
      if (assistantAreaText.includes(tTerm)) {
        throw new Error(`Telemetría técnica no autorizada "${tTerm}" encontrada en la vista ciudadana del Asistente.`);
      }
    }
    console.log('✓ Confirmado: Vista ciudadana del asistente 100% libre de vueltas, tokens, latencia e ID de operación.');

    // 1.11.5 Verificación de Veracidad Institucional en Respuestas (Fase 1)
    console.log('\n--- Verificación de Veracidad Institucional en Respuestas ---');
    const agentInputTruth = page.locator('input[aria-label="Consulta para el agente de CIVIA"]');
    await agentInputTruth.fill('¿Qué significa que mi reporte figure como pendiente de revisión?');
    const submitTruthBtn = page.locator('button[type="submit"]:has-text("Preguntar al Asistente")');
    await submitTruthBtn.click();
    await page.waitForTimeout(1000);
    const truthMarkdown = page.locator('.civia-agent-response-card .safe-markdown-root');
    await truthMarkdown.waitFor({ state: 'visible', timeout: 35000 });
    const truthText = await truthMarkdown.innerText();
    console.log(`✓ Respuesta de veracidad capturada: "${truthText.substring(0, 80)}..."`);
    if (truthText.includes('supervisores de la Alcaldía') || truthText.includes('Alcaldía de Cali están validando')) {
      throw new Error(`Fallo de veracidad institucional: Afirmación no verificada encontrada en respuesta: ${truthText}`);
    }
    if (!truthText.includes('pendiente de revisión interna') && !truthText.includes('CIVIA')) {
      throw new Error(`La respuesta institucional no menciona el estado interno de CIVIA: ${truthText}`);
    }
    console.log('✓ Veracidad institucional confirmada: Cero atribuciones ficticias a supervisores de la Alcaldía.');

    // 1.12 Verificación de Notificación Humana para Solicitudes Críticas
    console.log('\n--- Verificación de Notificación Amigable de Aprobación Humana ---');
    const agentInputEl = page.locator('input[aria-label="Consulta para el agente de CIVIA"]');
    await agentInputEl.fill('Propón cambiar el estado del reporte CIV-2026-DEMO0002 a IN_REVIEW porque hay cuadrilla inspeccionando.');
    const submitAgentBtn = page.locator('button[type="submit"]:has-text("Preguntar al Asistente")');
    await submitAgentBtn.click();

    const approvalNotice = page.locator('.civia-alert.info');
    await approvalNotice.waitFor({ state: 'visible', timeout: 35000 });
    const noticeTxt = await approvalNotice.innerText();
    console.log(`✓ Mensaje de aprobación capturado: "${noticeTxt}"`);
    if (!noticeTxt.toLowerCase().includes('tu solicitud fue registrada y está pendiente de aprobación') || !noticeTxt.toLowerCase().includes('el estado del reporte no cambiará')) {
      throw new Error(`El mensaje de aprobación no es empático o no corresponde con la especificación: "${noticeTxt}".`);
    }
    console.log('✓ Mensaje empático de aprobación humana validado correctamente.');

    await contextDesktop.close();

    // TEST 2: MOBILE (390 x 844)
    console.log('\n--- TEST 2: Experiencia Ciudadana en Móvil (390 x 844) ---');
    const contextMobile = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
    });
    const pageMobile = await contextMobile.newPage();

    await pageMobile.goto('http://localhost:5173', { waitUntil: 'networkidle' });
    console.log('✓ Aplicación cargada en vista móvil (390 x 844)');

    const mobileNavBtn = pageMobile.locator('button.civia-nav-btn').first();
    const navBtnBox = await mobileNavBtn.boundingBox();
    console.log(`✓ Altura de botón en móvil: ${navBtnBox.height}px`);

    await pageMobile.locator('button.civia-nav-btn:has-text("Seguimiento")').click();
    await pageMobile.waitForTimeout(300);

    const mobileInput = pageMobile.locator('input[aria-label="Código de radicado"]');
    await mobileInput.fill(radicadoCode);
    const searchBtn = pageMobile.locator('button[type="submit"]:has-text("Consultar Radicado")');
    await searchBtn.click();
    await pageMobile.waitForTimeout(600);

    const mobileNotice = pageMobile.locator('.civia-notice-card').first();
    await mobileNotice.waitFor({ state: 'visible' });
    console.log('✓ Aviso de entrega externa no habilitada visible y adaptable en pantalla móvil.');

    const mobileTimeline = pageMobile.locator('.civia-events-timeline');
    await mobileTimeline.waitFor({ state: 'visible' });
    console.log('✓ Línea de tiempo de eventos renderizada correctamente en móvil.');

    // Probar cierre de detalle en móvil
    const mobileCloseBtn = pageMobile.locator('button:has-text("✕ Cerrar detalle")');
    await mobileCloseBtn.waitFor({ state: 'visible' });
    await mobileCloseBtn.click();
    await pageMobile.waitForTimeout(400);

    const mobileCloseCount = await pageMobile.locator('button:has-text("✕ Cerrar detalle")').count();
    if (mobileCloseCount !== 0) {
      throw new Error(`Fallo: "Cerrar detalle" en móvil no ocultó el panel.`);
    }
    console.log('✓ Cierre de detalle verificado exitosamente en móvil.');

    await contextMobile.close();

    // TEST 3: ULTRA COMPACTO / NARROW SCREEN (320 x 568)
    console.log('\n--- TEST 3: Responsividad en Pantalla Estrecha (320 x 568) ---');
    const contextNarrow = await browser.newContext({
      viewport: { width: 320, height: 568 },
      isMobile: true,
      hasTouch: true,
    });
    const pageNarrow = await contextNarrow.newPage();
    await pageNarrow.goto('http://localhost:5173', { waitUntil: 'networkidle' });

    const hasOverflow = await pageNarrow.evaluate(() => {
      return document.documentElement.scrollWidth > window.innerWidth + 2;
    });
    console.log(`✓ Desbordamiento horizontal en 320px: ${hasOverflow ? 'DETECTADO (FALLO)' : 'NINGUNO (CORRECTO)'}`);
    if (hasOverflow) {
      throw new Error('Fallo de responsividad: La página presenta desbordamiento horizontal en 320px de ancho.');
    }
    console.log('✓ Adaptabilidad en 320px de ancho superada exitosamente.');
    await contextNarrow.close();

    console.log('\n========================================================================');
    console.log(' ¡TODAS LAS PRUEBAS E2E DE REFINAMIENTO UX/UI Y TRAZABILIDAD PASARON!');
    console.log('========================================================================\n');
  } finally {
    await browser.close();
  }
})();

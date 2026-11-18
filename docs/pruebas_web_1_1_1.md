# Verificación de interfaces web de CIVIA 1.1.1

## Reproducción anterior al cambio

Se sirvió `v1.0.0-academic` en un directorio temporal y se abrió el formulario en Edge con pantalla táctil emulada de 360 × 800. El navegador solicitó `/api/reports/stats` y `/api/reports?limit=60`, las rutas observadas en el reporte del propietario. Con esas solicitudes rechazadas deliberadamente, el navegador mantuvo el desborde. El ancho disponible era 360 píxeles y `document.documentElement.scrollWidth` llegó a 567. El borde derecho de título, descripción, dirección, selector de ubicación y longitud llegó a 567. El botón de foto llegó a 492. Con esta configuración `window.innerWidth` también llegó a 567, por lo que comparar únicamente ambos valores habría ocultado el problema.

La cuadrícula del formulario anterior empleaba pistas `1fr` con mínimos intrínsecos, incluso al pasar a una columna. La versión 1.1.1 usa pistas con mínimo cero en los contenedores que reciben campos, reflujo en las acciones y un observador de tamaño para recalcular el mapa. La prueba en la rama candidata 1.1.0 también confirmó un problema independiente. La vista de escritorio restringía la radicación por tamaño y tipo de puntero.

El Service Worker de `v1.0.0-academic` seleccionaba solicitudes GET con pocas exclusiones. La nueva versión sirve un trabajador de transición en `/sw.js`, elimina el caché histórico identificado y retira el registro. Cada PWA precarga un único aviso HTML público de su propio ámbito, con solicitud sin credenciales y validación de origen, protocolo, método, ruta y respuesta. La prueba abre el trabajador histórico en Edge y cambia el sitio servido bajo el mismo origen para verificar la transición.

## Verificación reproducible

Ejecutar desde `frontend` con Node, npm y Microsoft Edge. Los comandos sirven el build de producción e interceptan la API con datos sintéticos para probar el cliente. El despliegue sigue el [README principal](../README.md).

```powershell
npm ci
$env:CIVIA_BUILD_SHA = (git rev-parse HEAD)
npm run build
npm run preview
```

En otra consola desde `frontend`:

```powershell
$env:TARGET_URL = 'http://127.0.0.1:4173'
$env:CIVIA_SCREENSHOTS = Join-Path $env:TEMP 'civia-111-web-evidence'
npm run test:e2e
```

La ejecución de Edge obtuvo 13 pruebas satisfactorias. La suite cubre las interfaces y situaciones siguientes:

- La raíz convencional muestra únicamente la radicación, incluso al navegar con un fragmento antiguo. Se prueban registro y acceso sintéticos, ubicación de mapa y GPS emulado, archivos JPEG y WAV, recuperación de un envío interrumpido con idénticos binarios y clave de idempotencia, confirmación y nuevo reporte.
- `/app/` permite instalar CIVIA Ciudadano. Chromium informó una lista vacía de errores de instalabilidad en un perfil desechable normal de Edge. Se comprueban los cuatro PNG, el manifiesto, los enlaces directos, las cinco secciones, el aviso sin conexión y la reapertura del borrador con red. La suite principal emula standalone para recorrer las secciones. Una segunda prueba instaló y abrió la PWA con Chrome for Testing 158.0.8127.18 en un perfil temporal. La ventana inició en `/app/`, `(display-mode: standalone)` coincidió y la navegación apareció sin el aviso de instalación. La prueba desinstaló la PWA al terminar.
- `/admin/` registra su manifiesto y trabajador independientes. Se comprueban por separado las secciones visibles para CASE_ADMIN y WEB_ADMIN, el rechazo de una cuenta ciudadana y el desplazamiento interno de una tabla de veinte filas. Chrome for Testing también instaló, abrió en standalone y desinstaló el portal administrativo desde el gateway habitual.
- La misma sesión de navegador registra los ámbitos `/app/` y `/admin/` sin controlar la raíz. La transición histórica conserva la base IndexedDB de prueba y un caché ajeno. La recuperación de un borrador 1.1.0 exige una acción explícita y conserva la clave de idempotencia.
- Se verifican la anchura del documento y los bordes de los controles a 320 × 568, 360 × 800, 375 × 667, 390 × 844, 412 × 915, 768 × 1024, 1366 × 768, 1920 × 1080 y 800 × 360. Se usan nombres, textos, archivos y radicados largos. La suite verifica una ventana de 680 × 384 con el tamaño de texto al 200 %. En una prueba separada, Chrome for Testing fijó el zoom real del navegador al 200 % para el formulario de 1366 × 768 con el mapa expandido. La relación de píxeles fue 2, el ancho disponible y el ancho del documento fueron 683 píxeles CSS, y ningún control quedó fuera. No se registraron excepciones JavaScript no gestionadas.

El build de trabajo devolvió `{"version":"1.1.1","commit":"4b245fcbb182b6739bfe05e6d1d6daafc28d04b9-dirty"}` en `/build.json`. El sufijo distingue el directorio de trabajo del commit base. Un evaluador puede consultar `/build.json` y `/api/meta` tras desplegar una revisión.

Para reproducir la instalación real de escritorio, mantén `TARGET_URL` y ejecuta `npx playwright install chromium` seguido de `npm run test:pwa-install`. La prueba necesita una sesión gráfica y utiliza un perfil desechable.

Para repetir el zoom real, fija **Zoom de página → 200 %** en las preferencias de apariencia de Chromium, abre el formulario ciudadano con una cuenta de prueba y expande **Elegir en el mapa**. Comprueba `document.documentElement.clientWidth`, `document.documentElement.scrollWidth` y los bordes de los controles con `getBoundingClientRect()`.

## Matriz de verificación

| Hallazgo o tarea | Skill | Instrucción aplicada | Verificación |
| --- | --- | --- | --- |
| Desborde y bloqueo de radicación | `systematic-debugging`, `react-patterns`, `playwright-skill` | Reproducir las dos fallas, dar entradas separadas a las experiencias y probar dimensiones reales | Fallo en 1.0 a 360 × 800 y ausencia de formulario en escritorio en 1.1.0. En 1.1.1, anchura de documento y bordes de controles en nueve tamaños |
| Actualización de los trabajadores | `code-review-and-quality` y `playwright-skill` | Inspeccionar los límites de cada caché y reproducir una actualización en el mismo origen | Retirada del ámbito raíz, conservación de IndexedDB y caché ajeno, dos ámbitos independientes y un solo aviso en cada caché |
| Borrador y envío sin conexión | `frontend-api-integration-patterns`, `test-driven-development` | Conservar el envío hasta confirmar recepción y reintentar con la misma clave | Falló la recuperación de borrador anterior en RED. En GREEN, recuperación explícita, regreso de red, mismo JPEG y WAV y misma clave tras perder una respuesta |
| Estado servido y resultados | `verification-before-completion` | Comprobar el build, sus metadatos y el recorrido desde el navegador | TypeScript y Vite sin errores, 13 pruebas satisfactorias y capturas obtenidas por Edge |

El uso de cámara, micrófono, teclado virtual e instalación en teléfonos físicos requiere evidencia del dispositivo. Las pruebas de navegador usan emulación y archivos de prueba donde se indica.

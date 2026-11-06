# CIVIA — Auditoría independiente de navegación y evidencias sintéticas

**Dictamen NO APROBADA para publicación.** Commit exacto `48c872817ecd88353b25883fd25878126031358a`, rama `feat/ui-navigation-demo-evidence`. La navegación corregida pasó en escritorio y móvil. La actualización del catálogo dejó pasar un JPEG corrupto de igual tamaño y el navegador siguió sirviendo la evidencia PNG anterior tras una actualización satisfactoria. El flujo ciudadano también permitió publicar una muestra fotorrealista con clasificación de reporte ordinario.

## Alcance y entorno

- Auditoría local del 5 de noviembre de 2026. Se leyó `AGENTS.md`. `git rev-parse HEAD` y `git branch --show-current` confirmaron el objetivo. `git status --short` estaba vacío al inicio. `git merge-base --is-ancestor cf48e71 48c8728` devolvió 0.
- Base comparada `d14f64e31b3c8ab361682a0d023faf8ba53ae048`. Base G2.1.8 previamente aprobada `cf48e710a4d321455864d2b59a4257cdca9938aa`. `git diff --binary d14f64e 48c8728` quedó en `diff.patch`. Revisé los cambios en 23 archivos, en particular el estado de React, sembrado, actualizador, preparación de activos, Vite y pruebas. Entre la base funcional aprobada y el objetivo permanecen iguales los módulos de autorización y operaciones.
- Dos exportaciones de Git en ZIP, builds de ambas PWA y de la API, PostgreSQL **17.11** desechable, bases separadas `test_api`, `test_audit` y `test_suite`. Backend y base en red Docker interna, Nginx en loopback 55987 y 55988, datos y archivos de evidencia en la carpeta del auditor. La PWA base usa la misma API aislada para atribuir la diferencia al frontend.
- La API ejecutó FastAPI/Uvicorn y PostgreSQL reales. El instrumento `serve.py` sustituyó las respuestas de los modelos por datos sintéticos e inyectó la pérdida de una respuesta. La suite excluyó el marcador `live`. En Playwright se bloquearon destinos externos, incluidos los tiles. En la corrida de puntero se sirvió desde disco el CSS de Leaflet **1.9.4** pedido por ambos builds. Se bloquearon service workers para estas sesiones de control. La prueba E2E verificó que el despliegue sirve el manifest y el service worker. El caso de caché utilizó la caché HTTP de Chromium con intercepción desactivada.
- Carpeta de evidencia `C:/Users/Jhoesp/AppData/Local/Temp/civia-48c8728-5d00fdf5e9a548068441c4587e013942`. Contiene snapshots, diff, instrumentos, hashes, mosaicos, capturas y resultados. Los logs del proxy registran hashes de claves y capacidades.

## Matriz de aceptación

| Control | Resultado | Esperado y observado |
|---|---|---|
| Navegación | **PASS** | La base dejó visible la evidencia de DEMO0001 al entrar al asistente en ambos tamaños. El objetivo quitó la foto y el panel del DOM, mostró el asistente y el contenido de administración por separado y permitió abrir y cerrar otro marcador. Dos ciclos completos en 1280 × 850 y 390 × 720, con clic real y CSS local. Las tres piezas de recuperación F4 conservaron sus valores. |
| Calidad visual y coherencia | **PARCIAL** | Diez escenas distintas y coherentes con sus registros. Las cinco vistas previas se decodificaron desde recursos locales. La muestra OTRO reproduce un socavón de HUECO y el distintivo incrustado es pequeño y queda recortado en la vista de detalle. |
| Procedencia ética | **FAIL** | El catálogo muestra distintivos explícitos y los diez JPEG carecen de EXIF GPS. La muestra generada puede terminar en un registro ciudadano ordinario cuando ya existe descripción. La vista recorta el distintivo dentro de la imagen y omite el distintivo de UI en ese registro. |
| Actualización idempotente | **FAIL** | Dos ejecuciones sanas pasaron y los controles de negocio quedaron intactos. Fallaron la detección de corrupción de igual longitud y la renovación del contenido en caché. El rollback SQL dejó dos archivos sin referencia. |
| Instalación nueva | **PASS** | 10 filas sintéticas, tamaño 323 260–521 761 bytes, 1200 × 896, MIME JPEG y SHA-256 iguales entre filas, disco y activos. Diez respuestas de foto con bytes correctos y diez fotos decodificadas en la PWA. |
| Regresiones de seguridad | **PASS** | Confirmación anónima 403 y con capacidad propietaria 200 con estado CONFIRMED. Observabilidad anónima 401 y admin 200. Suite F1–F8 y casos adversariales aprobados en el entorno hermético. El etiquetado de muestras se evalúa en procedencia. |
| F4 y funcionamiento de la PWA | **PASS** | Primera respuesta descartada tras HTTP 200 de FastAPI, Nginx entregó 502, recarga recuperó la consulta, replay reutilizó clave y capacidad, sondeo COMMITTED con resultado autorizado, una operación y un solo efecto SQL. Carga de JPEG ciudadano 201 y recuperación de foto 200. |

## Hallazgos reproducibles

### 1. El actualizador acepta evidencia corrupta de igual longitud — bloqueante, regresión del actualizador nuevo

`backend/app/seed.py:419–425` compara existencia y tamaño del archivo. Conserva los metadatos calculados desde el activo de referencia aunque el archivo servido pueda contener bytes distintos.

1. En una base desechable, sembrar los diez PNG con la función de la base y ejecutar `update_synthetic_catalog_photos()` de 48c8728. Confirmar `updated=10`.
2. Leer `photo_path` de DEMO0001 y sustituir el primer byte del JPEG por `X`, conservando la longitud. Comparar SHA-256 con `photo_sha256`.
3. Volver a ejecutar el actualizador. Esperado `updated=1` o fallo explícito, con integridad restablecida o señalada. Observado `updated=0, unchanged=10`, longitud igual, hash distinto y cabecera JPEG inválida. El endpoint sirve el archivo apuntado por la fila.

En otro ensayo del mismo instrumento, un trigger `BEFORE UPDATE` levantó `RaiseException` al llegar a DEMO0002. PostgreSQL restauró todas las filas y los PNG activos conservaron su hash. Quedaron dos JPEG huérfanos porque la escritura de archivos precede a la confirmación SQL. Al retirar el trigger, la actualización cambió solo las seis columnas de foto y `updated_at` de los diez reportes. El centinela ciudadano, títulos, descripciones, coordenadas, análisis, estados, aprobaciones y operaciones conservaron sus valores. La segunda corrida sana dejó filas, bytes y mtime intactos.

Corrección mínima propuesta. Comparar SHA-256 de los bytes en disco, escribir los reemplazos mediante temporal y renombre atómico y usar destinos versionados. Gestionar los archivos sin referencia tras fallo o reintento. Evidencia en `catalog.py` y `catalog.log`.

### 2. La caché conserva el PNG después de la actualización — bloqueante

La URL estable de `backend/app/repository.py:84` y `Cache-Control: public, max-age=3600` de `backend/app/main.py:465` ya existían en la base. La nueva actualización de fotos vuelve observable el problema al cambiar bytes bajo la misma URL.

1. Apuntar DEMO0001 al PNG de la base dentro de `test_api`. En Chromium nuevo, consultar la foto mediante `fetch` con caché predeterminada.
2. Mantener el mismo contexto y correr el actualizador. Registró `updated=1, unchanged=9`.
3. Consultar la misma URL con caché normal y luego con `cache: 'no-store'`. Esperado JPEG en ambas. Observado PNG con el SHA original `f5331cc6…` en la primera y JPEG `7685c3a3…` en la segunda, ambas HTTP 200.

Corrección mínima propuesta. Añadir una versión derivada de `photo_sha256` a `photo_url` para que una lectura de catálogo actualizada obtenga una URL distinta y permitir revalidación en la URL canónica. Evidencia en `cache.cjs`, `catalog.py` modos `cache-old` y `cache-new`, `cache.log` y `cache-db.log`.

### 3. Una muestra fotorrealista puede publicarse como evidencia ciudadana ordinaria — bloqueante para procedencia

El generador de `frontend/src/App.tsx:263–281` solo escribe el texto de simulación si la descripción estaba vacía. El alta usa el flujo ciudadano de `backend/app/main.py:175` con clasificación ordinaria por defecto en `backend/app/repository.py:189`. El detalle muestra el distintivo exterior solo para `is_synthetic` y recorta la imagen con `objectFit: 'cover'` en `frontend/src/App.tsx:683–688`.

En móvil, llenar título y descripción ordinaria, generar muestra HUECO y enviar. Ambas PWA devolvieron 201, conservaron la descripción e informaron `is_synthetic=false`. La base usó PNG geométrico y el objetivo un JPEG fotorrealista. En el objetivo se midieron 394 × 280 píxeles CSS en el detalle para una imagen original de 1200 × 896. La franja inferior pierde el texto con el recorte, como muestran `sample-citizen-mobile.png` y `photo-390.png`. El catálogo marcado conserva un distintivo de simulación fuera de la imagen.

La clasificación ordinaria es preexistente. La sustitución por fotografía fotorrealista agrava el impacto. Corrección mínima propuesta. En el flujo ciudadano, permitir la muestra solo como vista previa o enviarla exclusivamente a un flujo demo que imponga una marca sintética verificable en servidor y en toda vista pública. Evidencia en `sample-policy.cjs` y `sample-policy.log`.

### 4. La muestra OTRO muestra un socavón — defecto de coherencia nuevo

`scripts/prepare_demo_assets.py:74` copia DEMO0009 como `sample_otro.jpg`. Sus SHA-256 son iguales (`1fa1c104…`) y el catálogo clasifica DEMO0009 como HUECO. Al seleccionar OTRO en el formulario, el navegador muestra el mismo socavón que el catálogo. Corrección mínima propuesta. Sustituir esa muestra por una escena propia de OTRO y verificar semántica junto con decodificación. Evidencia en `catalog.log` y `nav-css.json`.

## Inspección de las diez escenas

Se abrieron individualmente los diez JPEG y se compararon los dos mosaicos `visual-1.jpg` y `visual-2.jpg`. Las composiciones son distintas, aunque varias comparten contexto vial. Los radicados incrustados coinciden con sus archivos. El distintivo se distingue al ampliar el original, con tipografía pequeña y acentos deformados en el render del texto. A tamaño de detalle la franja se recorta. Conviene reeditar la marca de los diez con tipografía legible y conservarla en el encuadre de UI. Los diez carecen de etiquetas EXIF. La observación visual permite describir rostros y rótulos, pero no autenticar la procedencia de las imágenes ni asociarlos con personas, vehículos o comercios reales. El script declara generación sintética y los materiales de entrada que referencia fuera del repositorio quedaron fuera de la verificación.

| Radicado | Categoría | Observación individual |
|---|---|---|
| DEMO0001 | HUECO | Bache de grava en primer plano, calle con moto y taxi. Escena verosímil. Se lee el identificador lateral T-329, sin matrícula clara. Reeditar el identificador del taxi. |
| DEMO0002 | BASURAS | Escombros y bolsas en separador con tránsito y transeúntes desenfocados. Rótulos distorsionados de fondo, sin identificadores vehiculares claros. |
| DEMO0003 | TALA | Tronco cortado junto al cauce, distinto de la tala residencial. Escena coherente, sin personas ni placas visibles. |
| DEMO0004 | QUEMA | Humo en ladera con focos visibles y figuras lejanas. Humo denso y composición verosímil, sin rostros distinguibles. |
| DEMO0005 | HUECO | Grietas alrededor del bache en avenida con palmas. Diferente encuadre y escenario de DEMO0001, vehículos distantes. |
| DEMO0006 | BASURAS | Colchón, madera y residuos sobre separador verde, con buses y taxis. Placas pequeñas y borrosas, grafismos de vehículos distorsionados. |
| DEMO0007 | QUEMA | Fuego en residuos en lote residencial. Foco cercano y distinto de DEMO0004. Sin personas ni vehículos en primer plano. |
| DEMO0008 | TALA | Árbol podado y ramas que ocupan una calle residencial. Personas y placa lejana presentes, sin lectura concluyente. |
| DEMO0009 | HUECO | Socavón dramático con tubería y cerramiento. Se distinguen rasgos de algunos espectadores y hay letreros y uniformes reconocibles como tipos de objeto. Reeditar personas y rótulos, y reemplazar su copia en OTRO. |
| DEMO0010 | BASURAS | Bolsas frente a locales cerrados, con taxis y peatones al fondo. Se distingue un rótulo comercial con aparente número telefónico. Reeditar rótulo y número. |

## Regresiones y repetición

- **Builds.** Los Dockerfile del snapshot produjeron API y frontend, con `tsc -b && vite build` en el build del frontend. `build-api.log`, `build-front.log` y `build-base.log`.
- **Suite.** `python -m pytest -m 'not live'` en `backend`, con PostgreSQL desechable y alias Nginx `frontend`. **140 pasadas, una live deseleccionada**, una advertencia de deprecación de Starlette/AnyIO. Repetición focalizada **36 pasadas**, incluidas las ocho pruebas de remediación, los casos adversariales de procedencia de cancelación, la suite de activos y el E2E Nginx. El E2E verificó HTML, manifest standalone, service worker, health JSON y estadísticas de reportes del backend. `suite.log` y `focused.log`.
- **Navegación.** `node nav-css.cjs` desde evidencias con ambos Nginx disponibles. Abre DEMO0001, espera decodificación de foto, reproduce fuga base, verifica ausencia de foto y panel en asistente candidato, consulta al agente, abre admin y vuelve a mapa, donde hace clic real en un marcador distinto y cierra su detalle. Verifica dos ciclos en cada viewport, cero errores JS, misma clave, capacidad e ID al finalizar cada ciclo. El ensayo sin CSS externo no permitió el mismo clic directo en ambos builds, aunque la activación por teclado/DOM abrió el popup. La dependencia del CSS remoto es preexistente y se aisló con `leaflet-1.9.4.css`. Véanse `nav-css.log`, `nav-css.json`, `pointer.log` y las capturas.
- **Instalación limpia.** Con API sembrada sobre `test_api` desde vacío, `fresh.py` compara las diez filas con los bytes, longitud, MIME y dimensiones de cada archivo instalado y empaquetado. `catalog.py` registra hashes completos, respuesta HTTP y metadatos de los activos. El navegador confirmó carga y decodificación de las diez fotos y cinco muestras. `fresh-integrity.log`, `catalog.log` y `nav-css.json`.
- **F4.** `CIVIA_AUDIT_URL=http://127.0.0.1:55987` y `node playwright-test-final.cjs` con el proxy de `serve.py`. Se perdió la primera respuesta upstream 200 antes de entregar ID, luego hubo replay con la misma clave y capacidad y polling autorizado con resultado. Una fila `COMMITTED` para el hash de la clave. Contador SQL de 7 a 8 durante el ensayo. Capacidad ausente de DOM, URL y logs capturados. La segunda recarga conservó el ID y el borrado explícito limpió el estado. `pwa_final_results.json`, `pwa-operation.log`, `pwa-counter-before.txt`, `pwa-counter-after.txt` y `proxy_events.jsonl`.
- **Protecciones.** La prueba focalizada verificó privacidad en replay, separación de permisos de edición y administración, reconciliación con evidencia, ledger de estado y cancelaciones externas 57014/25P04 frente al deadline local. Las pruebas ciudadanas y de administración sobre el proxy real registraron los estados 403/200 y 401/200 respectivamente. Las fotos y muestras se sirvieron con contenido local verificado. Esta auditoría de regresión conserva el alcance funcional de la aceptación G2.1.8 previa.

## Cierre

La corrección de pestañas cumple su recorrido. La aceptación de la versión queda pendiente de corregir la validación del archivo activo, la caché de fotos actualizadas y la publicación de muestras sin clasificación demo. La muestra OTRO y el distintivo requieren ajuste para cumplir la revisión visual.

La auditoría se limita a los dos documentos de entrega en el checkout. Los registros de cierre de Docker y los instrumentos permanecen en la carpeta aislada.

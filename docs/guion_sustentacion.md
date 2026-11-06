# Guion de Sustentación en Vivo — CIVIA (6 minutos + 3 minutos de preguntas)

**Proyecto Académico de Ingeniería de Aplicaciones con IA — Universidad Cooperativa de Colombia**  
**Equipo:** Stefania Córdoba y Sebastian Espinosa (Momento Evaluativo 2)  
**Curso:** Ingeniería de Aplicaciones con IA — Momento Evaluativo 2  
**Regla de oro de la sustentación:** **Iniciar directamente con la aplicación CIVIA funcionando en pantalla (`http://localhost:5173`)**. Sin diapositivas teóricas introductorias.

---

## Preparación previa (2 minutos antes de entrar)

1. Confirmar contenedores saludables en terminal:
   ```powershell
   docker compose ps
   ```
2. Abrir dos pestañas en el navegador:
   - **Pestaña 1:** `http://localhost:5173` (Aplicación ciudadana CIVIA con el mapa de Cali y los 10 reportes sintéticos de demostración visibles).
   - **Pestaña 2:** Consola de Observabilidad y Resiliencia en la parte inferior de `http://localhost:5173` con el `ADMIN_TOKEN` listo para autenticar.
3. Tener a mano la imagen sintética de prueba (`hueco` o `quema`) o usar cualquier fotografía de prueba local.

---

## Estructura minuto a minuto (6:00 minutos)

### Minuto 0:00 – 0:50 | Problema real en Cali y arquitectura en vivo (Stefania)

- **Acción en pantalla:** Mostrar directamente `http://localhost:5173` con el tablero de estadísticas reales desde PostgreSQL y el mapa interactivo de Cali (`Leaflet`) con marcadores por categoría (`HUECO`, `BASURAS`, `TALA`, `QUEMA`) e insignia explícita `DATO SINTÉTICO DEMO`.
- **Guion (Stefania):**
  > «Buenas tardes. Estamos directamente sobre **CIVIA** en ejecución local sobre Docker. En Cali, un ciudadano que reporta un hueco severo en la Calle 5, acumulación de basuras en Mariano Ramos o una quema en Cristo Rey enfrenta dos problemas: formularios lentos donde la clasificación manual suele ser imprecisa, y cajas negras donde nunca sabe qué pasó con su radicado.  
  > CIVIA resuelve esto combinando **PostgreSQL transaccional** como única fuente de verdad con un **sistema agéntico y multimodal resiliente** de tres niveles (`Gemini 3.8 Flash` → `Groq Qwen 3.8 27B` → `Gemini 3.5 Flash Lite`). Todos los datos que ven en el mapa provienen de consultas SQL parametrizadas reales en PostgreSQL.»

---

### Minuto 0:50 – 2:15 | Flujo vertical ciudadano: foto + GPS + análisis multimodal + confirmación humana (Stefania)

- **Acción en pantalla:**
  1. En el formulario **«1. Registrar reporte ciudadano»**, hacer clic en **«Capturar mi GPS»** o hacer clic directo sobre el mapa de Cali para fijar latitud y longitud reales dentro del municipio.
  2. Seleccionar una fotografía de evidencia (y mencionar la carga opcional de nota de voz `<= 60s / 5MB`), escribir una descripción ciudadana breve y enviar.
  3. Mostrar la tarjeta **«Diagnóstico sugerido por IA vs. Confirmación Ciudadana»** (`ANALYZED_PENDING_CONFIRMATION`): categoría sugerida, severidad, nivel de confianza y resumen estructurado validado con Pydantic.
  4. Hacer clic en **«Confirmar clasificación»** (o corregir la categoría/severidad manualmente) y mostrar cómo pasa a estado `CONFIRMED` con su código único `CIV-2026-...`.
- **Guion (Stefania):**
  > «Veamos el flujo vertical completo. Al subir la fotografía, el backend valida los *magic bytes* reales, verifica dimensiones mínimas y máximas (`32x32` a `8192x8192`) y **elimina los metadatos EXIF** con Pillow para proteger la privacidad del ciudadano antes de tocar el disco.  
  > Observen una decisión clave de diseño: la IA **no** decide de forma definitiva. Entrega un diagnóstico sugerido bajo un contrato JSON estricto (`AIAnalysisContract`), pero el reporte queda en estado `ANALYZED_PENDING_CONFIRMATION` hasta que el ciudadano confirma o corrige la clasificación. Solo entonces pasa a `CONFIRMED` y queda trazado con su código de radicado.»

---

### Minuto 2:15 – 3:30 | Estrategia de datos (SQL directo vs. NO RAG) y agente con 4 límites (Sebastian)

- **Acción en pantalla:**
  1. Ir a la pestaña **«Asistente Ciudadano»**:
     - Ejecutar una consulta ciudadana: `¿Cuáles son los reportes de HUECO en la Comuna 2?` → mostrar cómo el asistente responde con empatía y claridad formateado en Markdown, citando los radicados exactos `CIV-2026-DEMO0001` y `CIV-2026-DEMO0007`. Resaltar que el ciudadano recibe una respuesta amigable sin tecnicismos ni SQL crudo expuesto.
     - Ejecutar una consulta sin evidencia en BD: `¿Cuál es el índice satelital NDVI en la Comuna 99?` → mostrar que responde verazmente que no dispone de evidencia registrada, sin inventar ni alucinar.
     - Ejecutar una solicitud de modificación: `Cambia el estado del reporte CIV-2026-DEMO0001 a RESOLVED` → mostrar el aviso ciudadano informando que la solicitud fue registrada para revisión administrativa y que ningún cambio se aplica sin autorización humana.
  2. Ir a la pestaña **«Administración»** (ingresando el `ADMIN_TOKEN`):
     - Desplegar la sección de telemetría técnica agéntica: mostrar al evaluador la herramienta tipada invocada (`consultar_reportes`), la consulta SQL parametrizada a PostgreSQL, las iteraciones y el uso de tokens.
     - Mostrar la bandeja de **Aprobaciones Humanas**: verificar la solicitud pendiente de cambio de estado y los controles de decisión de un solo uso.
- **Guion (Sebastian):**
  > «¿Por qué elegimos **PostgreSQL y SQL directo** en lugar de RAG o una base vectorial? Porque las consultas operativas de CIVIA exigen conteos exactos por comuna, búsquedas por código de radicado y filtros geográficos deterministas por radio en kilómetros. Un pipeline de *embeddings* introduciría costo extra, latencia y riesgo de falsos positivos semánticos sobre registros tabulares cortos.  
  > En la interfaz ciudadana, la IA dialoga con respuestas limpias y empáticas en Markdown, protegiendo al usuario de detalles técnicos. En la consola administrativa, auditamos la ejecución bajo **cuatro límites obligatorios en código**: máximo de iteraciones (`MAX_ITERATIONS`), presupuesto de tokens (`MAX_TOKENS`), timeout estricto (`TIMEOUT`), y **aprobación humana obligatoria** (`HUMAN_APPROVAL_REQUIRED`). La IA **no escribe en la tabla `reports`**: registra una propuesta en `pending_approvals` que solo un operador humano con credencial administrativa puede aprobar o rechazar.»

---

### Minuto 3:30 – 4:50 | Demostración en vivo de resiliencia y fallback Gemini → Groq → Gemini (Sebastian)

- **Acción en pantalla:**
  1. Abrir la **Consola de Observabilidad y Resiliencia** ingresando el `ADMIN_TOKEN`.
  2. Mostrar la cadena de 3 niveles y el estado de los *circuit breakers*.
  3. Activar en vivo **`429 Primario`** (o **`503 Primario`**) y lanzar una consulta o análisis. Mostrar que el ciudadano recibe respuesta limpia sin ver jamás un error `429`, un *traceback* ni los nombres `Gemini` o `Groq`, mientras que la traza administrativa registra el fallo del nivel 1 y el éxito inmediato del nivel 2 (`Groq`).
  4. Activar **`Caída Total`** (`TOTAL`) y mostrar que al registrar un reporte este no se pierde: se guarda en PostgreSQL con estado `PENDING_ANALYSIS` para reanálisis posterior. Restaurar a **`Normal (sin falla)`**.
- **Guion (Sebastian):**
  > «La resiliencia no es solo un `try/except`. Implementamos un router desacoplado con *circuit breaker* por proveedor, *backoff* exponencial con *jitter* y reparación acotada de JSON.  
  > Aquí inyectamos un fallo `HTTP 429` en el proveedor primario. Para el ciudadano la aplicación sigue funcionando sin mostrar errores internos ni nombres de proveedores, mientras que en la consola protegida vemos la conmutación automática hacia Groq en menos de un segundo. E incluso si los tres niveles caen simultáneamente, el reporte ciudadano se preserva íntegro en PostgreSQL bajo estado `PENDING_ANALYSIS`.»

---

### Minuto 4:50 – 6:00 | Métricas reales de evaluación, costos y cierre (Stefania y Sebastian)

- **Acción en pantalla:** Mostrar en la consola de observabilidad las métricas reales (`P50`, `P90`, tokens, tasa de fallback) y abrir brevemente `eval/resultados/reporte_evaluacion.md`.
- **Guion (Stefania y Sebastian):**
  > «Evaluamos el sistema con una suite reproducible de **6 preguntas doradas verificadas contra SQL** y **15 consultas representativas** en `eval/evaluar.py`.  
  > Medimos latencias reales (`P50` y `P90`), consumo de tokens y tiempo de recuperación ante fallos. Dado que operamos sobre las capas gratuitas de Google AI Studio y Groq Cloud, distinguimos con transparencia el **costo facturado real (`$0.00 USD`)** del **costo estimado de referencia a precios públicos por millón de tokens (`~$0.0002–$0.0005 USD` por consulta)**.  
  > Como evolución futura proponemos: geocodificación inversa automática por polígono oficial de comunas del DAGMA/IDESO y cola asíncrona para reanalizar automáticamente los reportes que queden en `PENDING_ANALYSIS`. Muchas gracias; quedamos atentos a sus preguntas.»

---

---

## Demostración Técnica de la API REST con Swagger UI (`/docs`)

Esta sección guía paso a paso al equipo o al profesor evaluador para auditar la interfaz OpenAPI interactiva de CIVIA en caso de requerir una inspección técnica profunda de los servicios:

1. **Apertura de la interfaz Swagger UI:**
   - Abrir en el navegador: `http://localhost:8000/docs`.
   - Señalar el título oficial (*CIVIA — API de Gestión Inteligente y Vigilancia Urbana*), la versión `1.0.0` y la arquitectura general documentada en la cabecera.
2. **Estructura por Categorías Temáticas (8 Tags y 23 Endpoints):**
   - Mostrar al evaluador las 8 categorías organizadas lógicamente:
     * *Salud del sistema* (1 endpoint: `/health`).
     * *Reportes ciudadanos* (7 endpoints: estadísticas, alta multipart, reanálisis IA, listado paginado, búsqueda por radicado, consulta por UUID y confirmación ciudadana).
     * *Fotografías y evidencias* (1 endpoint: entrega CAS con ETag, HTTP 304 y CSP).
     * *Seguimiento y trazabilidad* (2 endpoints: línea de tiempo de eventos por UUID o código radicado).
     * *Asistente ciudadano e IA* (2 endpoints: consulta agéntica con 4 límites y reconciliación transaccional).
     * *Administración y gestión operativa* (6 endpoints: estados, resiembra sintética, notificaciones internas y notas de gestión).
     * *Aprobaciones humanas* (2 endpoints: bandeja de decisiones éticas de un solo uso).
     * *Observabilidad y resiliencia* (2 endpoints: telemetría de latencias P50/P90, estado de circuit breakers e inyección de fallas).
3. **Ejecución en vivo de comprobación de salud (`GET /health`):**
   - Desplegar `GET /health`, pulsar **«Try it out»** y luego **«Execute»**.
   - Mostrar la respuesta `HTTP 200`: `"status": "ok"`, `"db": {"connected": true, "schema_ready": true}`, verificando conectividad transaccional con PostgreSQL 17.
4. **Consulta real de reportes de Cali (`GET /api/reports` o `GET /api/reports/stats`):**
   - Desplegar `GET /api/reports/stats` y pulsar **«Execute»**: mostrar el desglose de incidentes por categoría (`HUECO`, `BASURAS`, `TALA`, `QUEMA`, `OTRO`).
   - Desplegar `GET /api/reports` y filtrar por `category=HUECO`: comprobar cómo PostgreSQL devuelve los reportes sintéticos oficiales en Cali con sus coordenadas reales y radicados `CIV-2026-DEMO0001`, etc.
5. **Demostración de seguridad fail-closed y autenticación (`401 Unauthorized`):**
   - Desplegar `GET /api/admin/observability` y pulsar **«Execute»** sin cabeceras.
   - Mostrar el rechazo inmediato con código `HTTP 401 Unauthorized` (`detail: Token de administración no configurado o ausente`), demostrando que Swagger UI no da acceso libre a consolas operativas.
6. **Autorización con `X-Admin-Token` en Swagger UI:**
   - En el campo de parámetro `X-Admin-Token` de la petición, ingresar el token generado por el bootstrap en `.env` (obtenido mediante `Get-Content .env | Select-String "ADMIN_TOKEN"`).
   - Reejecutar la llamada: mostrar el código `HTTP 200`, la cadena de 3 niveles de IA, los circuit breakers activos y las métricas P50/P90.
7. **Relación entre modelos Pydantic y especificación OpenAPI:**
   - Desplazarse al final de la página a la sección **«Schemas»**.
   - Mostrar al profesor cómo los modelos Pydantic v2 de Python (`ReportPublicResponse`, `ReportCreateForm`, `AgentQueryRequest`, `AIAnalysisContract`) definen los tipos de datos, rangos numéricos y campos obligatorios/opcionales sin desfase documental.
8. **Articulación de la interfaz React SPA con la API:**
   - Explicar al profesor que la aplicación ciudadana (`http://localhost:5173`) no accede a PostgreSQL directamente: consume exactamente estos 23 endpoints a través del proxy inverso Nginx (`/api/*`), preservando desacoplamiento, seguridad e integridad referencial. Para la especificación completa, remitir a [`docs/API.md`](API.md).

## Banco de respuestas rápidas para los 3 minutos de preguntas (Q&A)

1. **«¿Qué ocurre si el modelo devuelve un JSON malformado o con campos en otro idioma/sinónimo?»**
   - *Respuesta:* En [`backend/app/ai_router.py`](backend/app/ai_router.py), la función `parse_and_validate_analysis_json` extrae de forma determinista el primer objeto `{...}` balanceado, elimina bloques Markdown y *trailing commas*, normaliza sinónimos acotados (por ejemplo `ALTO` → `ALTA`, `BACHE` → `HUECO`) y valida contra el esquema estricto `AIAnalysisContract` en Pydantic. Si el JSON es irrecuperable, lanza `AIProviderError("INVALID_JSON")` y conmuta inmediatamente al siguiente proveedor de la cadena.
2. **«¿Cómo garantizan que la IA no modifique ni borre reportes directamente en PostgreSQL?»**
   - *Respuesta:* Ninguna de las herramientas del agente ejecuta `DELETE` ni `UPDATE` de estado final sobre la tabla `reports`. La única herramienta de mutación administrativa es `proponer_actualizacion_critica` en [`backend/app/agent.py`](backend/app/agent.py), que inserta exclusivamente en la tabla `pending_approvals` con estado `PENDING` y activa el guardrail `HUMAN_APPROVAL_REQUIRED`. Solo el endpoint protegido `POST /api/admin/approvals/{id}/decide` (autenticado con `X-Admin-Token` mediante comparación en tiempo constante `hmac.compare_digest`) puede aplicar el cambio.
3. **«¿Por qué durante las pruebas se observa fallback frecuente del modelo primario `gemini-3.8-flash`?»**
   - *Respuesta:* Lo documentamos con total honestidad en [`docs/decisiones.md`](docs/decisiones.md): durante las pruebas reales contra la API de Google AI Studio, `gemini-3.8-flash` presentó episodios de `HTTP 503` por alta demanda en la capa gratuita. Eso demostró en condiciones reales el valor de nuestra arquitectura: el *circuit breaker* abre temporalmente el circuito primario y conmuta a Groq y al segundo modelo Gemini sin degradar la experiencia ciudadana.
4. **«¿Cómo protegen la privacidad de las fotos subidas por los ciudadanos?»**
   - *Respuesta:* En [`backend/app/security.py`](backend/app/security.py), `validate_and_sanitize_image` verifica la firma binaria (*magic bytes* JPEG/PNG/WEBP), decodifica la imagen con Pillow y la re-serializa desde cero creando un lienzo limpio sin diccionarios EXIF ni metadatos GPS ocultos del teléfono antes de guardarla con nombre UUID aleatorio.

# CIVIA — Decisiones de Ingeniería y Mediciones Reales (Momento Evaluativo 2)

**Equipo:** Stefania Córdoba y Sebastian Espinosa  
**Última actualización con mediciones reales:** `2026-11-01T23:49:34Z` (ver reporte reproducible en [`eval/resultados/reporte_evaluacion.json`](eval/resultados/reporte_evaluacion.json) y [`eval/resultados/reporte_evaluacion.md`](eval/resultados/reporte_evaluacion.md)).

---

## 1. Agente y Resiliencia Multimodal (25 puntos)

### Diseño de herramientas tipadas (`backend/app/agent.py`)
- **`consultar_reportes`**: búsqueda SQL parametrizada directa sobre PostgreSQL por categoría (`HUECO`, `BASURAS`, `TALA`, `QUEMA`, `OTRO`), severidad (`BAJA`, `MEDIA`, `ALTA`, `CRITICA`), estado, comuna/barrio (`ILIKE`), texto libre `q` y radio espacial ortodrómico Haversine (`lat`, `lon`, `radius_km`).
- **`obtener_reporte`**: consulta puntual por código de radicado (`CIV-2026-...`) o `UUID`.
- **`clasificar_evidencia`**: análisis multimodal de fotografía + descripción mediante el contrato Pydantic `AIAnalysisContract`, preservando la frontera de confirmación humana (`human_confirmed = False` y estado `ANALYZED_PENDING_CONFIRMATION`).
- **`proponer_actualizacion_critica`**: registra propuestas de cambio de estado en la tabla `pending_approvals` (`status = 'PENDING'`) sin modificar jamás la tabla `reports` directamente.

### Cuatro límites efectivos implementados y verificados con pruebas (`backend/tests/test_ai_and_agent.py`)
1. **Máximo de iteraciones (`AGENT_MAX_ITERATIONS=5`)**: corta el ciclo agéntico al alcanzar el tope de vueltas (`guardrail_triggered = "MAX_ITERATIONS"`).
2. **Presupuesto máximo de tokens (`AGENT_MAX_TOKENS=6000`)**: contabiliza `prompt_tokens + completion_tokens` por turno y detiene el ciclo si se alcanza el presupuesto (`guardrail_triggered = "MAX_TOKENS"`).
3. **Timeout por herramienta (`4.0s`) y presupuesto temporal global (`AI_TIMEOUT_SECONDS=15`)**: cada herramienta corre en un `ThreadPoolExecutor` con timeout estricto (`guardrail_triggered = "TIMEOUT"`).
4. **Confirmación humana obligatoria para escritura crítica (`HUMAN_APPROVAL_REQUIRED`)**: cualquier solicitud de cambio de estado crea un registro en `pending_approvals` que solo se aplica a `reports` cuando un humano autorizado invoca `POST /api/admin/approvals/{id}/decide`.

### Router de proveedores desacoplado (`backend/app/ai_router.py`)
- **Orden configurado por variables de entorno (`.env`)**:
  1. Nivel Primario (`google`): `AI_PRIMARY_MODEL=gemini-3.8-flash` (con respaldo de catálogo `gemini-3-flash-preview` cuando el bucket gratuito diario de 20 RPD se agota).
  2. Nivel de Respaldo Independiente (`groq`): `AI_FALLBACK_MODEL=qwen/qwen3.8-27b` (modelo multimodal con visión y *tool calling* en Groq Cloud).
  3. Nivel Terciario (`google`): `AI_TERTIARY_MODEL=gemini-3.6-flash` (con segunda clave `GOOGLE_API_KEY_SECONDARY` y respaldo `gemini-3.1-flash-lite` en catálogo).
- **Mecanismos de resiliencia**:
  - *Circuit breaker* por `(provider, model)` (`CircuitBreakerState`) con enfriamiento automático (`cooldown_seconds = 10.0s`) y apertura en `HALF_OPEN` del circuito más antiguo si los tres niveles llegan a abrirse simultáneamente (`ensure_at_least_one_circuit_openable`).
  - Conmutación inmediata al siguiente proveedor ante `HTTP_429` sin martillar al proveedor saturado.
  - Extracción determinista y reparación acotada de JSON (`extract_first_json_object` + `parse_and_validate_analysis_json`) validada con `AIAnalysisContract` en Pydantic.
  - Degradación honesta ante caída total (`FALLA_FORZADA=TOTAL`): el reporte ciudadano se almacena íntegro en PostgreSQL con `status = 'PENDING_ANALYSIS'`, sin exponer *tracebacks*, códigos HTTP internos ni nombres de proveedores al ciudadano.

---

## 2. Estrategia de Datos: PostgreSQL / SQL Directo vs. NO RAG (20 puntos)

- **Estrategia escogida**: consulta SQL directa sobre datos relacionales en PostgreSQL 17 (`postgres:17-alpine`), **sin RAG** y **sin PostGIS externo**.
- **Justificación técnica de NO RAG**:
  1. Las preguntas ciudadanas y administrativas sobre CIVIA exigen conteos exactos (`COUNT`), filtros discretos por categoría (`HUECO`, `BASURAS`, `TALA`, `QUEMA`), estado (`PENDING_ANALYSIS`, `ANALYZED_PENDING_CONFIRMATION`, `CONFIRMED`, `IN_REVIEW`, `RESOLVED`), comuna y búsqueda exacta por código de radicado (`CIV-2026-...`).
  2. Un pipeline RAG con *chunking* y *embeddings* vectoriales introduce costo adicional por consulta, mayor latencia, problemas de *recall* en agregaciones tabulares y riesgo de falsos positivos semánticos.
- **Justificación de SQL espacial nativo (B-Tree + Haversine)**:
  - Para consultas por radio en Cali (`lat`, `lon`, `radius_km`), aplicamos primero un filtro de caja delimitadora (*bounding box*) sobre el índice compuesto `idx_reports_coords (latitude, longitude)` y luego calculamos la distancia ortodrómica exacta mediante la fórmula de Haversine en SQL. Esto entrega tiempos de consulta de `< 5 ms` manteniendo la imagen oficial ligera `postgres:17-alpine` lista para levantar con `docker compose up --build` en cualquier equipo limpio.
- **Manejo honesto de información inexistente**:
  - Cuando se consulta por datos inexistentes en la base de datos (ej. caso dorado `GD-06` y consulta `Q14` sobre radiación nuclear o índice satelital NDVI en tiempo real en la Comuna 99), el sistema verifica la ausencia de registros y responde explícitamente que **no existe evidencia registrada en la base de datos de CIVIA**, sin inventar cifras ni sensores.
- **Datos sintéticos explícitamente identificados**:
  - Los 10 registros iniciales de demostración en Cali (`CIV-2026-DEMO0001` a `CIV-2026-DEMO0010`) tienen `is_synthetic = TRUE` en PostgreSQL, insignia visual `DATO SINTÉTICO DEMO` en la PWA y franja explícita `SINTETICO DEMO CIVIA (NO PRIVADO)` en cada imagen generada.

---

## 3. Aplicación Funcional, Seguridad y Prueba de Usabilidad (20 puntos)

- **Controles de seguridad activos (`backend/app/security.py` y `backend/app/main.py`)**:
  - Validación de *magic bytes* reales (`JPEG`, `PNG`, `WEBP`), dimensiones (`32x32` a `8192x8192` px) y **eliminación completa de metadatos EXIF** re-serializando cada imagen con Pillow antes de guardarla en disco con nombre UUID.
  - Validación de notas de voz opcionales (`<= 60s` y `<= 5 MB`).
  - Redacción automática de PII (cédula/teléfono, correos electrónicos) en descripciones ciudadanas (`sanitize_pii_text`).
  - Redacción automática de credenciales (`AIza...`, `gsk_...`, `Bearer ...`) en logs y trazas (`sanitize_secret_text`).
  - Autenticación administrativa en tiempo constante (`hmac.compare_digest`) mediante cabecera `X-Admin-Token`, sin exponer el token por defecto en el bundle del frontend.
  - *Rate limiting* por IP en memoria para creación de reportes (`20 req / 60s`), reanálisis (`25 req / 60s`) y consultas al agente (`30 req / 60s`).
- **Evaluación de usabilidad con usuario externo (`eval/plantilla_usabilidad.md`)**:
  - **Estado actual (No disponible / Pendiente de ejecución presencial)**: Siguiendo la regla estricta de integridad de `AGENTS.md` (*«No inventar resultados de pruebas con personas reales. Preparar la plantilla y dejarla pendiente hasta que se ejecute»*), la plantilla formal de 3 tareas sin instrucciones verbales está lista en [`eval/plantilla_usabilidad.md`](eval/plantilla_usabilidad.md) con tabla de tiempos, dudas y mejoras de UI para diligenciar con un integrante de otro equipo antes de la sustentación.

---

## 4. Evaluación Formal: Latencia, Costo, Precisión y Trazas (25 puntos)

### 4.1 Conjunto de preguntas doradas (`eval/casos_dorados.json`)
Se definieron **6 preguntas doradas (`GD-01` a `GD-06`)** verificadas directamente contra consultas SQL sobre PostgreSQL (`all_sql_verified = True` en `eval/evaluar.py`):
- `GD-01`: Conteo y listado exacto por categoría `HUECO` (`3` reportes: `CIV-2026-DEMO0001`, `CIV-2026-DEMO0007`, `CIV-2026-DEMO0009`).
- `GD-02`: Consulta puntual por código de radicado `CIV-2026-DEMO0004` (`QUEMA`, `CRITICA`, `IN_REVIEW`, `Comuna 2`).
- `GD-03`: Consulta geográfica por división administrativa `Comuna 2` (`2` reportes: `CIV-2026-DEMO0001` y `CIV-2026-DEMO0004`).
- `GD-04`: Consulta espacial Haversine en radio de `1.5 km` alrededor de `(3.3385, -76.5410)` en Pance (`1` reporte: `CIV-2026-DEMO0003`, `TALA`).
- `GD-05`: Consulta por estado `ANALYZED_PENDING_CONFIRMATION` pendiente de confirmación humana (`1` reporte: `CIV-2026-DEMO0008`, `human_confirmed = FALSE`).
- `GD-06`: **Pregunta sin respuesta posible con los datos disponibles** (radiación nuclear / índice satelital NDVI en tiempo real en la inexistente `Comuna 99` → `0` registros).

### 4.2 Métricas reales de la suite de 15 consultas representativas (`eval/evaluar.py`)
Ejecución registrada el **`2026-11-01T23:49:34Z`** (detalle completo en [`eval/resultados/reporte_evaluacion.json`](eval/resultados/reporte_evaluacion.json) y [`eval/resultados/reporte_evaluacion.md`](eval/resultados/reporte_evaluacion.md)):

| Métrica | Valor medido | Clasificación del dato |
|---|---|---|
| **Total de consultas ejecutadas** | `15` (`Q01` a `Q15`) | **Observado** |
| **Aciertos / Errores** | `14 aciertos / 1 error` | **Observado** |
| **Exactitud global de respuestas** | **`93.33%`** (`14/15`) | **Observado** |
| **Precisión de clasificación multimodal (`Q08..Q11` + `Q15`)** | **`100.0%`** (`5/5` sobre imágenes sintéticas de referencia `HUECO`, `BASURAS`, `TALA`, `QUEMA`) | **Observado** |
| **Latencia P50** | **`3549.0 ms`** (`3.55 s`) | **Observado** |
| **Latencia P90** | **`4815.2 ms`** (`4.82 s`) | **Observado** |
| **Latencia mínima / máxima** | `25.0 ms` / `6459.0 ms` | **Observado** |
| **Consumo total de tokens (15 consultas)** | **`30,400 tokens`** (`28,526` prompt + `1,874` completion; promedio `2,026.7 tokens/consulta`) | **Observado** |
| **Costo facturado real en cuentas de desarrollo** | **`$0.000000 USD`** (capa gratuita de Google AI Studio y Groq Cloud) | **Observado** |
| **Costo equivalente estimado por consulta** | **`$0.000375 USD`** (calculado sobre tokens reales con tarifas públicas de referencia por 1M tokens) | **Estimado** |
| **Costo equivalente estimado total (15 consultas)** | **`$0.005623 USD`** | **Estimado** |
| **Distribución de proveedor / modelo utilizado** | `google:gemini-3.8-flash`: `9` \| `groq:qwen/qwen3.8-27b`: `4` \| `google:gemini-3.6-flash`: `1` \| `respaldo SQL determinista`: `1` | **Observado** |
| **Frecuencia de fallback** | **`40.0%`** (`6/15` consultas conmutaron automáticamente ante límite de tasa o falla inyectada) | **Observado** |
| **Tiempo de recuperación ante fallo forzado (`Q15`)** | **`6459 ms`** (en la corrida previa con circuit breaker precalentado: **`897 ms`** hacia Groq) | **Observado** |
| **Pruebas con usuarios externos (3 tareas)** | Plantilla lista en `eval/plantilla_usabilidad.md` | **No disponible (pendiente de sesión presencial)** |

### 4.3 Mejoras concretas de ingeniería introducidas a partir de errores detectados en la evaluación
Durante las corridas iterativas de `eval/evaluar.py` detectamos y corregimos tres defectos reales:
1. **Omisión del signo negativo en longitud occidental por el modelo (`Q05`)**:
   - *Hallazgo en trazas (`ai_traces.tool_calls`)*: al procesar la consulta espacial `Q05` (`latitud 3.3385 y longitud -76.5410 en Pance`), el modelo `qwen/qwen3.8-27b` invocó `consultar_reportes` con `{"lat": 3.3385, "lon": 76.541, "radius_km": 1.5}` omitiendo el signo `-`, lo que buscaba en el hemisferio oriental (`+76.541° E`) y devolvía `0` reportes. Asimismo, cuando el modelo enviaba `comuna="Pance"`, la comparación exacta `UPPER(neighborhood) = UPPER('Pance')` no coincidía con `'Pance (Ecoparque)'`.
   - *Corrección aplicada*: en [`backend/app/agent.py`](backend/app/agent.py) (`tool_consultar_reportes`) normalizamos `lon = -abs(lon)` cuando `70.0 <= lon <= 80.0` (rango longitudinal de Colombia en el hemisferio occidental), y en [`backend/app/repository.py`](backend/app/repository.py) (`list_reports`) cambiamos el filtro de barrio a búsqueda parcial `ILIKE`. Con ello `Q05` pasó de `FAIL` a `PASS` (`3967 ms`).
2. **Bloqueo simultáneo de los 3 *circuit breakers* ante ráfagas `HTTP 429` en capa gratuita**:
   - *Hallazgo*: en la primera corrida, `classify_evidence_with_router` reintentaba `HTTP_429` 3 veces seguidas sobre el mismo proveedor en `150 ms` y abría los circuitos por `45 s` al primer fallo (`failure_threshold = 1`), dejando los tres niveles en `CIRCUIT_OPEN` simultáneamente entre `Q06` y `Q14`.
   - *Corrección aplicada*: en [`backend/app/ai_router.py`](backend/app/ai_router.py) configuramos conmutación inmediata al siguiente proveedor cuando aparece `HTTP_429`, redujimos `cooldown_seconds` a `10.0s`, añadimos `ensure_at_least_one_circuit_openable` para habilitar en `HALF_OPEN` el circuito más antiguo si los tres están abiertos y separamos los modelos de respaldo en catálogo para evitar colisión de cuota RPD. Esto elevó la exactitud de `60.0%` (`9/15`) a **`93.33%` (`14/15`)** y redujo la latencia **P50 de `7128 ms` a `3549 ms`** y **P90 de `16155 ms` a `4815 ms`**.
3. **Normalización de severidad y preservación de `thoughtSignature` en llamadas multi-turno**:
   - *Hallazgo*: `gemini-3.6-flash` devolvía en ocasiones adjetivos masculinos (`"ALTO"`, `"CRÍTICO"`) y Gemini 3 requería conservar el bloque `raw_gemini_part` en el historial de `functionCall`.
   - *Corrección aplicada*: mapeo determinista de sinónimos en `parse_and_validate_analysis_json` y preservación de `raw_gemini_part` en `_call_agent_turn_gemini`.

---

## 5. Sustentación (10 puntos)

- El guion estructurado minuto a minuto (6 minutos de demostración en vivo sobre `http://localhost:5173` sin diapositivas teóricas + 3 minutos de preguntas y respuestas) se encuentra documentado en [`docs/guion_sustentacion.md`](docs/guion_sustentacion.md).
- El mapeo completo contra los 5 criterios de evaluación del Momento 2 se encuentra en [`docs/checklist_rubrica.md`](docs/checklist_rubrica.md).

---

## 6. Decisiones de Ingeniería — Remediación Bloque G2 (2026-11-02)

1. **Contexto monotónico y rollback ante timeouts de herramientas (`A-02`, `M-03`)**:
   - Para evitar escrituras huérfanas o commits retardados en hilos secundarios cuando el hilo principal cancela una herramienta por timeout, se diseñó `_CURRENT_DEADLINE` (`contextvars.ContextVar[float | None]`).
   - Las conexiones de PostgreSQL en `get_conn()` comprueban el tiempo restante antes de abrirse y aplican dinámicamente `SET LOCAL statement_timeout` y `lock_timeout`.
   - La función `checked_commit(conn)` verifica que el deadline monotónico no haya vencido; si venció, aborta de inmediato con `conn.rollback()` y lanza `TimeoutError`.
   - `run_civia_agent()` propaga el deadline global a lo largo de todas las iteraciones y herramientas, garantizando interrupción limpia con el guardrail `"TIMEOUT"` sin dejar transacciones abiertas.

2. **Cotas del lado del servidor y reserva previa de tokens (`M-02`)**:
   - Para impedir agotamiento de recursos o elusión de límites desde el cliente, `AgentQueryRequest` impone cotas Pydantic (`max_iterations <= 5`, `max_tokens_budget <= 6000`).
   - El servidor acota forzosamente cualquier valor con `min(req, settings.MAX)`.
   - Se añadió reserva previa de tokens: si el presupuesto remanente es menor a 60 tokens, el agente detiene el ciclo antes de iniciar la llamada al LLM, marcando `guardrail_triggered = "MAX_TOKENS"`.
   - Se delimita `maxOutputTokens` en llamadas a Gemini y `max_tokens` en Groq al saldo remanente.

3. **Validación estricta de esquemas sin falseo ni coerciones silenciosas (`A-03`, `N-02`)**:
   - Se prohibió la coerción de categorías desconocidas a `OTRO`, la asignación por defecto de severidad `MEDIA` ante valores inventados o faltantes, el relleno de resúmenes artificiales y la admisión de confianzas negativas o fuera de rango. Payloads no conformes levantan `AIProviderError("INVALID_SCHEMA")`.
   - Se eliminó el diccionario `_EXHAUSTED_GEMINI_MODELS` para evitar sustituciones no declaradas de modelos en tiempo de ejecución.

4. **Prevención de tormentas en Circuit Breaker (`M-04`)**:
   - Al transicionar de `OPEN` a `HALF_OPEN`, `CircuitBreakerState` utiliza un candado `threading.Lock()` y la bandera `_half_open_in_flight` para admitir estrictamente un único ensayo concurrentemente, bloqueando ráfagas hacia proveedores en recuperación.

5. **Frontera de seguridad para encabezados de red y asincronía (`M-06`, `A-05`, `M-01`)**:
   - `get_trusted_client_ip()` confía en `X-Forwarded-For` únicamente si la conexión TCP directa proviene de una IP perteneciente a subredes privadas confiables (loopback, redes Docker, RFC1918). Si proviene de un peer externo no confiable, se utiliza su IP real descartando cualquier cabecera spoofed.
   - Operaciones pesadas de CPU/IO se envolvieron con `await run_in_threadpool(...)` para proteger la respuesta del bucle de eventos asíncrono de FastAPI.
   - `validate_and_store_audio()` valida tramas reales de sincronización MP3 y cuadros WAV, rechazando con HTTP 415 archivos falsificados consistentes únicamente en etiquetas `ID3`.

6. **Verificación y ajuste de modelo terciario (`gemini-3.5-flash-lite`)**:
   - Tras comprobar el agotamiento de la cuota diaria gratuita en `gemini-3.6-flash` (`20 req/day`), se verificó mediante API la disponibilidad y capacidades de visión de `gemini-3.5-flash-lite`, adoptándolo como el modelo terciario oficial en configuración y Compose.

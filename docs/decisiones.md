# CIVIA — decisiones y mediciones (Momento 2)

**Equipo:** Stefania Córdoba y Sebastian Espinosa.
**Estado:** pendiente de medición real; no registrar cifras inventadas.

## Agente (25 puntos)
- Diseño de herramientas tipadas implementadas en `backend/app/agent.py`:
  - `consultar_reportes`: búsqueda SQL directa por categoría (`HUECO`, `BASURAS`, `TALA`, `QUEMA`, `OTRO`), severidad (`BAJA`, `MEDIA`, `ALTA`, `CRITICA`), estado, comuna, texto libre `q` y radio espacial Haversine (`lat`, `lon`, `radius_km`).
  - `obtener_reporte`: consulta puntual por código de radicado (`CIV-2026-...`) o `UUID`.
  - `clasificar_evidencia`: análisis multimodal de fotografía + descripción mediante `AIAnalysisContract` preservando la frontera de confirmación humana (`human_confirmed = False`).
  - `proponer_actualizacion_critica`: registra propuestas de cambio de estado en `pending_approvals` (`status = 'PENDING'`) sin modificar jamás la tabla `reports` directamente.
- Cuatro límites efectivos implementados y verificados con pruebas (`backend/tests/test_ai_and_agent.py`):
  1. **Máximo de iteraciones (`AGENT_MAX_ITERATIONS=5`)**: corta el ciclo agéntico al alcanzar el tope de vueltas (`guardrail_triggered = "MAX_ITERATIONS"`).
  2. **Presupuesto máximo de tokens (`AGENT_MAX_TOKENS=6000`)**: contabiliza `prompt_tokens + completion_tokens` por turno y detiene el ciclo si se alcanza el presupuesto (`guardrail_triggered = "MAX_TOKENS"`).
  3. **Timeout por herramienta (`4.0s`) y presupuesto temporal global (`AI_TIMEOUT_SECONDS=15`)**: cada herramienta corre en un `ThreadPoolExecutor` con timeout estricto (`guardrail_triggered = "TIMEOUT"`).
  4. **Confirmación humana obligatoria para escritura crítica (`HUMAN_APPROVAL_REQUIRED`)**: cualquier solicitud de cambio de estado crea un registro en `pending_approvals` que solo se aplica a `reports` cuando un humano invoca `POST /api/admin/approvals/{id}/decide`.
- Proveedores desacoplados Gemini/Groq (`backend/app/ai_router.py`):
  - Orden configurado por `.env`: 1) `gemini-3.8-flash` (Google) → 2) `qwen/qwen3.8-27b` (Groq) → 3) `gemini-3.6-flash` (Google).
  - Resiliencia: reintentos acotados con *backoff* exponencial y *jitter*, *circuit breaker* por `(provider, model)` con enfriamiento, extracción y reparación acotada de JSON y validación Pydantic (`AIAnalysisContract`).
  - Si todos los proveedores fallan (`FALLA_FORZADA=TOTAL`), el reporte se guarda con `status = 'PENDING_ANALYSIS'` y la interfaz muestra confirmación honesta con cero *tracebacks* y cero nombres de proveedores.

## Datos (20 puntos)
- Estrategia escogida: consulta SQL directa de datos relacionales de reportes en PostgreSQL 17 (`postgres:17-alpine`), **no RAG** y **sin PostGIS externo**.
- Justificación de NO RAG:
  - Los reportes ciudadanos y consultas operativas requieren agregaciones deterministas (`COUNT`, `GROUP BY`), filtros exactos por categoría (`HUECO`, `BASURAS`, `TALA`, `QUEMA`), estado (`PENDING_ANALYSIS`, `CONFIRMED`, `IN_REVIEW`, `RESOLVED`), comuna, fecha e identificador único (`UUID` y `tracking_code` tipo `CIV-2026-XXXX`).
  - Un pipeline RAG con *embeddings* y búsqueda vectorial introduce errores de *recall* en conteos exactos, costo innecesario de indexación y riesgo de alucinación al responder preguntas cuantitativas sobre registros tabulares.
- Justificación de SQL espacial nativo (B-Tree + Haversine) frente a PostGIS:
  - Para búsquedas por radio en Cali y Valle del Cauca (`lat`, `lon`, `radius_km`), un pre-filtro de *bounding box* sobre el índice compuesto `idx_reports_coords (latitude, longitude)` combinado con la fórmula de distancia ortodrómica de Haversine en SQL directo logra precisión métrica en milisegundos conservando la imagen oficial ligera `postgres:17-alpine` sin dependencias adicionales de compilación.
- Ausencia de datos: responder explícitamente que no existe evidencia registrada en la base de datos para ese criterio (demostrado con consulta sobre Comuna 99 / radiación nuclear / NDVI satelital), jamás inventar cifras.
- Datos sintéticos identificados: se incluyeron 10 reportes sintéticos de demostración en Cali (`CIV-2026-DEMO0001` a `CIV-2026-DEMO0010`) marcados en BD con `is_synthetic = TRUE` y franja visual explícita `SINTETICO DEMO CIVIA (NO PRIVADO)` en sus imágenes generadas.

## Aplicación (20 puntos)
- Prueba de otro equipo: pendiente, anotar 3 tareas y ajustes posteriores.
- Fallos esperados: 429, timeout, JSON inválido, caída total; evidencia técnica protegida y UI ciudadana limpia.

## Medición y trazas (25 puntos)
- Fecha de medición: PENDIENTE.
- Suite: mínimo 5 preguntas doradas verificadas manualmente (al menos 1 sin respuesta posible); 15 consultas representativas.
- Acierto: PENDIENTE.
- P50 latencia: PENDIENTE ms.
- P90 latencia: PENDIENTE ms.
- Costo medio por consulta: PENDIENTE USD (real o estimación con tokens y tarifa identificada; documentar método).
- Uso/costo total y estrategia de caché: PENDIENTE.
- Trazas internas sin API keys: PENDIENTE.

## Sustentación (10 puntos)
- 6 minutos demostración desde aplicación funcional, 3 minutos preguntas.
- Demostrar fronteras IA/código, tool calling, fallback, trazas y cifras sin exponer fallos técnicos al ciudadano.

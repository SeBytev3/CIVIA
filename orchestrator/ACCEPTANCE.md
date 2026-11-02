# CIVIA — Criterios de Aceptación (ACCEPTANCE)

Este documento define las condiciones estrictas y verificables que el orquestador y los agentes deben satisfacer para declarar un hallazgo o bloque como **PASS**.

---

## 1. Bloque G2.1 — Remediación Residual Inmediata

### M-03 — Deadline Integral y Manejo Defensivo de Errores
- [ ] **Aislamiento de trabajadores no cooperativos:** `execute_tool_with_timeout` no debe bloquearse indefinidamente en `executor.shutdown(wait=True)`. Si un worker no responde, debe acotarse el tiempo de espera y cancelarse las conexiones activas sin colgar el ciclo de vida del request.
- [ ] **Corrección del manejador de TimeoutError:** En `backend/app/main.py:548`, corregir el `NameError` (`uuid.uuid4()`); asegurar importación correcta del módulo `uuid`. El fallback defensivo debe retornar HTTP 200 con guardrail `TIMEOUT`, sin jamás emitir HTTP 500.
- [ ] **Alineación de esquema HTTP:** Si se admite un timeout de 0.10 s en el agente, `schemas.py` debe aceptar `ge=0.10` (no `gt=0.10`) para evitar rechazos 422 en valores límite válidos.

### M-06 — Confianza de Proxy y Prevención de Evasión de Tasa
- [ ] **Configuración efectiva de Uvicorn y Middleware:** No confiar ciegamente en `X-Forwarded-For` proveniente de conexiones directas locales o privadas sin que provengan de un proxy de confianza validado.
- [ ] **Verificación contra evasión:** Múltiples peticiones con IPs ficticias en `XFF` desde un peer no confiable deben acumularse contra la IP real de conexión y recibir HTTP 429 al alcanzar el límite.

### M-02 — Presupuesto y Estimación de Tokens Multimodal
- [ ] **Propagación del presupuesto al hilo ejecutor:** El contexto de `TokenBudgetTracker` debe propagarse explícitamente a los trabajadores en `ThreadPoolExecutor`.
- [ ] **Reserva previa en análisis multimodal:** Antes de invocar el proveedor multimodal (visión/audio), calcular y reservar los tokens de entrada estimados (~1600 tokens). Si el saldo es insuficiente, abortar antes de la llamada de red.

---

## 2. Bloque G2.2 — Cierre de Hallazgos Residuales
- [ ] **A-03:** Validación estricta de JSON en router sin sustitución silenciosa de campos ni invención de categorías.
- [ ] **A-04:** Sanitización rigurosa de texto y PII en respuestas al ciudadano y repositorio público.
- [ ] **A-05:** Cierre de inconsistencias y verificación de integridad referencial.
- [ ] **M-01:** Validación profunda de cabeceras y bytes de audio (rechazo de ID3-only dummy).
- [ ] **M-04:** Circuit breaker con exactamente una sonda en estado `HALF_OPEN`.

---

## 3. Bloque G3 — Evaluación Formal y Auditoría de Cierre
- [ ] **Conjunto Dorado:** `eval/casos_dorados.json` con >= 5 preguntas verificadas manualmente sobre datos reales de PostgreSQL (al menos una no respondible).
- [ ] **Métricas Reales:** Suite de evaluación (`eval/evaluar.py`) reportando latencias P50 y P90 reales, costo estimado, precisión y trazas protegidas.
- [ ] **Observabilidad:** Endpoints de observabilidad protegidos mediante token administrativo criptográfico seguro.
- [ ] **README Desplegable:** Documentación integral que permita a un tercero clonar y levantar CIVIA con un único comando.

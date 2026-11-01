# Checklist de Evidencias contra la Rúbrica Oficial — CIVIA (Momento 2)

**Equipo:** Stefania Córdoba y Sebastian Espinosa · Universidad Cooperativa de Colombia.  
**Nota:** Este documento organiza las evidencias técnicas verificables para facilitar la revisión del profesor. **No incluye autocalificación numérica**, dado que la calificación corresponde exclusivamente al docente evaluador.

---

## 1. Agente (Peso en rúbrica: 25 puntos)

| Requisito evaluado | Archivos de implementación | Pruebas automatizadas y scripts | Evidencia verificable |
|---|---|---|---|
| **Agente genuino con herramientas tipadas y descripciones claras** | `backend/app/agent.py` (`AGENT_TOOLS_SPEC`, `tool_consultar_reportes`, `tool_obtener_reporte`, `tool_clasificar_evidencia`, `tool_proponer_actualizacion_critica`) | `backend/tests/test_ai_and_agent.py::test_agent_tools_and_unanswerable_query` y `eval/evaluar.py` (`Q01..Q07`, `Q12..Q14`) | El agente selecciona e invoca herramientas sobre PostgreSQL antes de sintetizar respuestas; la IA jamás escribe directamente en la tabla `reports`. |
| **Límite 1: Máximo de iteraciones (`AGENT_MAX_ITERATIONS=5`)** | `backend/app/agent.py` (`run_civia_agent`) | `backend/tests/test_ai_and_agent.py::test_four_agent_guardrails_enforced` | Corta el ciclo al alcanzar `max_iterations` y retorna `guardrail_triggered = "MAX_ITERATIONS"`. |
| **Límite 2: Presupuesto máximo de tokens (`AGENT_MAX_TOKENS=6000`)** | `backend/app/agent.py` (`run_civia_agent`) | `backend/tests/test_ai_and_agent.py::test_four_agent_guardrails_enforced` | Acumula `prompt_tokens + completion_tokens` por turno y detiene la ejecución con `guardrail_triggered = "MAX_TOKENS"`. |
| **Límite 3: Timeout por herramienta y presupuesto temporal total** | `backend/app/agent.py` (`execute_tool_with_timeout`, `ThreadPoolExecutor`) | `backend/tests/test_ai_and_agent.py::test_four_agent_guardrails_enforced` | Aborta herramientas lentas superado `tool_timeout_seconds` y registra `TOOL_TIMEOUT` en `ai_traces`. |
| **Límite 4: Confirmación humana obligatoria para escrituras críticas** | `backend/app/agent.py` (`tool_proponer_actualizacion_critica`, `decide_pending_approval`), tabla `pending_approvals` en `001_initial_schema.sql` | `backend/tests/test_ai_and_agent.py::test_four_agent_guardrails_enforced` y `eval/evaluar.py` (`Q13`) | Las propuestas de cambio de estado quedan en `pending_approvals` (`PENDING`) y solo modifican `reports` cuando un humano aprueba en `/api/admin/approvals/{id}/decide`. |
| **Proveedores desacoplados (`Gemini` → `Groq` → `Gemini`)** | `backend/app/ai_router.py` (`get_provider_chain`, `_call_gemini_multimodal`, `_call_groq_multimodal`) | `backend/tests/test_ai_and_agent.py::test_router_resilience_and_fallback_across_providers` | Configuración 100% por variables de entorno (`AI_PRIMARY_MODEL`, `AI_FALLBACK_MODEL`, `AI_TERTIARY_MODEL`). |

---

## 2. Datos (Peso en rúbrica: 20 puntos)

| Requisito evaluado | Archivos de implementación | Pruebas automatizadas y scripts | Evidencia verificable |
|---|---|---|---|
| **Estrategia de datos coherente y justificación de NO RAG** | `backend/app/repository.py`, `backend/migrations/001_initial_schema.sql`, `docs/decisiones.md` | `backend/tests/test_reports_crud.py` | Consultas SQL parametrizadas directas e índices B-Tree + fórmula espacial Haversine; justificación técnica en `docs/decisiones.md`. |
| **Manejo honesto de ausencia de datos (cero alucinación)** | `backend/app/agent.py` (`tool_consultar_reportes`, `AGENT_SYSTEM_PROMPT`), `eval/casos_dorados.json` (`GD-06`) | `backend/tests/test_ai_and_agent.py::test_agent_tools_and_unanswerable_query` y `eval/evaluar.py` (`Q14`) | Ante consultas sobre Comuna 99, radiación nuclear o NDVI satelital, responde explícitamente que no existe evidencia registrada (`0 encontrados`). |
| **Distinción explícita de datos sintéticos frente a reales** | `backend/app/seed.py` (`SYNTHETIC_REPORTS`, `generate_synthetic_evidence_png`), columna `is_synthetic` en `reports` | `backend/tests/test_reports_crud.py::test_synthetic_fixtures_loaded_and_identifiable` | Los 10 registros de demostración tienen `is_synthetic = true`, etiqueta UI `DEMO SINTÉTICO` y franja en imagen `SINTETICO DEMO CIVIA (NO PRIVADO)`. |

---

## 3. Aplicación y Resiliencia (Peso en rúbrica: 20 puntos)

| Requisito evaluado | Archivos de implementación | Pruebas automatizadas y scripts | Evidencia verificable |
|---|---|---|---|
| **Flujo vertical ciudadano completo y PWA** | `frontend/src/App.tsx`, `frontend/src/components/CaliMap.tsx`, `frontend/public/manifest.webmanifest`, `frontend/public/sw.js`, `backend/app/main.py` | `backend/tests/test_ai_and_agent.py::test_vertical_flow_create_analyze_confirm_and_query`, `backend/tests/test_e2e_frontend_proxy.py` | Crear reporte con foto/audio/GPS → guardar en PostgreSQL → clasificar con IA → confirmar/corregir categoría por ciudadano → consultar por radicado. |
| **Resiliencia ante 429, 503, Timeout, JSON inválido y caída total** | `backend/app/ai_router.py` (`CircuitBreakerState`, `parse_and_validate_analysis_json`, `classify_evidence_with_router`) | `backend/tests/test_ai_and_agent.py` (parametrizado con `429`, `503`, `TIMEOUT`, `INVALID_JSON`, `GROQ_FAIL`, `TOTAL`) | Conmutación automática entre proveedores; si todos fallan (`TOTAL`), el reporte se guarda con `PENDING_ANALYSIS` sin perder datos. |
| **Cero tracebacks, errores HTTP internos o nombres de proveedores al ciudadano** | `backend/app/main.py` (exception handlers), `frontend/src/api.ts`, `backend/app/observability.py` (`sanitize_secret_text`) | `backend/tests/test_ai_and_agent.py::test_secret_sanitization_never_leaks_keys` | Respuestas ciudadanas limpias; detalles técnicos restringidos a `/api/admin/observability` con `X-Admin-Token`. |
| **Protocolo de prueba de usabilidad externa (3 tareas)** | `eval/plantilla_usabilidad.md` | Revisión documental | Plantilla lista con 3 tareas sin instrucciones verbales y consentimiento; marcada honestamente como pendiente de sesión presencial. |

---

## 4. Medición y Trazas (Peso en rúbrica: 25 puntos)

| Requisito evaluado | Archivos de implementación | Pruebas automatizadas y scripts | Evidencia verificable |
|---|---|---|---|
| **Mínimo 5 preguntas doradas verificadas por SQL (1 sin respuesta)** | `eval/casos_dorados.json` (`GD-01` a `GD-06`) | `eval/evaluar.py` (`verify_golden_sql_ground_truth`) | 6 casos dorados con consulta SQL de comprobación, fecha de verificación y distinción de datos sintéticos. |
| **Suite de 15 consultas representativas y métricas P50/P90/costo/precisión** | `eval/evaluar.py`, `eval/resultados/reporte_evaluacion.json`, `eval/resultados/reporte_evaluacion.md`, `docs/decisiones.md` | `docker compose exec -T api python eval/evaluar.py --mode all` | Exactitud global observada: `93.33%` (`14/15`), precisión multimodal: `100.0%` (`5/5`), `P50 = 3549.0 ms`, `P90 = 4815.2 ms`, `30,400` tokens, costo facturado `$0.00 USD` / estimado `$0.000375 USD` por consulta, y mejoras documentadas tras hallazgos en `Q05`. |
| **Trazas observables sin exponer API keys** | `backend/app/observability.py`, tabla `ai_traces` | `backend/tests/test_ai_and_agent.py::test_protected_observability_endpoint` | Cada llamada e intento de *fallback* queda en `ai_traces` con `trace_group_id`, latencia, tokens y causa técnica sanitizada. |

---

## 5. Sustentación y Reproducibilidad (Peso en rúbrica: 10 puntos)

| Requisito evaluado | Archivos de implementación | Pruebas automatizadas y scripts | Evidencia verificable |
|---|---|---|---|
| **Despliegue reproducible con Docker Compose desde clon limpio** | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `.env.example`, `README.md`, `scripts/run.ps1`, `run.sh` | Prueba de clon limpio en directorio aislado (`Fase F2`) | Levanta `db`, `api` y `frontend` en un comando sin requerir Node.js ni Python instalados en el host. |
| **Guion de sustentación 6 + 3 minutos** | `docs/guion_sustentacion.md` | Revisión documental | Guion cronometrado para Stefania Córdoba y Sebastian Espinosa iniciando directamente sobre la aplicación funcional. |

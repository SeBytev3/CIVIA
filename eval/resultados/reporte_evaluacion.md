# Reporte Reproducible de Evaluación — CIVIA (Momento 2)

- **Fecha de ejecución (UTC):** `2026-11-01T23:49:34.028010+00:00`
- **Equipo:** Stefania Córdoba y Sebastian Espinosa
- **Casos dorados verificados por SQL:** `6/6` (`all_sql_verified = True`)

## 1. Resumen de Métricas Obligatorias (15 Consultas Representativas)

| Métrica | Valor | Tipo de dato |
|---|---|---|
| Total de consultas ejecutadas | `15` | Observado |
| Aciertos / Errores | `14 aciertos / 1 errores` | Observado |
| Exactitud global de respuestas | `93.33%` (`14/15`) | Observado |
| Precisión de clasificación multimodal (`Q08..Q11` + `Q15`) | `100.0%` (`5/5`) | Observado |
| Latencia **P50** | `3549.0 ms` | Observado |
| Latencia **P90** | `4815.2 ms` | Observado |
| Tokens consumidos totales (prompt + completion) | `30400` (`28526` in / `1874` out) | Observado |
| Costo facturado real (tier gratuito AI Studio / Groq) | `$0.000000 USD` | Observado |
| Costo equivalente estimado por consulta | `$0.000375 USD` | Estimado por tarifa/tokens |
| Costo equivalente estimado total (15 consultas) | `$0.005623 USD` | Estimado por tarifa/tokens |
| Frecuencia de fallback | `40.0%` (`6/15`) | Observado |
| Tiempo de recuperación ante fallo forzado 429 (`Q15`) | `6459 ms` | Observado |
| Distribución de proveedor/modelo | `{"google:gemini-3.8-flash": 9, "groq:qwen/qwen3.8-27b": 4, "none:none": 1, "google:gemini-3.6-flash": 1}` | Observado |

## 2. Detalle por Consulta (`Q01` .. `Q15`)

| ID | Grupo | Proveedor / Modelo | Latencia (ms) | Tokens | Fallback | Resultado |
|---|---|---|---|---|---|---|
| `Q01` | `1_consulta_exacta` | `google:gemini-3.8-flash` | `2823` | `2960` | `False` | **PASS** |
| `Q02` | `1_consulta_exacta` | `google:gemini-3.8-flash` | `2600` | `2792` | `False` | **PASS** |
| `Q03` | `1_consulta_exacta` | `google:gemini-3.8-flash` | `3371` | `2822` | `False` | **PASS** |
| `Q04` | `2_consulta_espacial` | `groq:qwen/qwen3.8-27b` | `3014` | `3239` | `True` | **PASS** |
| `Q05` | `2_consulta_espacial` | `google:gemini-3.8-flash` | `3967` | `2802` | `False` | **PASS** |
| `Q06` | `3_interpretacion_descripcion` | `google:gemini-3.8-flash` | `4340` | `2841` | `False` | **PASS** |
| `Q07` | `3_interpretacion_descripcion` | `google:gemini-3.8-flash` | `3836` | `2707` | `False` | **PASS** |
| `Q08` | `4_clasificacion_multimodal` | `google:gemini-3.8-flash` | `3780` | `1569` | `False` | **PASS** |
| `Q09` | `4_clasificacion_multimodal` | `groq:qwen/qwen3.8-27b` | `4745` | `2294` | `True` | **PASS** |
| `Q10` | `4_clasificacion_multimodal` | `google:gemini-3.8-flash` | `3377` | `1460` | `False` | **PASS** |
| `Q11` | `4_clasificacion_multimodal` | `groq:qwen/qwen3.8-27b` | `4862` | `2314` | `True` | **PASS** |
| `Q12` | `5_seleccion_herramientas` | `google:gemini-3.8-flash` | `3549` | `1033` | `True` | **PASS** |
| `Q13` | `5_seleccion_herramientas_y_guardrail` | `groq:qwen/qwen3.8-27b` | `833` | `0` | `True` | **FAIL** |
| `Q14` | `6_informacion_insuficiente` | `none:none` | `25` | `0` | `False` | **PASS** |
| `Q15` | `7_fallo_y_recuperacion_proveedores` | `google:gemini-3.6-flash` | `6459` | `1567` | `True` | **PASS** |

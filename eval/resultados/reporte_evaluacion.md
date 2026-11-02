# Reporte Reproducible de Evaluación — CIVIA (Momento 2)

- **Fecha de ejecución (UTC):** `2026-11-02T14:17:12.703152+00:00`
- **Equipo:** Stefania Córdoba y Sebastian Espinosa
- **Casos dorados verificados por SQL:** `6/6` (`all_sql_verified = True`)

## 1. Resumen de Métricas Obligatorias (15 Consultas Representativas)

| Métrica | Valor | Tipo de dato |
|---|---|---|
| Total de consultas ejecutadas | `15` | Observado |
| Aciertos / Errores | `11 aciertos / 4 errores` | Observado |
| Exactitud global de respuestas | `73.33%` (`11/15`) | Observado |
| Precisión de clasificación multimodal (`Q08..Q11` + `Q15`) | `40.0%` (`2/5`) | Observado |
| Latencia **P50** | `2692.0 ms` | Observado |
| Latencia **P90** | `11531.8 ms` | Observado |
| Tokens consumidos totales (prompt + completion) | `17820` (`16450` in / `1370` out) | Observado |
| Costo facturado real (tier gratuito AI Studio / Groq) | `$0.000000 USD` | Observado |
| Costo equivalente estimado por consulta | `$0.000224 USD` | Estimado por tarifa/tokens |
| Costo equivalente estimado total (15 consultas) | `$0.003354 USD` | Estimado por tarifa/tokens |
| Frecuencia de fallback | `73.33%` (`11/15`) | Observado |
| Tiempo de recuperación ante fallo forzado 429 (`Q15`) | `1649 ms` | Observado |
| Distribución de proveedor/modelo | `{"google:gemini-3.5-flash-lite": 11, "google:gemini-3.8-flash": 2, "groq:qwen/qwen3.8-27b": 2}` | Observado |

## 2. Detalle por Consulta (`Q01` .. `Q15`)

| ID | Grupo | Proveedor / Modelo | Latencia (ms) | Tokens | Fallback | Resultado |
|---|---|---|---|---|---|---|
| `Q01` | `1_consulta_exacta` | `google:gemini-3.5-flash-lite` | `3349` | `3054` | `True` | **PASS** |
| `Q02` | `1_consulta_exacta` | `google:gemini-3.5-flash-lite` | `6139` | `0` | `True` | **PASS** |
| `Q03` | `1_consulta_exacta` | `google:gemini-3.8-flash` | `357` | `0` | `True` | **PASS** |
| `Q04` | `2_consulta_espacial` | `groq:qwen/qwen3.8-27b` | `264` | `0` | `True` | **PASS** |
| `Q05` | `2_consulta_espacial` | `google:gemini-3.5-flash-lite` | `2078` | `2652` | `False` | **PASS** |
| `Q06` | `3_interpretacion_descripcion` | `google:gemini-3.5-flash-lite` | `2692` | `2613` | `False` | **PASS** |
| `Q07` | `3_interpretacion_descripcion` | `google:gemini-3.5-flash-lite` | `4275` | `2563` | `False` | **PASS** |
| `Q08` | `4_clasificacion_multimodal` | `google:gemini-3.5-flash-lite` | `2824` | `1562` | `True` | **PASS** |
| `Q09` | `4_clasificacion_multimodal` | `google:gemini-3.5-flash-lite` | `15145` | `0` | `True` | **FAIL** |
| `Q10` | `4_clasificacion_multimodal` | `google:gemini-3.5-flash-lite` | `921` | `0` | `True` | **FAIL** |
| `Q11` | `4_clasificacion_multimodal` | `google:gemini-3.5-flash-lite` | `15127` | `0` | `True` | **FAIL** |
| `Q12` | `5_seleccion_herramientas` | `google:gemini-3.8-flash` | `755` | `0` | `True` | **PASS** |
| `Q13` | `5_seleccion_herramientas_y_guardrail` | `groq:qwen/qwen3.8-27b` | `1135` | `1385` | `True` | **PASS** |
| `Q14` | `6_informacion_insuficiente` | `google:gemini-3.5-flash-lite` | `2876` | `2433` | `False` | **FAIL** |
| `Q15` | `7_fallo_y_recuperacion_proveedores` | `google:gemini-3.5-flash-lite` | `1649` | `1558` | `True` | **PASS** |

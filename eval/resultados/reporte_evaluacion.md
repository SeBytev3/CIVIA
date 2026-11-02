# Reporte Reproducible de Evaluación — CIVIA (Momento 2)

- **Fecha de ejecución (UTC):** `2026-11-02T15:16:49.872904+00:00`
- **Equipo:** Stefania Córdoba y Sebastian Espinosa
- **Casos dorados verificados por SQL:** `6/6` (`all_sql_verified = True`)

## 1. Resumen de Métricas Obligatorias (15 Consultas Representativas)

| Métrica | Valor | Tipo de dato |
|---|---|---|
| Total de consultas ejecutadas | `15` | Observado |
| Aciertos / Errores | `11 aciertos / 4 errores` | Observado |
| Exactitud global de respuestas | `73.33%` (`11/15`) | Observado |
| Precisión de clasificación multimodal (`Q08..Q11` + `Q15`) | `40.0%` (`2/5`) | Observado |
| Latencia **P50** | `2767.0 ms` | Observado |
| Latencia **P90** | `6380.4 ms` | Observado |
| Tokens consumidos totales (prompt + completion) | `26995` (`25163` in / `1832` out) | Observado |
| Costo facturado real (tier gratuito AI Studio / Groq) | `$0.000000 USD` | Observado |
| Costo equivalente estimado por consulta | `$0.000325 USD` | Estimado por tarifa/tokens |
| Costo equivalente estimado total (15 consultas) | `$0.004874 USD` | Estimado por tarifa/tokens |
| Frecuencia de fallback | `53.33%` (`8/15`) | Observado |
| Tiempo de recuperación ante fallo forzado 429 (`Q15`) | `741 ms` | Observado |
| Distribución de proveedor/modelo | `{"google:gemini-3.5-flash-lite": 15}` | Observado |

## 2. Detalle por Consulta (`Q01` .. `Q15`)

| ID | Grupo | Proveedor / Modelo | Latencia (ms) | Tokens | Fallback | Resultado |
|---|---|---|---|---|---|---|
| `Q01` | `1_consulta_exacta` | `google:gemini-3.5-flash-lite` | `3372` | `3055` | `True` | **PASS** |
| `Q02` | `1_consulta_exacta` | `google:gemini-3.5-flash-lite` | `6464` | `2713` | `False` | **PASS** |
| `Q03` | `1_consulta_exacta` | `google:gemini-3.5-flash-lite` | `2335` | `2668` | `False` | **PASS** |
| `Q04` | `2_consulta_espacial` | `google:gemini-3.5-flash-lite` | `3653` | `2833` | `False` | **PASS** |
| `Q05` | `2_consulta_espacial` | `google:gemini-3.5-flash-lite` | `3762` | `2656` | `False` | **PASS** |
| `Q06` | `3_interpretacion_descripcion` | `google:gemini-3.5-flash-lite` | `7976` | `2601` | `True` | **PASS** |
| `Q07` | `3_interpretacion_descripcion` | `google:gemini-3.5-flash-lite` | `6255` | `0` | `True` | **PASS** |
| `Q08` | `4_clasificacion_multimodal` | `google:gemini-3.5-flash-lite` | `793` | `0` | `True` | **FAIL** |
| `Q09` | `4_clasificacion_multimodal` | `google:gemini-3.5-flash-lite` | `298` | `0` | `True` | **FAIL** |
| `Q10` | `4_clasificacion_multimodal` | `google:gemini-3.5-flash-lite` | `1857` | `1557` | `True` | **PASS** |
| `Q11` | `4_clasificacion_multimodal` | `google:gemini-3.5-flash-lite` | `1405` | `1561` | `True` | **PASS** |
| `Q12` | `5_seleccion_herramientas` | `google:gemini-3.5-flash-lite` | `2595` | `2537` | `False` | **PASS** |
| `Q13` | `5_seleccion_herramientas_y_guardrail` | `google:gemini-3.5-flash-lite` | `2767` | `2483` | `False` | **PASS** |
| `Q14` | `6_informacion_insuficiente` | `google:gemini-3.5-flash-lite` | `3832` | `2331` | `False` | **FAIL** |
| `Q15` | `7_fallo_y_recuperacion_proveedores` | `google:gemini-3.5-flash-lite` | `741` | `0` | `True` | **FAIL** |

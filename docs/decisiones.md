# CIVIA — decisiones y mediciones (Momento 2)

**Equipo:** Stefania Córdoba y Sebastian Espinosa.
**Estado:** pendiente de medición real; no registrar cifras inventadas.

## Agente (25 puntos)
- Diseño de herramientas: `consultar_reportes`, `obtener_reporte`, `clasificar_evidencia` (pendiente de implementar en Fase D).
- Guardrails: máximo vueltas, presupuesto tokens, timeout herramienta, confirmación humana (pendiente de demostrar en Fase D).
- Proveedores desacoplados Gemini/Groq:
  - Preflight de modelos verificado en Fase A contra APIs oficiales:
    - Primario (`AI_PRIMARY_MODEL=gemini-3.8-flash`): disponible en catálogo `/v1beta/models`, pero propenso a picos `503/timeout` bajo alta demanda; se protegerá con timeout por intento y circuit breaker para conmutar rápido sin bloquear al ciudadano.
    - Respaldo independiente (`AI_FALLBACK_MODEL=qwen/qwen3.8-27b` en Groq): verificado con soporte real de visión (imágenes >= 32x32 px), salida JSON (`json_object`) y *tool calling*.
    - Alternativo (`AI_TERTIARY_MODEL=gemini-3.6-flash` en Google): verificado con soporte real de visión, salida JSON (`application/json`) y *tool calling* (~1.67s de latencia).
    - Nota sobre cuotas: dos claves Google en un mismo proyecto comparten cuota, por lo que el respaldo real ante `429` de cuota de proyecto recae en el proveedor independiente Groq (`qwen/qwen3.8-27b`), mientras que la clave secundaria / tercer modelo cubre fallos específicos de modelo (`503` en `gemini-3.8-flash` mientras `gemini-3.6-flash` está operativo).

## Datos (20 puntos)
- Estrategia escogida: consulta SQL directa de datos relacionales de reportes, no RAG.
- Justificación: filtros por categoría, fecha, estado e identificador requieren consulta exacta; RAG añade complejidad sin beneficio probado para ese problema.
- Ausencia de datos: responder que no hay evidencia, jamás inventar.

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

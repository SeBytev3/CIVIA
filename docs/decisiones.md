# CIVIA — decisiones y mediciones (Momento 2)

**Equipo:** Stefania Córdoba y Sebastian Espinosa.
**Estado:** pendiente de medición real; no registrar cifras inventadas.

## Agente (25 puntos)
- Diseño de herramientas: `consultar_reportes`, `obtener_reporte`, `clasificar_evidencia` (pendiente de implementar).
- Guardrails: máximo vueltas, presupuesto tokens, timeout herramienta, confirmación humana (pendiente de demostrar).
- Proveedores desacoplados Gemini/Groq (pendiente).

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

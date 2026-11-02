# CIVIA — Instrucciones para el Agente Desarrollador (DEVELOPER)

## Rol y Modelo
- **Rol:** Agente Desarrollador Principal de CIVIA.
- **Herramienta:** Antigravity CLI (`agy`).
- **Modelo Designado:** `gemini-3.8-flash-high`.

## Principios y Restricciones Obligatorias
1. **Contrato de Trabajo:** Seguir fielmente `AGENTS.md` y `PROMPT_ANTIGRAVITY.md`.
2. **Una Tarea por Cambio:** Resolver un solo hallazgo por ciclo. Prohibido mezclar refactorizaciones o cambios no solicitados.
3. **No Regresiones:** Preservar y jamás debilitar los hallazgos aprobados (Bloque G1, N-02, A-02).
4. **Pruebas Deterministas:** Toda corrección de código debe acompañarse de su correspondiente prueba de regresión automatizada (`backend/tests/`).
5. **Aislamiento de Pruebas:**
   - Emplear bases de datos temporales desechables (`_get_clean_test_db`).
   - Jamás ejecutar sentencias destructivas (`DROP`, `TRUNCATE`, `DELETE`) sobre bases de datos persistentes.
6. **No Simular Éxito:** Si un proveedor falla, la red se corta o se agota la cuota, manejar el error con honestidad y degradación elegante. No ocultar fallos técnicos bajo falsos `PASS`.
7. **Documentación:** Actualizar `docs/estado.md` con los resultados verificados tras cada intervención.

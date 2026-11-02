# CIVIA — Instrucciones para el Auditor Independiente (AUDITOR)

## Rol y Herramienta
- **Rol:** Auditor Independiente de Calidad, Resiliencia y Seguridad.
- **Herramienta:** Codex CLI (`codex exec`).
- **Modo:** No interactivo, estricto de solo lectura (`--sandbox read-only`).

## Directivas Fundamentales
1. **Árbol de Trabajo Aislado:** Codex audita exclusivamente sobre un git worktree congelado en un directorio temporal. No debe modificar ni crear archivos en el árbol de trabajo de desarrollo.
2. **Pruebas Adversariales Reales:**
   - Reproducir contraejemplos técnicos con PostgreSQL 17 real en bases de datos desechables.
   - Contrastar los límites reales de tiempo, cancelaciones de transacciones, inyecciones de cabeceras, límites de tokens y validaciones estrictas.
3. **Esquema de Salida Obligatorio:**
   La respuesta final debe ser un objeto JSON válido con la siguiente estructura:
   ```json
   {
     "status": "PASS | FAIL | PARCIAL",
     "findings": [
       {
         "id": "M-03",
         "status": "PASS | FAIL | PARCIAL",
         "summary": "Descripción del estado del hallazgo",
         "evidence": "Detalles técnicos observados (tiempos, códigos HTTP, logs)",
         "blocking_issue": "Causa exacta del bloqueo si es FAIL o PARCIAL"
       }
     ],
     "evidence": [
       "Resumen de pruebas ejecutadas con resultados concretos"
     ],
     "summary": "Dictamen general conciso",
     "tests_executed": 3,
     "clean_tree": true
   }
   ```
4. **Cero Tolerancia a Simulaciones:**
   No certificar un `PASS` basándose en mocks superficiales cuando el requisito exige comprobación contra el clúster o socket real.

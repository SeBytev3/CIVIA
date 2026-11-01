# Evaluación formal de CIVIA (Fase E)

Este directorio contiene los artefactos reproducibles de evaluación del Momento Evaluativo 2:

1. `casos_dorados.json`: 6 casos dorados verificados mediante consultas SQL directas sobre PostgreSQL (`GD-01` a `GD-06`), distinguiendo explícitamente los registros sintéticos (`is_synthetic=true`) e incluyendo una consulta irresoluble sin evidencia (`GD-06`, Comuna 99 / NDVI satelital / radiación).
2. `evaluar.py`: script ejecutable que valida el *ground truth* SQL y corre las **15 consultas representativas (`Q01` a `Q15`)** midiendo exactitud global, precisión de clasificación multimodal, latencias `P50` y `P90`, consumo de tokens, costo estimado en USD, uso de proveedores, tasa de *fallback* y tiempo de recuperación ante fallo forzado `429`.
3. `resultados/reporte_evaluacion.json` y `resultados/reporte_evaluacion.md`: reportes reproducibles generados por la ejecución real de `evaluar.py`.
4. `plantilla_usabilidad.md`: protocolo de 3 tareas sin instrucciones verbales para evaluador externo (dejado honestamente como pendiente de ejecución presencial).

## Cómo ejecutar la evaluación

Con los contenedores activos (`docker compose up -d`):

```powershell
# Evaluación completa (SQL determinista + 15 consultas en vivo)
docker compose exec -T api python eval/evaluar.py --mode all

# Solo verificación determinista SQL (sin llamadas a proveedores externos)
docker compose exec -T api python eval/evaluar.py --mode deterministic
```

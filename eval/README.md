# Evaluación formal de CIVIA (Fase E)

El diseño y la evaluación de la versión 1.0 se conservan como referencia histórica. Los resultados vigentes del candidato están en [estado.md](../docs/estado.md).

Este directorio contiene los artefactos reproducibles de evaluación del Momento Evaluativo 2:

1. `casos_dorados.json`: 6 casos dorados verificados mediante consultas SQL directas sobre PostgreSQL (`GD-01` a `GD-06`), distinguiendo explícitamente los registros sintéticos (`is_synthetic=true`) e incluyendo una consulta irresoluble sin evidencia (`GD-06`, Comuna 99 / NDVI satelital / radiación).
2. `evaluar.py`: script ejecutable que valida el *ground truth* SQL y corre las **15 consultas representativas (`Q01` a `Q15`)** midiendo exactitud global, precisión de clasificación multimodal, latencias `P50` y `P90`, consumo de tokens, costo estimado en USD, uso de proveedores, tasa de *fallback* y tiempo de recuperación ante fallo forzado `429`.
3. `resultados/reporte_evaluacion.json` y `resultados/reporte_evaluacion.md`: reportes reproducibles generados por la ejecución real de `evaluar.py`.
4. `plantilla_usabilidad.md`: protocolo de 3 tareas sin instrucciones verbales para evaluador externo (dejado honestamente como pendiente de ejecución presencial).

## Caja negra de CIVIA 1.1.1

Usa un clon desechable con su propio proyecto Compose, puertos y red. Arráncalo con el procedimiento del README y deja vacías las claves de proveedores. El smoke crea cuentas y reportes sintéticos, consulta los tres perfiles y cambia temporalmente el modo de fallas. Monta las credenciales sólo en lectura. Desde ese clon, en PowerShell:

```powershell
$root = (Get-Location).Path
docker compose run --rm --no-deps -T `
    --volume "${root}/.civia/access:/bootstrap:ro" `
    --volume "${root}/eval/aceptacion_v111.py:/app/acceptance.py:ro" `
    api python /app/acceptance.py --credentials-file /bootstrap/admin-access.json
```

## Casos dorados

La comprobación determinista emplea PostgreSQL desechable y escribe sus resultados en el contenedor de pruebas:

```powershell
docker compose --profile test run --rm -T tests python -c 'from pathlib import Path; from eval import evaluar as e; e.RESULTS_DIR=Path("/tmp/civia-results"); r=e.run_evaluation("deterministic"); print([(x["id"], x["sql_verificado"]) for x in r["golden_sql_verification"]]); assert all(x["sql_verificado"] for x in r["golden_sql_verification"])'
```

La evaluación histórica de 15 consultas necesita un despliegue de evaluación con credenciales autorizadas, capacidades verificadas, cuotas disponibles y PostgreSQL desechable. Conserva los informes publicados para comparar resultados de su versión y fecha.

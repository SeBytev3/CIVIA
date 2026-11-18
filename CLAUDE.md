# Guía de evaluación · CIVIA 1.1.1

Sigue [README](README.md) para un checkout limpio de la rama candidata del PR #1. Usa `./scripts/run.ps1` en Windows y `./scripts/run.sh` en Bash. El bootstrap prepara el esquema y las cuentas administrativas. Recupera el acceso en privado desde `.civia/access/admin-access.json`. Registra la cuenta ciudadana en la web.

Comprueba `/health`, `/build.json`, `/api/meta` y Swagger. La raíz es la radicación web, `/app/` sirve la PWA de ciudadanía y `/admin/` el portal por rol. En Android sigue [el emparejamiento LAN](docs/CONECTIVIDAD_LAN.md). El modo local se puede evaluar con claves vacías. El preflight real requiere autorización de cuota.

Ejecuta la suite indicada en README y consulta [estado](docs/estado.md) para conocer el entorno y alcance de cada comprobación. Mantén secretos, credenciales, trazas privadas y respaldos fuera de la entrega. Las pruebas usan proyectos aislados. El Autopilot queda fuera del procedimiento.

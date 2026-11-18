# Guía del evaluador · CIVIA 1.1.0

Consulta [README](README.md) para el arranque desde un checkout limpio y [estado](docs/estado.md) para las comprobaciones del candidato. Usa `.\scripts\run.ps1` en Windows y `./scripts/run.sh` en Bash. `main` es la rama oficial. Para evaluar 1.1.0 confirma el estado de publicación registrado.

La ciudadanía accede desde la app Android o desde [la contingencia web móvil](http://localhost:5173/). El portal [administrativo](http://localhost:5173/admin/) recibe sesiones CASE_ADMIN y WEB_ADMIN. Inicializa las cuentas locales con `docker compose exec api python -m app.bootstrap_admins`. Usa `docker compose exec -T api python -m app.validate_providers` para consultar la configuración. La validación en vivo requiere autorización de cuota y sólo usa fixtures sintéticos.

Prueba la salud con [health](http://localhost:8000/health), revisa [Swagger](http://localhost:8000/docs) y ejecuta la suite en aislamiento con `docker compose --profile test run --rm --build tests`. Los volúmenes de la instalación habitual se conservan. Nunca se deben copiar claves ni contraseñas a chats o evidencias. El Autopilot queda fuera del procedimiento.

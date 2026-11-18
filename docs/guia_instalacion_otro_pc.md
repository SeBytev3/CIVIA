# Instalación y evaluación en otro computador

1. Activa Docker Desktop y los contenedores Linux. Clona [el repositorio oficial](https://github.com/SeBytev3/CIVIA.git) y confirma la rama evaluada en [estado.md](estado.md).
2. Ejecuta `.\scripts\run.ps1` en la raíz. La variante Bash es `./scripts/run.sh`.
3. En [Swagger](http://localhost:8000/docs) confirma la versión y en [health](http://localhost:8000/health) la conexión con PostgreSQL. `docker compose ps` muestra el estado del worker.
4. Crea las dos cuentas administrativas con `docker compose exec api python -m app.bootstrap_admins` desde una terminal privada. Usa contraseñas distintas.
5. Abre [el portal](http://localhost:5173/admin/). Entra con CASE_ADMIN y recorre casos. Cierra sesión y entra con WEB_ADMIN para consultar usuarios, cola y auditoría.
6. Abre [la web móvil](http://localhost:5173/) desde un dispositivo o instala [el APK](ANDROID_BUILD.md). Registra un ciudadano y radica un caso sintético con evidencia propia de la demostración.
7. Para inferencia con cuota autorizada configura las claves mediante [AI_DEPLOY.md](AI_DEPLOY.md) y valida las modalidades que vas a mostrar.
8. Ejecuta `docker compose --profile test run --rm --build tests`. Consulta [resiliencia](RESILIENCIA.md), [seguridad](seguridad.md) y [estado](estado.md).

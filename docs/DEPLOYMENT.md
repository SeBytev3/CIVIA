# Despliegue local

Git y Docker Desktop con contenedores Linux son suficientes para levantar PostgreSQL 17, FastAPI, worker y Nginx. Ejecuta el [script de arranque](../README.md#arranque-local). PostgreSQL queda dentro de la red Docker. Los puertos de la API y Nginx se enlazan a loopback por defecto. Reserva el IP de Nginx fuera del rango dinámico y conserva `TRUSTED_PROXIES` con su valor exacto si cambias la red.

El servicio `migrate` recibe la conexión propietaria y prepara las cuentas PostgreSQL de aplicación, agente y worker. Los procesos normales sólo reciben sus credenciales operativas. La actualización desde 1.0 conserva el nombre habitual de los volúmenes y usa migraciones incrementales. Guarda una copia autorizada y protegida de la base y las evidencias antes de actualizar un entorno con datos propios. No uses `docker compose down -v` en esa instalación.

El portal está en `/admin/`, la contingencia móvil en `/` y Swagger en el puerto 8000. Consulta [roles](ROLES_Y_PERMISOS.md), [preflight](AI_DEPLOY.md) y [Android](ANDROID_BUILD.md). El estado vigente se registra en [estado.md](estado.md). El despliegue público requiere infraestructura, HTTPS, controles de egreso, gestión de secretos y validación de la rama aprobada.

## Otro proyecto Compose en la misma máquina

Si Docker informa que la subred predeterminada o su gateway ya está en uso, identifica un rango privado libre con `docker network ls` y `docker network inspect`. Ejemplo equivalente al de la verificación con un clon y volúmenes aparte en Windows:

```powershell
$env:CIVIA_SUBNET = '172.30.93.0/24'
$env:CIVIA_DYNAMIC_RANGE = '172.30.93.128/25'
$env:CIVIA_GATEWAY = '172.30.93.1'
$env:CIVIA_FRONTEND_IP = '172.30.93.2'
$env:TRUSTED_PROXIES = $env:CIVIA_FRONTEND_IP
.\scripts\run.ps1
```

Mantén el proxy fuera del rango dinámico. Cada conjunto de puertos publicado necesita quedar libre al iniciar el clon.

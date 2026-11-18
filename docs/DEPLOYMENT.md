# Despliegue local

Git y Docker con el complemento Compose son suficientes para levantar PostgreSQL 17, FastAPI, worker y Nginx. Ejecuta el script de tu sistema operativo. PostgreSQL queda dentro de la red Docker. Los puertos de la API y Nginx se enlazan a loopback por defecto. El proxy de confianza corresponde al valor exacto de `CIVIA_FRONTEND_IP`, que debe quedar fuera del rango dinámico. [Arranque](../README.md#requisitos-e-instalación)

El servicio `migrate` recibe la conexión propietaria y prepara las cuentas PostgreSQL de aplicación, agente y worker. Los procesos normales sólo reciben sus credenciales operativas. La actualización desde 1.0 conserva los volúmenes y usa migraciones incrementales. Si la red heredada carece de un rango dinámico compatible, el bootstrap recrea la red y sus contenedores dentro del proyecto Compose. Guarda una copia protegida de la base y las evidencias antes de actualizar un entorno con datos propios. Evita `docker compose down -v` en esa instalación.

El portal está en `/admin/`, la radicación web en `/`, la PWA ciudadana en `/app/` y Swagger en el puerto 8000. El modo LAN agrega sólo HTTPS de Nginx. [Red local](CONECTIVIDAD_LAN.md) Consulta [roles](ROLES_Y_PERMISOS.md), [preflight](AI_DEPLOY.md) y [Android](ANDROID_BUILD.md). El estado vigente se registra en [estado.md](estado.md). El despliegue público requiere infraestructura, HTTPS, controles de egreso, gestión de secretos y validación de la rama aprobada.

## Otro proyecto Compose en la misma máquina

Si Docker informa que la subred predeterminada o su gateway ya está en uso, identifica un rango privado libre con `docker network ls` y `docker network inspect`. Ejemplo equivalente al de la verificación con un clon y volúmenes aparte en Windows:

```powershell
$env:CIVIA_SUBNET = '172.30.93.0/24'
$env:CIVIA_DYNAMIC_RANGE = '172.30.93.128/25'
$env:CIVIA_GATEWAY = '172.30.93.1'
$env:CIVIA_FRONTEND_IP = '172.30.93.2'
$env:CIVIA_API_PORT = '18093'
$env:CIVIA_HTTP_PORT = '15093'
.\scripts\run.ps1
```

Mantén el proxy fuera del rango dinámico. Cada conjunto de puertos publicado necesita quedar libre al iniciar el clon.

## Credenciales de instalación

Los bootstrap de PowerShell y Bash ejecutan el iniciador administrativo efímero. En una instalación nueva guarda las credenciales iniciales CSPRNG en `.civia/access/admin-access.json` con acceso privado. Conserva el archivo fuera de Git. Si el proyecto ya tiene administración web, el arranque preserva las cuentas y usa la recuperación por los canales habituales.

## Evidencia de versión

`/build.json` indica versión y commit del frontend. `/api/meta` indica también identidad y protocolo de instalación. El arranque compara ambas compilaciones. `/health` responde 503 si PostgreSQL o el esquema requerido no están operativos. La configuración de red documentada es relativa al repositorio.

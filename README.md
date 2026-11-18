# CIVIA 1.1.1 · Momento 3

CIVIA es una plataforma académica de reportes viales y ambientales para Cali y el Valle del Cauca. Fue desarrollada por Stefania Córdoba y Sebastian Espinosa para Ingeniería de Aplicaciones con IA, Universidad Cooperativa de Colombia, con el profesor Julián Garzón.

## Requisitos e instalación

Para iniciar el servidor se requiere Git, Docker con contenedores Linux, Docker Compose y acceso a los registros de imágenes y dependencias durante la primera construcción. Docker Desktop proporciona estos componentes en Windows y macOS. En Linux instala Docker Engine y el complemento Compose. Python, Node, PostgreSQL y Nginx se ejecutan en contenedores.

`main` es la rama estable de evaluación y `dev` es la rama de desarrollo. El estado por plataforma se registra en la documentación de aceptación. [Estado](docs/estado.md) · [Flujo Git](docs/FLUJO_GIT.md)

**Windows, PowerShell**

```powershell
git clone https://github.com/SeBytev3/CIVIA.git
cd CIVIA
./scripts/run.ps1
```

**Linux y macOS, Bash**

```bash
git clone https://github.com/SeBytev3/CIVIA.git
cd CIVIA
./scripts/run.sh
```

El bootstrap muestra el estado de PostgreSQL, migraciones, API, worker, Nginx, versión y proveedores. Genera los secretos internos y las dos cuentas iniciales para una instalación nueva. Abre `.civia/access/admin-access.json` en privado para recuperar las credenciales de `WEB_ADMIN` y `CASE_ADMIN`. El ciudadano se registra desde la web. Los cambios de rol y contraseña los gestiona la administración web.

Para iniciar un clon adicional en la misma máquina, usa `./scripts/run.ps1 -Isolated` o `./scripts/run.sh --isolated` en su primer arranque, antes de crear `.env`. El bootstrap elige un proyecto Compose, dos puertos locales y una subred Docker disponibles. Guarda esos valores en `.env` y muestra las URLs resultantes. Usa el comando normal para los siguientes arranques.

| Acceso local | Uso |
| --- | --- |
| [http://localhost:5173/](http://localhost:5173/) | Radicar un reporte desde web en escritorio o móvil |
| [http://localhost:5173/app/](http://localhost:5173/app/) | Aplicación ciudadana instalable, mapa, historial y asistente |
| [http://localhost:5173/admin/](http://localhost:5173/admin/) | Portal administrativo por rol |
| [http://localhost:8000/docs](http://localhost:8000/docs) | Swagger |
| [http://localhost:5173/health](http://localhost:5173/health) | Salud a través de Nginx |

## Inteligencia artificial

Para una instalación interactiva, añade `-Interactive` en PowerShell o `--interactive` en Bash. Se ofrece ingresar las claves en privado cuando falta alguna. También puedes usar `./scripts/setup_ai_keys.ps1` o `./scripts/setup_ai_keys.sh` después del arranque. La configuración de claves se puede evaluar sin cuota con `docker compose exec -T api python -m app.validate_providers`. Con autorización expresa, añade `--live` para validar las modalidades configuradas. La radicación conserva el reporte y las evidencias si omites las claves o falla la inferencia. [Configuración y resultados](docs/AI_DEPLOY.md)

## PWA ciudadana y red local

Instala la PWA ciudadana desde `/app/` con el botón **Instalar CIVIA** o el menú del navegador. En Safari para iOS, usa **Compartir → Agregar a pantalla de inicio**. El portal `/admin/` se instala de forma independiente.

En el teléfono, inicia `./scripts/run.ps1 -Lan` en Windows o `./scripts/run.sh --lan` en Bash, conecta ambos equipos a la misma red privada y abre `/app/` en la URL HTTPS que muestra el bootstrap. El dispositivo debe confiar en la CA de esa instalación o en el certificado de un gateway autorizado. En el equipo anfitrión puedes usar `http://localhost:5173/app/`. [Conectividad y certificados](docs/CONECTIVIDAD_LAN.md)

La entrega móvil usa la PWA. El proyecto Android y el registro de la compilación anterior se conservan para consulta. [Android](docs/ANDROID_BUILD.md) · [CIVIA 1.1.1 — Momento 3](https://github.com/SeBytev3/CIVIA/releases/tag/v1.1.1)

## Verificar, detener y actualizar

- Compara versión y commit en [build.json](http://localhost:5173/build.json) y [api/meta](http://localhost:5173/api/meta). Una compilación con cambios locales lleva el sufijo `-dirty`.
- Ejecuta `docker compose --profile test run --rm --build tests pytest -m "not live" -q --tb=short` para la suite hermética. Para comprobar alta, gestión, cola y revocación de los tres perfiles, usa un clon desechable con claves vacías. [Recorrido de caja negra](eval/README.md) · [Resultados](docs/estado.md)
- Si hay un puerto o una subred en uso, revisa el diagnóstico del bootstrap y elige valores libres. Si CIVIA 1.0 sigue visible, vuelve a abrir la raíz con el gateway activo. El navegador retirará el Service Worker legado durante la actualización. Si en 1.1.0 quedó un borrador de esa cuenta, usa **Recuperar borrador anterior** cuando aparezca. [Despliegue y fallas](docs/DEPLOYMENT.md)
- Para detener ejecuta `./scripts/run.ps1 -Stop` o `./scripts/run.sh --stop`. Para actualizar, respalda la base y las evidencias, actualiza el checkout y vuelve a ejecutar el bootstrap. Los volúmenes persisten al detener.

[API REST](docs/API.md) · [Roles](docs/ROLES_Y_PERMISOS.md) · [Resiliencia](docs/RESILIENCIA.md) · [Semana 12](docs/seguridad.md) · [Semana 13](docs/arquitectura_escala.md) · [Sustentación](docs/guion_sustentacion.md)

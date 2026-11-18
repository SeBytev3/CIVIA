# CIVIA 1.1.1 · Momento 3

CIVIA es una plataforma académica de reportes viales y ambientales para Cali y el Valle del Cauca. Fue desarrollada por Stefania Córdoba y Sebastian Espinosa para Ingeniería de Aplicaciones con IA, Universidad Cooperativa de Colombia, con el profesor Julián Garzón.

## Requisitos e instalación

Para iniciar el servidor se requiere Git, Docker con contenedores Linux, Docker Compose y acceso a los registros de imágenes y dependencias durante la primera construcción. Docker Desktop proporciona estos componentes en Windows y macOS. En Linux instala Docker Engine y el complemento Compose. Python, Node, PostgreSQL y Nginx se ejecutan en contenedores.

La rama candidata es `feature/civia-v1.1-mobile-security-resilience` del [PR #1](https://github.com/SeBytev3/CIVIA/pull/1). El estado comprobado por plataforma está en [docs/estado.md](docs/estado.md).

**Windows, PowerShell**

```powershell
git clone --branch feature/civia-v1.1-mobile-security-resilience https://github.com/SeBytev3/CIVIA.git
cd CIVIA
./scripts/run.ps1
```

**Linux y macOS, Bash**

```bash
git clone --branch feature/civia-v1.1-mobile-security-resilience https://github.com/SeBytev3/CIVIA.git
cd CIVIA
./scripts/run.sh
```

El bootstrap muestra el estado de PostgreSQL, migraciones, API, worker, Nginx, versión y proveedores. Genera los secretos internos y las dos cuentas iniciales para una instalación nueva. Abre `.civia/access/admin-access.json` en privado para recuperar las credenciales de `WEB_ADMIN` y `CASE_ADMIN`. El ciudadano se registra desde la web. Los cambios de rol y contraseña los gestiona la administración web.

| Acceso local | Uso |
| --- | --- |
| [http://localhost:5173/](http://localhost:5173/) | Radicar un reporte desde web en escritorio o móvil |
| [http://localhost:5173/app/](http://localhost:5173/app/) | Aplicación ciudadana instalable, mapa, historial y asistente |
| [http://localhost:5173/admin/](http://localhost:5173/admin/) | Portal administrativo por rol |
| [http://localhost:8000/docs](http://localhost:8000/docs) | Swagger |
| [http://localhost:5173/health](http://localhost:5173/health) | Salud a través de Nginx |

## Inteligencia artificial

Ingresa las claves con `./scripts/setup_ai_keys.ps1` en Windows o `./scripts/setup_ai_keys.sh` en Bash. El sistema admite Gemini y Groq. Con autorización de cuota, ejecuta `docker compose exec -T api python -m app.validate_providers --live`. La radicación conserva el reporte y las evidencias si se omiten las claves o falla la inferencia. [Configuración y resultados](docs/AI_DEPLOY.md)

## Android, PWA y red local

Consulta el APK, su firma y SHA-256 en [docs/ANDROID_BUILD.md](docs/ANDROID_BUILD.md). En el teléfono autoriza la fuente del APK e instala el paquete. CIVIA Android empareja el servidor desde un QR o código de confianza.

Inicia la conexión remota con `./scripts/run.ps1 -Lan` en Windows o `./scripts/run.sh --lan` en Bash. Si hay varias interfaces, selecciona la IPv4 local con `-LanAddress` o `--lan-address`. El gateway HTTPS publica el puerto indicado, 5443 por defecto. Abre `.civia/lan/pairing.svg` para escanear el QR, o usa el código de `pairing.txt`. Si falla el descubrimiento, empareja con ese mismo código. [Conectividad LAN y certificados](docs/CONECTIVIDAD_LAN.md)

Desde un navegador compatible abre la aplicación ciudadana y usa su opción de instalación o el menú del navegador. En iOS usa **Compartir → Agregar a pantalla de inicio**. En un teléfono utiliza un origen HTTPS de LAN que el navegador reconozca como confiable. [PWA ciudadana](http://localhost:5173/app/)

## Verificar, detener y actualizar

- Compara versión y commit en [build.json](http://localhost:5173/build.json) y [api/meta](http://localhost:5173/api/meta). Una compilación con cambios locales lleva el sufijo `-dirty`.
- Ejecuta `docker compose --profile test run --rm --build tests pytest -m "not live" -q --tb=short` para la suite hermética. El recorrido de caja negra y los resultados están en [estado](docs/estado.md).
- Si hay un puerto o una subred en uso, revisa el diagnóstico del bootstrap y elige valores libres. Si CIVIA 1.0 sigue visible, vuelve a abrir la raíz con el gateway activo. El navegador retirará el Service Worker legado durante la actualización. Si en 1.1.0 quedó un borrador de esa cuenta, usa **Recuperar borrador anterior** cuando aparezca. [Despliegue y fallas](docs/DEPLOYMENT.md)
- Para detener ejecuta `./scripts/run.ps1 -Stop` o `./scripts/run.sh --stop`. Para actualizar, respalda la base y las evidencias, actualiza el checkout y vuelve a ejecutar el bootstrap. Los volúmenes persisten al detener.

[API REST](docs/API.md) · [Roles](docs/ROLES_Y_PERMISOS.md) · [Resiliencia](docs/RESILIENCIA.md) · [Semana 12](docs/seguridad.md) · [Semana 13](docs/arquitectura_escala.md) · [Sustentación](docs/guion_sustentacion.md)

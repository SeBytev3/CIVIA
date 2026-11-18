# CIVIA 1.1.0 · Momento 3

Plataforma académica de reportes ciudadanos viales y ambientales para Cali y el Valle del Cauca. Desarrollada por Stefania Córdoba y Sebastian Espinosa, Universidad Cooperativa de Colombia, para Ingeniería de Aplicaciones con IA con Julián Garzón.

La experiencia ciudadana usa React y Capacitor en Android y tiene una contingencia web móvil. El portal web PWA sirve a la administración de casos y del sistema. FastAPI y PostgreSQL comparten reportes, evidencias e historial. Un worker separado procesa la cola con Gemini y respaldo Groq. El radicado se confirma al guardar el reporte y su trabajo de análisis.

## Arranque local

Instala Git y Docker Desktop con contenedores Linux. Desde PowerShell en Windows 11:

```powershell
git clone --branch feature/civia-v1.1-mobile-security-resilience https://github.com/SeBytev3/CIVIA.git
cd CIVIA
.\scripts
un.ps1
```

En Linux o macOS ejecuta `./scripts/run.sh`. El script inicializa `.env` local y espera la salud de los servicios. Revisa la versión y la rama publicadas antes de evaluar el candidato 1.1.0. El estado del candidato y los resultados están en [docs/estado.md](docs/estado.md).

| Acceso | Dirección |
| --- | --- |
| Ciudadanía móvil web | [localhost:5173](http://localhost:5173/) |
| Portal administrativo | [localhost:5173/admin](http://localhost:5173/admin/) |
| Swagger | [localhost:8000/docs](http://localhost:8000/docs) |
| Salud básica | [localhost:8000/health](http://localhost:8000/health) |

Crea las dos primeras cuentas administrativas desde una terminal privada con `docker compose exec api python -m app.bootstrap_admins`. Usa credenciales distintas para ambos perfiles y conserva las contraseñas en un gestor. La ciudadanía se registra en la aplicación.

Usa `.\scripts\setup_ai_keys.ps1` o `./scripts/setup_ai_keys.sh` para ingresar las dos claves en privado. Una clave configurada se marca como **CONFIGURADA**. Con autorización de cuota, `docker compose exec -T api python -m app.validate_providers --live` verifica y habilita las modalidades de los modelos configurados. En modo local los reportes conservan su radicado y evidencias aunque la inferencia esté pendiente.

## Evaluación

```text
docker compose --profile test run --rm --build tests
```

La suite usa un servicio PostgreSQL descartable y una red interna. Usa el estado de la rama en [docs/estado.md](docs/estado.md) para interpretar los resultados. El catálogo está identificado como sintético. CIVIA opera como proyecto académico. El envío de correo institucional permanece deshabilitado.

- [Instalación en otro computador](docs/guia_instalacion_otro_pc.md) y [despliegue local](docs/DEPLOYMENT.md).
- [Aplicación móvil](docs/APLICACION_MOVIL.md), [compilación Android](docs/ANDROID_BUILD.md) y [roles](docs/ROLES_Y_PERMISOS.md).
- [API REST](docs/API.md), [proveedores de IA](docs/AI_DEPLOY.md), [resiliencia](docs/RESILIENCIA.md) y [decisión de SQL directo](docs/decisiones.md).
- [Semana 12, seguridad](docs/seguridad.md) y [semana 13, capacidad](docs/arquitectura_escala.md).
- [Sustentación](docs/guion_sustentacion.md), [rúbrica](docs/checklist_rubrica.md) y [entrega](docs/entrega_final.md).

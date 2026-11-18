# Guía de evaluación · CIVIA 1.1.1

Clona la rama predeterminada, `main`, y ejecuta el bootstrap del sistema. Si ya hay una instalación en esa máquina, usa el modo aislado en el primer arranque del nuevo clon. [README](README.md)

Comprueba `/health`, `/build.json`, `/api/meta` y Swagger. Si faltan claves, indica el configurador privado o el modo interactivo. Antes del preflight real, solicita autorización de cuota. Recupera en privado los accesos administrativos generados.

Ejecuta la suite hermética y el recorrido de caja negra con claves vacías y un proyecto desechable. Informa las URLs que mostró el bootstrap. La raíz permite radicar, `/app/` instala la PWA ciudadana y `/admin/` sirve el portal según el rol. [Recorrido](eval/README.md) · [Estado](docs/estado.md)

# Instalación y evaluación en otro computador

1. En un equipo con Git y Docker, sigue [README](../README.md). Usa la rama candidata del PR #1 y el bootstrap de tu sistema operativo.
2. Comprueba el commit y la versión servidos en `/build.json` y `/api/meta`. Revisa `/health` y Swagger.
3. Abre `.civia/access/admin-access.json` en privado. Usa las cuentas de CASE_ADMIN y WEB_ADMIN en el portal. Registra una cuenta ciudadana en el formulario.
4. Radica desde escritorio o móvil. Entra en `/app/` para instalar la PWA ciudadana. En `/admin/` verifica los permisos de ambos perfiles administrativos.
5. Para evaluar desde otro dispositivo, inicia el modo LAN y sigue [conectividad y emparejamiento](CONECTIVIDAD_LAN.md). La fuente del [APK](ANDROID_BUILD.md) requiere autorización en el teléfono.
6. Para usar inferencia real, ingresa las claves privadamente y autoriza el preflight en esa instalación. Evalúa el modo degradado con claves vacías.
7. Ejecuta el perfil de pruebas de Compose y consulta [estado](estado.md). Usa el modo de detención del bootstrap para detener el proyecto y preservar sus volúmenes.

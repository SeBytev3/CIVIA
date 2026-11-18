# Roles y permisos

| Capacidad | Ciudadano | Administrador de casos | Administrador web |
| --- | --- | --- | --- |
| Registro público | Crea una cuenta CITIZEN | — | — |
| Reporte y evidencia | Crea y consulta los propios | Consulta y gestiona | Consulta y gestiona |
| Mapa público | Vista minimizada | Vista operativa | Vista operativa |
| Historial y notas | Eventos públicos del propio reporte | Notas públicas y privadas | Notas públicas y privadas |
| Asistente | Datos de dominio de la propia cuenta y catálogo sintético | — | — |
| Propuestas | Solicita revisión de casos propios | Decide | Decide |
| Usuarios y roles | — | — | Crea, cambia rol, activa, desactiva y restablece |
| Auditoría, cola y simulación | — | — | Acceso técnico |

Las contraseñas se almacenan con Argon2id. FastAPI resuelve el rol vigente desde la sesión y la cuenta activa. El portal usa cookies HttpOnly y SameSite con validación CSRF en las mutaciones. Activa `AUTH_COOKIE_SECURE=1` detrás de HTTPS. Android usa una credencial opaca revocable guardada con Android Keystore. La revocación y desactivación cortan el acceso. Los identificadores de recurso se verifican en servidor.

El asistente lee una vista PostgreSQL minimizada con filtros de propiedad. Las solicitudes de cambio tienen solicitante, versión del reporte y vencimiento. Otra persona con rol administrativo decide. Las filas históricas sin propietario siguen conservadas bajo administración. El mapa público redondea ubicación y omite descripción, contacto, evidencia, notas e identificadores privados.

`ADMIN_TOKEN` conserva su presencia en instalaciones existentes y carece de autoridad en las rutas RBAC. Para copiarlo localmente durante mantenimiento histórico, sin escribir su valor en la terminal:

```powershell
Get-Content .env | Select-String '^ADMIN_TOKEN=' | ForEach-Object { $_.Line.Split('=', 2)[1].Trim() } | Set-Clipboard
```

Para evaluar el portal se usan las cuentas generadas por `python -m app.bootstrap_admins`.

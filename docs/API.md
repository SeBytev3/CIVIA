# API REST · CIVIA 1.1.0

Consulta [Swagger](http://localhost:8000/docs) y [OpenAPI JSON](http://localhost:8000/openapi.json) en la instalación local. La API mantiene una sola base PostgreSQL para los tres perfiles. La respuesta de alta distingue la persistencia de la evidencia del diagnóstico asíncrono.

La sesión web usa cookie HttpOnly y header `X-CSRF-Token` en mutaciones posteriores al login. Android usa el modo `X-Session-Mode: bearer` y `Authorization: Bearer …`. Las sesiones de administración usan cookie. Los roles y permisos constan en [ROLES_Y_PERMISOS.md](ROLES_Y_PERMISOS.md).

`POST /api/reports` recibe multipart con descripción, latitud, longitud y fotografía. Admite título y nota de voz opcionales. Usa `Idempotency-Key` con la misma carga al reintentar. Los datos propios y el catálogo identificado se consultan bajo sesión. Para el mapa público usa únicamente las rutas minimizadas.

`POST /api/agent/query` acepta una pregunta de dominio y devuelve la respuesta, la referencia de aprobación si corresponde y el estado de operación propio cuando aplique. Los detalles de proveedor y tokens están en observabilidad WEB_ADMIN.

```json
{"query":"¿Cuántos reportes de huecos están registrados?"}
```

## Inventario desde OpenAPI

| Método | Ruta | Acceso | Respuesta |
| --- | --- | --- | --- |
| GET | `/api/admin/approvals` | CASE_ADMIN o WEB_ADMIN | 200 |
| POST | `/api/admin/approvals/{approval_id}/decide` | CASE_ADMIN o WEB_ADMIN | 200 |
| GET | `/api/admin/audit` | WEB_ADMIN | 200 |
| POST | `/api/admin/fault-injection` | WEB_ADMIN | 200 |
| GET | `/api/admin/notifications` | CASE_ADMIN o WEB_ADMIN | 200 |
| POST | `/api/admin/notifications/mark-all-read` | CASE_ADMIN o WEB_ADMIN | 200 |
| PATCH | `/api/admin/notifications/{notification_id}/read` | CASE_ADMIN o WEB_ADMIN | 200 |
| GET | `/api/admin/observability` | WEB_ADMIN | 200 |
| GET | `/api/admin/queue` | WEB_ADMIN | 200 |
| GET | `/api/admin/queue/dead-letter` | WEB_ADMIN | 200 |
| POST | `/api/admin/queue/dead-letter/{job_id}/requeue` | WEB_ADMIN | 202 |
| GET | `/api/admin/reports/{report_id}/internal-notes` | CASE_ADMIN o WEB_ADMIN | 200 |
| POST | `/api/admin/reports/{report_id}/management` | CASE_ADMIN o WEB_ADMIN | 200 |
| POST | `/api/admin/seed` | WEB_ADMIN | 200 |
| GET | `/api/admin/system` | WEB_ADMIN | 200 |
| GET | `/api/admin/users` | WEB_ADMIN | 200 |
| POST | `/api/admin/users` | WEB_ADMIN | 201 |
| PATCH | `/api/admin/users/{user_id}` | WEB_ADMIN | 200 |
| POST | `/api/admin/users/{user_id}/reset-password` | WEB_ADMIN | 204 |
| POST | `/api/agent/query` | CITIZEN | 200 |
| POST | `/api/auth/login` | Público | 200 |
| POST | `/api/auth/logout` | Sesión y alcance del recurso | 204 |
| POST | `/api/auth/register` | Público | 201 |
| GET | `/api/auth/session` | Sesión y alcance del recurso | 200 |
| GET | `/api/operations/{operation_id}` | Sesión y alcance del recurso | 200 |
| GET | `/api/public/reports` | Público | 200 |
| GET | `/api/public/reports/stats` | Público | 200 |
| GET | `/api/reports` | Sesión y alcance del recurso | 200 |
| POST | `/api/reports` | CITIZEN | 201 |
| GET | `/api/reports/by-code/{tracking_code}` | Sesión y alcance del recurso | 200 |
| GET | `/api/reports/by-code/{tracking_code}/events` | Sesión y alcance del recurso | 200 |
| GET | `/api/reports/stats` | Sesión y alcance del recurso | 200 |
| GET | `/api/reports/{report_id}` | Sesión y alcance del recurso | 200 |
| POST | `/api/reports/{report_id}/analyze` | CITIZEN | 202 |
| GET | `/api/reports/{report_id}/audio` | Sesión y alcance del recurso | 200 |
| PATCH | `/api/reports/{report_id}/confirm` | CITIZEN | 200 |
| GET | `/api/reports/{report_id}/events` | Sesión y alcance del recurso | 200 |
| GET | `/api/reports/{report_id}/photo` | Sesión y alcance del recurso | 200 |
| PATCH | `/api/reports/{report_id}/status` | CASE_ADMIN o WEB_ADMIN | 200 |
| GET | `/health` | Público | 200 |

**40 operaciones**.

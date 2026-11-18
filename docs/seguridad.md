# Semana 12 · Seguridad de CIVIA

## 1. Modelo de amenazas

Los activos principales son las cuentas, las sesiones revocables, los hashes de contraseña, los reportes, las ubicaciones, las fotografías y el audio. También se protegen las notas internas, las aprobaciones administrativas, la telemetría y las claves de inferencia. Actores con diferentes capacidades incluyen visitantes, ciudadanos, administradores de casos, administradores web, el proceso worker y los proveedores de IA. Un titular puede enviar contenido libre en descripciones, fotografías, notas de voz y consultas. Los resultados de modelos son datos externos.

Los límites pasan del navegador o Android a Nginx y FastAPI, de FastAPI a PostgreSQL y del adaptador a Gemini y Groq. La auditoría y la respuesta del asistente son otras vías de salida. Cambiar un estado o rol, desactivar cuentas, restablecer contraseñas, activar fallas y reencolar trabajos son acciones críticas. La autorización utiliza identidad de sesión, rol vigente, titularidad y estado del recurso. El modelo genera propuestas y diagnósticos. El backend decide sobre la persistencia conforme a sus controles.

## 2. Tríada letal

| Condición | ¿Existe? | Evidencia | Control | Riesgo residual |
| --- | --- | --- | --- | --- |
| Datos privados | Sí | Usuarios, evidencias, notas, sesiones y secretos locales | Identidades de servicio diferentes, RBAC, vista minimizada y separación de la clasificación | Fotos o voz pueden contener información sensible aportada por el titular |
| Contenido no confiable | Sí | Chat, descripciones, imágenes, voz y resultados externos | Esquemas Pydantic, resultados de herramientas minimizados, autorización fuera del modelo | El modelo todavía puede generar contenido incorrecto |
| Salida | Sí | Respuesta ciudadana, Gemini, Groq y auditoría | Destinos fijos, TLS, sin redirects, Markdown restringido y sin herramientas de red | Los proveedores reciben evidencia minimizada para inferencia |

## 3. Evidencia de verificación

Las verificaciones defensivas se ejecutan con fixtures sintéticos en PostgreSQL desechable. Cubren denegación por rol, lecturas de recursos, almacenamiento inmutable, resultados estructurados y límites. El contrato de lectura del asistente comprueba que el detalle devuelto al modelo contiene únicamente radicado, gestión, categoría, severidad y comuna válida. El estado del reporte y las notas se comparan por la interfaz autorizada. El inventario y los resultados de la ejecución están en [estado.md](estado.md).

La misión pide una reproducción controlada de inyección indirecta con una carga y una traza completa. Ese experimento queda fuera de la evidencia entregada. La defensa se verifica mediante pruebas de contrato y alcance que usan contenido sintético ordinario y respuestas simuladas en el límite del modelo.

## 4. Controles aplicados

| Control | Base 1.0 | Candidato 1.1 | Verificación |
| --- | --- | --- | --- |
| Herramientas | Herramientas tipadas con clasificación síncrona | Operaciones ciudadanas acotadas por identidad, vista minimizada y parámetros estrictos | Pruebas de herramientas y recursos |
| PostgreSQL | Conexión compartida del servicio | Migración, API, lectura y worker con logins distintos | Pruebas con roles y privilegios PostgreSQL |
| Salida IA | Rutas fijas y clave de Google en URL | Cabecera, límites y TLS, allowlist de rutas | MockTransport comprueba destino y ausencia de query |
| Aprobación | Estado y versión del reporte | Solicitante, caducidad, revisor distinto y verificación de versión | Pruebas de aprobación y estado |
| Recursos | Iteraciones, tokens y deadline | Reservas antes de llamada, ventanas compartidas y límites de cola | Simulaciones y pruebas de concurrencia |
| Evidencia | Validación y almacenamiento inmutable | Propiedad en API, hash de audio y worker en lectura | Reportes, carga y colas |
| PWA | Ámbito raíz | Registro administrativo acotado y retirada del registro histórico | Pruebas de navegación y caché |
| Fuga técnica | Detalles agénticos ciudadanizados | Respuesta ciudadana reducida y telemetría técnica restringida | Contratos de sesión y respuesta |

El aislamiento de salida aplica en el adaptador de inferencia. El contenedor aún tiene conectividad general a través de la red Docker. El cifrado de evidencias en reposo y una red de egreso dedicada requieren infraestructura adicional. Los datos del catálogo son demo y los documentos de auditoría históricos conservan su contexto.

Material de curso consultado: [clase 12](https://ingenieria-aplicaciones-ia.netlify.app/semana12/slides), [taller guiado](https://ingenieria-aplicaciones-ia.netlify.app/semana12/exercise) y [reto](https://ingenieria-aplicaciones-ia.netlify.app/semana12/workshop).

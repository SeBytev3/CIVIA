# Resiliencia y radicación

FastAPI autentica al ciudadano y valida los campos y evidencias. Crea el reporte, el evento, la notificación y el trabajo de análisis en una transacción. La evidencia se publica de forma inmutable y se verifica por tamaño y SHA-256. El worker accede al volumen de evidencias en lectura. El cliente conserva la clave de idempotencia durante el reenvío. El borrador se identifica por instalación y cuenta. El backend rechaza la recepción si los encabezados de alcance del navegador difieren de la instalación o la sesión autorizada.

PostgreSQL es la fuente de verdad. El worker reclama filas con `FOR UPDATE SKIP LOCKED` y una concesión temporal. Libera la transacción antes de inferencia. La entrega de trabajo puede repetirse tras un reinicio. La versión de reporte y el fencing token impiden la publicación de resultados tardíos por un worker desplazado. La revisión humana prevalece.

La aceptación de cierre incluye una ejecución en modo degradado y un recorrido autorizado con imagen y habla sintéticas que verificó persistencia desde el worker. Los resultados de ese recorrido son independientes del preflight de modalidades. [Estado](estado.md)

| Condición | Efecto |
| --- | --- |
| Disponibilidad normal | Gemini intenta analizar, luego Groq si falla y admite la modalidad |
| Indisponibilidad técnica recuperable | El reporte sigue recibido y el trabajo se reprograma |
| Límite temporal de circuito o presupuesto | El worker aplaza la llamada |
| Error permanente o intentos agotados | El trabajo pasa a revisión manual y conserva la evidencia |
| Decisión humana posterior | El worker descarta resultados de la versión anterior |

Los circuitos abren ante saturación o fallo y conceden un sondeo después de su enfriamiento. Los reintentos durables usan backoff exponencial, jitter y `Retry-After` acotado. La ejecución queda limitada por leases, timeout, capacidad de trabajos y presupuesto. La DLQ conserva código sanitizado e historial. WEB_ADMIN puede reencolar trabajos elegibles. La simulación persistente se activa desde esa sesión y se restaura con `NONE`. Haz la demostración en un entorno aislado.

El asistente puede responder consultas de dominio con SQL. Las solicitudes conversacionales quedan fuera de la cola de evidencias. Revisa los casos ejecutados en [estado.md](estado.md).

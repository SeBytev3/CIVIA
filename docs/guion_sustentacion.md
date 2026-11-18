# Sustentación de Momento 3

## Ocho minutos de demostración

| Tiempo | Acción |
| --- | --- |
| 0:00–1:00 | Presentar la necesidad de radicar reportes viales y ambientales y mostrar la radicación de escritorio, la PWA ciudadana y el acceso de los dos roles administrativos. |
| 1:00–3:00 | Instalar y abrir la PWA ciudadana, registrar una cuenta y radicar evidencia sintética. Mostrar el radicado en la aplicación. Consultar el estado de análisis. |
| 3:00–4:30 | Entrar como CASE_ADMIN, ubicar el mismo radicado, asignar, registrar una nota y cambiar su gestión. Verificar el evento como ciudadano. |
| 4:30–6:00 | Entrar como WEB_ADMIN y abrir usuarios, auditoría y cola. Interpretar los timestamps y el estado de la inferencia. |
| 6:00–7:00 | En la instalación aislada activar TOTAL, radicar con una segunda evidencia sintética y comprobar el trabajo durable. Restaurar NONE. Mostrar recuperación hermética o una recuperación real si el preflight vigente habilitó la modalidad. |
| 7:00–8:00 | Mostrar el contrato de propiedad, los permisos PostgreSQL y la decisión humana sobre una propuesta. Consultar [seguridad](seguridad.md). |

Usa tres sesiones separadas. Guarda las credenciales en un gestor y evita mostrarlas. Indica el carácter sintético de los ejemplos y que el correo institucional permanece deshabilitado.

## Cuatro minutos de preguntas

Explica la tríada letal y qué minimiza cada frontera. Aborda la diferencia entre radicar y analizar, recepción e idempotencia, lease y fencing, autoridad humana, cuota estimada, apertura del circuito y plazo para vaciar backlog. Usa las [mediciones](estado.md) y enuncia los supuestos de [capacidad](arquitectura_escala.md).

## Pitch de arquitectura · tres minutos

- 0:00–0:45. Carga esperada, pico supuesto, flujo de entrada y transacción de radicación.
- 0:45–1:30. Little, concurrencia, RPM y TPM. Diferencia entre latencia medida y tiempo de inferencia supuesto.
- 1:30–2:15. Worker, fallback, jitter, cercado de publicaciones y DLQ.
- 2:15–3:00. Costo por modalidad, presupuesto local y condiciones de crecimiento.

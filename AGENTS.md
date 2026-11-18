# CIVIA — contrato para agentes de desarrollo

Equipo: Stefania Córdoba y Sebastian Espinosa. Proyecto de Ingeniería de Aplicaciones con IA, Momento 3.

## Prioridad
1. Mantener aplicación desplegable desde un checkout limpio según README; comprobarlo, no presumirlo.
2. Completar flujo vertical ciudadano: alta de reporte, foto, GPS, almacenamiento, análisis multimodal y consulta.
3. Agente genuino con herramientas tipadas y descripciones claras; cuatro límites efectivos: vueltas, tokens, timeout y aprobación humana para escritura crítica. La IA NO escribe directamente en BD.
4. Estrategia de datos: PostgreSQL/SQL directo; justificar NO RAG en docs/decisiones.md.
5. Resiliencia: Gemini -> Groq (proveedor independiente) con cola durable ante indisponibilidad; solo modelos accesibles tras preflight; registrar fallos técnicos solo en observabilidad protegida. No revelar error API, código HTTP interno, traceback ni nombres de proveedores al ciudadano. No simular éxito.
6. Pruebas 429/timeout/JSON inválido/caída total, suite dorada mínima 5 preguntas verificadas a mano (una sin respuesta) y 15 consultas para latencia P50/P90, costo, precisión y trazas.
7. README para equipo Windows 11 y otro computador limpio; scripts de arranque un comando y .env.example completo. No subir secretos, .venv, node_modules ni dumps privados.

## Forma de trabajar
- Una tarea por cambio; ejecutar lint/tests y documentar resultado en docs/estado.md antes de marcar terminado.
- No cambiar modelos IDs sin comprobación por API; validar visión, salida estructurada y tool calling según función.
- No inventar resultados de evaluación, métricas, datos satelitales reales ni fechas.
- Usar datos sintéticos identificados para la demo; nunca imágenes privadas sin permiso.
- No publicar despliegue hasta proteger logs y configuraciones.
- Un agente escribe por módulo; Codex audita y propone fixes en rama separada, evitando ediciones simultáneas.
- No interpretar este esqueleto inicial como producto terminado.

## Uso disciplinado de skills
- Antes de modificar código o arquitectura, identificar y leer los `SKILL.md` pertinentes en el entorno (`api-security`, `backend-security-coder`, `systematic-debugging`, `frontend-api-integration-patterns`, `react-patterns`, `playwright-skill`, `postgres-best-practices`, `code-review-and-quality`).
- Extraer instrucciones concretas y aplicables para el problema en curso; evitar parches reactivos o atajos heurísticos.
- Documentar explícitamente en cada ciclo la matriz de correspondencia: hallazgo/tarea -> skill utilizada -> instrucción aplicada -> verificación adversarial realizada.
- Verificar invariantes mediante TDD adversarial: reproducir y confirmar el fallo exacto (RED) antes de implementar (GREEN) y proteger regresiones con suites herméticas.

## Contrato de instalación autónoma

- El README es el procedimiento canónico. Con terminal y Docker, ejecuta el protocolo y verifica el resultado. Cuando falte acceso o autorización indispensable, indica el impedimento y entrega comandos exactos para ese entorno. [Protocolo universal](README.md#despliegue-autónomo-con-tu-agente-de-ia-favorito)
- Instala desde `main` para evaluación ordinaria y desarrolla en `dev`. Usa las URLs y el proyecto que declara el bootstrap. Antes de actuar, identifica instalaciones existentes y reserva un clon aislado con claves vacías para datos sintéticos, mutaciones y simulaciones. [Flujo Git](docs/FLUJO_GIT.md)
- Resuelve problemas ordinarios mediante los comandos documentados. Conserva volúmenes y secretos de otras instalaciones, la lógica de negocio y los controles de seguridad.
- Usa el configurador privado para claves y el acceso administrativo generado sólo en el equipo autorizado. Nunca pidas secretos por chat, uses credenciales de los desarrolladores ni imprimas sus valores. Obtén autorización expresa antes de usar cuota externa. Separa claves configuradas de modalidades validadas.
- Limita las solicitudes al usuario a permisos indispensables, secretos privados, cuota, certificados o acciones físicas. Informa versión y commit, URLs, mecanismo privado de acceso, verificaciones ejecutadas y limitaciones. Distingue radicación de análisis y navegador de dispositivo físico.

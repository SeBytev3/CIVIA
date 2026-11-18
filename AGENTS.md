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

## Protocolo de Evaluación Autónoma para Agentes
- Para cualquier agente evaluador (Claude, Gemini, ChatGPT):
  1. Clonar desde la rama predeterminada `main`, salvo evaluación explícita de un PR. Trabajar en `dev` para cambios futuros. [Flujo Git](docs/FLUJO_GIT.md)
  2. Ejecutar `.\scripts\run.ps1` (PowerShell) o `./scripts/run.sh` (Bash).
  3. Comprobar salud en `http://localhost:8000/health` y acceso a frontend en `http://localhost:5173`.
  4. Ejecutar `docker compose --profile test run --rm --build tests` en la red de pruebas aislada.
  5. Consultar `docker compose exec -T api python -m app.validate_providers`. Si falta una clave, indicar el configurador privado o el arranque interactivo. Pedir autorización de cuota antes de `--live` y registrar sólo las modalidades comprobadas.
  6. Recuperar el acceso creado por el bootstrap en `.civia/access/admin-access.json` en privado. Ejecutar el [recorrido de caja negra](eval/README.md) con un clon desechable y claves vacías.
  7. Informar las URLs que mostró el bootstrap. Radicación en `/`, PWA ciudadana en `/app/` y portal en `/admin/`. Comparar `/build.json` y `/api/meta`. Consultar [estado](docs/estado.md) para conocer límites comprobados.
  8. La API está en [docs/API.md](docs/API.md) y en `http://localhost:8000/docs`. Sustituir conteos sólo con evidencia de ejecución.

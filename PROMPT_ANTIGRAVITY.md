# PROMPT MAESTRO — ANTIGRAVITY (copiar íntegro)

Actúa como arquitecto principal y desarrollador de CIVIA. El repositorio `SeBytev3/CIVIA` contiene un **scaffold inicial**, no la aplicación completa. Antes de escribir código lee `AGENTS.md`, `README.md`, `docs/arquitectura.md`, `docs/decisiones.md`, `docs/estado.md` y los archivos presentes. Trabaja en Windows 11 con Docker Desktop, Node 26, Python 3.14.10 y Git. Usa dependencias dentro de contenedores y versiones compatibles comprobadas. No presupongas WSL ni MADRE en la máquina del evaluador; Docker Compose es la ruta de despliegue.

CONTEXTO: Equipo Stefania Córdoba y Sebastian Espinosa. CIVIA es una PWA para reportes ciudadanos en Cali/Valle del Cauca: huecos, basuras, tala, quemas; foto y GPS, texto, transcripción de audio opcional de <=60s/5 MB. En fase futura: vídeo, puntos críticos predictivos y cruce satelital (no fingir implementación).

CRITERIOS DEL PROFESOR — Momento 2: ZIP reproducible sin node_modules/.venv/.git, README contrato ejecutable, configuración `.env.example`, `docker compose up --build` en un comando, app visible, agentes con herramientas y cuatro límites (vueltas, tokens, timeout, confirmación humana), datos SQL directo o RAG justificado, interfaz usable por tercero, fallos 429/timeout/JSON inválido/caída total, fallback y cero tracebacks ante el ciudadano, 5 preguntas doradas (una sin respuesta), 15 consultas medibles, P50/P90/costo y trazas de herramientas demostrables, 6 minutos de demo más 3 de preguntas.

STACK: React + TS + Vite PWA; FastAPI; PostgreSQL; evaluar PostGIS si conviene. Docker Compose inicial contiene solo API/BD, añadir frontend, migraciones y servicios estrictamente necesarios. Preferir menos dependencias y más reproducibilidad. El backend implementa clasificación multimodal con salida JSON tipada y explicación limitada, posibilidad de corrección humana, id de reporte persistente, estados reales y búsqueda por coordenadas/categoría. Interfaz ciudadana de alta calidad, responsive, accesible.

API keys desde `.env` solamente. Tenemos `GOOGLE_API_KEY_PRIMARY`, `GOOGLE_API_KEY_SECONDARY` y `GROQ_API_KEY`. Modelos candidatos actuales: `gemini-3.8-flash`, `qwen/qwen3.8-27b` y `gemini-3.6-flash`. PRIMERO prueba disponibilidad, visión, JSON y tool calling con claves del ambiente en llamada mínima, sin revelar secretos ni gastar innecesariamente. No confundir cuotas de desarrollo AG con inferencia backend. Si un modelo no existe o no está autorizado, elegir un modelo soportado basado en catálogo oficial y dejar constancia. Dos claves Google en un mismo proyecto NO crean cuotas separadas.

RESILIENCIA: router principal Google -> respaldo Groq -> alternativa Google, reintentos acotados/backoff con jitter, timeout y circuit breaker. `FALLA_FORZADA=429` demostrable. Los errores de IA son *internos*: jamás mostrar proveedor, HTTP error, traceback o API key en el frontend. Si fallan todos, mantener reporte recibido con `PENDING_ANALYSIS` (si BD disponible), sin falsear análisis concluido. Trazas, tiempos, modelo, intentos y causa técnica solo en zona admin protegida o logs. NO fake streaming: usar SSE real o estados honestos backend si JSON estricto.

FASES OBLIGATORIAS, iterativas:
A. Preflight: git status, docker compose config, build, healthcheck, tests scaffold; registrar evidencia.
B. Migraciones, esquema y API CRUD; fotos y coordenadas con validaciones de seguridad; fixtures de prueba.
C. Frontend real y PWA: formulario, mapa, lista/detalle, confirmación editable de categoría IA, estados honestos.
D. Servicio de modelos y fallback real; herramientas de agente; cuatro límites auditables; política de aprobación humana.
E. Suite unit/integration/e2e, casos 429/timeout/JSON inválido/total failure, scripts de evaluación, trazas, 5 preguntas manuales y 15 consultas; no inventes métricas, deja pendientes las pruebas humanas no ejecutadas.
F. Entrega: README con versiones, variables, comandos, URLs, reset de datos, fallos frecuentes; recrear desde checkout limpio, medir tiempo, exportar ZIP limpio; checklist de rúbrica y guion 6+3 min.

En cada fase: 1) plan breve; 2) implementar; 3) ejecutar pruebas y mostrar resultados resumidos; 4) actualizar `docs/estado.md` y `docs/decisiones.md`; 5) commit Git coherente. No reescribir arquitectura sin razón explícita. Priorizar un flujo E2E funcional sobre funciones decorativas. No hacer claims de terminado sin ejecutar las pruebas. Si algo exige acción manual (API keys, prueba usuario de otro equipo), señalarlo claramente.

EMPIEZA AHORA POR FASE A y luego FASE B. No inicies otros módulos hasta dejar estas bases verificadas. Evita esperar confirmaciones salvo credenciales o decisiones que realmente bloqueen la ejecución.

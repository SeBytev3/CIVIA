# CIVIA — reportes ciudadanos asistidos por IA

Equipo: Stefania Córdoba y Sebastian Espinosa · Universidad Cooperativa de Colombia.

> **ESTADO: ESQUELETO TÉCNICO INICIAL — NO ES EL ENTREGABLE FINAL.** Levanta una API y base PostgreSQL con healthcheck; **todavía no** procesa reportes ni integra IA. Antigravity completará el MVP y actualizará este contrato tras pruebas de instalación limpia.

## Requisitos
- Docker Desktop con Docker Compose v2 (en Windows 11, backend WSL2 activo).
- Git opcional si se descarga el ZIP.
- Acceso a internet para construir imágenes la primera vez.
- Credenciales Google AI Studio y Groq para análisis real **una vez implementado** el adaptador de IA.

## Inicio en una sola orden
1. Copia `.env.example` como `.env` en la raíz. No subas `.env` a Git.
2. Ejecuta en la raíz del proyecto:

```powershell
docker compose up --build -d
```

3. Abre http://localhost:8000/health — actualmente responde `status: ok` y `phase: scaffold`.
4. Consulta logs con `docker compose logs -f --tail=100`.
5. Para detener: `docker compose down` (conserva los datos); `docker compose down -v` **elimina datos**.

En esta fase se ejecutan solo `db` y `api`. El frontend se creará durante la implementación. **No afirmar que la prueba completa de despliegue está superada hasta ejecutarla en otro equipo o Docker limpio.**

## Proveedores de IA (a implementar)
- Principal: Google Gemini `gemini-3.8-flash` (confirmar acceso de cuenta/visión).
- Respaldo: Groq `qwen/qwen3.8-27b` (confirmar acceso de cuenta/visión).
- Alternativo: Google Gemini `gemini-3.6-flash` (confirmar acceso).
- Las claves Google pueden compartir cuota si están en el mismo proyecto; no multiplican automáticamente límites.
- Configuración únicamente por `.env`; fallos transitorios invisibles para usuario ciudadano; si todos fallan, reporte persistido con `PENDING_ANALYSIS` y estado honesto.

## Verificaciones de aceptación pendientes
- [ ] CRUD real de reportes, ubicación y evidencia fotográfica.
- [ ] Clasificación multimodal con al menos 2 proveedores y contrato validado.
- [ ] Herramientas de agente observables y cuatro límites operativos.
- [ ] Falla forzada 429, timeout, JSON inválido y caída total sin traceback en UI.
- [ ] Evaluación de 5 preguntas doradas y 15 consultas; métricas verificadas.
- [ ] Prueba de compañero documentada.
- [ ] Levantar desde ZIP/clone limpio en menos de cinco minutos **medido**.
- [ ] Sustentación 6 minutos y 3 de preguntas ensayada.

Referencias: `docs/arquitectura.md`, `docs/decisiones.md`, `docs/estado.md`, `PROMPT_ANTIGRAVITY.md`.

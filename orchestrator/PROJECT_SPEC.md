# CIVIA — Especificación Técnica del Proyecto (PROJECT_SPEC)

## 1. Identidad y Propósito
**CIVIA (Ciudad Inteligente con Visión e IA)** es un sistema ciudadano de reporte e incidencia urbana para el Momento Evaluativo 2 de Ingeniería de Aplicaciones con IA (Stefania Córdoba y Sebastian Espinosa). Permite a los ciudadanos crear reportes con fotos, geolocalización, análisis multimodal y consultas asistidas por agentes inteligentes.

## 2. Arquitectura del Sistema
- **Frontend:** PWA con React 19, TypeScript, Vite, Tailwind CSS y Lucide Icons (`/frontend`).
- **Backend:** FastAPI (Python 3.13/3.14) modular (`/backend`).
- **Base de Datos:** PostgreSQL 17 relacional con PostGIS (`civia-db`). Direct SQL; **NO RAG** (justificado en `docs/decisiones.md`).
- **Proxy Inverso:** Nginx con terminación segura y reenvío de encabezados de confianza (`/nginx`).
- **Infraestructura:** Docker Compose unificado (`docker-compose.yml`).

## 3. Cadena de Resiliencia de IA
1. **Proveedor Primario:** Google Gemini (`gemini-2.5-flash` / `gemini-3.8-flash-high`).
2. **Proveedor Secundario (Independiente):** Groq (`llama-3.3-70b-versatile`).
3. **Proveedor Terciario:** Google Gemini respaldo (`gemini-2.5-pro` o alternativo).
4. **Fallback Determinista:** Reglas locales sin IA y consultas SQL parametrizadas directas si todos los proveedores fallan o exceden límites.

## 4. Invariantes y Guardrails Agénticos
1. **Límites estrictos del agente:**
   - **Vueltas (Turns):** Máximo 10 iteraciones.
   - **Presupuesto de Tokens:** Monitoreo dinámico y corte anticipado antes de invocar el modelo si el saldo es insuficiente.
   - **Timeout Integral:** Límites estrictos cliente/servidor; ninguna herramienta retiene la solicitud indefinidamente.
   - **Aprobación Humana:** La IA **NUNCA** escribe directamente en la base de datos para operaciones críticas (estado, categoría, notas). Genera una propuesta pendiente de aprobación por un funcionario humano.
2. **Sanitización hacia el ciudadano:**
   - Jamás exponer trazas (tracebacks), códigos de error HTTP internos, nombres de proveedores de IA ni claves API al usuario final.
   - Toda respuesta ciudadana debe ser empática, clara y sanitizada de datos internos o PII.

## 5. Políticas de Pruebas y Seguridad
- **Bases de datos desechables:** Ninguna prueba destructiva o de regresión puede ejecutarse contra la base de datos principal (`civia`). Se deben crear clústeres o bases desechables (`civia_test_*`) por cada corrida.
- **Sin credenciales por defecto:** `ADMIN_TOKEN` debe generarse criptográficamente (`secrets.token_urlsafe(32)`) y no aceptar patrones predecibles.
- **Control de Versiones y Aislamiento:** Todo ciclo de desarrollo trabaja sobre una rama de trabajo (`fix/auditoria-final`) y checkpoints congelados en git worktrees para auditoría independiente.
- **Prohibición de auto-push / auto-merge:** El orquestador no realiza `git push` ni merge a `main` sin aprobación humana explícita.

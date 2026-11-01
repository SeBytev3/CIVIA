# Arquitectura propuesta — CIVIA

**Estado:** diseño; no se ha implementado el flujo ciudadano.

- Frontend: React + TypeScript + Vite, PWA de reportes ciudadanos, mapa y accesibilidad.
- Backend: FastAPI (Python), API y agente; las decisiones de escritura quedan en código y requieren aprobación humana cuando corresponda.
- Datos: PostgreSQL; considerar PostGIS si los criterios espaciales lo requieren, actualizando imagen Docker y migraciones (la imagen inicial NO incluye PostGIS).
- IA: adaptadores Google Gemini y Groq con contrato de salida validado, fallback y trazas protegidas.
- Entrada: texto + imagen + coordenadas; voz hasta 60s/5MB si las prioridades y pruebas permiten incluirla.
- Fuera del MVP: predicción de hotspots, satélite en tiempo real y video; no fingir datos externos.
- Integración: respuesta JSON estructurada con estados honestos por etapa, no animación falsa ni streaming simulado.
- Seguridad: límites de tamaño/tipo de archivo, rate limit, sanitización y minimización de datos personales.

## Flujo MVP
1. Ciudadano ingresa descripción, foto y punto geográfico.
2. Backend valida y persiste un reporte en estado pendiente.
3. Servicio de IA clasifica la evidencia mediante contrato tipado; fallos tratados por router con 2 proveedores.
4. Usuario revisa/edita categoría sugerida; sistema confirma registro.
5. Admin consulta reportes, métricas y trazas protegidas; ciudadanía nunca ve errores internos.

## Por confirmar con pruebas
- Acceso a modelos y cuota en cada API key.
- Métricas del dataset sintético y límites de latencia/costo.
- Requisitos exactos de despliegue de cPanel; no depender de hosting compartido para entrega.

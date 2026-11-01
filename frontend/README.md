# CIVIA Frontend (React + TypeScript + Vite PWA)

Interfaz ciudadana progresiva (PWA) para Santiago de Cali y el Valle del Cauca:
- Mapa interactivo de Cali con Leaflet y marcadores en tiempo real desde PostgreSQL (`HUECO`, `BASURAS`, `TALA`, `QUEMA`).
- Formulario de reporte ciudadano con captura de GPS del navegador, selección en mapa, fotografía validada y grabación/carga opcional de nota de voz (`<= 60s`, `<= 5 MB`).
- Vista de análisis multimodal asistido por IA con confirmación o corrección humana de categoría y severidad.
- Consulta de seguimiento por código de radicado (`CIV-2026-...`) con línea de tiempo de estados.
- Asistente agéntico conectado a herramientas SQL tipadas y zona de observabilidad protegida por `X-Admin-Token`.

Se compila con TypeScript estricto (`tsc -b && vite build`) y se sirve mediante Nginx en `http://localhost:5173` a través de `docker compose up --build -d`.

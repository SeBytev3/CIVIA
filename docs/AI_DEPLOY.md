# Configuración de IA

CIVIA usa Gemini como principal y Groq como respaldo. Configura `GOOGLE_API_KEY_PRIMARY` y `GROQ_API_KEY` mediante el configurador privado. Las variables antiguas pueden quedar en tu `.env` personal por compatibilidad de archivo. Compose sólo transmite las dos vigentes.

```powershell
.\scripts\setup_ai_keys.ps1
docker compose exec -T api python -m app.validate_providers
```

Autoriza el uso de cuota antes de ejecutar `docker compose exec -T api python -m app.validate_providers --live`. El preflight comprueba texto y, con fixtures generados, tool calling, JSON y visión cuando exista modelo configurado. Groq audio usa una entrada WAV de prueba. La comprobación de audio mide compatibilidad con la modalidad. La calidad de transcripción requiere habla real autorizada. Las capacidades exitosas quedan vinculadas a proveedor, modelo y huella de credencial en PostgreSQL. La rotación obliga a repetirlas. La validación normal informa configuración sin consumir cuota.

El preflight autorizado validó `qwen/qwen3.8-27b` para texto, herramientas, JSON estructurado y visión con una imagen sintética. `AI_GROQ_VISION_MODEL` se mantiene vacío por defecto. Para habilitar ese respaldo visual en la instalación de evaluación, configura `AI_GROQ_VISION_MODEL=qwen/qwen3.8-27b` en su `.env`, recarga API y worker con `docker compose up -d --no-deps api worker` y valida la modalidad en esa instalación con cuota autorizada. Un trabajo con foto queda pendiente de proveedor apto o va a revisión conforme a la causa y al presupuesto de reintentos.

La cuenta de Google listó `gemini-3.8-flash` en el catálogo autenticado y la generación quedó sin validar. Revisa el acceso a generación para el proyecto y repite el preflight antes de contar con Gemini durante la demostración. [Resultados por modalidad](estado.md#preflight-autorizado-con-proveedores-reales)

Los adaptadores restringen los destinos y rutas de red, usan TLS, deshabilitan redirecciones y acotan el tamaño de la respuesta. El worker envía fotografía y contexto de incidente minimizado. La consulta agéntica usa herramientas tipadas con lecturas minimizadas. PostgreSQL registra reservas compartidas antes de cada llamada. Las referencias de modalidad están en [Gemini](https://ai.google.dev/api/generate-content), [visión de Groq](https://console.groq.com/docs/vision) y [voz de Groq](https://console.groq.com/docs/speech-to-text).

Estado real de la cuenta y de la evaluación en [estado.md](estado.md).

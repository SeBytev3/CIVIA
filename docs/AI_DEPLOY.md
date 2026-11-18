# Configuración de IA

CIVIA usa Gemini como principal y Groq como respaldo. Configura `GOOGLE_API_KEY_PRIMARY` y `GROQ_API_KEY` mediante el configurador privado. Las variables antiguas pueden quedar en tu `.env` personal por compatibilidad de archivo. Compose sólo transmite las dos vigentes.

```powershell
.\scripts\setup_ai_keys.ps1
docker compose exec -T api python -m app.validate_providers
```

Autoriza el uso de cuota antes de ejecutar `docker compose exec -T api python -m app.validate_providers --live`. El preflight comprueba texto y, con fixtures generados, tool calling, JSON y visión cuando exista modelo configurado. Groq audio usa una entrada WAV de prueba. La comprobación de audio mide compatibilidad con la modalidad. La calidad de transcripción requiere habla real autorizada. Las capacidades exitosas quedan vinculadas a proveedor, modelo y huella de credencial en PostgreSQL. La rotación obliga a repetirlas. La validación normal informa configuración sin consumir cuota.

Los identificadores de Gemini y Groq se preservaron desde 1.0. `AI_GROQ_VISION_MODEL` se mantiene vacío por defecto. Configúralo cuando la cuenta permita un modelo con visión y JSON en la misma llamada. Un trabajo con foto queda pendiente de proveedor apto o va a revisión conforme a la causa y al presupuesto de reintentos.

Los adaptadores restringen los destinos y rutas de red, usan TLS, deshabilitan redirecciones y acotan el tamaño de la respuesta. El worker envía fotografía y contexto de incidente minimizado. La consulta agéntica usa herramientas tipadas con lecturas minimizadas. PostgreSQL registra reservas compartidas antes de cada llamada. Las referencias de modalidad están en [Gemini](https://ai.google.dev/api/generate-content), [visión de Groq](https://console.groq.com/docs/vision) y [voz de Groq](https://console.groq.com/docs/speech-to-text).

Estado real de la cuenta y de la evaluación en [estado.md](estado.md).

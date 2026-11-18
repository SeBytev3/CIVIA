# Configuración de IA

CIVIA usa Gemini como principal y Groq como respaldo. Configura `GOOGLE_API_KEY_PRIMARY` y `GROQ_API_KEY` mediante el configurador privado. Las variables antiguas pueden quedar en tu `.env` personal por compatibilidad de archivo. Compose sólo transmite las dos vigentes.

```powershell
.\scripts\setup_ai_keys.ps1
docker compose exec -T api python -m app.validate_providers
```

Autoriza el uso de cuota antes de ejecutar `docker compose exec -T api python -m app.validate_providers --live`. El preflight comprueba texto y, con fixtures generados, tool calling, JSON y visión cuando exista modelo configurado. Groq audio usa una entrada WAV de prueba. La comprobación de audio mide compatibilidad con la modalidad. La calidad de transcripción requiere habla real autorizada. Las capacidades exitosas quedan vinculadas a proveedor, modelo y huella de credencial en PostgreSQL. La rotación obliga a repetirlas. La validación normal informa configuración sin consumir cuota.

`AI_GROQ_VISION_MODEL` propone `qwen/qwen3.8-27b`, validado previamente con una imagen sintética. Para activar cada modalidad con la propia credencial, completa el preflight autorizado en la instalación de evaluación. Un valor explícitamente vacío en `.env` desactiva ese modelo de visión. Un trabajo con foto queda pendiente de proveedor apto o va a revisión conforme a la causa y al presupuesto de reintentos.

Si el catálogo autenticado lista el modelo de Gemini, el preflight aún requiere una generación exitosa para registrar la capacidad de texto. Si esa primera generación falla, omite modalidades adicionales en ese proveedor. [Resultados por modalidad](estado.md)

Los adaptadores restringen los destinos y rutas de red, usan TLS, deshabilitan redirecciones y acotan el tamaño de la respuesta. El worker envía fotografía y contexto de incidente minimizado. La consulta agéntica usa herramientas tipadas con lecturas minimizadas. PostgreSQL registra reservas compartidas antes de cada llamada. Las referencias de modalidad están en [Gemini](https://ai.google.dev/api/generate-content), [visión de Groq](https://console.groq.com/docs/vision) y [voz de Groq](https://console.groq.com/docs/speech-to-text).

Estado real de la cuenta y de la evaluación en [estado.md](estado.md).

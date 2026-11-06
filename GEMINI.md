# CIVIA — Guía de Operación y Evaluación con Google Gemini / Antigravity

Guía de referencia para evaluar y ejecutar CIVIA utilizando modelos y agentes de la familia Gemini.

---

## 1. Misión y Alcance
CIVIA es una plataforma para la gestión inteligente de reportes ciudadanos en Santiago de Cali, integrando visión computacional y modelos multimodales con bases de datos relacionales PostgreSQL bajo estrictos principios de seguridad, robustez e interpretabilidad ética.

---

## 2. Instrucción Rápida de Despliegue
Ejecute en la raíz del repositorio en la rama `main`:

```powershell
# En Windows 11 PowerShell:
.\scripts\run.ps1
```

```bash
# En Linux / macOS / Bash:
chmod +x ./scripts/run.sh && ./scripts/run.sh
```

Los tres contenedores orquestados se levantarán:
- `civia-db-1`: PostgreSQL 17 con esquema y 10 reportes sintéticos de prueba sembrados de forma inmutable.
- `civia-api-1`: FastAPI en Python 3.13 con validación Pydantic v2 y enrutador multimodal (`Gemini` → `Groq` → `Gemini`).
- `civia-frontend-1`: Aplicación Web Progresiva (PWA) construida con React 19 y servida por Nginx 1.27 en el puerto `5173`.

---

## 3. Endpoints de Verificación
- **Frontend PWA:** `http://localhost:5173`
- **Health Check API:** `http://localhost:8000/health` (debe devolver `status: ok` y `db: {connected: true, schema_ready: true}`)
- **Swagger UI:** `http://localhost:8000/docs` (especificación canónica exhaustiva en [`docs/API.md`](docs/API.md))

---

## 4. Invariantes de Seguridad y Ética
1. **Procedencia ética forzada:** Toda fotografía cuyo hash SHA-256 coincida con el catálogo sintético de prueba es clasificada incondicionalmente en el backend como `is_synthetic = True`, impidiendo que datos simulados pasen como evidencia ciudadana real.
2. **Visualización íntegra:** Las imágenes en la interfaz utilizan `objectFit: contain` sobre fondo neutro, impidiendo el recorte de las franjas de simulación ética.
3. **Control de acceso:** Endpoints de observabilidad y mutación de estado operativo exigen `ADMIN_TOKEN` seguro generado mediante CSPRNG.
4. **Agente genuino:** Las herramientas del agente (`consultar_reportes`, `obtener_reporte`, etc.) ejecutan SQL directo tipado y tienen prohibida la escritura directa en base de datos; cualquier mutación crítica requiere propuesta y aprobación humana por parte de un operador calificado.
5. **Almacenamiento inmutable Content-Addressed:** Las fotografías de catálogo sintético emplean direccionamiento por contenido (`synthetic_{code}_{sha[:16]}.jpg`), garantizando idempotencia, atomicidad y cero orfandad.

---

## 5. Suite Hermética de Pruebas
Para validar los 155 contratos herméticos:
```powershell
docker compose exec -T api pytest -m "not live" -v
```
**Resultado:** `155 passed, 1 deselected, 0 failed`.


---

## 6. Documentación Canónica de la API REST y Swagger/OpenAPI
La especificación técnica de los 23 endpoints clasificados en 8 categorías temáticas, los modelos de datos Pydantic v2, la integración React-FastAPI, las directrices de seguridad y los códigos de respuesta se encuentran detallados en [`docs/API.md`](docs/API.md).
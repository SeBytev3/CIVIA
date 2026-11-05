# Informe de Prepublicación GitHub y Validación de Entrega Académica

**Fecha y Hora:** 2026-11-05 09:20 (America/Bogota)  
**Proyecto:** CIVIA — Plataforma de Reportes Ciudadanos Asistidos por IA (Cali y Valle del Cauca)  
**Equipo:** Stefania Córdoba y Sebastian Espinosa  
**Repositorio local:** `C:\Users\Jhoesp\Desarrollo\CIVIA`  
**Repositorio remoto:** `https://github.com/SeBytev3/CIVIA.git`  
**Rama activa:** `fix/auditoria-final`

---

## 1. Estado de Git y Trazabilidad de Commits

| Elemento | Estado / Identificador | Observaciones |
|---|---|---|
| **Rama local activa** | `fix/auditoria-final` | Rama de remediación y auditoría formal G2.1.8 |
| **Commit de código aprobado** | `cf48e710a4d321455864d2b59a4257cdca9938aa` | Auditado y **APROBADO** por Codex en `docs/auditoria_codex_g2_1_8_cf48e71.md` (F1–F8 PASS) |
| **Commit documental de entrega** | Inmediato posterior a `cf48e71` en `fix/auditoria-final` | Agrupa exclusivamente documentación, guías de instalación y actas de auditoría |
| **Rama remota `origin/main`** | `91bff47b3a8bb56e089f9760e09c223a64f208af` | Main público actual en GitHub |
| **Rama local `main`** | `a14e895fa3ba0b1504e5b7d9d9bbf9d07472647c` | 2 commits por delante de origin/main (Fases E y F locales) |
| **Existencia en remoto `origin/fix/auditoria-final`** | **NO EXISTE AÚN** | Verificado con `git ls-remote --heads origin fix/auditoria-final` (sin salida) |
| **Diferencias frente a `main`** | 22 commits por delante en `fix/auditoria-final` | Contiene todas las remediaciones transaccionales, de seguridad, agente y resiliencia |

> [!IMPORTANT]
> **Preservación del commit aprobado:** El código ejecutable funcional está formal y contractualmente congelado en **`cf48e71`**. Cualquier cambio posterior a ese commit es **estrictamente documental** (`README.md`, `docs/estado.md`, `docs/guia_instalacion_otro_pc.md`, `docs/auditoria_codex_g2_1_8_cf48e71.md` y este informe). Cero líneas de lógica de negocio, base de datos o pruebas fueron alteradas tras el dictamen aprobatorio de Codex.

---

## 2. Resultado de la Revisión de Seguridad y Secretos

El repositorio en GitHub es **PÚBLICO**. Se ejecutó un análisis exhaustivo y sistemático de seguridad previo a cualquier publicación:

### A. Escaneo automatizado de credenciales y entropía
- **Alcance del escaneo:**
  1. Todos los commits del historial a publicar (`origin/main..fix/auditoria-final`, 24 commits en total).
  2. Todos los archivos actualmente rastreados por Git (`git ls-files`).
  3. Archivos no rastreados y pendientes de incorporación en `docs/`.
- **Patrones evaluados:**
  - Claves de API de Google AI Studio / Gemini (`AIza[0-9A-Za-z-_]{35}`).
  - Claves de API de Groq Cloud (`gsk_[0-9A-Za-z]{30,}`).
  - Claves privadas SSH, RSA, EC, PGP (`-----BEGIN ... PRIVATE KEY`).
  - Tokens de acceso personal de GitHub (`ghp_`, `github_pat_`).
  - Credenciales de AWS (`AKIA...`).
  - Cadenas de conexión PostgreSQL con contraseñas no sintéticas.
- **Resultado:** **CERO HALLAZGOS (0 secretos expuestos).**
  - Todas las cadenas de conexión encontradas corresponden a valores locales sintéticos documentados (`local_dev_change_me` en `.env.example` y `audit_synthetic_only` en pruebas aisladas de auditoría).
  - Las claves en archivos de prueba están mockeadas explícitamente (`SYNTHETIC_NOT_REAL`, `fake`).

### B. Verificación de exclusiones en `.gitignore`
- El archivo `.env` local del desarrollador está estrictamente ignorado por `.gitignore` (verificado con `git status --ignored` → `!! .env`).
- Archivos temporales de Python (`__pycache__`, `*.pyc`), cachés de pruebas (`.pytest_cache/`), volúmenes y entornos virtuales (`.venv/`, `node_modules/`) están completamente excluidos.
- Solo se incluye la plantilla pública `!.env.example`.

### C. Política estricta de `ADMIN_TOKEN`
- No existen valores predeterminados ni credenciales de demostración ("demo", "admin", "civia-admin-demo-2026").
- `docker-compose.yml` impone fail-closed obligatorio (`ADMIN_TOKEN: ${ADMIN_TOKEN:?Configure ADMIN_TOKEN en .env...}`).
- Los scripts de arranque (`scripts/run.ps1` y `run.sh`) generan tokens aleatorios únicos mediante CSPRNG (`secrets.token_urlsafe(32)`) por instalación individual.

---

## 3. Documentación Corregida y Generada

1. **[`README.md`](../README.md):**
   - Actualizado para reflejar la realidad del proyecto en Windows 11 con Docker Desktop y WSL2.
   - Aclarado que Node.js y Python no requieren instalación global en el computador evaluador.
   - Documentado el procedimiento de clonación y checkout explícito a `fix/auditoria-final`.
   - Detalle exhaustivo de las variables de `.env` y su correspondencia.
   - Comandos seguros de diagnóstico (`docker compose ps`, logs, rebuild) y aislamiento con alerta explícita de precaución (`> [!CAUTION]`) sobre comandos destructivos (`docker compose down -v`).
   - Enlace directo a la guía de instalación para otro PC.
2. **[`docs/guia_instalacion_otro_pc.md`](guia_instalacion_otro_pc.md):**
   - Nueva guía paso a paso con 17 secciones completas para el profesor o evaluador.
   - Incluye checklist de sustentación académica de 6 puntos con tiempos estimados y mapeo contra la rúbrica del Momento 2.
   - Distinción transparente entre lo implementado en el sistema y propuestas futuras (imágenes satelitales / predicción prospectiva).
3. **[`docs/estado.md`](estado.md):**
   - Incorporación formal del registro de auditoría independiente de Codex para el commit `cf48e71` con dictamen **APROBADA** al 100%.
4. **[`docs/auditoria_codex_g2_1_8_cf48e71.md`](auditoria_codex_g2_1_8_cf48e71.md):**
   - Acta oficial inmutable de la auditoría independiente realizada por Codex CLI.

---

## 4. Resultado de Validaciones de Docker y Arquitectura

1. **Sintaxis de Compose:**
   - Comando: `docker compose config --quiet`
   - Salida: Código de salida `0` (sintaxis y variables válidas).
2. **Topología de red y advertencia sobre subredes:**
   - La red `civia_net` define la subred estática `172.28.0.0/16` con asignación fija de IPs (`172.28.0.10` para `db`, `172.28.0.11` para `api`, `172.28.0.2` para `frontend`).
   - Esta topología permite que `api` valide a `frontend` como proxy de confianza exacto (`TRUSTED_PROXIES: 172.28.0.2`), satisfaciendo el contrato M-06.
   - En un segundo computador limpio, esta red se creará sin conflictos siempre que no exista previamente otra red Docker en ese equipo usando el segmento `172.28.0.0/16`.
3. **Estado de contenedores habituales:**
   - Los contenedores habituales de CIVIA (`civia-api-1`, `civia-frontend-1`, `civia-db-1`) se comprobaron mediante `docker ps` y permanecen activos, intactos y saludables (`Up 30 hours (healthy)`).
   - Ningún contenedor de desarrollo fue modificado ni reiniciado durante esta fase.

---

## 5. Requisitos y Consideraciones para el Segundo PC

Para la prueba de instalación limpia en otro computador:
- **SO:** Windows 11 (64-bit) con virtualización habilitada en BIOS.
- **Herramientas:** Git para Windows y Docker Desktop con backend WSL2.
- **RAM libre para Docker:** Mínimo 4 GB.
- **Espacio libre en disco:** Mínimo 10 GB.
- **Conexión a Internet:** Requerida en el primer inicio para descargar las imágenes base oficiales.
- **Claves IA:** Opcionales para arranque básico y suite sintética; requeridas si se desea probar análisis multimodal con Gemini/Groq en vivo.

---

## 6. Riesgos Identificados y Medidas de Mitigación

| Riesgo | Probabilidad | Impacto | Mitigación Implementada |
|---|---|---|---|
| **Evaluador clona `main` en lugar de `fix/auditoria-final`** | Media | Alto | Documentado en el README con un aviso de advertencia (`> [!IMPORTANT]`) y en el comando #2 de la guía de clonación. |
| **Conflicto de subred `172.28.0.0/16` si el segundo PC ya tiene redes Docker** | Baja | Medio | Documentado comando `docker network prune` o diagnóstico de redes previas en la guía de solución de problemas. |
| **Agotamiento de cuota gratuita en Gemini o Groq durante la sustentación** | Media | Bajo | Resiliencia de 3 niveles conmutará automáticamente entre proveedores; si ambos fallan, el sistema degrada elegantemente a `PENDING_ANALYSIS` sin tracebacks; la suite determinista no consume cuota. |
| **Política de ejecución de PowerShell (`PSSecurityException`)** | Alta | Bajo | Documentada la bandera `-ExecutionPolicy Bypass` y el comando alternativo directo `docker compose up --build -d`. |

---

## 7. Instrucciones Exactas para Publicar la Rama (Push)

> [!WARNING]
> **RESTRICCIÓN ACTIVA:** No ejecutar estos comandos hasta recibir la autorización expresa del usuario.

Una vez autorizado el push hacia el repositorio remoto:

```powershell
# 1. Asegurar que estamos en la rama correcta y con el arbol limpio
git checkout fix/auditoria-final
git status

# 2. Publicar la rama en GitHub por primera vez configurando upstream
git push -u origin fix/auditoria-final
```

---

## 8. Instrucciones Exactas para Clonar en el Segundo Computador

Una vez publicada la rama en GitHub, en el segundo computador con Windows 11 y Docker Desktop:

```powershell
# 1. Clonar el repositorio
git clone https://github.com/SeBytev3/CIVIA.git
cd CIVIA

# 2. Situarse en la rama aprobada
git checkout fix/auditoria-final

# 3. Arrancar los servicios con generacion automatica de ADMIN_TOKEN
.\scripts\run.ps1

# 4. Validar salud en navegador o terminal
Invoke-RestMethod -Uri "http://localhost:8000/health"
Start-Process "http://localhost:5173"
```

---

## 9. Dictamen Final

# **LISTO PARA PUSH**

### Justificación técnica:
1. **Código 100% aprobado:** G2.1.8 fue auditada y formalmente aprobada por Codex CLI en el commit `cf48e71`, con 8 de 8 contratos (F1 a F8) superados y 135 pruebas herméticas pasando sin fallos.
2. **Cero secretos en el repositorio:** Escaneo automatizado exhaustivo confirmó ausencia total de credenciales reales, claves de API, tokens privados o contraseñas en todos los commits y archivos a publicar.
3. **Documentación alineada y completa:** `README.md` actualizado con instrucciones reproducibles para Windows 11/WSL2; `docs/guia_instalacion_otro_pc.md` elaborada con 17 secciones y checklist de sustentación académica; acta oficial de auditoría incorporada.
4. **Integridad del entorno:** Servicios habituales intactos y saludables. Árbol de trabajo listo para el commit documental final y su posterior publicación controlada.

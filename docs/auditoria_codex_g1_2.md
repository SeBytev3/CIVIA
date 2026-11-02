# CIVIA — verificación independiente de C-01 / G1.2

Fecha: 2026-11-01, America/Bogota.

**Dictamen: PASS para C-01 y el contraejemplo contextual solicitado.**

HEAD auditado: `b76e634690bf7b4bb36b2ada9a994833241d9795`, rama `fix/auditoria-final`.
Comparación: `74ecc025e01bd5ccff36cb28d8a1c182a9c6ea82`.

El patrón que permitió arranque y privilegios en G1.1 ahora se rechaza. Se comprobó tanto el lifespan de FastAPI como el arranque del proceso Uvicorn real. Un secreto aleatorio CSPRNG permite inicializar PostgreSQL y usar administración, mientras la ausencia de credencial, una incorrecta y el antiguo token demo se rechazan.

## Alcance y comparación

Se leyeron AGENTS.md y el contraejemplo de docs/auditoria_codex_g1_1.md. El árbol original estaba limpio al comenzar. El diff contiene nueve archivos: configuración, prueba C-01, documentación y scripts de arranque. En producción cambia backend/app/config.py; no cambian main.py, repository.py, agent.py, security.py, db.py, conftest.py ni eval/evaluar.py respecto de G1.1.

Por lo solicitado, **no se repitieron A-01, M-07, N-03, A-06, A-07 ni B-03**. No se ejecutaron evaluaciones de modelos, builds frontend ni otros bloques. Las rutas administrativas se probaron únicamente para validar C-01.

No se editó código de producción, no se cambió de rama y no se crearon/publicaron commits. Solo se añade este informe.

## Entorno aislado

Se congeló HEAD con git archive y se extrajo en:

`C:\Users\Jhoesp\AppData\Local\Temp\civia-g12-0eb2c34f76864a30b0c1985cdba43cc7\src`.

Se inicializó un clúster nuevo **PostgreSQL 17.6 real**, escuchando exclusivamente en `127.0.0.1:55479`, con base nueva `test_g12_c01`. PGDATA y uploads fueron directorios desechables bajo la misma raíz. No se conectó a la BD habitual ni se copió .env.

Se reutilizaron CPython 3.13.18 y las dependencias directas exactas de backend/requirements.txt, que no cambió en este commit. PYTHONPATH apuntó a la nueva copia archivada. Las claves de proveedores quedaron ausentes/vacías. No se usaron datos privados, inferencia externa ni mocks de PostgreSQL o de la dependencia administrativa.

Docker no está disponible: no se ejecutó Compose ni se afirma haber verificado contenedores. El arranque completo comprobado es el del backend real: Uvicorn, lifespan, tres migraciones, carga sintética y endpoints contra PostgreSQL real.

## Evidencia independiente ejecutada

El patrón se construyó **exactamente igual** que en el informe anterior:

```python
pattern = '_'.join(('Civia', 'AdminToken', '2026', 'Demo')) + '!'
```

Es una entrada sintética pública para reproducción; no es un secreto extraído de una instalación. Los secretos aleatorios de auditoría no se imprimieron ni se guardaron en .env o en los resultados.

Se ejecutó cada caso en un proceso Python nuevo, con configuración recibida por variables de entorno. Los negativos no se limitaron a llamar is_strong_admin_token: se intentó iniciar el lifespan completo. Tras el rechazo, se comprobó por separado que la dependencia de autorización también devuelve 401, incluso cuando la cabecera coincide con la configuración inválida. Esa comprobación separada no representa un servidor que haya arrancado a pesar del error.

| Caso | Arranque completo | Acceso administrativo | Resultado |
|---|---|---|---|
| Patrón contextual exacto que pasó en 74ecc025 | Rechazado con RuntimeError | Dependencia: 401 | PASS |
| Mismo patrón con ADMIN_TOKEN_ALLOW_CUSTOM_FORMAT=true | Rechazado | Dependencia: 401 | PASS |
| Patrón contextual alargado, formato personalizado habilitado | Rechazado | Dependencia: 401 | PASS: el control no depende solo de longitud/formato |
| ADMIN_TOKEN ausente | Rechazado; configuración efectiva vacía | Dependencia: 401 | PASS: no aparece fallback implícito |
| ADMIN_TOKEN explícitamente vacío | Rechazado | Dependencia: 401 | PASS |
| Antiguo token demo | Rechazado | Dependencia: 401 | PASS |
| Patrón numérico repetido de auditorías anteriores | Rechazado | Dependencia: 401 | PASS |
| Secreto nuevo de secrets.token_urlsafe(32) | Completado, health 200 y BD/esquema listos | Correcto 200; ausente/incorrecto/demo 401 | PASS |
| Secreto nuevo de generate_admin_token(), basado en CSPRNG | Completado, health 200 y BD/esquema listos | Correcto 200; ausente/incorrecto/demo 401 | PASS |

En ambos positivos se consultó PostgreSQL: **tres migraciones registradas y diez reportes sintéticos**. La respuesta administrativa no contenía el secreto configurado. El supervisor verificó las aserciones de los nueve casos y terminó con `Independent C-01 assertions: PASS`.

### Proceso Uvicorn real y HTTP por TCP

Para distinguir una prueba ASGI de un arranque real, se ejecutó adicionalmente:

`python -m uvicorn app.main:app --host 127.0.0.1 --port <puerto temporal libre>`

Cada proceso recibió un entorno aislado y se cerró al terminar.

| Configuración | Resultado observado |
|---|---|
| Patrón contextual exacto | Uvicorn termina con **exit 3**, por rechazo en startup. |
| Secreto nuevo CSPRNG | Uvicorn permanece activo; `/health` confirma conexión y esquema listos; observabilidad con credencial correcta **200**, sin credencial **401**, con otra aleatoria **401**. |

Se comprobó que el secreto configurado no aparecía en stdout/stderr antes de conservar los logs. No se enviaron credenciales en argumentos de línea de comandos ni en URLs.

## Ausencia de credencial predeterminada

Además de los procesos de arranque sin ADMIN_TOKEN, se inspeccionó la copia exacta del commit:

| Comprobación | Resultado |
|---|---|
| Settings.ADMIN_TOKEN | os.getenv con valor por defecto vacío. |
| .env.example | ADMIN_TOKEN vacío; instrucciones de generación CSPRNG. |
| docker-compose.yml | Interpolación obligatoria `${ADMIN_TOKEN:?...}`; sin secreto de respaldo. Verificación estática, no ejecución Docker. |
| Frontend | Estado administrativo inicial vacío; no incluye el antiguo valor demo en App.tsx. |
| Backend con credencial CSPRNG válida y cabecera demo antigua | 401 en ambos positivos. |

Los literales demo presentes en listas de rechazo, pruebas o informes no constituyen una credencial válida por defecto. No se leyó ni imprimió el .env habitual del usuario.

## Pruebas del proyecto, solo C-01

Se ejecutó sin modificar sus fuentes:

```text
python -m pytest backend/tests/test_audit_g1_security.py -k c01 -q --tb=short
3 passed, 11 deselected, 1 warning in 0.87s
```

El warning es de deprecación de AnyIO. Las once pruebas ajenas a C-01 quedaron excluidas. Este resultado complementa, pero no reemplaza, los procesos y peticiones independientes descritos arriba.

## Motivo del cierre y límites

G1.2 amplía el rechazo de términos contextuales, patrones y formato en config.py, aumenta el mínimo a 32 caracteres y mantiene generación con secrets. El patrón exacto de G1.1, la variante que supera la longitud mínima y el modo de formato personalizado ya no permiten privilegios. El control falla cerrado sin configuración y acepta secretos CSPRNG nuevos con funcionalidad administrativa comprobada.

**No queda un bloqueo de C-01 reproducido en las condiciones solicitadas: PASS.** No se afirma que un filtro de cadenas pueda demostrar matemáticamente el origen aleatorio de todo valor externo arbitrario. El procedimiento de instalación debe seguir generando el secreto con CSPRNG. Tampoco se extiende este dictamen a publicación, despliegue Docker o los demás bloques de CIVIA.

## Reproductores y evidencia

En la raíz temporal indicada se conservaron:

- `case.py` y `run_c01.py`: nueve procesos independientes, sin persistir secretos aleatorios.
- `results.json`: configuración aceptada/rechazada, estado de startup, HTTP y conteos SQL; sin valores de tokens.
- `tcp_c01.py` y `tcp_results.json`: arranque Uvicorn y peticiones reales por TCP.
- Logs de startup sanitizados mediante comprobación de ausencia del secreto configurado.

Las aserciones comprueban el rechazo de los siete negativos y, para cada positivo, startup completado, BD lista, 200 con secreto correcto, 401 sin él/con uno erróneo/demo, tres migraciones, diez sintéticos y ausencia del secreto en la respuesta. La permanencia futura del directorio temporal no está garantizada; este informe conserva el patrón exacto, procedimiento y resultados.

Al finalizar se detuvo PostgreSQL temporal y se cerraron ambos procesos Uvicorn; no se tocaron otros servidores o volúmenes. HEAD original sigue en b76e634690bf7b4bb36b2ada9a994833241d9795 y solo aparece este informe como archivo nuevo. No se publicaron commits.

SHA256 de evidencia:

- head.zip: `2F8B063C7710A6E184006E27DAD5FC2B63AC77A2E5397E6D78163A5E9AC50546`.
- results.json: `0050661C412093F2825C02FE4497755E0EE41112A334F382F76DF418C96C4735`.
- tcp_results.json: `3EA45125E72883D4639DA1A21D497F3987B740B15C86798F79497D7B1B2C84EA`.

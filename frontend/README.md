# Interfaz web y Android de CIVIA

CIVIA sirve tres interfaces web mediante Nginx. Todas usan la misma API y requieren una sesión del perfil correspondiente para las operaciones privadas.

- `/` permite radicar un reporte desde el computador o el teléfono. El formulario ofrece registro o inicio de sesión ciudadano, fotografía, ubicación, audio opcional y confirmación con el radicado.
- `/app/` es CIVIA Ciudadano. Permite reportar, consultar el mapa, seguir reportes propios, usar el asistente y gestionar la cuenta. Selecciona **Instalar CIVIA** desde el pie de la web. La aplicación muestra el botón de instalación cuando Chromium lo ofrece o las instrucciones del navegador. En iOS, abre el enlace en Safari y selecciona **Compartir → Añadir a pantalla de inicio**.
- `/admin/` es el portal administrativo instalable. La sesión emitida por el servidor determina si el usuario puede gestionar casos o administrar la plataforma.

Las PWA requieren un origen seguro. En el computador puedes usar `http://localhost:5173`. Desde otro dispositivo abre la dirección HTTPS que entrega el arranque LAN con su certificado de confianza instalado. Cada PWA registra su propio Service Worker y conserva únicamente su aviso estático para cuando falta conexión. Los datos de sesión, API y evidencias permanecen fuera de CacheStorage. La actualización retira el Service Worker histórico de la raíz y el caché `civia-pwa-v1`. Los borradores se recuperan cuando vuelve la conexión y se valida la sesión. Si se actualiza desde 1.1.0 en el mismo origen y aparece **Recuperar borrador anterior**, úsalo para revisar el borrador de tu cuenta antes de decidir su envío.

Consulta `/build.json` para comprobar la versión y revisión servidas por Nginx y `/api/meta` para comprobar la revisión, el identificador público de instalación y la versión de protocolo de la API.

## Herramientas de desarrollo web

Con el API local iniciado, desde `frontend` ejecuta estos comandos. Si el puerto 5173 ya está ocupado por Nginx, usa otro puerto para Vite.

```powershell
npm ci
npm run typecheck
npm run build
npm run dev -- --port 5174
```

En otra consola, ejecuta las pruebas de navegación, perfiles, formularios, persistencia del borrador, instalación y ámbitos de los Service Workers en Microsoft Edge. La suite intercepta la API y usa datos sintéticos. Puedes apuntarla a una instalación Docker con `TARGET_URL`.

```powershell
$env:TARGET_URL = 'http://localhost:5174'
npm run test:e2e
```

Para otro navegador Chromium compatible, configura `BROWSER_CHANNEL` con su canal de Playwright. Si defines `CIVIA_SCREENSHOTS` con una ruta de salida, la suite guarda capturas del recorrido responsive.

## Android

Para compilar se necesita Node.js 22 o superior, JDK 21 y Android SDK Platform 35 con Build-Tools, Platform-Tools y licencias aceptadas. El APK admite Android 7.0 (API 24) o posterior. Define `JAVA_HOME` y `ANDROID_HOME` con las rutas de tu instalación o configura `sdk.dir` en `android/local.properties`. Gradle 8.11.1 viene fijado por el wrapper. Desde `frontend` en PowerShell:

```powershell
npm ci
$env:CIVIA_BUILD_SHA = (git rev-parse --verify HEAD).Trim()
npm run sync:android
Push-Location android
.\gradlew.bat :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
Pop-Location
$apk = 'android/app/build/outputs/apk/debug/CIVIA-1.1.1-android-debug.apk'
Copy-Item 'android/app/build/outputs/apk/debug/app-debug.apk' -Destination $apk
Get-FileHash -Algorithm SHA256 -LiteralPath $apk
adb install -r $apk
```

En Linux o macOS, usa `./gradlew` desde `frontend/android`. Con un emulador o dispositivo conectado, `./gradlew :app:connectedDebugAndroidTest` comprueba el transporte registrado, el bloqueo de HTTP y el descubrimiento DNS-SD desde Android. El APK debug usa la clave de depuración de la instalación de Gradle. Para actualizar una instalación existente, Android exige el mismo identificador `co.edu.ucc.civia` y la misma firma. Conserva la instalación si debes rescatar información local de una compilación anterior.

### Conectar el APK

1. Inicia CIVIA en el modo LAN descrito en el [README principal](../README.md) y conecta ambos equipos a la misma red Wi-Fi.
2. Abre CIVIA, selecciona el servidor descubierto y usa **Escanear QR**, **Abrir imagen de QR** o pega el contenido de `.civia/lan/pairing.txt`. Escanea el archivo `.civia/lan/pairing.svg` que genera tu instalación. Confirma el emparejamiento e inicia sesión como ciudadano.
3. Si la red bloquea mDNS, el código sigue permitiendo conectar directamente siempre que exista conectividad al puerto HTTPS. Con la instalación ya emparejada puedes actualizar manualmente su dirección HTTPS desde **Perfil → Configurar conexión**. Cuando cambie el certificado, usa el nuevo código generado por el responsable de la instalación.
4. Para desarrollar con un emulador, usa su alias de host `10.0.2.2` si alcanza el gateway HTTPS, o `adb reverse tcp:<puerto> tcp:<puerto>` y el host `127.0.0.1`. En el código autorizado cambia solo el origen HTTPS a la dirección de prueba y conserva intactos el identificador y la huella. El acceso requiere que el puerto local de destino termine en el mismo gateway HTTPS.

El APK incluye los recursos compilados. El transporte Android envía credenciales únicamente después de confirmar la huella SHA-256 del certificado de instalación y los metadatos del servidor. El token queda cifrado con AES-GCM en Android Keystore y se asocia a la instalación y al certificado. El cierre de sesión elimina la copia local y solicita revocación cuando el servidor está accesible. Cámara y galería usan Capacitor. El GPS usa geolocalización nativa. Android graba notas WAV mono mediante `AudioRecord` con permiso del sistema y un límite de 60 segundos.

IndexedDB conserva el borrador, la evidencia y la clave de idempotencia por instalación y por cuenta. Los reintentos se autorizan para esa misma cuenta y el borrador se elimina después de recibir el radicado real. La actualización de un APK 1.1.0 requiere emparejar e iniciar sesión de nuevo. Si hay un borrador antiguo en el mismo origen local del APK o del navegador, usa **Recuperar borrador anterior** desde la cuenta que lo creó, verifica su contenido y envíalo. Ese paso asigna explícitamente el borrador a la instalación actual.

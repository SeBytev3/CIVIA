# Interfaz web y Android de CIVIA

CIVIA publica el cliente ciudadano en `/` y el portal PWA administrativo en `/admin/`. Comparten el backend y el proxy de Nginx. El portal distingue las cuentas de administración de casos y de administración web a partir de la sesión emitida por el servidor.

El portal administrativo instala su manifest y service worker con alcance `/admin/`. El service worker guarda una página estática que explica el estado sin conexión. El contenido autenticado y las solicitudes al API requieren la red. La actualización retira el registro del antiguo service worker y su caché `civia-pwa-v1`.

La web ciudadana habilita el formulario en un viewport de hasta 767 píxeles con puntero táctil. Es una comprobación de presentación. La autorización de radicación y la propiedad de reportes se verifican en el backend.

## Herramientas de desarrollo web

Con el API local iniciado, desde `frontend` ejecuta estos comandos. Si el puerto 5173 ya está ocupado por Nginx, usa otro puerto para Vite.

```powershell
npm ci
npm run typecheck
npm run build
npm run dev -- --port 5174
```

En otra consola, verifica la navegación, los perfiles, la persistencia del borrador después de una desconexión y el aislamiento del service worker en Microsoft Edge. La suite intercepta la API y usa datos sintéticos.

```powershell
$env:TARGET_URL = 'http://localhost:5174'
npm run test:e2e
```

Para otro navegador Chromium compatible, configura `BROWSER_CHANNEL` con su canal de Playwright.

## Android

Se necesita Node.js 22 o superior, JDK 21 y Android SDK Platform 35 con Build-Tools, Platform-Tools y las licencias del SDK aceptadas. La aplicación admite Android 7.0 (API 24) o posterior. Gradle 8.11.1 viene fijado por el wrapper del proyecto. Define `JAVA_HOME` y `ANDROID_HOME` con las rutas de tu instalación o configura `sdk.dir` en `android/local.properties`. Desde `frontend` en PowerShell:

```powershell
npm ci
$env:VITE_API_BASE_URL = 'http://127.0.0.1:5173'
npm run sync:android
Push-Location android
.\gradlew.bat assembleDebug lintDebug
Pop-Location
$apk = 'android/app/build/outputs/apk/debug/CIVIA-1.1.0-android-debug.apk'
Copy-Item 'android/app/build/outputs/apk/debug/app-debug.apk' $apk
Get-FileHash -Algorithm SHA256 $apk
```

El valor de `VITE_API_BASE_URL` es el origen del proxy, sin ruta ni credenciales. Usa el mismo valor al sincronizar Capacitor y al compilar Gradle.

- **USB.** Con depuración USB autorizada, iniciar CIVIA en el computador y ejecutar `adb reverse tcp:5173 tcp:5173`. El APK predeterminado conecta con `http://127.0.0.1:5173` mediante esa redirección. Instalar desde `frontend` con `adb install -r android/app/build/outputs/apk/debug/CIVIA-1.1.0-android-debug.apk`.
- **Emulador Android Studio.** Usar `adb reverse` con el mismo APK o recompilar con `$env:VITE_API_BASE_URL = 'http://10.0.2.2:5173'`. Android Studio configura el alias `10.0.2.2` hacia el propio host.
- **Wi-Fi de demostración.** Publicar solamente el proxy en la IP de la red local del computador mediante `FRONTEND_PORT_BINDING`, permitir el puerto en el firewall para esa red y recompilar con su origen real, por ejemplo `http://192.168.1.20:5173`. Solo el APK de depuración permite HTTP para el host privado seleccionado. La dirección de ejemplo debe sustituirse por la IP específica del host.
- **HTTPS.** Configurar un origen `https://` con certificado válido y mantener la publicación restringida al proxy. La variante release deniega HTTP en la red y el portal requiere HTTPS para cookies Secure en un despliegue público.

La app usa el selector de fotos y cámara de Capacitor, geolocalización nativa y el micrófono del WebView mediante permiso de Android. El token móvil se cifra con una clave AES-GCM de Android Keystore y queda en preferencias privadas. Los borradores, fotos y audios se guardan mediante IndexedDB en el espacio privado de la aplicación, con la copia de seguridad de Android deshabilitada. Cada borrador pertenece al UUID de la cuenta que lo creó. Si se interrumpe el envío, el borrador conserva la clave de idempotencia al reintentar. Se puede reintentar manualmente o al recuperar conexión con la pantalla de reporte abierta. Tras confirmar la recepción, se muestra el radicado real y se elimina el borrador.

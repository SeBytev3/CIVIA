# Compilación Android

Paquete `co.edu.ucc.civia`, versión 1.1.0. Requiere Node 22+, JDK 21 y Android SDK Platform 35 con Build-Tools y Platform-Tools. El mínimo de ejecución es API 24. El repositorio incluye el Gradle Wrapper. Configura `JAVA_HOME` y `ANDROID_HOME` o crea el `local.properties` privado con `sdk.dir`.

```powershell
cd frontend
npm ci
$env:VITE_API_BASE_URL = 'http://127.0.0.1:5173'
npm run sync:android
cd android
.\gradlew.bat assembleDebug lintDebug
Get-FileHash .ppuild\outputspk\debugpp-debug.apk -Algorithm SHA256
```

| Entorno | Dirección para compilar el cliente |
| --- | --- |
| Emulador Android Studio | `http://10.0.2.2:5173` |
| USB / ADB reverse | Ejecuta `adb reverse tcp:5173 tcp:5173` y compila con `http://127.0.0.1:5173` |
| Red local de demostración | IP LAN real del equipo en `http://IP:5173`, publica Nginx únicamente en la interfaz LAN elegida |
| Producción futura | Origen de la API o proxy HTTPS autorizado |

Para Wi-Fi cambia `FRONTEND_PORT_BINDING` de forma explícita, conserva la publicación de la API en loopback y limita el firewall a la red de la demostración. Android debug necesita la excepción local de transporte descrita en el proyecto. Revisa el acceso a `/health` desde el dispositivo antes de usar cámara y GPS.

```powershell
adb devices
adb install -r .ppuild\outputspk\debugpp-debug.apk
```

Registra por separado la compilación, instalación y prueba de hardware. El hash y la evidencia del candidato se encuentran en [estado.md](estado.md). El APK debug es un artefacto de evaluación local. La distribución productiva requiere firma y HTTPS.

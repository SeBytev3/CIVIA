# Compilación e instalación en Android

La entrega móvil de Momento 3 se realiza mediante la PWA ciudadana. Este documento conserva el registro del APK debug anterior y el procedimiento para mantener el proyecto Android. [Instalación de la PWA](../README.md#pwa-ciudadana-y-red-local)

El paquete de CIVIA es `co.edu.ucc.civia`. La versión 1.1.1 usa `versionCode=111`, admite Android 7.0 (API 24) en adelante y apunta a API 35. El APK de evaluación usa firma de depuración. Android permite instalarlo sobre otro paquete `co.edu.ucc.civia` únicamente si la firma coincide.

| Artefacto local de evaluación | Valor |
| --- | --- |
| Ruta relativa al repositorio | `frontend/android/app/build/outputs/civia/CIVIA-1.1.1-android-debug.apk` |
| Revisión incluida en `build.json` | `79c1d44254bc2ae7f3f06f277fd6b7a15dc8709e` |
| Tamaño | 8 241 778 bytes |
| SHA-256 del archivo | `e9b9612cdb10e833153bc19faddf00da1ff370825d02b69e05418e5526a93134` |
| Certificado de depuración SHA-256, firma APK v2 verificada | `50d460e3e1c4a4ab449faa0472d46062eaa1e179789468b80a38769212a83c58` |

La distribución en GitHub queda pendiente de aprobación del candidato. El archivo indicado arriba es el binario generado para la evaluación local.

## Instalar y emparejar

1. Abre el APK de evaluación desde Android y autoriza la fuente de instalación que estés usando. En un emulador o dispositivo con ADB puedes ejecutar `adb install -r CIVIA-1.1.1-android-debug.apk`.
2. Arranca CIVIA en modo LAN y conecta teléfono y computador a la misma red Wi-Fi. El APK inicia la búsqueda de servidores.
3. Si estás conectando por primera vez, selecciona la instalación que anuncia el computador y escanea `.civia/lan/pairing.svg`. También puedes abrir una imagen del QR o pegar el código de `pairing.txt`. La variante de texto permite emparejar cuando el dispositivo llega al gateway y la red limita mDNS.
4. Inicia sesión como ciudadano. Para actualizar la dirección de una instalación emparejada, abre **Perfil → Configurar conexión**. Conserva el certificado y la identidad de instalación cuando cambie la IP. Si cambia el certificado, repite el emparejamiento.

La actualización desde el APK 1.1.0 pide volver a emparejar e iniciar sesión. Si encuentra un borrador anterior de esa misma cuenta en los datos locales, muestra **Recuperar borrador anterior**. La transición se probó con los APK de ambas versiones, con recuperación explícita del contenido y la fotografía del borrador antes de cualquier envío.

[Conectividad y diagnóstico](CONECTIVIDAD_LAN.md) · [Resultados y huella del APK](estado.md)

## Reconstruir

Para compilar se requiere Node 22+, JDK 21, Android SDK Platform 35 y Build-Tools con licencias aceptadas. Define `JAVA_HOME` y `ANDROID_HOME`, o guarda `sdk.dir` en `frontend/android/local.properties`. El Gradle Wrapper fija su propia versión. Desde el repositorio:

```powershell
Set-Location frontend
npm ci
$env:CIVIA_BUILD_SHA = (git rev-parse --verify HEAD).Trim()
npm run sync:android
Set-Location android
.\gradlew.bat :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
$apk = 'app/build/outputs/apk/debug/CIVIA-1.1.1-android-debug.apk'
Copy-Item 'app/build/outputs/apk/debug/app-debug.apk' -Destination $apk
Get-FileHash $apk -Algorithm SHA256
```

Ejecuta `./gradlew` en Bash. Con un emulador o teléfono de evaluación, ejecuta `:app:connectedDebugAndroidTest`. Para ADB reverse emplea un gateway HTTPS ya preparado y el puerto seleccionado. Mantén el identificador de instalación y la huella del certificado cuando se ajuste el destino de prueba a `127.0.0.1` o al alias de emulador `10.0.2.2`.

El APK se construye con una interfaz local incluida y recibe el destino durante el emparejamiento. FastAPI y Nginx se reconstruyen de forma independiente. La firma de producción y la distribución pública requieren una revisión adicional de infraestructura y aceptación.

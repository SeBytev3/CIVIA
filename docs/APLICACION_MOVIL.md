# Aplicación móvil ciudadana

CIVIA empaqueta el frontend ciudadano React y TypeScript con Capacitor. Las secciones son Inicio, Reportar, Mis reportes, Asistente y Perfil. El usuario elige cámara o galería, usa geolocalización o un punto manual, y puede incluir una nota de voz de hasta 60 s y 5 MB. El servidor valida los archivos y devuelve el radicado después de persistir el reporte.

El borrador se conserva por cuenta en IndexedDB con los archivos y su clave de idempotencia. Ante una interrupción, la interfaz mantiene explícito el envío pendiente y conserva la clave hasta confirmar la recepción. El reintento requiere abrir la aplicación y mantener una sesión válida.

La contingencia web está en `/`. En escritorio el formulario muestra «Para registrar un reporte, utiliza CIVIA desde tu dispositivo móvil». Esto es una regla de experiencia de usuario. La autorización efectiva del backend se basa en sesión CITIZEN y propiedad. Una pantalla pequeña o el User-Agent carecen de valor como atestación.

La PWA está bajo `/admin/`. Su service worker se limita a ese ámbito y la raíz retira el registro histórico. La experiencia administrativa tiene login, bandeja de casos y acciones según rol. El caché omite sesiones, API, evidencia privada y telemetría. Una operación sólo se confirma con respuesta del servidor.

Consulta [ANDROID_BUILD.md](ANDROID_BUILD.md) para el APK y conectividad.

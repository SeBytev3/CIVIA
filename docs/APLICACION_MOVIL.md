# Interfaces de CIVIA 1.1.1

La vía de instalación móvil para la entrega académica es la PWA ciudadana en `/app/`. El cliente Android se conserva en el repositorio como interfaz independiente. [Instalación y HTTPS LAN](../README.md#pwa-ciudadana-y-red-local)

| Entrada | Alcance |
| --- | --- |
| `/` | Web de radicación con encabezado institucional. Incluye autenticación, selección de ubicación, foto, audio opcional, confirmación y radicado. Funciona en escritorio y móvil. |
| `/app/` | Ciudadanía instalable. Inicio, mapa, reportes propios, seguimiento, asistente y perfil. Manifiesto, iconos y Service Worker propios. |
| Android | Empaqueta la experiencia ciudadana y establece el destino de red tras el emparejamiento. |
| `/admin/` | Portal administrativo con su propio ámbito PWA. |

Los indicadores de modo nativo e instalado seleccionan la presentación. La API autoriza por sesión, rol y propiedad. Web y PWA usan el API del mismo origen. Android guarda su sesión en Android Keystore y limita sus peticiones a la instalación emparejada.

Los borradores se guardan en IndexedDB con archivos y clave de idempotencia, bajo la cuenta y la instalación correspondientes. El borrador se mantiene hasta recibir confirmación. El fallo de red permite reintentar al recuperar la sesión y la conexión.

La PWA ciudadana se instala desde `/app/` en un contexto seguro. La raíz enlaza el flujo de instalación. El Service Worker legado se retira al actualizar CIVIA y conserva los borradores. Los ámbitos instalables almacenan sólo su aviso estático de desconexión. [Conectividad](CONECTIVIDAD_LAN.md) · [Pruebas y límites](estado.md)

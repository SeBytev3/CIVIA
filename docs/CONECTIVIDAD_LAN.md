# Conectividad LAN · CIVIA 1.1.1

## Arranque y selección de interfaz

```powershell
./scripts/run.ps1 -Lan
./scripts/run.ps1 -Lan -LanAddress '192.168.1.25'
./scripts/run.ps1 -Stop
```

```bash
./scripts/run.sh --lan
./scripts/run.sh --lan --lan-address 192.168.1.25
./scripts/run.sh --stop
```

Sustituye la dirección por la de la interfaz Wi-Fi o Ethernet elegida. En el arranque normal, HTTP está limitado a loopback. El modo LAN agrega HTTPS de Nginx en la dirección seleccionada. PostgreSQL carece de puertos publicados. FastAPI acepta el esquema reenviado únicamente desde el gateway exacto.

## Emparejamiento y reconexión

1. Inicia LAN y espera que el gateway confirme identidad y salud.
2. Abre `.civia/lan/pairing.svg` en el equipo autorizado. La alternativa textual es `.civia/lan/pairing.txt`.
3. En CIVIA Android, elige el servidor anunciado o abre el flujo de emparejamiento. Escanea el QR o ingresa su código desde el equipo autorizado.
4. Android verifica la huella SHA-256 del certificado y la identidad pública de instalación antes de abrir autenticación.
5. La reconexión intenta las direcciones anunciadas para el perfil guardado. Si cambia la IP y se renueva el anuncio, el mismo certificado permite actualizar el destino sin recompilar. Una instalación desconocida requiere otro emparejamiento.

El tipo de servicio es `_civia._tcp.local.`. Android usa DNS-SD nativo con NSD. Windows anuncia desde el anfitrión. Linux puede usar el anunciante contenedorizado con red de host si el motor propaga multicast. Docker Desktop en macOS puede requerir el QR o un nombre DNS estable. Los anuncios contienen datos públicos de protocolo, instalación y transporte. [Comprobaciones](estado.md)

## TLS para navegador y PWA

El bootstrap LAN guarda una CA local y el certificado de Nginx en `.civia/lan/`. Transfiere sólo `ca.crt` por un canal autorizado cuando un navegador deba confiar en la CA de demostración. Las claves privadas permanecen en el computador. Abre el nombre DNS que figure en el certificado o la IP inicial incluida. Puedes elegir un nombre estable mediante `-LanName` o `--lan-name` al preparar el certificado. Ese nombre debe resolver a la interfaz publicada.

Safari, Edge y Chromium requieren un origen confiable para instalar la PWA y usar cámara, micrófono y ubicación. En iOS autoriza la confianza de la CA conforme a la política del dispositivo. El QR de Android usa el certificado fijado en el perfil. Si el certificado se rota, comparte el QR nuevo mediante el canal autorizado y repite el emparejamiento.

## Firewall, diagnóstico y detención

Permite, cuando sea necesario y esté autorizado, sólo TCP en `CIVIA_HTTPS_PORT` para el perfil privado y la subred o dispositivo de evaluación. El descubrimiento requiere multicast local y puede fallar en una red de invitados, universidad o con aislamiento. En ese caso, usa QR o la dirección HTTPS de una instalación emparejada. Para una ejecución explícita sin anuncios añade `-NoDiscovery` o `--no-discovery`.

En Windows, la regla TCP debe usar `-Profile Private`, `-LocalPort` con el puerto activo, `-LocalAddress` con la IPv4 autorizada y `-RemoteAddress LocalSubnet` o una dirección más acotada. El anunciante usa la API DNS-SD de Windows. Si la política bloquea multicast, consulta al responsable de red antes de cambiar la habilitación de mDNS en UDP 5353.

Consulta `/health` y `/api/meta` desde el dispositivo. Si falla TLS, revisa DNS, nombres del certificado, CA y conectividad. ADB reverse es una alternativa de desarrollo para el mismo gateway TLS en el emulador. [Android](ANDROID_BUILD.md)

Detén la exposición con `./scripts/run.ps1 -Stop` o `./scripts/run.sh --stop`. Esto retira los contenedores del proyecto y el anuncio. El material TLS, la identidad y los volúmenes se conservan para el siguiente arranque.

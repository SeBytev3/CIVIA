import argparse
import http.client
import ipaddress
import json
import os
import re
import signal
import socket
import ssl
import subprocess
import tempfile
import threading
import uuid
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode


PRIVATE_NETWORKS = tuple(map(ipaddress.IPv4Network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")))
SERVICE_TYPE = "_civia._tcp.local."
STATE = Path("/state")


def installation_id(metadata):
    if metadata.get("protocol") != 1:
        raise ValueError("Protocolo CIVIA incompatible.")
    return uuid.UUID(metadata["installation_id"])


def private_address(value):
    address = ipaddress.IPv4Address(value)
    if not any(address in network for network in PRIVATE_NETWORKS):
        raise ValueError("La dirección LAN debe ser una IPv4 privada activa.")
    return address


def pairing_uri(identity, address, port, fingerprint):
    origin = f"https://{address}" + (f":{port}" if port != 443 else "")
    fields = {"v": 1, "id": str(identity), "origin": origin, "pin": fingerprint}
    return f"civia://pair?{urlencode(fields)}"


def hostname(value):
    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    if len(value) > 253 or not re.fullmatch(fr"{label}(?:\.{label})+", value):
        raise ValueError("Especifica un nombre DNS válido para HTTPS.")
    return value


def run_openssl(*args):
    subprocess.run(["openssl", *map(str, args)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def prepare_certificate(state, name, address):
    ca_key, ca_cert = state / "ca.key", state / "ca.crt"
    leaf_key, leaf_cert = state / "server.key", state / "server.crt"
    if all(path.is_file() for path in (ca_key, ca_cert, leaf_key, leaf_cert)):
        if (state / "tls-name").read_text().strip() != name:
            raise ValueError("Este certificado tiene otro nombre DNS. Usa el mismo nombre o rota el certificado.")
        run_openssl("x509", "-in", leaf_cert, "-checkend", "0", "-noout")
        return
    if any(path.exists() for path in (ca_key, ca_cert, leaf_key, leaf_cert)):
        raise ValueError("El material TLS está incompleto. Restaura la copia o usa un directorio nuevo.")
    with tempfile.TemporaryDirectory(dir=state) as staging:
        staging = Path(staging)
        run_openssl("req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
                    "-nodes", "-sha256", "-days", "1825", "-subj", "/CN=CIVIA Demo CA",
                    "-addext", "basicConstraints=critical,CA:true,pathlen:0",
                    "-addext", "keyUsage=critical,keyCertSign,cRLSign",
                    "-keyout", staging / "ca.key", "-out", staging / "ca.crt")
        run_openssl("req", "-new", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
                    "-subj", f"/CN={name}", "-keyout", staging / "server.key", "-out", staging / "server.csr")
        ext = staging / "extensions.cnf"
        ext.write_text(f"subjectAltName=DNS:{name},IP:{address}\n"
                       "basicConstraints=critical,CA:false\n"
                       "keyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\n")
        run_openssl("x509", "-req", "-in", staging / "server.csr", "-CA", staging / "ca.crt",
                    "-CAkey", staging / "ca.key", "-set_serial", str(uuid.uuid4().int), "-sha256", "-days", "365",
                    "-extfile", ext, "-out", staging / "server.crt")
        (staging / "tls-name").write_text(name + "\n")
        for filename in ("ca.key", "ca.crt", "server.key", "server.crt", "tls-name"):
            os.replace(staging / filename, state / filename)


def write_pairing(state, identity, address, port):
    from qrcode import make
    from qrcode.image.svg import SvgPathImage

    der = ssl.PEM_cert_to_DER_cert((state / "server.crt").read_text())
    uri = pairing_uri(identity, address, port, sha256(der).hexdigest())
    (state / "pairing.txt").write_text(uri + "\n")
    make(uri, image_factory=SvgPathImage).save(state / "pairing.svg")


class LanHttpsConnection(http.client.HTTPSConnection):
    def __init__(self, address, port, name, ca):
        super().__init__(name, port, timeout=3, context=ssl.create_default_context(cafile=str(ca)))
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def https_json(address, port, name, ca, path):
    connection = LanHttpsConnection(address, port, name, ca)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        if response.status != 200:
            return None
        body = response.read(4097)
        if len(body) > 4096:
            return None
        return json.loads(body)
    finally:
        connection.close()


def healthy(address, port, name, ca, identity):
    try:
        health = https_json(address, port, name, ca, "/health")
        if not isinstance(health, dict) or health.get("status") != "ok":
            return False
        metadata = https_json(address, port, name, ca, "/api/meta")
        return isinstance(metadata, dict) and installation_id(metadata) == identity
    except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
        return False


def announce(address, port, name, ca, identity):
    from zeroconf import IPVersion, ServiceInfo, Zeroconf

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    interface = str(address)
    info = ServiceInfo(SERVICE_TYPE, f"CIVIA - Servidor local {identity.hex[:8]}.{SERVICE_TYPE}",
                       addresses=[address.packed], port=port, server=f"{name}.",
                       properties={"v": "1", "id": str(identity), "scheme": "https"})
    zeroconf = None
    while not stop.is_set():
        try:
            if healthy(interface, port, name, ca, identity):
                if zeroconf is None:
                    zeroconf = Zeroconf(interfaces=[interface], ip_version=IPVersion.V4Only)
                    zeroconf.register_service(info)
            elif zeroconf is not None:
                zeroconf.close()
                zeroconf = None
            stop.wait(5)
        except (OSError, RuntimeError):
            if zeroconf is not None:
                zeroconf.close()
                zeroconf = None
            stop.wait(5)
    if zeroconf is not None:
        zeroconf.close()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "announce"))
    parser.add_argument("address", type=private_address)
    parser.add_argument("port", type=int, choices=range(1, 65536), metavar="PORT")
    parser.add_argument("identity", type=uuid.UUID)
    parser.add_argument("name", nargs="?")
    args = parser.parse_args()
    try:
        name_file = STATE / "tls-name"
        default_name = name_file.read_text().strip() if name_file.is_file() else f"civia-{args.identity.hex[:12]}.local"
        name = hostname(args.name or default_name)
        if args.mode == "prepare":
            prepare_certificate(STATE, name, args.address)
            write_pairing(STATE, args.identity, args.address, args.port)
            print(name)
        else:
            announce(args.address, args.port, name, STATE / "ca.crt", args.identity)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"CIVIA LAN: {error}\n")


if __name__ == "__main__":
    main()

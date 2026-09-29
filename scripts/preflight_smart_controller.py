"""Prevalidación local PE2 antes de una sesión con DJI Pilot 2."""

import json
import socket
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from ipaddress import ip_address
from cryptography import x509

ROOT = Path(__file__).resolve().parents[1]

FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5050

BASE_URL = f"http://{FLASK_HOST}:{FLASK_PORT}"

CHECKS = []

TLS_DIR = (
    ROOT
    / "diagnosticos_smart_controller"
    / "tls"
)

SERVER_CERT_FILE = (
    TLS_DIR
    / "server.pem"
)

def ok(name, detail=""):
    CHECKS.append((True, name, detail))


def fail(name, detail=""):
    CHECKS.append((False, name, detail))


def http_get(path, timeout=3):
    request = Request(
        BASE_URL + path,
        method="GET",
    )

    with urlopen(
        request,
        timeout=timeout,
    ) as response:
        return (
            response.status,
            response.read(),
        )


def http_post_json(
    path,
    payload,
    timeout=3,
):
    body = json.dumps(payload).encode(
        "utf-8"
    )

    request = Request(
        BASE_URL + path,
        data=body,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urlopen(
        request,
        timeout=timeout,
    ) as response:
        return (
            response.status,
            response.read(),
        )


def tcp_check(host, port, timeout=2):
    with socket.create_connection(
        (host, port),
        timeout=timeout,
    ):
        return True


def detect_lan_ip():
    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    try:
        sock.connect(
            ("1.1.1.1", 80)
        )

        candidate = sock.getsockname()[0]

        if (
            candidate
            and not candidate.startswith("127.")
            and not candidate.startswith("169.254.")
        ):
            return candidate

    except OSError:
        pass

    finally:
        sock.close()

    # Fallback si no existe salida a Internet.
    try:
        _, _, addresses = (
            socket.gethostbyname_ex(
                socket.gethostname()
            )
        )

        for candidate in addresses:
            if (
                not candidate.startswith("127.")
                and not candidate.startswith("169.254.")
            ):
                return candidate

    except OSError:
        pass

    return None

def certificate_ips(cert_path):
    if not cert_path.is_file():
        return []

    try:
        certificate = (
            x509.load_pem_x509_certificate(
                cert_path.read_bytes()
            )
        )

        san = (
            certificate
            .extensions
            .get_extension_for_class(
                x509.SubjectAlternativeName
            )
            .value
        )

        return [
            str(address)
            for address in san.get_values_for_type(
                x509.IPAddress
            )
        ]

    except (
        ValueError,
        x509.ExtensionNotFound,
    ):
        return []

def check_network_certificate():
    lan_ip = detect_lan_ip()

    if not lan_ip:
        fail(
            "IP LAN",
            "No fue posible determinarla",
        )
        return

    ok(
        "IP LAN",
        lan_ip,
    )

    addresses = certificate_ips(
        SERVER_CERT_FILE
    )

    if lan_ip in addresses:
        ok(
            "Certificado TLS",
            f"{lan_ip} incluida en SAN",
        )

    else:
        fail(
            "Certificado TLS",
            (
                f"{lan_ip} no incluida. "
                "Ejecutar "
                "scripts\\actualizar_certificado_mqtt.py"
            ),
        )

def check_flask():
    try:
        status, _ = http_get("/")

        if status == 200:
            ok("Flask PE2 responde")
        else:
            fail(
                "Flask PE2 responde",
                f"HTTP {status}",
            )

    except (URLError, OSError) as exc:
        fail(
            "Flask PE2 responde",
            str(exc),
        )

def check_mqtt_lan():
    lan_ip = detect_lan_ip()

    if not lan_ip:
        fail(
            "MQTT TLS LAN",
            "IP LAN desconocida",
        )
        return

    try:
        tcp_check(
            lan_ip,
            8883,
        )

        ok(
            "MQTT TLS LAN",
            f"{lan_ip}:8883",
        )

    except OSError as exc:
        fail(
            "MQTT TLS LAN",
            str(exc),
        )

def check_cloud_probe():
    try:
        status, _ = http_get("/dji-cloud")

        if status == 200:
            ok("DJI Cloud Probe responde")
        else:
            fail(
                "DJI Cloud Probe responde",
                f"HTTP {status}",
            )

    except (URLError, OSError) as exc:
        fail(
            "DJI Cloud Probe responde",
            str(exc),
        )


def check_cloud_ping():
    try:
        status, body = http_post_json(
            "/api/dji-cloud/ping",
            {
                "source":
                    "pe2-smart-controller-preflight",
                "client_request_id":
                    "preflight-local",
            },
        )

        data = json.loads(
            body.decode("utf-8")
        )

        if (
            status == 200
            and data.get("ok") is True
        ):
            ok("DJI Cloud Probe ping")
        else:
            fail(
                "DJI Cloud Probe ping",
                f"HTTP {status}",
            )

    except (
        URLError,
        OSError,
        ValueError,
    ) as exc:
        fail(
            "DJI Cloud Probe ping",
            str(exc),
        )


def check_mqtt_ports():
    for port, label in (
        (1883, "MQTT local 1883"),
        (8883, "MQTT TLS 8883"),
    ):
        try:
            tcp_check(
                "127.0.0.1",
                port,
            )

            ok(label)

        except OSError as exc:
            fail(
                label,
                str(exc),
            )


def check_receiver():
    try:
        sys.path.insert(
            0,
            str(ROOT),
        )

        from mqtt_diagnostics import (
            read_receiver_status,
        )

        status = read_receiver_status()

        if (
            status.get("state")
            == "connected"
        ):
            ok(
                "Receptor MQTT",
                "connected",
            )
        else:
            fail(
                "Receptor MQTT",
                status.get(
                    "state",
                    "unknown",
                ),
            )

    except Exception as exc:
        fail(
            "Receptor MQTT",
            str(exc),
        )


def check_files():
    ca_file = (
        ROOT
        / "diagnosticos_smart_controller"
        / "tls"
        / "ca.pem"
    )

    server_cert = (
        ROOT
        / "diagnosticos_smart_controller"
        / "tls"
        / "server.pem"
    )

    if ca_file.is_file():
        ok("CA MQTT disponible")
    else:
        fail("CA MQTT disponible")

    if server_cert.is_file():
        ok(
            "Certificado servidor MQTT"
        )
    else:
        fail(
            "Certificado servidor MQTT"
        )


def check_cloud_tracking():
    try:
        sys.path.insert(
            0,
            str(ROOT),
        )

        from dji_cloud_diagnostics import (
            read_dji_cloud_status,
        )

        status = read_dji_cloud_status()

        if status.get(
            "last_contact_at"
        ):
            ok(
                "Registro DJI Cloud",
                "contactos registrados",
            )
        else:
            ok(
                "Registro DJI Cloud",
                "habilitado, sin contactos",
            )

    except Exception as exc:
        fail(
            "Registro DJI Cloud",
            str(exc),
        )


def print_report():
    print()
    print("=" * 64)
    print(
        "PE2 - PREFLIGHT SMART CONTROLLER"
    )
    print("=" * 64)

    for success, name, detail in CHECKS:
        marker = "[OK]" if success else "[FALLO]"

        line = f"{marker:<8} {name}"

        if detail:
            line += f" | {detail}"

        print(line)

    lan_ip = detect_lan_ip()

    print()
    print(
        "IP LAN detectada:",
        lan_ip or "No determinada",
    )

    failed = [
        item
        for item in CHECKS
        if not item[0]
    ]

    print()
    print("-" * 64)

    if failed:
        print(
            "PREVALIDACION: REQUIERE REVISION"
        )
    else:
        print(
            "PREVALIDACION LOCAL: CORRECTA"
        )

    print()
    print(
        "PENDIENTE CON SMART CONTROLLER:"
    )
    print(
        "  1. Abrir DJI Cloud Probe desde Pilot 2."
    )
    print(
        "  2. Ejecutar el ping HTTP."
    )
    print(
        "  3. Verificar last_remote_addr."
    )
    print(
        "  4. Comprobar JSBridge DJI."
    )
    print(
        "  5. Confirmar disponibilidad de licencia Cloud API."
    )

    print("=" * 64)

    return not failed


def main():
    check_flask()
    check_cloud_probe()
    check_cloud_ping()
    check_mqtt_ports()
    check_receiver()
    check_files()
    check_cloud_tracking()

    check_network_certificate()
    check_mqtt_lan()

    success = print_report()

    raise SystemExit(
        0 if success else 1
    )


if __name__ == "__main__":
    main()
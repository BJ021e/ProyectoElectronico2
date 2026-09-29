import argparse
import socket
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import (
    hashes,
    serialization,
)
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import (
    ExtendedKeyUsageOID,
    NameOID,
)


ROOT = Path(__file__).resolve().parents[1]

TLS_DIR = (
    ROOT
    / "diagnosticos_smart_controller"
    / "tls"
)

CA_CERT_FILE = TLS_DIR / "ca.pem"
CA_KEY_FILE = TLS_DIR / "ca.key"

SERVER_CERT_FILE = TLS_DIR / "server.pem"
SERVER_KEY_FILE = TLS_DIR / "server.key"


def detect_lan_ip():
    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    try:
        # No necesitamos completar una conexión TCP.
        # Esto permite conocer qué interfaz usaría
        # la ruta por defecto.
        sock.connect(("1.1.1.1", 80))
        return sock.getsockname()[0]

    finally:
        sock.close()


def certificate_contains_ip(cert_path, target_ip):
    if not cert_path.is_file():
        return False

    try:
        cert = x509.load_pem_x509_certificate(
            cert_path.read_bytes()
        )

        san = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value

        addresses = san.get_values_for_type(
            x509.IPAddress
        )

        return ip_address(target_ip) in addresses

    except (
        ValueError,
        x509.ExtensionNotFound,
    ):
        return False


def load_ca():
    if not CA_CERT_FILE.is_file():
        raise RuntimeError(
            f"No existe {CA_CERT_FILE}"
        )

    if not CA_KEY_FILE.is_file():
        raise RuntimeError(
            f"No existe {CA_KEY_FILE}"
        )

    ca_cert = x509.load_pem_x509_certificate(
        CA_CERT_FILE.read_bytes()
    )

    ca_key = serialization.load_pem_private_key(
        CA_KEY_FILE.read_bytes(),
        password=None,
    )

    return ca_cert, ca_key


def regenerate_server_certificate(lan_ip):
    ca_cert, ca_key = load_ca()

    now = datetime.now(timezone.utc)

    server_key = ec.generate_private_key(
        ec.SECP256R1()
    )

    subject = x509.Name([
        x509.NameAttribute(
            NameOID.COMMON_NAME,
            "PE2 MQTT Broker",
        ),
    ])

    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(
            x509.random_serial_number()
        )
        .not_valid_before(
            now - timedelta(minutes=5)
        )
        .not_valid_after(
            now + timedelta(days=45)
        )
        .add_extension(
            x509.BasicConstraints(
                ca=False,
                path_length=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(
                    ip_address("127.0.0.1")
                ),
                x509.IPAddress(
                    ip_address(lan_ip)
                ),
            ]),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.SERVER_AUTH
            ]),
            critical=False,
        )
        .sign(
            ca_key,
            hashes.SHA256(),
        )
    )

    SERVER_KEY_FILE.write_bytes(
        server_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=(
                serialization.NoEncryption()
            ),
        )
    )

    SERVER_CERT_FILE.write_bytes(
        certificate.public_bytes(
            serialization.Encoding.PEM
        )
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--lan-ip",
        help=(
            "IP LAN manual. "
            "Si se omite, se detecta automáticamente."
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
    )

    args = parser.parse_args()

    lan_ip = (
        args.lan_ip
        or detect_lan_ip()
    )

    # Validar formato.
    ip_address(lan_ip)

    print("IP LAN detectada:", lan_ip)

    if (
        not args.force
        and certificate_contains_ip(
            SERVER_CERT_FILE,
            lan_ip,
        )
    ):
        print(
            "CERTIFICADO MQTT: YA ES VALIDO "
            "PARA ESTA IP"
        )
        return

    print(
        "La IP actual no está incluida "
        "en el certificado."
    )

    print(
        "Regenerando únicamente "
        "server.pem y server.key..."
    )

    regenerate_server_certificate(
        lan_ip
    )

    print(
        "CERTIFICADO MQTT ACTUALIZADO"
    )

    print(
        "CA conservada:",
        CA_CERT_FILE,
    )

    print(
        "Certificado:",
        SERVER_CERT_FILE,
    )


if __name__ == "__main__":
    main()
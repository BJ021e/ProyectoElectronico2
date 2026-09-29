import argparse
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
OUTPUT = (
    ROOT
    / "diagnosticos_smart_controller"
    / "tls"
)


def save_private_key(path, key):
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=(
                serialization.NoEncryption()
            ),
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lan-ip", required=True)
    args = parser.parse_args()

    lan_ip = ip_address(args.lan_ip)

    OUTPUT.mkdir(parents=True, exist_ok=True)

    # Evitar sobrescribir certificados anteriores.
    if any(OUTPUT.iterdir()):
        raise RuntimeError(
            "La carpeta TLS ya contiene archivos. "
            "Revísala antes de generar nuevos certificados."
        )

    now = datetime.now(timezone.utc)

    # CA privada, exclusiva para las pruebas PE2.
    ca_key = ec.generate_private_key(
        ec.SECP256R1()
    )

    ca_name = x509.Name([
        x509.NameAttribute(
            NameOID.COMMON_NAME,
            "PE2 MQTT Test CA",
        ),
    ])

    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(
            x509.BasicConstraints(
                ca=True,
                path_length=0,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    # Certificado del broker.
    server_key = ec.generate_private_key(
        ec.SECP256R1()
    )

    server_name = x509.Name([
        x509.NameAttribute(
            NameOID.COMMON_NAME,
            "PE2 MQTT Broker",
        ),
    ])

    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_name)
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=45))
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
                x509.IPAddress(lan_ip),
            ]),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.SERVER_AUTH
            ]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    save_private_key(
        OUTPUT / "ca.key",
        ca_key,
    )

    save_private_key(
        OUTPUT / "server.key",
        server_key,
    )

    (OUTPUT / "ca.pem").write_bytes(
        ca_cert.public_bytes(
            serialization.Encoding.PEM
        )
    )

    (OUTPUT / "server.pem").write_bytes(
        server_cert.public_bytes(
            serialization.Encoding.PEM
        )
    )

    print("CERTIFICADOS MQTT GENERADOS")
    print("IP incluida:", lan_ip)
    print("Directorio:", OUTPUT)
    print("CA:", OUTPUT / "ca.pem")
    print("Certificado:", OUTPUT / "server.pem")


if __name__ == "__main__":
    main()

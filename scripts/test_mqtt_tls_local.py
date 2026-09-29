import getpass
import ssl
import threading
import os

from pathlib import Path

import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parents[1]

CA_FILE = (
    ROOT
    / "diagnosticos_smart_controller"
    / "tls"
    / "ca.pem"
)

HOST = os.environ.get(
    "PE2_MQTT_TEST_HOST",
    "127.0.0.1",
)

PORT = 8883
TOPIC = "pe2/diagnostico/tls"

connected = threading.Event()
subscribed = threading.Event()
received = threading.Event()

errors = []


def on_connect(
    client,
    userdata,
    flags,
    reason_code,
    properties,
):
    print("Conexión MQTT:", reason_code)

    if reason_code != 0:
        errors.append(str(reason_code))
        connected.set()
        return

    connected.set()
    client.subscribe(TOPIC, qos=1)


def on_subscribe(
    client,
    userdata,
    mid,
    reason_codes,
    properties,
):
    print("Suscripción:", reason_codes)

    if any(code.is_failure for code in reason_codes):
        errors.append("Suscripción rechazada.")

    subscribed.set()


def on_message(client, userdata, message):
    print(
        "Mensaje recibido:",
        message.payload.decode("utf-8"),
    )

    if message.payload == b"PE2_MQTT_TLS_OK":
        received.set()


def main():
    password = getpass.getpass(
        "Contraseña MQTT de pe2_diag: "
    )

    # Verificar certificado y dirección IP.
    tls_context = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH,
        cafile=str(CA_FILE),
    )

    tls_context.minimum_version = (
        ssl.TLSVersion.TLSv1_2
    )

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="pe2-tls-local-test",
        protocol=mqtt.MQTTv5,
    )

    client.username_pw_set(
        "pe2_diag",
        password,
    )

    client.tls_set_context(tls_context)

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    try:
        print("Conectando mediante TLS...")

        client.connect(
            HOST,
            PORT,
            keepalive=30,
        )

        client.loop_start()

        if not connected.wait(timeout=10):
            raise RuntimeError(
                "El broker no confirmó la conexión."
            )

        if errors:
            raise RuntimeError(errors[0])

        if not subscribed.wait(timeout=10):
            raise RuntimeError(
                "No se confirmó la suscripción."
            )

        if errors:
            raise RuntimeError(errors[0])

        publication = client.publish(
            TOPIC,
            "PE2_MQTT_TLS_OK",
            qos=1,
        )

        publication.wait_for_publish(
            timeout=5
        )

        if not publication.is_published():
            raise RuntimeError(
                "No se confirmó la publicación."
            )

        if not received.wait(timeout=10):
            raise RuntimeError(
                "El mensaje TLS no fue recibido."
            )

        print(
            "DIAGNOSTICO MQTT TLS: CORRECTO"
        )

    finally:
        client.disconnect()
        client.loop_stop()

if __name__ == "__main__":
    main()

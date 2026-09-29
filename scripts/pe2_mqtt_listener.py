
import getpass
import json
import threading
import time

from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt


HOST = "127.0.0.1"
PORT = 1883

TOPIC = "pe2/diagnostico/#"

ROOT = Path(__file__).resolve().parents[1]

LOG_DIR = ROOT / "diagnosticos_smart_controller"

LOG_FILE = LOG_DIR / "mqtt_events.jsonl"

connected = threading.Event()
subscribed = threading.Event()

connection_errors = []


def timestamp():
    return datetime.now(
        timezone.utc
    ).isoformat()


def on_connect(
    client,
    userdata,
    flags,
    reason_code,
    properties,
):
    print("MQTT CONNECT:", reason_code)

    if reason_code != 0:
        connection_errors.append(str(reason_code))
        connected.set()
        return

    connected.set()

    result, _ = client.subscribe(
        TOPIC,
        qos=1,
    )

    if result != mqtt.MQTT_ERR_SUCCESS:
        connection_errors.append(
            "No fue posible solicitar la suscripción."
        )
        subscribed.set()


def on_subscribe(
    client,
    userdata,
    mid,
    reason_codes,
    properties,
):
    print("MQTT SUBSCRIBE:", reason_codes)
    subscribed.set()

EXPECTED_MESSAGES = {
    "pe2/diagnostico/local": b"PE2_MQTT_LOCAL_OK",
    "pe2/diagnostico/tls": b"PE2_MQTT_TLS_OK",
}

def on_message(client, userdata, message):
    # Solo registramos metadatos y verificamos
    # el mensaje de prueba conocido.
    # No guardamos cargas útiles desconocidas.

    event = {
        "timestamp": timestamp(),
        "topic": message.topic,
        "qos": message.qos,
        "payload_bytes": len(message.payload),
        "diagnostic_ok": (
            message.topic in EXPECTED_MESSAGES
            and message.payload == EXPECTED_MESSAGES[message.topic]
        ),
    }

    with LOG_FILE.open(
        "a",
        encoding="utf-8",
    ) as file:
        file.write(
            json.dumps(event) + "\n"
        )

    print(
        "MQTT MESSAGE:",
        json.dumps(event),
    )


def main():
    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    password = getpass.getpass(
        "Contraseña MQTT de pe2_diag: "
    )

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="pe2-diagnostic-listener",
        protocol=mqtt.MQTTv5,
    )

    client.username_pw_set(
        "pe2_diag",
        password,
    )

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    try:
        print("Conectando con Mosquitto...")

        client.connect(
            HOST,
            PORT,
            keepalive=30,
        )

        client.loop_start()

        if not connected.wait(timeout=10):
            raise RuntimeError(
                "El broker no respondió."
            )

        if connection_errors:
            raise RuntimeError(
                connection_errors[0]
            )

        if not subscribed.wait(timeout=10):
            raise RuntimeError(
                "Suscripción no confirmada."
            )

        if connection_errors:
            raise RuntimeError(
                connection_errors[0]
            )

        print("RECEPTOR PE2 LISTO")
        print("Tópico:", TOPIC)
        print("Registro:", LOG_FILE)

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nDeteniendo receptor PE2...")

    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()

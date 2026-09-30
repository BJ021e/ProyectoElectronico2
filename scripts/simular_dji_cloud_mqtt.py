"""Simulador local de mensajes MQTT compatibles con el diagnóstico DJI Cloud."""

from __future__ import annotations

import getpass
import json
import os
import threading
import time
from uuid import uuid4

import paho.mqtt.client as mqtt


HOST = os.getenv(
    "PE2_DJI_MQTT_HOST",
    "127.0.0.1",
)

PORT = int(
    os.getenv(
        "PE2_DJI_MQTT_PORT",
        "1884",
    )
)

USERNAME = os.getenv(
    "PE2_DJI_MQTT_SIM_USER",
    "pilot2_cloud",
)

GATEWAY_SN = "RC_SIMULADO_001"
AIRCRAFT_SN = "AIRCRAFT_SIMULADO_001"

STATUS_TOPIC = (
    f"sys/product/{GATEWAY_SN}/status"
)

STATUS_REPLY_TOPIC = (
    f"sys/product/{GATEWAY_SN}/status_reply"
)

STATE_TOPIC = (
    f"thing/product/{AIRCRAFT_SN}/state"
)

reply_received = threading.Event()
reply_payload = None


def now_ms():
    return int(time.time() * 1000)


def build_topology_payload():
    return {
        "tid": uuid4().hex,
        "bid": uuid4().hex,
        "timestamp": now_ms(),
        "method": "update_topo",
        "data": {
            "type": 119,
            "sub_type": 0,

            # Valores ficticios para comprobar
            # que PE2 los redacta.
            "device_secret":
                "SIMULATED_DEVICE_SECRET",

            "nonce":
                "SIMULATED_NONCE",

            "sub_devices": [
                {
                    "sn": AIRCRAFT_SN,
                    "type": 60,
                    "sub_type": 0,
                    "device_secret":
                        "SIMULATED_AIRCRAFT_SECRET",
                    "nonce":
                        "SIMULATED_AIRCRAFT_NONCE",
                }
            ],
        },
    }


def build_state_payload():
    return {
        "tid": uuid4().hex,
        "bid": uuid4().hex,
        "timestamp": now_ms(),
        "method": "property.set",
        "data": {
            "simulation": True,
            "source": "pe2-local-simulator",
        },
    }


def on_connect(
    client,
    userdata,
    flags,
    reason_code,
    properties,
):
    if reason_code.is_failure:
        print(
            "Conexión fallida:",
            reason_code,
        )
        return

    print(
        "SIMULADOR MQTT conectado:",
        reason_code,
    )

    client.subscribe(
        STATUS_REPLY_TOPIC,
        qos=1,
    )

    print(
        "Esperando ACK en:",
        STATUS_REPLY_TOPIC,
    )

def on_subscribe(
    client,
    userdata,
    mid,
    reason_codes,
    properties,
):
    topology = build_topology_payload()

    print()
    print(
        "Publicando update_topo simulado..."
    )

    info = client.publish(
        STATUS_TOPIC,
        json.dumps(
            topology,
            separators=(",", ":"),
        ),
        qos=1,
    )

    print(
        "update_topo encolado:",
        STATUS_TOPIC,
        "| mid=",
        info.mid,
    )

    state = build_state_payload()

    print()
    print(
        "Publicando state simulado..."
    )

    info = client.publish(
        STATE_TOPIC,
        json.dumps(
            state,
            separators=(",", ":"),
        ),
        qos=1,
    )

    print(
        "state encolado:",
        STATE_TOPIC,
        "| mid=",
        info.mid,
    )

def on_message(
    client,
    userdata,
    message,
):
    global reply_payload

    if message.topic != STATUS_REPLY_TOPIC:
        return

    try:
        reply_payload = json.loads(
            message.payload.decode(
                "utf-8"
            )
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        reply_payload = None

    reply_received.set()


def main():
    password = getpass.getpass(
        f"Contraseña MQTT de "
        f"{USERNAME}: "
    )

    client = mqtt.Client(
        callback_api_version=(
            mqtt.CallbackAPIVersion.VERSION2
        ),
        client_id=(
            "pe2-dji-cloud-simulator"
        ),
        protocol=mqtt.MQTTv5,
    )

    client.username_pw_set(
        USERNAME,
        password,
    )

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    print(
        f"Conectando simulador a "
        f"{HOST}:{PORT}..."
    )

    client.connect(
        HOST,
        PORT,
        keepalive=60,
    )

    client.loop_start()

    received = reply_received.wait(
        timeout=10
    )

    client.loop_stop()
    client.disconnect()

    print()
    print("=" * 64)
    print("RESULTADO SIMULADOR DJI CLOUD")
    print("=" * 64)

    if not received:
        print(
            "[FALLO] No se recibió "
            "status_reply."
        )
        raise SystemExit(1)

    print(
        "[OK] Se recibió status_reply."
    )

    print(
        json.dumps(
            reply_payload,
            indent=2,
            ensure_ascii=False,
        )
    )

    if (
        isinstance(reply_payload, dict)
        and reply_payload.get(
            "method"
        ) == "update_topo"
        and reply_payload.get(
            "data",
            {},
        ).get("result") == 0
    ):
        print()
        print(
            "SIMULACION DJI MQTT: CORRECTA"
        )
        raise SystemExit(0)

    print()
    print(
        "SIMULACION DJI MQTT: "
        "RESPUESTA INESPERADA"
    )

    raise SystemExit(1)


if __name__ == "__main__":
    main()
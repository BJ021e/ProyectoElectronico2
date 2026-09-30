"""Listener pasivo/diagnóstico para MQTT DJI Cloud API."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from dji_cloud_mqtt import (  # noqa: E402
    build_event_record,
    build_topology_reply,
)

from dji_cloud_state import (  # noqa: E402
    update_dji_cloud_state,
)

OUTPUT_DIR = (
    ROOT
    / "diagnosticos_smart_controller"
)

EVENTS_FILE = (
    OUTPUT_DIR
    / "dji_cloud_mqtt_events.jsonl"
)

STATUS_FILE = (
    OUTPUT_DIR
    / "dji_cloud_mqtt_receiver_status.json"
)


TOPICS = (
    ("sys/product/+/status", 1),
    ("thing/product/+/osd", 0),
    ("thing/product/+/state", 1),
    ("thing/product/+/events", 1),
    ("thing/product/+/requests", 1),
    (
        "thing/product/+/services_reply",
        1,
    ),
)

def utc_now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()

def write_status(state, **extra):
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "state": state,
        "last_heartbeat_at": utc_now_iso(),
        **extra,
    }

    temp = STATUS_FILE.with_suffix(
        ".json.tmp"
    )

    temp.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    os.replace(
        temp,
        STATUS_FILE,
    )

def append_event(record):
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with EVENTS_FILE.open(
        "a",
        encoding="utf-8",
    ) as file:
        file.write(
            json.dumps(
                record,
                ensure_ascii=False,
            )
            + "\n"
        )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--host",
        default=os.getenv(
            "PE2_DJI_MQTT_HOST",
            "127.0.0.1",
        ),
    )

    parser.add_argument(
        "--port",
        type=int,
        default=int(
            os.getenv(
                "PE2_DJI_MQTT_PORT",
                "1884",
            )
        ),
    )

    parser.add_argument(
        "--username",
        default=os.getenv(
            "PE2_DJI_MQTT_USER",
            "pe2_dji_reader",
        ),
    )

    parser.add_argument(
        "--ack-topology",
        action="store_true",
        help=(
            "Responder update_topo con result=0."
        ),
    )

    args = parser.parse_args()

    runtime = {
        "connected": False,
        "stopping": False,
    }

    heartbeat_stop = threading.Event()

    password = getpass.getpass(
        f"Contraseña MQTT de "
        f"{args.username}: "
    )

    client = mqtt.Client(
        callback_api_version=(
            mqtt.CallbackAPIVersion.VERSION2
        ),
        client_id="pe2-dji-cloud-listener",
        protocol=mqtt.MQTTv5,
    )

    client.username_pw_set(
        args.username,
        password,
    )

    def on_connect(
        client,
        userdata,
        flags,
        reason_code,
        properties,
    ):
        if reason_code.is_failure:
            print(
                "Conexión MQTT fallida:",
                reason_code,
            )

            write_status(
                "connection_failed",
                reason=str(reason_code),
            )

            return

        runtime["connected"] = True

        print(
            "DJI MQTT conectado:",
            reason_code,
        )

        for topic, qos in TOPICS:
            client.subscribe(
                topic,
                qos=qos,
            )

            print(
                "Suscrito:",
                topic,
            )

        write_status(
            "connected",
            broker=(
                f"{args.host}:"
                f"{args.port}"
            ),
            ack_topology=(
                args.ack_topology
            ),
        )

    def on_disconnect(
        client,
        userdata,
        disconnect_flags,
        reason_code,
        properties,
    ):
        runtime["connected"] = False

        if runtime["stopping"]:
            print(
                "DJI MQTT detenido normalmente."
            )

            write_status(
                "stopped",
                broker=(
                    f"{args.host}:"
                    f"{args.port}"
                ),
                ack_topology=(
                    args.ack_topology
                ),
            )

            return

        print(
            "DJI MQTT desconectado:",
            reason_code,
        )

        write_status(
            "disconnected",
            reason=str(reason_code),
        )

    def on_message(
        client,
        userdata,
        message,
    ):
        record = build_event_record(
            topic=message.topic,
            payload=message.payload,
            qos=message.qos,
        )

        append_event(record)

        try:
            update_dji_cloud_state(
                record
            )

        except (
            OSError,
            ValueError,
        ) as exc:
            print(
                "[DJI] No se pudo actualizar "
                "estado persistente:",
                exc,
            )

        print(
            f"[DJI] {message.topic} "
            f"| bytes="
            f"{record['payload_bytes']} "
            f"| json="
            f"{record['json_valid']}"
        )

        if not args.ack_topology:
            return

        reply = build_topology_reply(
            topic=message.topic,
            payload=message.payload,
        )

        if reply is None:
            return

        payload = json.dumps(
            reply["payload"],
            separators=(",", ":"),
        )

        info = client.publish(
            reply["topic"],
            payload,
            qos=1,
        )

        print(
            "[DJI] topology ACK:",
            reply["topic"],
            "| mid=",
            info.mid,
        )

    def heartbeat_loop():
        while not heartbeat_stop.wait(5):
            state = (
                "connected"
                if runtime["connected"]
                else "disconnected"
            )

            write_status(
                state,
                broker=(
                    f"{args.host}:"
                    f"{args.port}"
                ),
                ack_topology=(
                    args.ack_topology
                ),
            )

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    print(
        f"Conectando a "
        f"{args.host}:{args.port}..."
    )

    client.connect(
        args.host,
        args.port,
        keepalive=60,
    )

    heartbeat_thread = threading.Thread(
        target=heartbeat_loop,
        name="dji-mqtt-heartbeat",
        daemon=True,
    )

    heartbeat_thread.start()

    try:
        client.loop_forever()

    except KeyboardInterrupt:
        print()
        print("Listener DJI detenido.")

    finally:
        heartbeat_stop.set()

        runtime["connected"] = False
        runtime["stopping"] = True

        client.disconnect()

        write_status(
            "stopped",
            broker=(
                f"{args.host}:"
                f"{args.port}"
            ),
            ack_topology=(
                args.ack_topology
            ),
        )


if __name__ == "__main__":
    main()
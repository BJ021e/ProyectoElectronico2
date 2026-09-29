"""Captura antes/después de una sesión de diagnóstico con DJI Pilot 2."""

import argparse
import json
import socket
import sys

from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT_DIR = (
    ROOT
    / "diagnosticos_smart_controller"
    / "sesiones"
)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def detect_lan_ip():
    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    try:
        sock.connect(("1.1.1.1", 80))
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

    try:
        _, _, addresses = socket.gethostbyname_ex(
            socket.gethostname()
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


def collect_snapshot():
    from dji_cloud_diagnostics import (
        read_dji_cloud_status,
    )

    from mqtt_diagnostics import (
        read_mqtt_events,
        read_receiver_status,
    )

    dji_cloud = read_dji_cloud_status()
    mqtt_events = read_mqtt_events()
    mqtt_receiver = read_receiver_status()

    return {
        "captured_at": timestamp(),
        "lan_ip": detect_lan_ip(),

        "mqtt": {
            "receiver": mqtt_receiver,
            "last_event": mqtt_events.get(
                "last_event"
            ),
        },

        "dji_cloud_probe": dji_cloud,
    }


def save_snapshot(session_id, stage):
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        OUTPUT_DIR
        / f"{session_id}_{stage}.json"
    )

    data = collect_snapshot()

    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print(
        f"SNAPSHOT {stage.upper()} GUARDADO"
    )
    print("Archivo:", path)
    print("IP LAN:", data["lan_ip"])

    probe = data["dji_cloud_probe"]

    print(
        "Último contacto DJI:",
        probe.get("last_contact_at"),
    )

    print(
        "Última IP cliente DJI:",
        probe.get("last_remote_addr"),
    )

    return path, data


def load_snapshot(path):
    return json.loads(
        Path(path).read_text(
            encoding="utf-8"
        )
    )


def compare(before, after):
    old_probe = before.get(
        "dji_cloud_probe",
        {},
    )

    new_probe = after.get(
        "dji_cloud_probe",
        {},
    )

    old_contact = old_probe.get(
        "last_contact_at"
    )

    new_contact = new_probe.get(
        "last_contact_at"
    )

    old_ip = old_probe.get(
        "last_remote_addr"
    )

    new_ip = new_probe.get(
        "last_remote_addr"
    )

    contact_changed = (
        bool(new_contact)
        and new_contact != old_contact
    )

    old_agent = old_probe.get(
        "last_user_agent"
    )

    new_agent = new_probe.get(
        "last_user_agent"
    )

    print()
    print("=" * 64)
    print("COMPARACION DE SESION")
    print("=" * 64)

    print(
        "Contacto anterior:",
        old_contact,
    )

    print(
        "Contacto posterior:",
        new_contact,
    )

    print(
        "IP anterior:",
        old_ip,
    )

    print(
        "IP posterior:",
        new_ip,
    )

    print(
        "Cliente anterior:",
        old_agent,
    )

    print(
        "Cliente posterior:",
        new_agent,
    )

    print()

    if contact_changed:
        print(
            "[OK] Se registró un nuevo "
            "contacto HTTP durante la sesión."
        )
    else:
        print(
            "[PENDIENTE] No se detectó "
            "un nuevo contacto HTTP."
        )

    if (
        new_ip
        and new_ip not in (
            "127.0.0.1",
            "::1",
        )
    ):
        print(
            "[OK] El último contacto procede de una dirección no-loopback."
        )
    else:
        print(
            "[INFO] El último contacto sigue "
            "siendo local."
        )

    mqtt = after.get(
        "mqtt",
        {},
    )

    receiver = mqtt.get(
        "receiver",
        {},
    )

    print(
        "Receptor MQTT:",
        receiver.get(
            "state",
            "unknown",
        ),
    )

    print("=" * 64)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--stage",
        required=True,
        choices=[
            "before",
            "after",
        ],
    )

    parser.add_argument(
        "--session-id",
        required=True,
    )

    args = parser.parse_args()

    path, snapshot = save_snapshot(
        args.session_id,
        args.stage,
    )

    if args.stage != "after":
        return

    before_path = (
        OUTPUT_DIR
        / f"{args.session_id}_before.json"
    )

    if not before_path.is_file():
        print()
        print(
            "[AVISO] No existe snapshot BEFORE."
        )
        return

    before = load_snapshot(
        before_path
    )

    compare(
        before,
        snapshot,
    )


if __name__ == "__main__":
    main()
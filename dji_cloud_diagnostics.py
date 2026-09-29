"""Persistencia mínima de contactos HTTP de DJI Cloud Probe."""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

DEFAULT_STATUS_PATH = (
    PROJECT_ROOT
    / "diagnosticos_smart_controller"
    / "dji_cloud_status.json"
)

_WRITE_LOCK = threading.Lock()


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


def _empty_status():
    return {
        "last_contact_at": None,
        "last_event": None,
        "last_page_open_at": None,
        "last_ping_at": None,
        "last_remote_addr": None,
        "last_client_request_id": None,
        "last_user_agent": None,
    }


def read_dji_cloud_status(status_path=None):
    path = (
        Path(status_path)
        if status_path is not None
        else DEFAULT_STATUS_PATH
    )

    if not path.is_file():
        return _empty_status()

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError, TypeError):
        return _empty_status()

    result = _empty_status()

    for key in result:
        value = data.get(key)

        if value is None or isinstance(value, str):
            result[key] = value

    return result

def record_dji_cloud_contact(
    *,
    event_type,
    remote_addr,
    client_request_id=None,
    user_agent=None,
    status_path=None,
):
    if event_type not in {
        "page_open",
        "ping",
    }:
        raise ValueError(
            "Tipo de evento DJI Cloud no válido."
        )

    path = (
        Path(status_path)
        if status_path is not None
        else DEFAULT_STATUS_PATH
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with _WRITE_LOCK:
        status = read_dji_cloud_status(path)

        now = _timestamp()

        status["last_contact_at"] = now
        status["last_event"] = event_type

        if isinstance(remote_addr, str):
            status["last_remote_addr"] = (
                remote_addr[:64]
            )

        if isinstance(user_agent, str):
            status["last_user_agent"] = (
                user_agent[:300]
            )

        if event_type == "page_open":
            status["last_page_open_at"] = now

        if event_type == "ping":
            status["last_ping_at"] = now

            if client_request_id:
                status[
                    "last_client_request_id"
                ] = str(
                    client_request_id
                )[:64]

        temp_path = path.with_suffix(
            ".json.tmp"
        )

        with temp_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                status,
                file,
                ensure_ascii=False,
            )

        os.replace(
            temp_path,
            path,
        )

    return status
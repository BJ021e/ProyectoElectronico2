
import argparse
import csv
import json
import time

from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


ENDPOINTS = {
    "servidor": "/",
    "integracion": (
        "/api/drone/operation/integration-status"
    ),
    "estado_dron": "/api/drone/state",
    "contexto": "/api/drone/operation/context",
}


def now():
    return datetime.now().astimezone().isoformat(
        timespec="seconds"
    )


def check_endpoint(base_url, name, path):
    url = base_url.rstrip("/") + path
    start = time.perf_counter()

    result = {
        "timestamp": now(),
        "endpoint": name,
        "http_status": "",
        "latency_ms": "",
        "configured": "",
        "aircraft_online": "",
        "telemetry_available": "",
        "telemetry_fresh": "",
        "telemetry_age_seconds": "",
        "error": "",
    }

    try:
        with urlopen(url, timeout=4) as response:
            result["http_status"] = response.status

            if name != "servidor":
                data = json.load(response)

                for field in (
                    "configured",
                    "aircraft_online",
                    "telemetry_available",
                    "telemetry_fresh",
                    "telemetry_age_seconds",
                ):
                    if field in data:
                        result[field] = data[field]

    except HTTPError as exc:
        result["http_status"] = exc.code
        result["error"] = f"HTTP {exc.code}"

    except URLError as exc:
        result["error"] = (
            f"Error de conexión: {exc.reason}"
        )

    except Exception as exc:
        result["error"] = (
            f"{type(exc).__name__}: {exc}"
        )

    finally:
        result["latency_ms"] = round(
            (time.perf_counter() - start) * 1000,
            1,
        )

    return result


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--base-url",
        required=True,
    )

    parser.add_argument(
        "--duration",
        type=int,
        default=300,
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=3,
    )

    args = parser.parse_args()

    output_dir = Path(
        "diagnosticos_smart_controller"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = output_dir / "peticiones.csv"

    fields = [
        "timestamp",
        "endpoint",
        "http_status",
        "latency_ms",
        "configured",
        "aircraft_online",
        "telemetry_available",
        "telemetry_fresh",
        "telemetry_age_seconds",
        "error",
    ]

    print("Iniciando diagnóstico...")
    print("Servidor:", args.base_url)
    print("Registro:", output_file)

    end_time = time.monotonic() + args.duration

    with output_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fields,
        )

        writer.writeheader()

        try:
            while time.monotonic() < end_time:
                for name, path in ENDPOINTS.items():
                    result = check_endpoint(
                        args.base_url,
                        name,
                        path,
                    )

                    writer.writerow(result)
                    file.flush()

                    print(
                        result["timestamp"],
                        name,
                        result["http_status"],
                        result["latency_ms"],
                        result["error"],
                    )

                time.sleep(args.interval)

        except KeyboardInterrupt:
            print("\nDiagnóstico interrumpido.")

    print("Registro guardado:", output_file)


if __name__ == "__main__":
    main()

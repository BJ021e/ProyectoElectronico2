from __future__ import annotations

import importlib
import os
import sqlite3
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEPENDENCIES = ("rasterio", "numpy", "flask", "sqlalchemy")


def _project_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _sqlite_database_path(database_url: str) -> Path | None:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return None
    return _project_path(database_url[len(prefix):])


def _check_directory(path: Path) -> tuple[bool, str]:
    if not path.is_dir():
        return False, f"NO EXISTE: {path}"
    if not os.access(path, os.R_OK):
        return False, f"SIN LECTURA: {path}"

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path,
            prefix="preflight_",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
        return True, str(path)
    except OSError as exc:
        return False, f"SIN ESCRITURA: {path} ({exc})"
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass


def _check_sqlite_database(database_url: str) -> tuple[bool, str]:
    path = _sqlite_database_path(database_url)
    if path is None:
        return False, "DATABASE_URL no usa SQLite."
    if not path.is_file():
        return False, f"NO EXISTE: {path}"

    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            connection.execute("SELECT 1").fetchone()
    except sqlite3.Error as exc:
        return False, f"NO ACCESIBLE: {path} ({exc})"
    return True, str(path)


def _check_dependency(module_name: str) -> tuple[bool, str]:
    try:
        importlib.import_module(module_name)
    except Exception as exc:
        return False, str(exc)
    try:
        return True, version(module_name)
    except PackageNotFoundError:
        return True, "importado"


def _record(
    report: dict[str, Any],
    label: str,
    status: str,
    detail: str,
) -> None:
    report["checks"].append({
        "label": label,
        "status": status,
        "detail": detail,
    })


def run_preflight(
    *,
    config: Any,
    backend_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Evalúa el entorno sin inicializar la base de datos ni modificar datos."""
    report: dict[str, Any] = {"checks": []}
    viewing_ok = True

    _record(
        report,
        "Python",
        "OK",
        sys.version.split()[0],
    )

    debug_disabled = not bool(config.FLASK_DEBUG)
    _record(
        report,
        "Flask debug",
        "OK" if debug_disabled else "INFO",
        "deshabilitado" if debug_disabled else "habilitado; no es apto para procesamiento largo",
    )

    for dependency in DEPENDENCIES:
        ok, detail = _check_dependency(dependency)
        viewing_ok &= ok
        _record(report, dependency.capitalize(), "OK" if ok else "ERROR", detail)

    database_ok, database_detail = _check_sqlite_database(config.DATABASE_URL)
    viewing_ok &= database_ok
    _record(report, "Database", "OK" if database_ok else "ERROR", database_detail)

    storage_ok, storage_detail = _check_directory(
        _project_path(config.CAMPAIGN_STORAGE_ROOT)
    )
    viewing_ok &= storage_ok
    _record(report, "Campaign storage", "OK" if storage_ok else "ERROR", storage_detail)

    staging_ok, staging_detail = _check_directory(
        _project_path(config.RED_EDGE_STAGING_ROOT)
    )
    _record(report, "RedEdge staging", "OK" if staging_ok else "ERROR", staging_detail)

    temp_ok, temp_detail = _check_directory(Path(tempfile.gettempdir()))
    viewing_ok &= temp_ok
    _record(report, "TEMP/TMP", "OK" if temp_ok else "ERROR", temp_detail)

    backend_name = str(config.PHOTOGRAMMETRY_BACKEND).strip().upper()
    processing_enabled = bool(config.PROCESSING_ENABLED)
    _record(
        report,
        "Processing guard",
        "OK" if processing_enabled else "INFO",
        "habilitado" if processing_enabled else "procesamiento deshabilitado intencionalmente",
    )

    metashape_ok = False
    if not processing_enabled:
        _record(
            report,
            "Photogrammetry backend",
            "INFO",
            f"configurado como {backend_name or 'VACÍO'}; no se evalúa en modo visualización",
        )
        _record(
            report,
            "Metashape executable",
            "SKIP",
            "no se comprueba porque el procesamiento está deshabilitado",
        )
    elif backend_name != "METASHAPE":
        _record(
            report,
            "Photogrammetry backend",
            "ERROR",
            f"configurado como {backend_name or 'VACÍO'}; se requiere METASHAPE",
        )
        _record(
            report,
            "Metashape executable",
            "SKIP",
            "no se comprueba porque PHOTOGRAMMETRY_BACKEND no es METASHAPE",
        )
    elif not str(config.METASHAPE_EXECUTABLE).strip():
        _record(report, "Photogrammetry backend", "OK", "METASHAPE")
        _record(report, "Metashape executable", "ERROR", "METASHAPE_EXECUTABLE no está definido")
    else:
        executable = Path(str(config.METASHAPE_EXECUTABLE)).expanduser()
        executable_exists = executable.is_file()
        _record(report, "Photogrammetry backend", "OK", "METASHAPE")
        _record(report, "Metashape executable", "OK" if executable_exists else "ERROR", str(executable))
        if executable_exists:
            try:
                if backend_factory is None:
                    from services.photogrammetry_backend_factory import PhotogrammetryBackendFactory
                    backend_factory = PhotogrammetryBackendFactory.create
                metashape_ok = bool(backend_factory().is_available())
                _record(report, "Metashape availability", "OK" if metashape_ok else "ERROR", "--version respondió correctamente" if metashape_ok else "el backend no está disponible")
            except Exception as exc:
                _record(report, "Metashape availability", "ERROR", str(exc))

    report["ready_for_viewing"] = bool(viewing_ok)
    report["ready_for_processing"] = bool(
        viewing_ok
        and processing_enabled
        and debug_disabled
        and backend_name == "METASHAPE"
        and metashape_ok
    )
    return report


def print_report(report: dict[str, Any]) -> None:
    width = max(len(check["label"]) for check in report["checks"])
    for check in report["checks"]:
        print(f"{check['label']:<{width}} {check['status']:<5} {check['detail']}")
    print()
    print(f"READY_FOR_VIEWING    {'YES' if report['ready_for_viewing'] else 'NO'}")
    print(f"READY_FOR_PROCESSING {'YES' if report['ready_for_processing'] else 'NO'}")


def main() -> int:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from config import Config

    report = run_preflight(config=Config)
    print_report(report)
    return 0 if report["ready_for_viewing"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

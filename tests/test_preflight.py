from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

from config import Config, env_bool
from scripts import preflight


class DemoConfig:
    PHOTOGRAMMETRY_BACKEND = "METASHAPE"
    PROCESSING_ENABLED = True
    FLASK_DEBUG = False
    METASHAPE_EXECUTABLE = ""


def create_demo_config(tmp_path: Path) -> type[DemoConfig]:
    database_path = tmp_path / "ground_control.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE marker (id INTEGER PRIMARY KEY)")

    storage = tmp_path / "campaigns"
    staging = tmp_path / "staging"
    storage.mkdir()
    staging.mkdir()

    class ConfigForTest(DemoConfig):
        DATABASE_URL = f"sqlite:///{database_path.as_posix()}"
        CAMPAIGN_STORAGE_ROOT = str(storage)
        RED_EDGE_STAGING_ROOT = str(staging)

    return ConfigForTest


def test_env_bool_and_config_default_keep_debug_disabled():
    assert env_bool("UNSET_PREFLIGHT_BOOLEAN", False) is False

    source = inspect.getsource(Config)
    assert '"FLASK_DEBUG",\n        False' in source
    assert '"PE2_DEMO_MODE",\n        False' in source


def test_preflight_is_ready_for_viewing_without_metashape(tmp_path):
    config = create_demo_config(tmp_path)

    report = preflight.run_preflight(config=config)

    assert report["ready_for_viewing"] is True
    assert report["ready_for_processing"] is False
    assert any(
        check["label"] == "Metashape executable"
        and check["status"] == "ERROR"
        for check in report["checks"]
    )


def test_preflight_accepts_available_simulated_metashape_backend(tmp_path):
    config = create_demo_config(tmp_path)
    executable = tmp_path / "metashape.exe"
    executable.write_text("simulated", encoding="utf-8")
    config.METASHAPE_EXECUTABLE = str(executable)

    class AvailableBackend:
        def is_available(self):
            return True

    report = preflight.run_preflight(
        config=config,
        backend_factory=AvailableBackend,
    )

    assert report["ready_for_viewing"] is True
    assert report["ready_for_processing"] is True


def test_preflight_processing_guard_does_not_block_viewing(tmp_path):
    config = create_demo_config(tmp_path)
    config.PROCESSING_ENABLED = False
    config.PHOTOGRAMMETRY_BACKEND = "MOCK"

    report = preflight.run_preflight(config=config)

    assert report["ready_for_viewing"] is True
    assert report["ready_for_processing"] is False
    checks = {check["label"]: check for check in report["checks"]}
    assert checks["Processing guard"]["status"] == "INFO"
    assert checks["Photogrammetry backend"]["status"] == "INFO"
    assert checks["Metashape executable"]["status"] == "SKIP"


def test_preflight_reports_mock_as_processing_error_when_enabled(tmp_path):
    config = create_demo_config(tmp_path)
    config.PHOTOGRAMMETRY_BACKEND = "MOCK"

    report = preflight.run_preflight(config=config)

    assert report["ready_for_viewing"] is True
    assert report["ready_for_processing"] is False
    checks = {check["label"]: check for check in report["checks"]}
    assert checks["Photogrammetry backend"]["status"] == "ERROR"
    assert checks["Metashape executable"]["status"] == "SKIP"

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from geospatial.processing_types import (
    PhotogrammetryRequest,
    ProcessingResult,
)


class MetashapeBackendError(
    Exception
):
    """
    Error de integración con Agisoft Metashape.
    """

    pass


class MetashapeBackend:

    def __init__(
        self,
        *,
        executable_path: str,
        worker_script: str | None = None,
    ):

        self._executable_path = (
            Path(
                executable_path
            )
            .expanduser()
        )

        if worker_script is None:

            worker_script = str(
                Path(__file__)
                .with_name(
                    "metashape_worker.py"
                )
            )

        self._worker_script = (
            Path(
                worker_script
            )
            .expanduser()
            .resolve()
        )

    @property
    def name(self) -> str:
        return "METASHAPE"

    @property
    def executable_path(
        self,
    ) -> Path:

        return (
            self._executable_path
        )

    @property
    def worker_script(
        self,
    ) -> Path:

        return (
            self._worker_script
        )

    def is_available(
        self,
    ) -> bool:

        if (
            not self._executable_path
            .is_file()
        ):

            return False

        if (
            not self._worker_script
            .is_file()
        ):

            return False

        try:

            completed = (
                subprocess.run(
                    [
                        str(
                            self._executable_path
                        ),
                        "--version",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
            )

        except (
            OSError,
            subprocess.SubprocessError,
        ):

            return False

        return (
            completed.returncode
            == 0
        )

    def _run_worker(
        self,
        *,
        manifest_path: Path,
        result_path: Path,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess:

        command = [
            str(
                self._executable_path
            ),
            "-r",
            str(
                self._worker_script
            ),
            str(
                manifest_path
            ),
            str(
                result_path
            ),
        ]

        try:

            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )

        except (
            OSError,
            subprocess.SubprocessError,
        ) as exc:

            raise MetashapeBackendError(
                "No fue posible ejecutar "
                f"Metashape: {exc}"
            ) from exc

    def probe(
        self,
    ) -> dict:

        if not self.is_available():

            raise MetashapeBackendError(
                "Metashape no está disponible "
                "o su configuración no es válida."
            )

        with tempfile.TemporaryDirectory(
            prefix="metashape_probe_"
        ) as temp_dir:

            workspace = Path(
                temp_dir
            )

            manifest_path = (
                workspace
                / "manifest.json"
            )

            result_path = (
                workspace
                / "result.json"
            )

            manifest = {
                "mode": "probe",
            }

            manifest_path.write_text(
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            completed = (
                self._run_worker(
                    manifest_path=(
                        manifest_path
                    ),
                    result_path=(
                        result_path
                    ),
                    timeout_seconds=60,
                )
            )

            if (
                completed.returncode
                != 0
            ):

                raise MetashapeBackendError(
                    "Metashape terminó con "
                    f"código "
                    f"{completed.returncode}. "
                    f"stderr: "
                    f"{completed.stderr.strip()}"
                )

            if (
                not result_path
                .is_file()
            ):

                raise MetashapeBackendError(
                    "Metashape finalizó sin "
                    "generar result.json."
                )

            try:

                result = json.loads(
                    result_path.read_text(
                        encoding="utf-8"
                    )
                )

            except (
                OSError,
                json.JSONDecodeError,
            ) as exc:

                raise MetashapeBackendError(
                    "El resultado devuelto "
                    "por Metashape no es válido."
                ) from exc

            if (
                result.get(
                    "success"
                )
                is not True
            ):

                raise MetashapeBackendError(
                    result.get(
                        "error_message"
                    )
                    or (
                        "Metashape informó "
                        "un error."
                    )
                )

            return result

    def process(
        self,
        request: PhotogrammetryRequest,
    ) -> ProcessingResult:

        raise MetashapeBackendError(
            "El backend Metashape está "
            "conectado, pero el procesamiento "
            "fotogramétrico real todavía no "
            "ha sido habilitado."
        )
        
    def inspect_inputs(
        self,
        request: PhotogrammetryRequest,
    ) -> dict:

        if not self.is_available():

            raise MetashapeBackendError(
                "Metashape no está disponible."
            )

        if not request.capture_groups:

            raise MetashapeBackendError(
                "La solicitud no contiene "
                "grupos de captura explícitos."
            )

        output_dir = (
            Path(
                request.output_dir
            )
            .expanduser()
            .resolve()
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        manifest_path = (
            output_dir
            / "metashape_manifest.json"
        )

        result_path = (
            output_dir
            / "metashape_inspection.json"
        )

        manifest = {
            "mode": "inspect_inputs",
            "campaign_id": (
                request.campaign_id
            ),
            "sensor_type": (
                request.sensor_type.value
            ),
            "input_files": list(
                request.input_files
            ),
            "capture_groups": [
                {
                    "capture_code": (
                        group.capture_code
                    ),
                    "assets": [
                        {
                            "band": (
                                asset.band
                            ),
                            "path": (
                                asset.path
                            ),
                        }
                        for asset
                        in group.assets
                    ],
                }
                for group
                in request.capture_groups
            ],
        }

        manifest_path.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        completed = self._run_worker(
            manifest_path=manifest_path,
            result_path=result_path,
            timeout_seconds=120,
        )

        if completed.returncode != 0:

            raise MetashapeBackendError(
                "Metashape no pudo inspeccionar "
                "las entradas. "
                f"Código={completed.returncode}. "
                f"stderr={completed.stderr.strip()}"
            )

        if not result_path.is_file():

            raise MetashapeBackendError(
                "Metashape terminó sin generar "
                "el resultado de inspección."
            )

        result = json.loads(
            result_path.read_text(
                encoding="utf-8"
            )
        )

        if result.get("success") is not True:

            raise MetashapeBackendError(
                result.get(
                    "error_message"
                )
                or (
                    "Metashape reportó un "
                    "error de inspección."
                )
            )

        return result
    
    def align_inputs(
        self,
        request: PhotogrammetryRequest,
    ) -> dict:

        if not self.is_available():

            raise MetashapeBackendError(
                "Metashape no está disponible."
            )

        if not request.capture_groups:

            raise MetashapeBackendError(
                "La solicitud no contiene "
                "grupos de captura explícitos."
            )

        output_dir = (
            Path(
                request.output_dir
            )
            .expanduser()
            .resolve()
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        manifest_path = (
            output_dir
            / "metashape_alignment_manifest.json"
        )

        result_path = (
            output_dir
            / "metashape_alignment_result.json"
        )

        manifest = {
            "mode": "align_inputs",
            "campaign_id": (
                request.campaign_id
            ),
            "sensor_type": (
                request.sensor_type.value
            ),
            "input_files": list(
                request.input_files
            ),
            "capture_groups": [
                {
                    "capture_code": (
                        group.capture_code
                    ),
                    "assets": [
                        {
                            "band": (
                                asset.band
                            ),
                            "path": (
                                asset.path
                            ),
                        }
                        for asset
                        in group.assets
                    ],
                }
                for group
                in request.capture_groups
            ],
        }

        manifest_path.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        completed = self._run_worker(
            manifest_path=manifest_path,
            result_path=result_path,
            timeout_seconds=600,
        )

        if completed.returncode != 0:

            raise MetashapeBackendError(
                "Metashape falló durante "
                "matching/alineamiento. "
                f"Código={completed.returncode}. "
                f"stdout={completed.stdout.strip()} "
                f"stderr={completed.stderr.strip()}"
            )

        if not result_path.is_file():

            raise MetashapeBackendError(
                "Metashape terminó sin generar "
                "el resultado de alineamiento."
            )

        result = json.loads(
            result_path.read_text(
                encoding="utf-8"
            )
        )

        if result.get("success") is not True:

            raise MetashapeBackendError(
                result.get(
                    "error_message"
                )
                or (
                    "Metashape reportó un "
                    "error de alineamiento."
                )
            )

        return result
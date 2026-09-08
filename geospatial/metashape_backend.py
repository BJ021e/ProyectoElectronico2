from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import rasterio

from geospatial.processing_types import (
    GeneratedRasterProduct,
    GeospatialProductType,
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

        if not self.is_available():

            raise MetashapeBackendError(
                "Metashape no está "
                "disponible."
            )

        if not request.capture_groups:

            raise MetashapeBackendError(
                "La solicitud no contiene "
                "grupos de captura "
                "explícitos."
            )

        output_dir = Path(
            request.output_dir
        ).expanduser().resolve()

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        manifest_path = (
            output_dir
            / "metashape_process_manifest.json"
        )

        result_path = (
            output_dir
            / "metashape_process_result.json"
        )

        canonical_orthomosaic_path = (
            output_dir
            / (
                "metashape_orthomosaic_"
                "multispectral.tif"
            )
        )

        manifest = {
            "mode": "process",
            "campaign_id": (
                request.campaign_id
            ),
            "sensor_type": (
                request.sensor_type.value
            ),
            "output_dir": str(
                output_dir
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
                            "band": asset.band,
                            "path": asset.path,
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

            #
            # La reconstrucción densa puede
            # tardar horas. No usar el timeout
            # de los probes.
            #
            timeout_seconds=43200,
        )

        if completed.returncode != 0:

            raise MetashapeBackendError(
                "Metashape falló durante "
                "el procesamiento "
                "fotogramétrico. "
                f"Código="
                f"{completed.returncode}. "
                f"stdout="
                f"{completed.stdout.strip()} "
                f"stderr="
                f"{completed.stderr.strip()}"
            )

        if not result_path.is_file():

            raise MetashapeBackendError(
                "Metashape terminó sin "
                "generar el resultado del "
                "procesamiento."
            )

        result = json.loads(
            result_path.read_text(
                encoding="utf-8"
            )
        )

        if result.get(
            "success"
        ) is not True:

            raise MetashapeBackendError(
                result.get(
                    "error_message"
                )
                or (
                    "Metashape reportó "
                    "un procesamiento fallido."
                )
            )

        if result.get(
            "mode"
        ) != "process":

            raise MetashapeBackendError(
                "El worker Metashape devolvió "
                "un modo inesperado."
            )

        dsm_path = Path(
            result.get(
                "dsm_path",
                "",
            )
        ).expanduser().resolve()

        native_orthomosaic_path = Path(
            result.get(
                "orthomosaic_native_path",
                "",
            )
        ).expanduser().resolve()

        if not dsm_path.is_file():

            raise MetashapeBackendError(
                "Metashape no devolvió "
                "un DSM GeoTIFF."
            )

        if not native_orthomosaic_path.is_file():

            raise MetashapeBackendError(
                "Metashape no devolvió "
                "un ortomosaico "
                "multiespectral."
            )

        self._normalize_multispectral_raster(
            source_path=(
                native_orthomosaic_path
            ),
            destination_path=(
                canonical_orthomosaic_path
            ),
            band_mapping=(
                result.get(
                    "band_mapping"
                )
                or {}
            ),
        )

        if not canonical_orthomosaic_path.is_file():

            raise MetashapeBackendError(
                "No se generó el "
                "ortomosaico canónico PE2."
            )

        products = (
            GeneratedRasterProduct(
                product_type=(
                    GeospatialProductType.DSM
                ),
                name=(
                    "DSM Metashape"
                ),
                path=str(
                    dsm_path
                ),
            ),
            GeneratedRasterProduct(
                product_type=(
                    GeospatialProductType
                    .ORTHOMOSAIC_MULTISPECTRAL
                ),
                name=(
                    "Ortomosaico "
                    "Multiespectral Metashape"
                ),
                path=str(
                    canonical_orthomosaic_path
                ),
            ),
        )

        return ProcessingResult(
            backend=self.name,
            success=True,
            products=products,
            error_message=None,
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
            timeout_seconds=3600,
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

    def inspect_reflectance(
        self,
        request: PhotogrammetryRequest,
        *,
        perform_calibration: bool = False,
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
            Path(request.output_dir)
            .expanduser()
            .resolve()
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        manifest_path = (
            output_dir
            / "metashape_reflectance_manifest.json"
        )

        result_path = (
            output_dir
            / "metashape_reflectance_result.json"
        )

        manifest = {
            "mode": "inspect_reflectance",
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
                            "band": asset.band,
                            "path": asset.path,
                        }
                        for asset
                        in group.assets
                    ],
                }
                for group
                in request.capture_groups
            ],

            "perform_calibration": (
                perform_calibration
            ),
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
                "la detección de paneles. "
                f"Código={completed.returncode}. "
                f"stdout={completed.stdout.strip()} "
                f"stderr={completed.stderr.strip()}"
            )

        if not result_path.is_file():

            raise MetashapeBackendError(
                "Metashape terminó sin generar "
                "el resultado de reflectancia."
            )

        result = json.loads(
            result_path.read_text(
                encoding="utf-8"
            )
        )

        if result.get("success") is not True:

            raise MetashapeBackendError(
                result.get("error_message")
                or (
                    "Metashape reportó un error "
                    "detectando paneles."
                )
            )

        return result

    def calibrate_reflectance(
        self,
        request: PhotogrammetryRequest,
    ) -> dict:

        return self.inspect_reflectance(
            request,
            perform_calibration=True,
        )

    @staticmethod
    def _normalize_multispectral_raster(
        *,
        source_path: Path,
        destination_path: Path,
        band_mapping: dict,
    ) -> None:

        canonical_order = (
            band_mapping.get(
                "canonical_order"
            )
            or []
        )

        layer_by_band = (
            band_mapping.get(
                "metashape_layer_by_band"
            )
            or {}
        )

        expected_order = [
            "BLUE",
            "GREEN",
            "RED",
            "NIR",
            "RED_EDGE",
        ]

        if canonical_order != expected_order:

            raise MetashapeBackendError(
                "El orden canónico informado "
                "por Metashape no coincide "
                "con el contrato PE2."
            )

        missing = [
            band
            for band in expected_order
            if band not in layer_by_band
        ]

        if missing:

            raise MetashapeBackendError(
                "Faltan bandas en el "
                "mapeo Metashape: "
                f"{missing}"
            )

        #
        # layer_index de Metashape es
        # zero-based.
        # Rasterio es one-based.
        #
        source_band_indexes = [
            int(
                layer_by_band[band]
            )
            + 1
            for band in expected_order
        ]

        if destination_path.exists():

            raise MetashapeBackendError(
                "El ortomosaico canónico "
                "ya existe: "
                f"{destination_path}"
            )

        try:

            with rasterio.open(
                source_path
            ) as src:

                if src.count != 5:

                    raise (
                        MetashapeBackendError(
                            "El ortomosaico "
                            "Metashape debe "
                            "contener exactamente "
                            "5 bandas; se "
                            f"detectaron {src.count}."
                        )
                    )

                if not src.crs:

                    raise (
                        MetashapeBackendError(
                            "El ortomosaico "
                            "Metashape no posee CRS."
                        )
                    )

                profile = (
                    src.profile.copy()
                )

                #
                # Metashape exporta el exterior del
                # ortomosaico multiespectral uint16
                # con 65535 en las cinco bandas.
                #
                # PE2 lo declara explícitamente como
                # NoData para que Rasterio y los
                # índices espectrales lo excluyan.
                #
                profile.update(
                    count=5,
                    nodata=65535,
                )

                with rasterio.open(
                    destination_path,
                    "w",
                    **profile,
                ) as dst:

                    #
                    # Copia por ventanas para no
                    # cargar una banda aérea
                    # completa en RAM.
                    #
                    for (
                        destination_band,
                        source_band,
                        canonical_band,
                    ) in zip(
                        range(1, 6),
                        source_band_indexes,
                        expected_order,
                    ):

                        for (
                            _,
                            window,
                        ) in src.block_windows(
                            source_band
                        ):

                            data = src.read(
                                source_band,
                                window=window,
                            )

                            dst.write(
                                data,
                                destination_band,
                                window=window,
                            )

                        dst.set_band_description(
                            destination_band,
                            canonical_band,
                        )

                        source_tags = (
                            src.tags(
                                source_band
                            )
                        )

                        if source_tags:

                            dst.update_tags(
                                destination_band,
                                **source_tags,
                            )

                    dataset_tags = (
                        src.tags()
                    )

                    if dataset_tags:
                        dst.update_tags(
                            **dataset_tags
                        )

                    #
                    # Mantener escalas/offsets
                    # cuando Rasterio/GeoTIFF
                    # los exponga.
                    #
                    try:

                        dst.scales = tuple(
                            src.scales[
                                index - 1
                            ]
                            for index
                            in source_band_indexes
                        )

                    except Exception:
                        pass

                    try:

                        dst.offsets = tuple(
                            src.offsets[
                                index - 1
                            ]
                            for index
                            in source_band_indexes
                        )

                    except Exception:
                        pass

        except MetashapeBackendError:
            raise

        except Exception as exc:

            if destination_path.exists():
                destination_path.unlink()

            raise MetashapeBackendError(
                "No fue posible normalizar "
                "el ortomosaico "
                f"multiespectral: {exc}"
            ) from exc
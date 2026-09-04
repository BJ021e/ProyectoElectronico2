from __future__ import annotations

import re
from pathlib import Path

from models import ImageBand

from services.campaign_service import (
    CampaignService,
)
from services.capture_service import (
    CaptureService,
)
from services.image_ingestion_service import (
    ImageIngestionService,
)

from services.micasense_metadata_service import (
    MicaSenseMetadataError,
    MicaSenseMetadataService,
)

class RedEdgeImportError(Exception):
    """
    Error producido durante la inspección o importación
    de una carpeta RedEdge.
    """
    pass


class InvalidRedEdgeFolderError(RedEdgeImportError):
    """
    La carpeta suministrada no existe o contiene una
    estructura RedEdge ambigua.
    """
    pass

class InvalidRedEdgeCampaignError(
    RedEdgeImportError
):
    """
    La campaña indicada no existe o no corresponde
    a un sensor multiespectral.
    """
    pass


class IncompleteRedEdgeFolderError(
    RedEdgeImportError
):
    """
    La carpeta contiene una o más capturas
    multiespectrales incompletas.
    """
    pass


class RedEdgeImportExecutionError(
    RedEdgeImportError
):
    """
    La carpeta era estructuralmente importable,
    pero ocurrió un error durante la ingestión.
    """
    pass

class RedEdgeImportService:

    BAND_BY_INDEX = {
        1: ImageBand.BLUE,
        2: ImageBand.GREEN,
        3: ImageBand.RED,
        4: ImageBand.NIR,
        5: ImageBand.RED_EDGE,
    }

    EXPECTED_BANDS = (
        ImageBand.BLUE,
        ImageBand.GREEN,
        ImageBand.RED,
        ImageBand.NIR,
        ImageBand.RED_EDGE,
    )

    FILE_PATTERN = re.compile(
        r"^(?P<base>.+)_(?P<band>[1-5])"
        r"\.(?P<extension>tif|tiff)$",
        re.IGNORECASE,
    )

    @classmethod
    def inspect_folder(
        cls,
        source_dir: str | Path,
    ) -> dict:

        source = Path(
            source_dir
        ).expanduser().resolve()

        if not source.exists():
            raise InvalidRedEdgeFolderError(
                f"La carpeta no existe: {source}"
            )

        if not source.is_dir():
            raise InvalidRedEdgeFolderError(
                f"La ruta no corresponde "
                f"a una carpeta: {source}"
            )

        groups: dict[str, dict] = {}
        ignored_files: list[str] = []

        files = sorted(
            (
                path
                for path in source.rglob("*")
                if path.is_file()
            ),
            key=lambda path: (
                path.as_posix().lower()
            ),
        )

        for file_path in files:

            match = cls.FILE_PATTERN.match(
                file_path.name
            )

            relative_path = (
                file_path.relative_to(
                    source
                )
            )

            if match is None:
                ignored_files.append(
                    relative_path.as_posix()
                )
                continue

            base_name = match.group(
                "base"
            )

            band_index = int(
                match.group(
                    "band"
                )
            )

            band = cls.BAND_BY_INDEX[
                band_index
            ]

            relative_parent = (
                relative_path.parent
            )

            if str(relative_parent) == ".":
                source_key = base_name
                relative_directory = ""
            else:
                source_key = (
                    relative_parent
                    / base_name
                ).as_posix()

                relative_directory = (
                    relative_parent.as_posix()
                )

            group = groups.setdefault(
                source_key,
                {
                    "source_key": source_key,
                    "base_name": base_name,
                    "relative_directory": (
                        relative_directory
                    ),
                    "files": {},
                },
            )

            if band.value in group["files"]:
                raise InvalidRedEdgeFolderError(
                    "Se detectaron dos archivos "
                    f"para la banda {band.value} "
                    f"del grupo {source_key}."
                )

            group["files"][
                band.value
            ] = str(
                file_path
            )

        result_groups = []

        for source_key in sorted(
            groups.keys()
        ):

            group = groups[
                source_key
            ]

            present = [
                band.value
                for band in cls.EXPECTED_BANDS
                if band.value
                in group["files"]
            ]

            missing = [
                band.value
                for band in cls.EXPECTED_BANDS
                if band.value
                not in group["files"]
            ]

            result_groups.append(
                {
                    **group,
                    "present_bands": present,
                    "missing_bands": missing,
                    "is_complete": (
                        len(missing) == 0
                    ),
                }
            )

        complete_count = sum(
            1
            for group in result_groups
            if group["is_complete"]
        )

        return {
            "source_dir": str(source),
            "group_count": len(
                result_groups
            ),
            "complete_count": (
                complete_count
            ),
            "incomplete_count": (
                len(result_groups)
                - complete_count
            ),
            "ignored_files": (
                ignored_files
            ),
            "groups": result_groups,
        }
        
    @classmethod
    def import_folder(
        cls,
        *,
        campaign_id: int,
        source_dir: str | Path,
        skip_incomplete: bool = False,
    ) -> dict:
        """
        Importa automáticamente los grupos RedEdge
        encontrados dentro de una carpeta.

        Por defecto la operación es estricta:
        si existe alguna captura incompleta, no se
        importa ninguna.

        Con skip_incomplete=True se importan únicamente
        los grupos completos y se reportan los demás.
        """

        campaign = CampaignService.get_campaign(
            campaign_id
        )

        if campaign is None:
            raise InvalidRedEdgeCampaignError(
                f"La campaña con ID "
                f"{campaign_id} no existe."
            )

        if (
            campaign["sensor_type"]
            != "MULTISPECTRAL"
        ):
            raise InvalidRedEdgeCampaignError(
                "La importación RedEdge requiere "
                "una campaña MULTISPECTRAL."
            )

        inspection = cls.inspect_folder(
            source_dir
        )

        if inspection["group_count"] == 0:
            raise InvalidRedEdgeFolderError(
                "No se detectaron capturas "
                "RedEdge en la carpeta."
            )

        incomplete_groups = [
            group
            for group in inspection["groups"]
            if not group["is_complete"]
        ]

        if (
            incomplete_groups
            and not skip_incomplete
        ):
            summary = ", ".join(
                (
                    f"{group['source_key']} "
                    f"(faltan: "
                    f"{', '.join(group['missing_bands'])})"
                )
                for group in incomplete_groups
            )

            raise IncompleteRedEdgeFolderError(
                "La carpeta contiene capturas "
                f"incompletas: {summary}"
            )

        imported_captures = []
        skipped_groups = []

        for group in inspection["groups"]:

            if not group["is_complete"]:
                skipped_groups.append(
                    {
                        "source_key": (
                            group["source_key"]
                        ),
                        "missing_bands": (
                            group["missing_bands"]
                        ),
                    }
                )
                continue
            
            metadata_files = {}

            for (
                band,
                source_path,
            ) in group["files"].items():

                band_name = (
                    band.value
                    if hasattr(
                        band,
                        "value",
                    )
                    else str(band)
                )

                resolved_source = Path(
                    source_path
                )

                if not resolved_source.is_absolute():
                    resolved_source = (
                        source_root
                        / resolved_source
                    )

                metadata_files[
                    band_name
                ] = (
                    resolved_source.resolve()
                )

            try:
                capture_metadata = (
                    MicaSenseMetadataService
                    .extract_capture_metadata(
                        metadata_files
                    )
                )

            except MicaSenseMetadataError as exc:
                raise RedEdgeImportExecutionError(
                    "Los metadatos MicaSense "
                    f"del grupo "
                    f"{group['source_key']} "
                    "no son válidos: "
                    f"{exc}"
                ) from exc
            
            capture = (
                CaptureService.create_capture(
                    campaign_id=campaign_id,
                    latitude=(
                        capture_metadata.latitude
                    ),
                    longitude=(
                        capture_metadata.longitude
                    ),
                    altitude=(
                        capture_metadata.altitude
                    ),
                    captured_at=(
                        capture_metadata.captured_at
                    ),
                )
            )
            

            try:
                last_result = None

                for band in cls.EXPECTED_BANDS:

                    source_path = (
                        group["files"][
                            band.value
                        ]
                    )

                    last_result = (
                        ImageIngestionService.ingest_file(
                            capture_id=(
                                capture["id"]
                            ),
                            band=band,
                            source_path=source_path,
                        )
                    )

                final_capture = (
                    last_result["capture"]
                )

                if (
                    final_capture["status"]
                    != "READY"
                ):
                    raise RedEdgeImportExecutionError(
                        "La captura importada "
                        f"{group['source_key']} "
                        "no alcanzó el estado READY."
                    )

                imported_captures.append(
                    {
                        "source_key": (
                            group["source_key"]
                        ),
                        "capture": (
                            final_capture
                        ),
                    }
                )

            except Exception as exc:

                # Primero eliminamos cualquier archivo
                # que ya se hubiese copiado.
                try:
                    (
                        ImageIngestionService
                        .remove_capture_storage(
                            campaign_code=(
                                campaign[
                                    "campaign_code"
                                ]
                            ),
                            sequence=(
                                capture[
                                    "sequence"
                                ]
                            ),
                        )
                    )
                except Exception:
                    pass

                # Después revertimos la persistencia.
                try:
                    CaptureService.delete_capture(
                        capture["id"]
                    )
                except Exception:
                    pass

                if isinstance(
                    exc,
                    RedEdgeImportExecutionError,
                ):
                    raise

                raise RedEdgeImportExecutionError(
                    "Falló la importación del grupo "
                    f"{group['source_key']}: {exc}"
                ) from exc

        return {
            "campaign_id": campaign_id,
            "campaign_code": (
                campaign["campaign_code"]
            ),
            "source_dir": (
                inspection["source_dir"]
            ),
            "detected_count": (
                inspection["group_count"]
            ),
            "imported_count": len(
                imported_captures
            ),
            "skipped_count": len(
                skipped_groups
            ),
            "imported_captures": (
                imported_captures
            ),
            "skipped_groups": (
                skipped_groups
            ),
            "ignored_files": (
                inspection["ignored_files"]
            ),
        }
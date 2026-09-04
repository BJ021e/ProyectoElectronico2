from __future__ import annotations

import json
import re
import shutil

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4

from config import Config

from services.rededge_import_service import (
    RedEdgeImportService,
)


class RedEdgeStagingError(Exception):
    """
    Error general durante el staging temporal
    de una importación RedEdge.
    """
    pass


class InvalidRedEdgeStageError(
    RedEdgeStagingError
):
    """
    El staging solicitado no existe o no cumple
    las condiciones de seguridad esperadas.
    """
    pass


class RedEdgeStagingService:

    TOKEN_PATTERN = re.compile(
        r"^[a-f0-9]{32}$"
    )

    METADATA_FILENAME = (
        ".rededge_stage.json"
    )

    @classmethod
    def _staging_root(
        cls,
    ) -> Path:

        configured = Path(
            Config.RED_EDGE_STAGING_ROOT
        )

        if configured.is_absolute():
            return configured.resolve()

        project_root = Path(
            __file__
        ).resolve().parents[1]

        return (
            project_root
            / configured
        ).resolve()

    @classmethod
    def _validate_token(
        cls,
        token: str,
    ) -> str:

        if (
            not isinstance(token, str)
            or not cls.TOKEN_PATTERN.fullmatch(
                token
            )
        ):
            raise InvalidRedEdgeStageError(
                "El token de staging "
                "no es válido."
            )

        return token

    @classmethod
    def _stage_directory(
        cls,
        token: str,
    ) -> Path:

        validated = (
            cls._validate_token(
                token
            )
        )

        root = (
            cls._staging_root()
        )

        return (
            root
            / validated
        ).resolve()

    @classmethod
    def _metadata_path(
        cls,
        token: str,
    ) -> Path:

        return (
            cls._stage_directory(token)
            / cls.METADATA_FILENAME
        )

    @staticmethod
    def _normalize_relative_path(
        relative_path: str,
    ) -> PurePosixPath:

        if (
            not isinstance(
                relative_path,
                str,
            )
            or not relative_path.strip()
        ):
            raise InvalidRedEdgeStageError(
                "La ruta relativa "
                "del archivo es obligatoria."
            )

        normalized = (
            relative_path
            .strip()
            .replace("\\", "/")
        )

        path = PurePosixPath(
            normalized
        )

        if path.is_absolute():
            raise InvalidRedEdgeStageError(
                "No se permiten rutas absolutas."
            )

        if not path.parts:
            raise InvalidRedEdgeStageError(
                "La ruta relativa "
                "no es válida."
            )

        for part in path.parts:

            if part in {
                "",
                ".",
                "..",
            }:
                raise InvalidRedEdgeStageError(
                    "La ruta contiene "
                    "segmentos no permitidos."
                )

            if ":" in part:
                raise InvalidRedEdgeStageError(
                    "La ruta contiene "
                    "un segmento no permitido."
                )

        if (
            path.name
            == RedEdgeStagingService
            .METADATA_FILENAME
        ):
            raise InvalidRedEdgeStageError(
                "Nombre de archivo reservado."
            )

        return path

    @classmethod
    def _read_metadata(
        cls,
        token: str,
    ) -> dict:

        metadata_path = (
            cls._metadata_path(
                token
            )
        )

        if not metadata_path.exists():
            raise InvalidRedEdgeStageError(
                "El staging RedEdge "
                "no existe."
            )

        try:
            return json.loads(
                metadata_path.read_text(
                    encoding="utf-8"
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise InvalidRedEdgeStageError(
                "Los metadatos del staging "
                "no son válidos."
            ) from exc

    @classmethod
    def create_stage(
        cls,
        *,
        campaign_id: int,
    ) -> str:

        if (
            not isinstance(campaign_id, int)
            or campaign_id <= 0
        ):
            raise InvalidRedEdgeStageError(
                "campaign_id no es válido."
            )

        root = (
            cls._staging_root()
        )

        root.mkdir(
            parents=True,
            exist_ok=True,
        )

        token = uuid4().hex

        stage_directory = (
            cls._stage_directory(
                token
            )
        )

        stage_directory.mkdir(
            parents=True,
            exist_ok=False,
        )

        metadata = {
            "campaign_id": campaign_id,
            "created_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        }

        cls._metadata_path(
            token
        ).write_text(
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return token

    @classmethod
    def get_stage_directory(
        cls,
        *,
        token: str,
        campaign_id: int,
    ) -> Path:

        stage_directory = (
            cls._stage_directory(
                token
            )
        )

        if (
            not stage_directory.exists()
            or not stage_directory.is_dir()
        ):
            raise InvalidRedEdgeStageError(
                "El staging RedEdge "
                "no existe."
            )

        metadata = (
            cls._read_metadata(
                token
            )
        )

        if (
            metadata.get(
                "campaign_id"
            )
            != campaign_id
        ):
            raise InvalidRedEdgeStageError(
                "El staging no pertenece "
                "a la campaña indicada."
            )

        return stage_directory

    @classmethod
    def stage_file(
        cls,
        *,
        token: str,
        campaign_id: int,
        relative_path: str,
        source_stream,
    ) -> Path:

        stage_directory = (
            cls.get_stage_directory(
                token=token,
                campaign_id=campaign_id,
            )
        )

        normalized_path = (
            cls._normalize_relative_path(
                relative_path
            )
        )

        destination = (
            stage_directory
            / Path(
                *normalized_path.parts
            )
        ).resolve()

        try:
            destination.relative_to(
                stage_directory
            )

        except ValueError as exc:
            raise InvalidRedEdgeStageError(
                "La ruta intenta salir "
                "del staging permitido."
            ) from exc

        if destination.exists():
            raise InvalidRedEdgeStageError(
                "Se recibió más de una vez "
                f"el archivo {relative_path}."
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            with destination.open(
                "wb"
            ) as output:

                shutil.copyfileobj(
                    source_stream,
                    output,
                )

        except OSError as exc:

            if destination.exists():
                destination.unlink()

            raise RedEdgeStagingError(
                "No fue posible almacenar "
                f"{relative_path}: {exc}"
            ) from exc

        if (
            not destination.exists()
            or destination.stat().st_size == 0
        ):

            if destination.exists():
                destination.unlink()

            raise InvalidRedEdgeStageError(
                "El archivo recibido "
                f"está vacío: {relative_path}."
            )

        return destination

    @classmethod
    def inspect_stage(
        cls,
        *,
        token: str,
        campaign_id: int,
    ) -> dict:

        stage_directory = (
            cls.get_stage_directory(
                token=token,
                campaign_id=campaign_id,
            )
        )

        return (
            RedEdgeImportService
            .inspect_folder(
                stage_directory
            )
        )

    @classmethod
    def delete_stage(
        cls,
        *,
        token: str,
        campaign_id: int,
    ) -> bool:

        stage_directory = (
            cls.get_stage_directory(
                token=token,
                campaign_id=campaign_id,
            )
        )

        shutil.rmtree(
            stage_directory
        )

        return (
            not stage_directory.exists()
        )
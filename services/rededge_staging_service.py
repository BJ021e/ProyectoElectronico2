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
    def cleanup_expired_stages(
        cls,
        *,
        max_age_hours: int | None = None,
        now: datetime | None = None,
    ) -> dict:
        """
        Elimina stagings RedEdge que hayan superado
        el tiempo máximo permitido.

        Los directorios o metadatos inválidos se
        reportan pero no se eliminan automáticamente.
        """

        if max_age_hours is None:
            max_age_hours = (
                Config
                .RED_EDGE_STAGING_MAX_AGE_HOURS
            )

        if (
            not isinstance(
                max_age_hours,
                int,
            )
            or max_age_hours <= 0
        ):
            raise RedEdgeStagingError(
                "max_age_hours debe "
                "ser un entero mayor que cero."
            )

        if now is None:
            now = datetime.now(
                timezone.utc
            )

        if now.tzinfo is None:
            raise RedEdgeStagingError(
                "now debe contener "
                "información de zona horaria."
            )

        now_utc = now.astimezone(
            timezone.utc
        )

        root = (
            cls._staging_root()
        )

        if not root.exists():
            return {
                "scanned_count": 0,
                "deleted_count": 0,
                "kept_count": 0,
                "invalid_count": 0,
                "deleted_tokens": [],
                "invalid_entries": [],
            }

        if not root.is_dir():
            raise RedEdgeStagingError(
                "La raíz de staging "
                "no corresponde a un directorio."
            )

        scanned_count = 0
        deleted_tokens = []
        invalid_entries = []
        kept_count = 0

        try:
            entries = list(
                root.iterdir()
            )

        except OSError as exc:
            raise RedEdgeStagingError(
                "No fue posible inspeccionar "
                f"el staging: {exc}"
            ) from exc

        for entry in entries:

            if not entry.is_dir():
                continue

            token = entry.name

            if not cls.TOKEN_PATTERN.fullmatch(
                token
            ):
                invalid_entries.append({
                    "entry": token,
                    "reason": (
                        "Nombre de staging inválido."
                    ),
                })

                continue

            scanned_count += 1

            metadata_path = (
                entry
                / cls.METADATA_FILENAME
            )

            if not metadata_path.exists():

                invalid_entries.append({
                    "entry": token,
                    "reason": (
                        "No existe metadata."
                    ),
                })

                continue

            try:
                metadata = json.loads(
                    metadata_path.read_text(
                        encoding="utf-8"
                    )
                )

            except (
                OSError,
                json.JSONDecodeError,
            ):

                invalid_entries.append({
                    "entry": token,
                    "reason": (
                        "Metadata inválida."
                    ),
                })

                continue

            created_at_raw = (
                metadata.get(
                    "created_at"
                )
            )

            if (
                not isinstance(
                    created_at_raw,
                    str,
                )
                or not created_at_raw.strip()
            ):

                invalid_entries.append({
                    "entry": token,
                    "reason": (
                        "created_at ausente."
                    ),
                })

                continue

            try:
                created_at = (
                    datetime.fromisoformat(
                        created_at_raw
                    )
                )

            except ValueError:

                invalid_entries.append({
                    "entry": token,
                    "reason": (
                        "created_at inválido."
                    ),
                })

                continue

            if created_at.tzinfo is None:

                invalid_entries.append({
                    "entry": token,
                    "reason": (
                        "created_at no posee "
                        "zona horaria."
                    ),
                })

                continue

            created_at_utc = (
                created_at.astimezone(
                    timezone.utc
                )
            )

            age_seconds = (
                now_utc
                - created_at_utc
            ).total_seconds()

            max_age_seconds = (
                max_age_hours
                * 60
                * 60
            )

            if age_seconds < 0:

                invalid_entries.append({
                    "entry": token,
                    "reason": (
                        "created_at se encuentra "
                        "en el futuro."
                    ),
                })

                continue

            if (
                age_seconds
                < max_age_seconds
            ):
                kept_count += 1
                continue

            try:
                shutil.rmtree(
                    entry
                )

            except OSError as exc:

                invalid_entries.append({
                    "entry": token,
                    "reason": (
                        "No fue posible eliminar: "
                        f"{exc}"
                    ),
                })

                continue

            deleted_tokens.append(
                token
            )

        return {
            "scanned_count": (
                scanned_count
            ),
            "deleted_count": len(
                deleted_tokens
            ),
            "kept_count": kept_count,
            "invalid_count": len(
                invalid_entries
            ),
            "deleted_tokens": (
                deleted_tokens
            ),
            "invalid_entries": (
                invalid_entries
            ),
        }
    
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
        
        cls.cleanup_expired_stages()
        
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
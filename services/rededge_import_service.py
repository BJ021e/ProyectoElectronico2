from __future__ import annotations

import re
from pathlib import Path

from models import ImageBand


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
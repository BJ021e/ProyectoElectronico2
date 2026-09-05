from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio


class SpectralIndexError(Exception):
    """
    Error general durante el cálculo
    de un índice espectral.
    """
    pass


class InvalidSpectralIndexError(
    SpectralIndexError
):
    """
    El índice solicitado o el ráster de
    entrada no cumplen las condiciones.
    """
    pass


class SpectralIndexService:

    INDEX_DEFINITIONS = {
        "NDVI": {
            "positive_band": 4,  # NIR
            "negative_band": 3,  # RED
        },
        "NDRE": {
            "positive_band": 4,  # NIR
            "negative_band": 5,  # RED_EDGE
        },
        "GNDVI": {
            "positive_band": 4,  # NIR
            "negative_band": 2,  # GREEN
        },
    }

    OUTPUT_NODATA = -9999.0

    @classmethod
    def normalize_index_name(
        cls,
        index_name: str,
    ) -> str:

        normalized = (
            str(index_name or "")
            .strip()
            .upper()
        )

        if (
            normalized
            not in cls.INDEX_DEFINITIONS
        ):
            raise InvalidSpectralIndexError(
                "Índice espectral no soportado: "
                f"{index_name}."
            )

        return normalized

    @classmethod
    def calculate_array(
        cls,
        *,
        positive,
        negative,
        valid_mask=None,
    ) -> np.ndarray:

        positive_array = np.asarray(
            positive,
            dtype=np.float32,
        )

        negative_array = np.asarray(
            negative,
            dtype=np.float32,
        )

        if (
            positive_array.shape
            != negative_array.shape
        ):
            raise InvalidSpectralIndexError(
                "Las bandas utilizadas por "
                "el índice no tienen las "
                "mismas dimensiones."
            )

        denominator = (
            positive_array
            + negative_array
        )

        if valid_mask is None:
            valid = (
                np.isfinite(
                    positive_array
                )
                &
                np.isfinite(
                    negative_array
                )
            )
        else:
            valid = np.asarray(
                valid_mask,
                dtype=bool,
            )

            if (
                valid.shape
                != positive_array.shape
            ):
                raise InvalidSpectralIndexError(
                    "La máscara válida no "
                    "coincide con las bandas."
                )

            valid = (
                valid
                &
                np.isfinite(
                    positive_array
                )
                &
                np.isfinite(
                    negative_array
                )
            )

        valid &= (
            np.abs(
                denominator
            )
            > 1e-12
        )

        result = np.full(
            positive_array.shape,
            cls.OUTPUT_NODATA,
            dtype=np.float32,
        )

        result[
            valid
        ] = (
            (
                positive_array[valid]
                - negative_array[valid]
            )
            /
            denominator[valid]
        )

        result[
            valid
        ] = np.clip(
            result[valid],
            -1.0,
            1.0,
        )

        return result

    @classmethod
    def calculate_raster(
        cls,
        *,
        source_path: str | Path,
        output_path: str | Path,
        index_name: str,
    ) -> Path:

        normalized_index = (
            cls.normalize_index_name(
                index_name
            )
        )

        definition = (
            cls.INDEX_DEFINITIONS[
                normalized_index
            ]
        )

        positive_band = (
            definition[
                "positive_band"
            ]
        )

        negative_band = (
            definition[
                "negative_band"
            ]
        )

        source = Path(
            source_path
        ).resolve()

        output = Path(
            output_path
        ).resolve()

        if (
            not source.exists()
            or not source.is_file()
        ):
            raise InvalidSpectralIndexError(
                "El ortomosaico "
                "multiespectral no existe."
            )

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            with rasterio.open(
                source
            ) as dataset:

                required_band = max(
                    positive_band,
                    negative_band,
                )

                if (
                    dataset.count
                    < required_band
                ):
                    raise InvalidSpectralIndexError(
                        "El ortomosaico no "
                        "contiene las bandas "
                        f"necesarias para "
                        f"{normalized_index}."
                    )

                if dataset.crs is None:
                    raise InvalidSpectralIndexError(
                        "El ortomosaico no "
                        "posee CRS."
                    )

                profile = (
                    dataset.profile.copy()
                )

                profile.update(
                    count=1,
                    dtype="float32",
                    nodata=(
                        cls.OUTPUT_NODATA
                    ),
                    compress="deflate",
                )

                with rasterio.open(
                    output,
                    "w",
                    **profile,
                ) as destination:

                    for (
                        _,
                        window,
                    ) in dataset.block_windows(
                        positive_band
                    ):

                        positive = (
                            dataset.read(
                                positive_band,
                                window=window,
                                masked=True,
                            )
                        )

                        negative = (
                            dataset.read(
                                negative_band,
                                window=window,
                                masked=True,
                            )
                        )

                        positive_mask = (
                            np.ma.getmaskarray(
                                positive
                            )
                        )

                        negative_mask = (
                            np.ma.getmaskarray(
                                negative
                            )
                        )

                        valid_mask = ~(
                            positive_mask
                            |
                            negative_mask
                        )

                        result = (
                            cls.calculate_array(
                                positive=(
                                    positive.filled(
                                        0
                                    )
                                ),
                                negative=(
                                    negative.filled(
                                        0
                                    )
                                ),
                                valid_mask=(
                                    valid_mask
                                ),
                            )
                        )

                        destination.write(
                            result,
                            1,
                            window=window,
                        )

                    destination.update_tags(
                        SPECTRAL_INDEX=(
                            normalized_index
                        ),

                        SOURCE_POSITIVE_BAND=(
                            positive_band
                        ),

                        SOURCE_NEGATIVE_BAND=(
                            negative_band
                        ),
                    )

        except InvalidSpectralIndexError:
            raise

        except (
            rasterio.errors.RasterioError,
            OSError,
            ValueError,
        ) as exc:

            if output.exists():
                output.unlink()

            raise SpectralIndexError(
                "No fue posible calcular "
                f"{normalized_index}: {exc}"
            ) from exc

        return output
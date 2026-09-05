from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import rasterio

from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT


class SpectralIndexVisualizationError(
    Exception
):
    pass


class InvalidSpectralIndexVisualizationError(
    SpectralIndexVisualizationError
):
    pass


class SpectralIndexVisualizationService:

    SUPPORTED_INDEXES = {
        "NDVI",
        "NDRE",
        "GNDVI",
    }

    DEFAULT_MAX_DIMENSION = 1600

    # Escala FIJA.
    #
    # No representa categorías de salud.
    # Representa únicamente magnitud del índice.
    COLOR_STOPS = (
        (
            -1.0,
            (
                49,
                54,
                149,
            ),
        ),
        (
            -0.5,
            (
                69,
                117,
                180,
            ),
        ),
        (
            0.0,
            (
                255,
                255,
                191,
            ),
        ),
        (
            0.5,
            (
                145,
                207,
                96,
            ),
        ),
        (
            1.0,
            (
                0,
                104,
                55,
            ),
        ),
    )

    @classmethod
    def normalize_index_name(
        cls,
        index_name: str,
    ) -> str:

        normalized = (
            str(
                index_name or ""
            )
            .strip()
            .upper()
        )

        if (
            normalized
            not in cls.SUPPORTED_INDEXES
        ):
            raise (
                InvalidSpectralIndexVisualizationError(
                    "Índice espectral "
                    "no soportado para "
                    "visualización: "
                    f"{index_name}."
                )
            )

        return normalized

    @staticmethod
    def _calculate_preview_size(
        *,
        width: int,
        height: int,
        max_dimension: int,
    ) -> tuple[int, int]:

        if (
            width <= 0
            or height <= 0
        ):
            raise (
                InvalidSpectralIndexVisualizationError(
                    "Las dimensiones del "
                    "ráster no son válidas."
                )
            )

        if max_dimension <= 0:
            raise (
                InvalidSpectralIndexVisualizationError(
                    "max_dimension debe "
                    "ser mayor que cero."
                )
            )

        largest = max(
            width,
            height,
        )

        if largest <= max_dimension:

            return (
                width,
                height,
            )

        scale = (
            max_dimension
            / largest
        )

        return (
            max(
                1,
                int(
                    round(
                        width
                        * scale
                    )
                ),
            ),
            max(
                1,
                int(
                    round(
                        height
                        * scale
                    )
                ),
            ),
        )

    @classmethod
    def _colorize(
        cls,
        values,
        valid_mask,
    ) -> np.ndarray:

        values_array = np.asarray(
            values,
            dtype=np.float32,
        )

        valid = np.asarray(
            valid_mask,
            dtype=bool,
        )

        if (
            values_array.shape
            != valid.shape
        ):
            raise (
                InvalidSpectralIndexVisualizationError(
                    "La máscara del índice "
                    "no coincide con el ráster."
                )
            )

        clipped = np.clip(
            values_array,
            -1.0,
            1.0,
        )

        stop_values = np.array(
            [
                stop[0]
                for stop
                in cls.COLOR_STOPS
            ],
            dtype=np.float32,
        )

        stop_colors = np.array(
            [
                stop[1]
                for stop
                in cls.COLOR_STOPS
            ],
            dtype=np.float32,
        )

        rgb = np.zeros(
            (
                values_array.shape[0],
                values_array.shape[1],
                3,
            ),
            dtype=np.uint8,
        )

        for channel in range(
            3
        ):

            rgb[
                :,
                :,
                channel,
            ] = np.interp(
                clipped,
                stop_values,
                stop_colors[
                    :,
                    channel,
                ],
            ).astype(
                np.uint8
            )

        alpha = (
            valid.astype(
                np.uint8
            )
            * 255
        )

        rgba = np.dstack(
            (
                rgb,
                alpha,
            )
        )

        rgba[
            ~valid
        ] = (
            0,
            0,
            0,
            0,
        )

        return rgba

    @classmethod
    def render_png(
        cls,
        *,
        source_path: str | Path,
        index_name: str,
        max_dimension: int | None = None,
    ) -> bytes:

        cls.normalize_index_name(
            index_name
        )

        source = Path(
            source_path
        ).resolve()

        if (
            not source.exists()
            or not source.is_file()
        ):
            raise (
                InvalidSpectralIndexVisualizationError(
                    "El producto espectral "
                    "no existe."
                )
            )

        if max_dimension is None:

            max_dimension = (
                cls.DEFAULT_MAX_DIMENSION
            )

        try:

            with rasterio.open(
                source
            ) as dataset:

                if dataset.count != 1:

                    raise (
                        InvalidSpectralIndexVisualizationError(
                            "Un índice espectral "
                            "debe contener "
                            "exactamente una banda."
                        )
                    )

                if dataset.crs is None:

                    raise (
                        InvalidSpectralIndexVisualizationError(
                            "El índice espectral "
                            "no posee CRS."
                        )
                    )

                with WarpedVRT(
                    dataset,
                    crs="EPSG:3857",
                    resampling=(
                        Resampling.bilinear
                    ),
                    nodata=(
                        dataset.nodata
                    ),
                ) as warped:

                    (
                        preview_width,
                        preview_height,
                    ) = (
                        cls
                        ._calculate_preview_size(
                            width=(
                                warped.width
                            ),
                            height=(
                                warped.height
                            ),
                            max_dimension=(
                                max_dimension
                            ),
                        )
                    )

                    data = warped.read(
                        1,
                        out_shape=(
                            preview_height,
                            preview_width,
                        ),
                        resampling=(
                            Resampling.bilinear
                        ),
                        masked=True,
                    )

        except (
            InvalidSpectralIndexVisualizationError
        ):
            raise

        except (
            rasterio.errors.RasterioError,
            OSError,
            ValueError,
        ) as exc:

            raise (
                SpectralIndexVisualizationError(
                    "No fue posible generar "
                    "la visualización del índice: "
                    f"{exc}"
                )
            ) from exc

        mask = np.ma.getmaskarray(
            data
        )

        values = (
            data
            .filled(0.0)
            .astype(
                np.float32
            )
        )

        valid_mask = (
            ~mask
            &
            np.isfinite(
                values
            )
        )

        rgba = cls._colorize(
            values,
            valid_mask,
        )

        bgra = cv2.cvtColor(
            rgba,
            cv2.COLOR_RGBA2BGRA,
        )

        success, encoded = (
            cv2.imencode(
                ".png",
                bgra,
            )
        )

        if not success:

            raise (
                SpectralIndexVisualizationError(
                    "OpenCV no pudo "
                    "codificar el índice "
                    "como PNG."
                )
            )

        return encoded.tobytes()

    @classmethod
    def calculate_statistics(
        cls,
        *,
        source_path: str | Path,
        index_name: str,
    ) -> dict:

        normalized_index = (
            cls.normalize_index_name(
                index_name
            )
        )

        source = Path(
            source_path
        ).resolve()

        if (
            not source.exists()
            or not source.is_file()
        ):
            raise (
                InvalidSpectralIndexVisualizationError(
                    "El producto espectral "
                    "no existe."
                )
            )

        minimum = None
        maximum = None

        total = 0.0
        valid_pixel_count = 0

        try:

            with rasterio.open(
                source
            ) as dataset:

                if dataset.count != 1:

                    raise (
                        InvalidSpectralIndexVisualizationError(
                            "Un índice espectral "
                            "debe contener "
                            "una sola banda."
                        )
                    )

                for (
                    _,
                    window,
                ) in dataset.block_windows(
                    1
                ):

                    data = dataset.read(
                        1,
                        window=window,
                        masked=True,
                    )

                    values = (
                        data.compressed()
                    )

                    if (
                        values.size
                        == 0
                    ):
                        continue

                    values = values[
                        np.isfinite(
                            values
                        )
                    ]

                    if (
                        values.size
                        == 0
                    ):
                        continue

                    local_min = float(
                        np.min(
                            values
                        )
                    )

                    local_max = float(
                        np.max(
                            values
                        )
                    )

                    if minimum is None:

                        minimum = (
                            local_min
                        )

                    else:

                        minimum = min(
                            minimum,
                            local_min,
                        )

                    if maximum is None:

                        maximum = (
                            local_max
                        )

                    else:

                        maximum = max(
                            maximum,
                            local_max,
                        )

                    total += float(
                        np.sum(
                            values,
                            dtype=np.float64,
                        )
                    )

                    valid_pixel_count += int(
                        values.size
                    )

        except (
            InvalidSpectralIndexVisualizationError
        ):
            raise

        except (
            rasterio.errors.RasterioError,
            OSError,
            ValueError,
        ) as exc:

            raise (
                SpectralIndexVisualizationError(
                    "No fue posible calcular "
                    "las estadísticas del índice: "
                    f"{exc}"
                )
            ) from exc

        if valid_pixel_count == 0:

            raise (
                InvalidSpectralIndexVisualizationError(
                    "El índice no posee "
                    "píxeles válidos."
                )
            )

        mean = (
            total
            / valid_pixel_count
        )

        return {
            "index": (
                normalized_index
            ),
            "minimum": (
                minimum
            ),
            "mean": (
                mean
            ),
            "maximum": (
                maximum
            ),
            "valid_pixel_count": (
                valid_pixel_count
            ),
            "range": {
                "minimum": -1.0,
                "maximum": 1.0,
            },
        }

    @classmethod
    def get_legend(
        cls,
    ) -> list[dict]:

        return [
            {
                "value": value,
                "rgb": list(
                    rgb
                ),
            }
            for (
                value,
                rgb,
            ) in cls.COLOR_STOPS
        ]
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import rasterio

from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT


class RasterPreviewError(Exception):
    """
    Error durante la generación de una
    representación web de un ráster.
    """
    pass


class InvalidRasterPreviewError(
    RasterPreviewError
):
    """
    El ráster no cumple las condiciones
    necesarias para generar un preview.
    """
    pass


class RasterPreviewService:

    DEFAULT_MAX_DIMENSION = 1600

    @staticmethod
    def _calculate_preview_size(
        width: int,
        height: int,
        max_dimension: int,
    ) -> tuple[int, int]:

        if width <= 0 or height <= 0:
            raise InvalidRasterPreviewError(
                "Las dimensiones del ráster "
                "no son válidas."
            )

        if max_dimension <= 0:
            raise InvalidRasterPreviewError(
                "max_dimension debe ser "
                "mayor que cero."
            )

        largest_dimension = max(
            width,
            height,
        )

        if (
            largest_dimension
            <= max_dimension
        ):
            return (
                width,
                height,
            )

        scale = (
            max_dimension
            / largest_dimension
        )

        preview_width = max(
            1,
            int(
                round(
                    width * scale
                )
            ),
        )

        preview_height = max(
            1,
            int(
                round(
                    height * scale
                )
            ),
        )

        return (
            preview_width,
            preview_height,
        )

    @staticmethod
    def _select_band_indexes(
        *,
        band_count: int,
        product_type: str | None,
    ) -> tuple[int, ...]:

        normalized_type = (
            str(product_type or "")
            .strip()
            .upper()
        )

        if (
            normalized_type
            == "ORTHOMOSAIC_MULTISPECTRAL"
            and band_count >= 5
        ):
            # Convención RedEdge del proyecto:
            #
            # 1 BLUE
            # 2 GREEN
            # 3 RED
            # 4 NIR
            # 5 RED_EDGE
            #
            # Para composición natural RGB:
            return (
                3,
                2,
                1,
            )

        if band_count >= 3:
            return (
                1,
                2,
                3,
            )

        if band_count >= 1:
            return (1,)

        raise InvalidRasterPreviewError(
            "El ráster no contiene bandas."
        )

    @staticmethod
    def _stretch_band(
        band,
    ) -> tuple[np.ndarray, np.ndarray]:

        masked_band = np.ma.asarray(
            band
        )

        mask = np.ma.getmaskarray(
            masked_band
        )

        valid_values = (
            masked_band.compressed()
        )

        if valid_values.size == 0:
            return (
                np.zeros(
                    masked_band.shape,
                    dtype=np.uint8,
                ),
                np.zeros(
                    masked_band.shape,
                    dtype=bool,
                ),
            )

        valid_values = (
            valid_values[
                np.isfinite(
                    valid_values
                )
            ]
        )

        if valid_values.size == 0:
            return (
                np.zeros(
                    masked_band.shape,
                    dtype=np.uint8,
                ),
                np.zeros(
                    masked_band.shape,
                    dtype=bool,
                ),
            )

        low, high = np.percentile(
            valid_values,
            [
                2,
                98,
            ],
        )

        if (
            not np.isfinite(low)
            or not np.isfinite(high)
        ):
            low = float(
                np.min(
                    valid_values
                )
            )

            high = float(
                np.max(
                    valid_values
                )
            )

        if high <= low:
            low = float(
                np.min(
                    valid_values
                )
            )

            high = float(
                np.max(
                    valid_values
                )
            )

        if high <= low:
            stretched = np.zeros(
                masked_band.shape,
                dtype=np.uint8,
            )

            stretched[
                ~mask
            ] = 255

            return (
                stretched,
                ~mask,
            )

        data = (
            masked_band
            .filled(low)
            .astype(
                np.float32
            )
        )

        stretched = (
            (
                data - low
            )
            / (
                high - low
            )
            * 255.0
        )

        stretched = np.clip(
            stretched,
            0,
            255,
        ).astype(
            np.uint8
        )

        stretched[
            mask
        ] = 0

        return (
            stretched,
            ~mask,
        )

    @classmethod
    def render_png(
        cls,
        *,
        source_path: str | Path,
        product_type: str | None = None,
        max_dimension: int | None = None,
    ) -> bytes:

        source = Path(
            source_path
        ).resolve()

        if (
            not source.exists()
            or not source.is_file()
        ):
            raise InvalidRasterPreviewError(
                "El ráster solicitado "
                "no existe."
            )

        if max_dimension is None:
            max_dimension = (
                cls.DEFAULT_MAX_DIMENSION
            )

        try:
            with rasterio.open(
                source
            ) as dataset:

                if dataset.crs is None:
                    raise (
                        InvalidRasterPreviewError(
                            "El ráster no posee CRS "
                            "y no puede publicarse "
                            "geográficamente."
                        )
                    )

                with WarpedVRT(
                    dataset,
                    crs="EPSG:3857",
                    resampling=(
                        Resampling.bilinear
                    ),
                ) as warped:

                    (
                        preview_width,
                        preview_height,
                    ) = (
                        cls
                        ._calculate_preview_size(
                            warped.width,
                            warped.height,
                            max_dimension,
                        )
                    )

                    indexes = (
                        cls
                        ._select_band_indexes(
                            band_count=(
                                warped.count
                            ),
                            product_type=(
                                product_type
                            ),
                        )
                    )

                    raster_data = (
                        warped.read(
                            indexes,
                            out_shape=(
                                len(indexes),
                                preview_height,
                                preview_width,
                            ),
                            resampling=(
                                Resampling.bilinear
                            ),
                            masked=True,
                        )
                    )

        except InvalidRasterPreviewError:
            raise

        except (
            rasterio.errors.RasterioError,
            OSError,
            ValueError,
        ) as exc:
            raise RasterPreviewError(
                "No fue posible generar "
                f"el preview ráster: {exc}"
            ) from exc

        if len(indexes) == 1:

            (
                grayscale,
                valid_mask,
            ) = cls._stretch_band(
                raster_data[0]
            )

            output = cv2.cvtColor(
                grayscale,
                cv2.COLOR_GRAY2BGRA,
            )

            output[
                :,
                :,
                3,
            ] = (
                valid_mask.astype(
                    np.uint8
                )
                * 255
            )

        else:

            channels = []
            valid_masks = []

            for index in range(
                len(indexes)
            ):
                (
                    channel,
                    valid_mask,
                ) = cls._stretch_band(
                    raster_data[index]
                )

                channels.append(
                    channel
                )

                valid_masks.append(
                    valid_mask
                )

            rgb = np.dstack(
                channels
            )

            valid_mask = np.logical_and.reduce(
                valid_masks
            )

            output = cv2.cvtColor(
                rgb,
                cv2.COLOR_RGB2BGRA,
            )

            output[
                :,
                :,
                3,
            ] = (
                valid_mask.astype(
                    np.uint8
                )
                * 255
            )

        success, encoded = (
            cv2.imencode(
                ".png",
                output,
            )
        )

        if not success:
            raise RasterPreviewError(
                "OpenCV no pudo codificar "
                "el preview como PNG."
            )

        return encoded.tobytes()
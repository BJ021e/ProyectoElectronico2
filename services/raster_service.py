from __future__ import annotations

from math import isfinite, sqrt
from pathlib import Path

import numpy as np
import rasterio

from affine import Affine
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds


class RasterServiceError(Exception):
    """
    Error producido durante una operación
    relacionada con un raster.
    """
    pass


class InvalidRasterError(RasterServiceError):
    """
    El archivo suministrado no existe o no
    puede ser interpretado como raster.
    """
    pass


class RasterService:

    DEFAULT_MAX_STATISTICS_PIXELS = 1_000_000

    @staticmethod
    def _validate_path(
        raster_path: str | Path,
    ) -> Path:

        path = Path(
            raster_path
        ).expanduser().resolve()

        if not path.exists():
            raise InvalidRasterError(
                f"El raster no existe: {path}"
            )

        if not path.is_file():
            raise InvalidRasterError(
                f"La ruta no corresponde "
                f"a un archivo: {path}"
            )

        return path

    @staticmethod
    def _safe_number(
        value,
    ) -> float | None:

        if value is None:
            return None

        try:
            number = float(value)

        except (TypeError, ValueError):
            return None

        if not isfinite(number):
            return None

        return number

    @staticmethod
    def _serialize_bounds(
        bounds,
    ) -> dict:

        return {
            "left": float(bounds.left),
            "bottom": float(bounds.bottom),
            "right": float(bounds.right),
            "top": float(bounds.top),
        }

    @staticmethod
    def _serialize_transform(
        transform: Affine,
    ) -> dict:

        return {
            "a": float(transform.a),
            "b": float(transform.b),
            "c": float(transform.c),
            "d": float(transform.d),
            "e": float(transform.e),
            "f": float(transform.f),
        }

    @classmethod
    def _statistics_shape(
        cls,
        *,
        width: int,
        height: int,
        max_pixels: int,
    ) -> tuple[int, int, str]:

        total_pixels = width * height

        if total_pixels <= max_pixels:
            return (
                width,
                height,
                "exact",
            )

        scale = sqrt(
            total_pixels
            / max_pixels
        )

        sampled_width = max(
            1,
            int(width / scale),
        )

        sampled_height = max(
            1,
            int(height / scale),
        )

        return (
            sampled_width,
            sampled_height,
            "sampled",
        )

    @classmethod
    def _band_statistics(
        cls,
        dataset,
        *,
        band_index: int,
        max_pixels: int,
    ) -> dict:

        (
            sample_width,
            sample_height,
            mode,
        ) = cls._statistics_shape(
            width=dataset.width,
            height=dataset.height,
            max_pixels=max_pixels,
        )

        data = dataset.read(
            band_index,
            out_shape=(
                sample_height,
                sample_width,
            ),
            masked=True,
            resampling=Resampling.nearest,
        )

        values = np.asarray(
            data.compressed(),
            dtype=np.float64,
        )

        values = values[
            np.isfinite(values)
        ]

        sample_pixel_count = (
            sample_width
            * sample_height
        )

        if values.size == 0:
            return {
                "band": band_index,
                "mode": mode,
                "sample_width": sample_width,
                "sample_height": sample_height,
                "sample_pixel_count": (
                    sample_pixel_count
                ),
                "valid_pixel_count": 0,
                "min": None,
                "max": None,
                "mean": None,
                "std": None,
            }

        return {
            "band": band_index,
            "mode": mode,
            "sample_width": sample_width,
            "sample_height": sample_height,
            "sample_pixel_count": (
                sample_pixel_count
            ),
            "valid_pixel_count": int(
                values.size
            ),
            "min": float(
                np.min(values)
            ),
            "max": float(
                np.max(values)
            ),
            "mean": float(
                np.mean(values)
            ),
            "std": float(
                np.std(values)
            ),
        }

    @classmethod
    def inspect_raster(
        cls,
        raster_path: str | Path,
        *,
        include_statistics: bool = True,
        max_statistics_pixels: int = (
            DEFAULT_MAX_STATISTICS_PIXELS
        ),
    ) -> dict:

        path = cls._validate_path(
            raster_path
        )

        if max_statistics_pixels < 1:
            raise InvalidRasterError(
                "max_statistics_pixels debe "
                "ser mayor que cero."
            )

        try:
            with rasterio.open(
                path
            ) as dataset:

                crs = dataset.crs

                transform = (
                    dataset.transform
                )

                has_spatial_transform = (
                    transform
                    != Affine.identity()
                )

                is_georeferenced = (
                    crs is not None
                    and has_spatial_transform
                )

                native_bounds = (
                    cls._serialize_bounds(
                        dataset.bounds
                    )
                )

                bounds_wgs84 = None

                if is_georeferenced:
                    try:
                        transformed = (
                            transform_bounds(
                                crs,
                                "EPSG:4326",
                                *dataset.bounds,
                                densify_pts=21,
                            )
                        )

                        bounds_wgs84 = {
                            "left": float(
                                transformed[0]
                            ),
                            "bottom": float(
                                transformed[1]
                            ),
                            "right": float(
                                transformed[2]
                            ),
                            "top": float(
                                transformed[3]
                            ),
                        }

                    except Exception:
                        bounds_wgs84 = None

                statistics = []

                if include_statistics:

                    for band_index in range(
                        1,
                        dataset.count + 1,
                    ):
                        statistics.append(
                            cls._band_statistics(
                                dataset,
                                band_index=(
                                    band_index
                                ),
                                max_pixels=(
                                    max_statistics_pixels
                                ),
                            )
                        )

                return {
                    "path": str(path),
                    "filename": path.name,
                    "driver": dataset.driver,
                    "width": dataset.width,
                    "height": dataset.height,
                    "band_count": dataset.count,
                    "dtypes": list(
                        dataset.dtypes
                    ),
                    "nodata_values": [
                        cls._safe_number(
                            value
                        )
                        for value
                        in dataset.nodatavals
                    ],
                    "crs": (
                        crs.to_string()
                        if crs is not None
                        else None
                    ),
                    "epsg": (
                        crs.to_epsg()
                        if crs is not None
                        else None
                    ),
                    "is_georeferenced": (
                        is_georeferenced
                    ),
                    "transform": (
                        cls._serialize_transform(
                            transform
                        )
                    ),
                    "resolution": {
                        "x": abs(
                            float(
                                dataset.res[0]
                            )
                        ),
                        "y": abs(
                            float(
                                dataset.res[1]
                            )
                        ),
                    },
                    "bounds": native_bounds,
                    "bounds_wgs84": (
                        bounds_wgs84
                    ),
                    "statistics": statistics,
                }

        except InvalidRasterError:
            raise

        except Exception as exc:
            raise InvalidRasterError(
                "No fue posible leer el raster "
                f"{path.name}: {exc}"
            ) from exc
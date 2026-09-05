from __future__ import annotations

from tempfile import TemporaryDirectory

from services.geospatial_product_service import (
    GeospatialProductService,
)

from services.image_ingestion_service import (
    ImageIngestionService,
)

from services.spectral_index_service import (
    InvalidSpectralIndexError,
    SpectralIndexError,
    SpectralIndexService,
)


class SpectralIndexProductError(Exception):
    """
    Error general durante la creación de
    productos geoespaciales espectrales.
    """
    pass


class InvalidSpectralIndexSourceError(
    SpectralIndexProductError
):
    """
    El producto seleccionado no puede utilizarse
    como fuente para calcular índices.
    """
    pass


class SpectralIndexProductAlreadyExistsError(
    SpectralIndexProductError
):
    """
    El índice ya fue generado para la misma
    ejecución de procesamiento.
    """
    pass


class SpectralIndexProductService:

    SOURCE_PRODUCT_TYPE = (
        "ORTHOMOSAIC_MULTISPECTRAL"
    )

    SUPPORTED_INDEXES = {
        "NDVI",
        "NDRE",
        "GNDVI",
    }

    @staticmethod
    def _product_type(
        product: dict,
    ) -> str:

        return (
            str(
                product.get(
                    "product_type"
                )
                or product.get(
                    "type"
                )
                or ""
            )
            .strip()
            .upper()
        )

    @classmethod
    def _get_source_product(
        cls,
        product_id: int,
    ) -> dict:

        product = (
            GeospatialProductService
            .get_product(
                product_id
            )
        )

        if product is None:
            raise (
                InvalidSpectralIndexSourceError(
                    "El producto geoespacial "
                    f"con ID {product_id} "
                    "no existe."
                )
            )

        product_type = (
            cls._product_type(
                product
            )
        )

        if (
            product_type
            != cls.SOURCE_PRODUCT_TYPE
        ):
            raise (
                InvalidSpectralIndexSourceError(
                    "Los índices espectrales "
                    "solo pueden generarse "
                    "desde un "
                    "ORTHOMOSAIC_MULTISPECTRAL."
                )
            )

        if not product.get(
            "storage_path"
        ):
            raise (
                InvalidSpectralIndexSourceError(
                    "El producto fuente "
                    "no posee una ruta "
                    "de almacenamiento."
                )
            )

        return product

    @classmethod
    def _normalize_index(
        cls,
        index_name: str,
    ) -> str:

        try:
            normalized = (
                SpectralIndexService
                .normalize_index_name(
                    index_name
                )
            )

        except InvalidSpectralIndexError as exc:
            raise SpectralIndexProductError(
                str(exc)
            ) from exc

        if (
            normalized
            not in cls.SUPPORTED_INDEXES
        ):
            raise SpectralIndexProductError(
                "Índice no habilitado "
                "como producto geoespacial."
            )

        return normalized

    @classmethod
    def _assert_not_generated(
        cls,
        *,
        source_product: dict,
        index_name: str,
    ) -> None:

        campaign_id = (
            source_product[
                "campaign_id"
            ]
        )

        products = (
            GeospatialProductService
            .list_products(
                campaign_id,
            )
        )

        source_job_id = (
            source_product.get(
                "processing_job_id"
            )
        )

        for product in products:

            if (
                cls._product_type(
                    product
                )
                != index_name
            ):
                continue

            product_job_id = (
                product.get(
                    "processing_job_id"
                )
            )

            if (
                source_job_id is not None
                and product_job_id
                == source_job_id
            ):
                raise (
                    SpectralIndexProductAlreadyExistsError(
                        f"{index_name} ya fue "
                        "generado para este "
                        "procesamiento."
                    )
                )

            if (
                source_job_id is None
                and product_job_id is None
            ):
                raise (
                    SpectralIndexProductAlreadyExistsError(
                        f"{index_name} ya existe "
                        "para esta campaña sin "
                        "trabajo asociado."
                    )
                )

    @classmethod
    def generate_index(
        cls,
        *,
        source_product_id: int,
        index_name: str,
    ) -> dict:

        source_product = (
            cls._get_source_product(
                source_product_id
            )
        )

        normalized_index = (
            cls._normalize_index(
                index_name
            )
        )

        cls._assert_not_generated(
            source_product=(
                source_product
            ),
            index_name=(
                normalized_index
            ),
        )

        try:
            source_path = (
                ImageIngestionService
                .resolve_managed_path(
                    source_product[
                        "storage_path"
                    ]
                )
            )

        except Exception as exc:
            raise (
                InvalidSpectralIndexSourceError(
                    "No fue posible resolver "
                    "el ortomosaico fuente: "
                    f"{exc}"
                )
            ) from exc

        with TemporaryDirectory(
            prefix=(
                "spectral_index_"
            )
        ) as temporary_directory:

            output_path = (
                f"{temporary_directory}/"
                f"{normalized_index.lower()}.tif"
            )

            try:
                (
                    SpectralIndexService
                    .calculate_raster(
                        source_path=source_path,
                        output_path=output_path,
                        index_name=(
                            normalized_index
                        ),
                    )
                )

            except SpectralIndexError as exc:
                raise SpectralIndexProductError(
                    "No fue posible calcular "
                    f"{normalized_index}: "
                    f"{exc}"
                ) from exc

            product = (
                GeospatialProductService
                .register_raster_product(
                    campaign_id=(
                        source_product[
                            "campaign_id"
                        ]
                    ),
                    processing_job_id=(
                        source_product.get(
                            "processing_job_id"
                        )
                    ),
                    product_type=(
                        normalized_index
                    ),
                    name=(
                        f"{normalized_index} - "
                        + (
                            source_product.get(
                                "product_code"
                            )
                            or "Ortomosaico"
                        )
                    ),
                    source_path=(
                        output_path
                    ),
                )
            )

        return product
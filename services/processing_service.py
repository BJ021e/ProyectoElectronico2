from __future__ import annotations

from tempfile import TemporaryDirectory

from geospatial import (
    PhotogrammetryBackend,
    PhotogrammetryBackendError,
    PhotogrammetryBackendUnavailableError,
    PhotogrammetryRequest,
)
from models import SensorType
from services.campaign_service import (
    CampaignService,
)
from services.capture_service import (
    CaptureService,
)
from services.geospatial_product_service import (
    GeospatialProductService,
)
from services.image_ingestion_service import (
    ImageIngestionService,
)
from services.processing_job_service import (
    ProcessingJobService,
)


class ProcessingServiceError(Exception):
    """
    Error general del orquestador de procesamiento.
    """
    pass


class InvalidCampaignProcessingError(
    ProcessingServiceError
):
    """
    La campaña no cumple las condiciones necesarias
    para iniciar el procesamiento.
    """
    pass


class ProcessingExecutionError(
    ProcessingServiceError
):
    """
    El procesamiento comenzó pero no pudo completarse.
    """
    pass


class ProcessingService:

    @staticmethod
    def _validate_backend(
        backend,
    ) -> None:

        if not isinstance(
            backend,
            PhotogrammetryBackend,
        ):
            raise InvalidCampaignProcessingError(
                "El objeto suministrado no implementa "
                "PhotogrammetryBackend."
            )

        if (
            not isinstance(backend.name, str)
            or not backend.name.strip()
        ):
            raise InvalidCampaignProcessingError(
                "El backend no posee "
                "un nombre válido."
            )

    @staticmethod
    def _error_message(
        exc: Exception,
    ) -> str:

        message = str(exc).strip()

        if message:
            return message

        return exc.__class__.__name__

    @classmethod
    def _collect_inputs(
        cls,
        *,
        campaign_id: int,
    ) -> tuple[str, ...]:

        captures = (
            CaptureService.list_captures(
                campaign_id
            )
        )

        if not captures:
            raise InvalidCampaignProcessingError(
                "La campaña no contiene capturas."
            )

        incomplete = [
            capture["capture_code"]
            for capture in captures
            if capture["status"] != "READY"
        ]

        if incomplete:
            raise InvalidCampaignProcessingError(
                "La campaña contiene capturas "
                "que todavía no están READY: "
                + ", ".join(incomplete)
            )

        input_files = []

        for capture in captures:

            if not capture["assets"]:
                raise InvalidCampaignProcessingError(
                    "La captura "
                    f"{capture['capture_code']} "
                    "no contiene archivos."
                )

            for asset in capture["assets"]:

                path = (
                    ImageIngestionService
                    .resolve_managed_path(
                        asset["storage_path"]
                    )
                )

                if not path.exists():
                    raise InvalidCampaignProcessingError(
                        "No existe el archivo físico "
                        f"registrado para "
                        f"{capture['capture_code']} / "
                        f"{asset['band']}: {path}"
                    )

                if not path.is_file():
                    raise InvalidCampaignProcessingError(
                        "La entrada registrada no "
                        f"corresponde a un archivo: "
                        f"{path}"
                    )

                input_files.append(
                    str(path)
                )

        return tuple(input_files)

    @classmethod
    def process_campaign(
        cls,
        *,
        campaign_id: int,
        backend,
    ) -> dict:

        cls._validate_backend(
            backend
        )

        campaign = (
            CampaignService.get_campaign(
                campaign_id
            )
        )

        if campaign is None:
            raise InvalidCampaignProcessingError(
                f"La campaña con ID "
                f"{campaign_id} no existe."
            )

        try:
            sensor_type = SensorType(
                campaign["sensor_type"]
            )

        except ValueError as exc:
            raise InvalidCampaignProcessingError(
                "La campaña posee un tipo "
                "de sensor no soportado."
            ) from exc

        input_files = cls._collect_inputs(
            campaign_id=campaign_id
        )

        job = ProcessingJobService.create_job(
            campaign_id=campaign_id,
            backend=backend.name,
        )

        registered_products = []

        try:
            job = (
                ProcessingJobService.start_job(
                    job["id"]
                )
            )

            if not backend.is_available():
                raise (
                    PhotogrammetryBackendUnavailableError(
                        f"El backend "
                        f"{backend.name} "
                        "no está disponible."
                    )
                )

            with TemporaryDirectory(
                prefix=(
                    f"pe2_{job['job_code']}_"
                )
            ) as output_dir:

                request = (
                    PhotogrammetryRequest(
                        campaign_id=(
                            campaign_id
                        ),
                        sensor_type=(
                            sensor_type
                        ),
                        input_files=(
                            input_files
                        ),
                        output_dir=(
                            output_dir
                        ),
                    )
                )

                result = backend.process(
                    request
                )

                if not result.success:
                    raise ProcessingExecutionError(
                        result.error_message
                        or (
                            "El backend reportó "
                            "un procesamiento fallido."
                        )
                    )

                if (
                    result.backend.strip().upper()
                    != backend.name.strip().upper()
                ):
                    raise ProcessingExecutionError(
                        "El backend devolvió un "
                        "identificador diferente "
                        "al backend ejecutado."
                    )

                if not result.products:
                    raise ProcessingExecutionError(
                        "El backend no generó "
                        "productos geoespaciales."
                    )

                for generated in result.products:

                    product = (
                        GeospatialProductService
                        .register_raster_product(
                            campaign_id=(
                                campaign_id
                            ),
                            processing_job_id=(
                                job["id"]
                            ),
                            product_type=(
                                generated
                                .product_type
                            ),
                            name=(
                                generated.name
                            ),
                            source_path=(
                                generated.path
                            ),
                        )
                    )

                    registered_products.append(
                        product
                    )

            completed_job = (
                ProcessingJobService
                .complete_job(
                    job["id"]
                )
            )

            return {
                "job": completed_job,
                "products": (
                    registered_products
                ),
                "input_file_count": len(
                    input_files
                ),
            }

        except Exception as exc:

            rollback_error = None

            try:
                (
                    GeospatialProductService
                    .delete_products_for_job(
                        job["id"]
                    )
                )

            except Exception as rollback_exc:
                rollback_error = (
                    rollback_exc
                )

            try:
                current_job = (
                    ProcessingJobService.get_job(
                        job["id"]
                    )
                )

                if (
                    current_job is not None
                    and current_job["status"]
                    in {
                        "PENDING",
                        "RUNNING",
                    }
                ):
                    ProcessingJobService.fail_job(
                        job["id"],
                        error_message=(
                            cls._error_message(
                                exc
                            )
                        ),
                    )

                if rollback_error is not None:
                    raise ProcessingExecutionError(
                        cls._error_message(exc)
                        + " | Error durante rollback: "
                        + cls._error_message(
                            rollback_error
                        )
                    ) from exc
                    
            except Exception:
                pass

            if isinstance(
                exc,
                ProcessingExecutionError,
            ):
                raise

            if isinstance(
                exc,
                PhotogrammetryBackendError,
            ):
                raise ProcessingExecutionError(
                    cls._error_message(exc)
                ) from exc

            raise ProcessingExecutionError(
                cls._error_message(exc)
            ) from exc
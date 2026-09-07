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
    def prepare_campaign(
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
            SensorType(
                campaign["sensor_type"]
            )

        except ValueError as exc:
            raise InvalidCampaignProcessingError(
                "La campaña posee un tipo "
                "de sensor no soportado."
            ) from exc

        # Validamos las entradas antes de crear
        # un ProcessingJob persistente.
        cls._collect_inputs(
            campaign_id=campaign_id
        )

        # Evita tener dos trabajos PENDING/RUNNING
        # simultáneamente para la misma campaña.
        jobs = (
            ProcessingJobService.list_jobs(
                campaign_id,
                limit=50,
            )
        )

        active_job = next(
            (
                job
                for job in jobs
                if job["status"]
                in {
                    "PENDING",
                    "RUNNING",
                }
            ),
            None,
        )

        if active_job is not None:
            raise InvalidCampaignProcessingError(
                "La campaña ya posee un trabajo "
                "de procesamiento activo: "
                f"{active_job['job_code']} "
                f"({active_job['status']})."
            )

        return (
            ProcessingJobService.create_job(
                campaign_id=campaign_id,
                backend=backend.name,
            )
        )
        
    @classmethod
    def execute_job(
        cls,
        *,
        job_id: int,
        backend,
    ) -> dict:

        cls._validate_backend(
            backend
        )

        job = (
            ProcessingJobService.get_job(
                job_id
            )
        )

        if job is None:
            raise InvalidCampaignProcessingError(
                f"El trabajo con ID "
                f"{job_id} no existe."
            )

        registered_products = []

        try:

            if (
                job["status"]
                != "PENDING"
            ):
                raise InvalidCampaignProcessingError(
                    "Solo puede ejecutarse un "
                    "trabajo en estado PENDING."
                )

            normalized_backend = (
                backend.name
                .strip()
                .upper()
            )

            if (
                job["backend"]
                .strip()
                .upper()
                != normalized_backend
            ):
                raise InvalidCampaignProcessingError(
                    "El backend del trabajo "
                    "no coincide con el backend "
                    "suministrado para ejecutarlo."
                )

            campaign_id = (
                job["campaign_id"]
            )

            campaign = (
                CampaignService.get_campaign(
                    campaign_id
                )
            )

            if campaign is None:
                raise InvalidCampaignProcessingError(
                    "La campaña asociada al "
                    "trabajo no existe."
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

            input_files = (
                cls._collect_inputs(
                    campaign_id=campaign_id
                )
            )

            job = (
                ProcessingJobService.start_job(
                    job_id
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
                    result.backend
                    .strip()
                    .upper()
                    != normalized_backend
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
                                job_id
                            ),
                            product_type=(
                                generated.product_type
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
                    job_id
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
            state_error = None

            try:
                (
                    GeospatialProductService
                    .delete_products_for_job(
                        job_id
                    )
                )

            except Exception as rollback_exc:
                rollback_error = (
                    rollback_exc
                )

            try:

                current_job = (
                    ProcessingJobService
                    .get_job(
                        job_id
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
                    (
                        ProcessingJobService
                        .fail_job(
                            job_id,
                            error_message=(
                                cls._error_message(
                                    exc
                                )
                            ),
                        )
                    )

            except Exception as state_exc:
                state_error = (
                    state_exc
                )

            error_message = (
                cls._error_message(
                    exc
                )
            )

            if rollback_error is not None:
                error_message += (
                    " | Error durante rollback: "
                    + cls._error_message(
                        rollback_error
                    )
                )

            if state_error is not None:
                error_message += (
                    " | Error actualizando "
                    "estado del trabajo: "
                    + cls._error_message(
                        state_error
                    )
                )

            if (
                rollback_error is not None
                or state_error is not None
            ):
                raise ProcessingExecutionError(
                    error_message
                ) from exc

            if isinstance(
                exc,
                InvalidCampaignProcessingError,
            ):
                raise

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
                    cls._error_message(
                        exc
                    )
                ) from exc

            raise ProcessingExecutionError(
                cls._error_message(
                    exc
                )
            ) from exc
    
    @classmethod
    def process_campaign(
        cls,
        *,
        campaign_id: int,
        backend,
    ) -> dict:

        job = cls.prepare_campaign(
            campaign_id=campaign_id,
            backend=backend,
        )

        return cls.execute_job(
            job_id=job["id"],
            backend=backend,
        )
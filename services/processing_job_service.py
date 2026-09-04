from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from database import SessionLocal
from models import (
    Campaign,
    ProcessingJob,
    ProcessingJobStatus,
)


class ProcessingJobPersistenceError(Exception):
    """
    Error producido durante la persistencia
    de trabajos de procesamiento.
    """
    pass


class InvalidProcessingJobError(Exception):
    """
    Los datos suministrados para el trabajo
    de procesamiento no son válidos.
    """
    pass


class InvalidProcessingJobTransitionError(Exception):
    """
    Se intentó realizar una transición de estado
    no permitida.
    """
    pass


class ProcessingJobService:

    @staticmethod
    def _serialize(
        job: ProcessingJob,
    ) -> dict:

        return {
            "id": job.id,
            "job_code": job.job_code,
            "campaign_id": job.campaign_id,
            "backend": job.backend,
            "status": job.status.value,
            "created_at": (
                job.created_at.isoformat()
                if job.created_at
                else None
            ),
            "started_at": (
                job.started_at.isoformat()
                if job.started_at
                else None
            ),
            "finished_at": (
                job.finished_at.isoformat()
                if job.finished_at
                else None
            ),
            "error_message": (
                job.error_message
            ),
        }

    @staticmethod
    def _get_job_entity(
        session,
        job_id: int,
    ) -> ProcessingJob | None:

        statement = select(
            ProcessingJob
        ).where(
            ProcessingJob.id == job_id
        )

        return session.scalar(statement)

    @classmethod
    def create_job(
        cls,
        *,
        campaign_id: int,
        backend: str,
    ) -> dict:

        if (
            not isinstance(backend, str)
            or not backend.strip()
        ):
            raise InvalidProcessingJobError(
                "El nombre del backend "
                "es obligatorio."
            )

        session = SessionLocal()

        try:
            campaign = session.get(
                Campaign,
                campaign_id,
            )

            if campaign is None:
                raise InvalidProcessingJobError(
                    f"La campaña con ID "
                    f"{campaign_id} no existe."
                )

            job = ProcessingJob(
                job_code=(
                    f"TEMP-{uuid4().hex}"
                ),
                campaign_id=campaign_id,
                backend=backend.strip().upper(),
                status=(
                    ProcessingJobStatus.PENDING
                ),
            )

            session.add(job)
            session.flush()

            today = datetime.now(
                timezone.utc
            ).strftime(
                "%Y%m%d"
            )

            job.job_code = (
                f"PJ-{today}-{job.id:04d}"
            )

            session.commit()
            session.refresh(job)

            return cls._serialize(job)

        except InvalidProcessingJobError:
            session.rollback()
            raise

        except SQLAlchemyError as exc:
            session.rollback()

            raise ProcessingJobPersistenceError(
                "No fue posible crear "
                f"el trabajo: {exc}"
            ) from exc

        finally:
            session.close()

    @classmethod
    def start_job(
        cls,
        job_id: int,
    ) -> dict:

        session = SessionLocal()

        try:
            job = cls._get_job_entity(
                session,
                job_id,
            )

            if job is None:
                raise InvalidProcessingJobError(
                    f"El trabajo con ID "
                    f"{job_id} no existe."
                )

            if (
                job.status
                != ProcessingJobStatus.PENDING
            ):
                raise (
                    InvalidProcessingJobTransitionError(
                        "Solo puede iniciarse un "
                        "trabajo en estado PENDING."
                    )
                )

            job.status = (
                ProcessingJobStatus.RUNNING
            )

            job.started_at = datetime.now(
                timezone.utc
            )

            job.error_message = None

            session.commit()
            session.refresh(job)

            return cls._serialize(job)

        except (
            InvalidProcessingJobError,
            InvalidProcessingJobTransitionError,
        ):
            session.rollback()
            raise

        except SQLAlchemyError as exc:
            session.rollback()

            raise ProcessingJobPersistenceError(
                "No fue posible iniciar "
                f"el trabajo: {exc}"
            ) from exc

        finally:
            session.close()

    @classmethod
    def complete_job(
        cls,
        job_id: int,
    ) -> dict:

        session = SessionLocal()

        try:
            job = cls._get_job_entity(
                session,
                job_id,
            )

            if job is None:
                raise InvalidProcessingJobError(
                    f"El trabajo con ID "
                    f"{job_id} no existe."
                )

            if (
                job.status
                != ProcessingJobStatus.RUNNING
            ):
                raise (
                    InvalidProcessingJobTransitionError(
                        "Solo puede completarse un "
                        "trabajo en estado RUNNING."
                    )
                )

            job.status = (
                ProcessingJobStatus.COMPLETED
            )

            job.finished_at = datetime.now(
                timezone.utc
            )

            job.error_message = None

            session.commit()
            session.refresh(job)

            return cls._serialize(job)

        except (
            InvalidProcessingJobError,
            InvalidProcessingJobTransitionError,
        ):
            session.rollback()
            raise

        except SQLAlchemyError as exc:
            session.rollback()

            raise ProcessingJobPersistenceError(
                "No fue posible completar "
                f"el trabajo: {exc}"
            ) from exc

        finally:
            session.close()

    @classmethod
    def fail_job(
        cls,
        job_id: int,
        *,
        error_message: str,
    ) -> dict:

        if (
            not isinstance(error_message, str)
            or not error_message.strip()
        ):
            raise InvalidProcessingJobError(
                "El mensaje de error "
                "es obligatorio."
            )

        session = SessionLocal()

        try:
            job = cls._get_job_entity(
                session,
                job_id,
            )

            if job is None:
                raise InvalidProcessingJobError(
                    f"El trabajo con ID "
                    f"{job_id} no existe."
                )

            if job.status not in {
                ProcessingJobStatus.PENDING,
                ProcessingJobStatus.RUNNING,
            }:
                raise (
                    InvalidProcessingJobTransitionError(
                        "Solo puede marcarse FAILED "
                        "un trabajo PENDING o RUNNING."
                    )
                )

            job.status = (
                ProcessingJobStatus.FAILED
            )

            job.finished_at = datetime.now(
                timezone.utc
            )

            job.error_message = (
                error_message.strip()
            )

            session.commit()
            session.refresh(job)

            return cls._serialize(job)

        except (
            InvalidProcessingJobError,
            InvalidProcessingJobTransitionError,
        ):
            session.rollback()
            raise

        except SQLAlchemyError as exc:
            session.rollback()

            raise ProcessingJobPersistenceError(
                "No fue posible marcar "
                f"el trabajo como FAILED: {exc}"
            ) from exc

        finally:
            session.close()

    @classmethod
    def get_job(
        cls,
        job_id: int,
    ) -> dict | None:

        session = SessionLocal()

        try:
            job = cls._get_job_entity(
                session,
                job_id,
            )

            if job is None:
                return None

            return cls._serialize(job)

        except SQLAlchemyError as exc:
            raise ProcessingJobPersistenceError(
                "No fue posible consultar "
                f"el trabajo: {exc}"
            ) from exc

        finally:
            session.close()

    @classmethod
    def list_jobs(
        cls,
        campaign_id: int,
        *,
        limit: int = 50,
    ) -> list[dict]:

        session = SessionLocal()

        try:
            campaign = session.get(
                Campaign,
                campaign_id,
            )

            if campaign is None:
                raise InvalidProcessingJobError(
                    f"La campaña con ID "
                    f"{campaign_id} no existe."
                )

            limit = max(
                1,
                min(limit, 500),
            )

            statement = (
                select(ProcessingJob)
                .where(
                    ProcessingJob.campaign_id
                    == campaign_id
                )
                .order_by(
                    ProcessingJob.id.desc()
                )
                .limit(limit)
            )

            jobs = session.scalars(
                statement
            ).all()

            return [
                cls._serialize(job)
                for job in jobs
            ]

        except InvalidProcessingJobError:
            raise

        except SQLAlchemyError as exc:
            raise ProcessingJobPersistenceError(
                "No fue posible listar "
                f"los trabajos: {exc}"
            ) from exc

        finally:
            session.close()
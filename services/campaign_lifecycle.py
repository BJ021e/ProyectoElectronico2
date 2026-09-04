from __future__ import annotations

from sqlalchemy import select

from models import (
    Campaign,
    CampaignStatus,
    CaptureStatus,
    ImageCapture,
)


class CampaignLifecycleError(Exception):
    """
    Se intentó realizar una operación incompatible
    con el estado actual de una campaña.
    """
    pass


class CampaignLifecyclePolicy:

    PROCESSABLE_STATUSES = {
        CampaignStatus.READY,
        CampaignStatus.COMPLETED,
        CampaignStatus.ERROR,
    }

    CAPTURE_MUTABLE_STATUSES = {
        CampaignStatus.CREATED,
        CampaignStatus.CAPTURING,
        CampaignStatus.READY,
        CampaignStatus.ERROR,
    }

    @classmethod
    def assert_capture_mutation_allowed(
        cls,
        campaign: Campaign,
    ) -> None:

        if (
            campaign.status
            not in cls.CAPTURE_MUTABLE_STATUSES
        ):
            raise CampaignLifecycleError(
                "No pueden modificarse las capturas "
                "de una campaña en estado "
                f"{campaign.status.value}."
            )

    @classmethod
    def synchronize_capture_state(
        cls,
        session,
        campaign: Campaign,
    ) -> CampaignStatus:
        """
        Deriva el estado de adquisición a partir
        de las capturas persistidas.

        0 capturas
        -> CREATED

        alguna captura ERROR
        -> ERROR

        todas READY
        -> READY

        cualquier otro caso
        -> CAPTURING
        """

        cls.assert_capture_mutation_allowed(
            campaign
        )

        statement = (
            select(ImageCapture)
            .where(
                ImageCapture.campaign_id
                == campaign.id
            )
            .order_by(
                ImageCapture.sequence.asc()
            )
        )

        captures = session.scalars(
            statement
        ).all()

        if not captures:

            campaign.status = (
                CampaignStatus.CREATED
            )

            return campaign.status

        if any(
            capture.status
            == CaptureStatus.ERROR
            for capture in captures
        ):

            campaign.status = (
                CampaignStatus.ERROR
            )

            return campaign.status

        if all(
            capture.status
            == CaptureStatus.READY
            for capture in captures
        ):

            campaign.status = (
                CampaignStatus.READY
            )

            return campaign.status

        campaign.status = (
            CampaignStatus.CAPTURING
        )

        return campaign.status

    @classmethod
    def assert_processing_allowed(
        cls,
        campaign: Campaign,
    ) -> None:

        if (
            campaign.status
            not in cls.PROCESSABLE_STATUSES
        ):
            raise CampaignLifecycleError(
                "La campaña no puede iniciar "
                "procesamiento desde el estado "
                f"{campaign.status.value}."
            )

    @classmethod
    def mark_processing(
        cls,
        campaign: Campaign,
    ) -> CampaignStatus:

        cls.assert_processing_allowed(
            campaign
        )

        campaign.status = (
            CampaignStatus.PROCESSING
        )

        return campaign.status

    @classmethod
    def mark_completed(
        cls,
        campaign: Campaign,
    ) -> CampaignStatus:

        if (
            campaign.status
            != CampaignStatus.PROCESSING
        ):
            raise CampaignLifecycleError(
                "Solo una campaña PROCESSING "
                "puede pasar a COMPLETED."
            )

        campaign.status = (
            CampaignStatus.COMPLETED
        )

        return campaign.status

    @classmethod
    def mark_error(
        cls,
        campaign: Campaign,
    ) -> CampaignStatus:

        if (
            campaign.status
            != CampaignStatus.PROCESSING
        ):
            raise CampaignLifecycleError(
                "Solo una campaña PROCESSING "
                "puede pasar a ERROR por "
                "fallo de procesamiento."
            )

        campaign.status = (
            CampaignStatus.ERROR
        )

        return campaign.status
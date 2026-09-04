from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(
    frozen=True
)
class IntegrationStatus:
    """
    Estado diagnóstico de la integración
    técnica con el proveedor de dron.

    Es independiente del lifecycle persistente
    del Flight.
    """

    provider: str | None

    configured: bool

    transport_connected: bool

    aircraft_online: bool

    telemetry_available: bool

    telemetry_fresh: bool

    last_telemetry_at: datetime | None

    telemetry_age_seconds: float | None

    last_error: str | None

    health: str


    def to_dict(
        self
    ) -> dict:

        return {
            "provider":
                self.provider,

            "configured":
                self.configured,

            "transport_connected":
                self.transport_connected,

            "aircraft_online":
                self.aircraft_online,

            "telemetry_available":
                self.telemetry_available,

            "telemetry_fresh":
                self.telemetry_fresh,

            "last_telemetry_at": (
                self.last_telemetry_at.isoformat()
                if self.last_telemetry_at
                else None
            ),

            "telemetry_age_seconds":
                self.telemetry_age_seconds,

            "last_error":
                self.last_error,

            "health":
                self.health,
        }
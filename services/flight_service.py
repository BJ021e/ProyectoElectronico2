from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from database import SessionLocal
from models.flight import Flight, FlightStatus


class FlightPersistenceError(Exception):
    """
    Error producido durante una operación de persistencia
    relacionada con vuelos.
    """
    pass


class FlightService:
    @staticmethod
    def _serialize(flight: Flight) -> dict:
        """
        Convierte una entidad Flight en una estructura
        independiente de la sesión de SQLAlchemy.
        """
        return {
            "id": flight.id,
            "flight_code": flight.flight_code,
            "name": flight.name,
            "status": flight.status.value,
            "started_at": (
                flight.started_at.isoformat()
                if flight.started_at
                else None
            ),
            "finished_at": (
                flight.finished_at.isoformat()
                if flight.finished_at
                else None
            ),
            "created_at": (
                flight.created_at.isoformat()
                if flight.created_at
                else None
            ),
            "notes": flight.notes,
        }

    @staticmethod
    def create_flight(
        name: str | None = None,
        notes: str | None = None
    ) -> dict:
        """
        Crea un nuevo vuelo en estado CREATED.

        El código definitivo utiliza el ID generado por la BD:
        FL-YYYYMMDD-0001
        """
        session = SessionLocal()

        try:
            provisional_code = f"TEMP-{uuid4().hex}"

            flight = Flight(
                flight_code=provisional_code,
                name=name,
                notes=notes,
                status=FlightStatus.CREATED
            )

            session.add(flight)

            # Obtiene el ID autoincremental sin confirmar aún
            session.flush()

            today = datetime.now(timezone.utc).strftime("%Y%m%d")

            flight.flight_code = (
                f"FL-{today}-{flight.id:04d}"
            )

            session.commit()
            session.refresh(flight)

            return FlightService._serialize(flight)

        except SQLAlchemyError as exc:
            session.rollback()

            raise FlightPersistenceError(
                f"No fue posible crear el vuelo: {exc}"
            ) from exc

        finally:
            session.close()

    @staticmethod
    def get_flight(flight_id: int) -> dict | None:
        """
        Recupera un vuelo mediante su ID.
        """
        session = SessionLocal()

        try:
            statement = select(Flight).where(
                Flight.id == flight_id
            )

            flight = session.scalar(statement)

            if flight is None:
                return None

            return FlightService._serialize(flight)

        except SQLAlchemyError as exc:
            raise FlightPersistenceError(
                f"No fue posible consultar el vuelo: {exc}"
            ) from exc

        finally:
            session.close()
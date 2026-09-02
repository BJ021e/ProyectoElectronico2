from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from database import SessionLocal

from models import (
    Flight,
    FlightStatus,
    Route,
    RouteStatus,
    FlightRouteAssignment,
)


class FlightRoutePersistenceError(Exception):
    """
    Error producido durante operaciones de persistencia
    relacionadas con la asignación Flight-Route.
    """
    pass


class InvalidFlightRouteAssignmentError(Exception):
    """
    Error producido cuando una asignación Flight-Route
    incumple las reglas de negocio.
    """
    pass


class FlightRouteService:

    @staticmethod
    def _serialize(
        assignment: FlightRouteAssignment
    ) -> dict:

        return {
            "id": assignment.id,

            "flight_id": assignment.flight_id,

            "route_id": assignment.route_id,

            "assigned_at": (
                assignment.assigned_at.isoformat()
                if assignment.assigned_at
                else None
            ),

            "flight": {
                "id": assignment.flight.id,
                "flight_code":
                    assignment.flight.flight_code,
                "name":
                    assignment.flight.name,
                "status":
                    assignment.flight.status.value,
            },

            "route": {
                "id": assignment.route.id,
                "route_code":
                    assignment.route.route_code,
                "name":
                    assignment.route.name,
                "status":
                    assignment.route.status.value,
            },
        }


    @staticmethod
    def assign_route(
        flight_id: int,
        route_id: int
    ) -> dict:
        """
        Asigna una ruta READY a un vuelo CREATED.
        """

        session = SessionLocal()

        try:

            flight = session.get(
                Flight,
                flight_id
            )

            if flight is None:

                raise InvalidFlightRouteAssignmentError(
                    f"El vuelo con ID {flight_id} no existe."
                )


            route = session.get(
                Route,
                route_id
            )

            if route is None:

                raise InvalidFlightRouteAssignmentError(
                    f"La ruta con ID {route_id} no existe."
                )


            if flight.status != FlightStatus.CREATED:

                raise InvalidFlightRouteAssignmentError(
                    f"No se puede asignar una ruta al vuelo "
                    f"{flight.flight_code} porque está en estado "
                    f"{flight.status.value}."
                )


            if route.status != RouteStatus.READY:

                raise InvalidFlightRouteAssignmentError(
                    f"No se puede utilizar la ruta "
                    f"{route.route_code} porque está en estado "
                    f"{route.status.value}."
                )


            existing_statement = (
                select(
                    FlightRouteAssignment
                )
                .where(
                    FlightRouteAssignment.flight_id
                    == flight_id
                )
            )


            existing_assignment = (
                session.scalar(
                    existing_statement
                )
            )


            if existing_assignment is not None:

                raise InvalidFlightRouteAssignmentError(
                    f"El vuelo {flight.flight_code} "
                    "ya tiene una ruta asignada."
                )


            assignment = (
                FlightRouteAssignment(
                    flight_id=flight_id,
                    route_id=route_id
                )
            )


            session.add(
                assignment
            )

            session.commit()


            # Volvemos a consultar con las relaciones
            # cargadas explícitamente.
            statement = (
                select(
                    FlightRouteAssignment
                )
                .options(
                    selectinload(
                        FlightRouteAssignment.flight
                    ),
                    selectinload(
                        FlightRouteAssignment.route
                    )
                )
                .where(
                    FlightRouteAssignment.id
                    == assignment.id
                )
            )


            assignment = session.scalar(
                statement
            )


            return (
                FlightRouteService._serialize(
                    assignment
                )
            )


        except InvalidFlightRouteAssignmentError:

            session.rollback()
            raise


        except SQLAlchemyError as exc:

            session.rollback()

            raise FlightRoutePersistenceError(
                f"No fue posible asignar la ruta al vuelo: {exc}"
            ) from exc


        finally:

            session.close()


    @staticmethod
    def get_assignment_for_flight(
        flight_id: int
    ) -> dict | None:
        """
        Recupera la ruta planificada asignada
        a un vuelo.
        """

        session = SessionLocal()

        try:

            statement = (
                select(
                    FlightRouteAssignment
                )
                .options(
                    selectinload(
                        FlightRouteAssignment.flight
                    ),
                    selectinload(
                        FlightRouteAssignment.route
                    )
                )
                .where(
                    FlightRouteAssignment.flight_id
                    == flight_id
                )
            )


            assignment = session.scalar(
                statement
            )


            if assignment is None:
                return None


            return (
                FlightRouteService._serialize(
                    assignment
                )
            )


        except SQLAlchemyError as exc:

            raise FlightRoutePersistenceError(
                f"No fue posible consultar la ruta "
                f"asignada al vuelo: {exc}"
            ) from exc


        finally:

            session.close()
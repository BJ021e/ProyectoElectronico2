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

from services.flight_service import (
    FlightService,
    FlightPersistenceError,
    InvalidFlightTransitionError,
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
            
    @staticmethod
    def start_assigned_flight(
        flight_id: int
    ) -> dict:
        """
        Inicia un vuelo que ya tiene una ruta
        planificada válida asignada.

        Requisitos:
        - El vuelo debe tener una asignación.
        - El vuelo debe estar CREATED.
        - La ruta asignada debe continuar READY.
        """

        assignment = (
            FlightRouteService
            .get_assignment_for_flight(
                flight_id
            )
        )

        if assignment is None:
            raise InvalidFlightRouteAssignmentError(
                f"El vuelo con ID {flight_id} "
                "no tiene una ruta planificada asignada."
            )


        flight_data = assignment["flight"]
        route_data = assignment["route"]


        if (
            flight_data["status"]
            != FlightStatus.CREATED.value
        ):
            raise InvalidFlightRouteAssignmentError(
                f"No se puede iniciar el vuelo "
                f"{flight_data['flight_code']} "
                f"porque está en estado "
                f"{flight_data['status']}."
            )


        if (
            route_data["status"]
            != RouteStatus.READY.value
        ):
            raise InvalidFlightRouteAssignmentError(
                f"No se puede iniciar el vuelo porque "
                f"la ruta {route_data['route_code']} "
                f"está en estado "
                f"{route_data['status']}."
            )


        try:

            flight = FlightService.start_flight(
                flight_id
            )

        except InvalidFlightTransitionError as exc:

            raise InvalidFlightRouteAssignmentError(
                str(exc)
            ) from exc

        except FlightPersistenceError as exc:

            raise FlightRoutePersistenceError(
                f"No fue posible iniciar el vuelo "
                f"con ruta asignada: {exc}"
            ) from exc


        return {
            "flight": flight,
            "planned_route": {
                "id": route_data["id"],
                "route_code":
                    route_data["route_code"],
                "name":
                    route_data["name"],
                "status":
                    route_data["status"],
            },
            "assignment_id":
                assignment["id"],
        }
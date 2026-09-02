from services.flight_service import (
    FlightService,
    FlightPersistenceError,
)

from services.route_service import (
    RouteService,
    RoutePersistenceError,
)

from services.telemetry_service import (
    TelemetryService,
    TelemetryPersistenceError,
)

from services.flight_route_service import (
    FlightRouteService,
    FlightRoutePersistenceError,
)


class MissionPersistenceError(Exception):
    """
    Error producido al construir la información
    consolidada de una misión.
    """
    pass


class MissionNotFoundError(Exception):
    """
    Error producido cuando el vuelo solicitado
    no existe.
    """
    pass


class MissionService:

    @staticmethod
    def get_mission(
        flight_id: int
    ) -> dict:
        """
        Construye una vista consolidada de una misión:

        - información del vuelo;
        - ruta planificada, si existe;
        - waypoints;
        - trayectoria ejecutada.
        """

        try:

            # -----------------------------------------
            # Flight
            # -----------------------------------------

            flight = FlightService.get_flight(
                flight_id
            )

            if flight is None:
                raise MissionNotFoundError(
                    f"El vuelo con ID {flight_id} no existe."
                )


            # -----------------------------------------
            # Asignación Flight ↔ Route
            # -----------------------------------------

            assignment = (
                FlightRouteService
                .get_assignment_for_flight(
                    flight_id
                )
            )


            planned_route = None

            assignment_summary = None


            if assignment is not None:

                route_id = assignment[
                    "route_id"
                ]

                planned_route = (
                    RouteService.get_route(
                        route_id
                    )
                )

                assignment_summary = {
                    "id":
                        assignment["id"],

                    "assigned_at":
                        assignment["assigned_at"],
                }


            # -----------------------------------------
            # Telemetría ejecutada
            # -----------------------------------------

            telemetry_points = (
                TelemetryService
                .get_flight_points(
                    flight_id
                )
            )


            gps_points = [
                point
                for point in telemetry_points
                if (
                    point["latitude"] is not None
                    and
                    point["longitude"] is not None
                )
            ]


            # -----------------------------------------
            # Respuesta consolidada
            # -----------------------------------------

            return {

                "flight":
                    flight,

                "assignment":
                    assignment_summary,

                "planned_route":
                    planned_route,

                "executed_trajectory": {

                    "telemetry_count":
                        len(
                            telemetry_points
                        ),

                    "gps_point_count":
                        len(
                            gps_points
                        ),

                    "points":
                        gps_points,
                },
            }


        except MissionNotFoundError:
            raise


        except (
            FlightPersistenceError,
            RoutePersistenceError,
            TelemetryPersistenceError,
            FlightRoutePersistenceError,
        ) as exc:

            raise MissionPersistenceError(
                f"No fue posible construir la misión: {exc}"
            ) from exc
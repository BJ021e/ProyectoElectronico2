from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from database import SessionLocal
from models import Route, RouteStatus, Waypoint


class RoutePersistenceError(Exception):
    """
    Error producido durante una operación de persistencia
    relacionada con rutas.
    """
    pass


class InvalidRouteError(Exception):
    """
    Error producido cuando una ruta no cumple
    las reglas mínimas de negocio.
    """
    pass


class RouteService:
    @staticmethod
    def _serialize_waypoint(
        waypoint: Waypoint
    ) -> dict:
        return {
            "id": waypoint.id,
            "route_id": waypoint.route_id,
            "sequence": waypoint.sequence,
            "latitude": waypoint.latitude,
            "longitude": waypoint.longitude,
            "altitude": waypoint.altitude,
            "speed": waypoint.speed,
            "heading": waypoint.heading,
            "action": waypoint.action,
            "created_at": (
                waypoint.created_at.isoformat()
                if waypoint.created_at
                else None
            ),
        }

    @staticmethod
    def _serialize(route: Route) -> dict:
        return {
            "id": route.id,
            "route_code": route.route_code,
            "name": route.name,
            "description": route.description,
            "status": route.status.value,
            "created_at": (
                route.created_at.isoformat()
                if route.created_at
                else None
            ),
            "updated_at": (
                route.updated_at.isoformat()
                if route.updated_at
                else None
            ),
            "waypoint_count": len(route.waypoints),
            "waypoints": [
                RouteService._serialize_waypoint(waypoint)
                for waypoint in route.waypoints
            ],
        }

    @staticmethod
    def create_route(
        name: str,
        description: str | None = None
    ) -> dict:
        """
        Crea una nueva ruta en estado DRAFT.
        """

        if not name or not name.strip():
            raise InvalidRouteError(
                "El nombre de la ruta es obligatorio."
            )

        session = SessionLocal()

        try:
            provisional_code = (
                f"TEMP-{uuid4().hex}"
            )

            route = Route(
                route_code=provisional_code,
                name=name.strip(),
                description=(
                    description.strip()
                    if description
                    else None
                ),
                status=RouteStatus.DRAFT
            )

            session.add(route)

            # Obtiene el ID autoincremental
            # antes del commit definitivo.
            session.flush()

            today = datetime.now(
                timezone.utc
            ).strftime("%Y%m%d")

            route.route_code = (
                f"RT-{today}-{route.id:04d}"
            )

            session.commit()
            session.refresh(route)

            return RouteService._serialize(
                route
            )

        except InvalidRouteError:
            session.rollback()
            raise

        except SQLAlchemyError as exc:
            session.rollback()

            raise RoutePersistenceError(
                f"No fue posible crear la ruta: {exc}"
            ) from exc

        finally:
            session.close()

    @staticmethod
    def get_route(
        route_id: int
    ) -> dict | None:
        """
        Recupera una ruta junto con sus waypoints
        ordenados.
        """

        session = SessionLocal()

        try:
            statement = (
                select(Route)
                .options(
                    selectinload(
                        Route.waypoints
                    )
                )
                .where(
                    Route.id == route_id
                )
            )

            route = session.scalar(
                statement
            )

            if route is None:
                return None

            return RouteService._serialize(
                route
            )

        except SQLAlchemyError as exc:
            raise RoutePersistenceError(
                f"No fue posible consultar la ruta: {exc}"
            ) from exc

        finally:
            session.close()
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
    def _validate_coordinates(
        latitude: float,
        longitude: float
    ) -> None:
        if not (-90 <= latitude <= 90):
            raise InvalidRouteError(
                "La latitud debe estar entre -90 y 90."
            )

        if not (-180 <= longitude <= 180):
            raise InvalidRouteError(
                "La longitud debe estar entre -180 y 180."
            )


    @staticmethod
    def _validate_waypoint_values(
        altitude: float | None,
        speed: float | None,
        heading: float | None
    ) -> None:
        if altitude is not None and altitude < 0:
            raise InvalidRouteError(
                "La altitud objetivo no puede ser negativa."
            )

        if speed is not None and speed < 0:
            raise InvalidRouteError(
                "La velocidad objetivo no puede ser negativa."
            )

        if heading is not None and not (0 <= heading <= 360):
            raise InvalidRouteError(
                "El heading debe estar entre 0 y 360 grados."
            )
    @staticmethod
    
    @staticmethod
    def add_waypoint(
        route_id: int,
        latitude: float,
        longitude: float,
        altitude: float | None = None,
        speed: float | None = None,
        heading: float | None = None,
        action: str | None = None,
        sequence: int | None = None,
    ) -> dict:
        """
        Añade un waypoint a una ruta DRAFT.

        Si no se especifica sequence, se coloca
        automáticamente al final de la ruta.
        """

        RouteService._validate_coordinates(
            latitude,
            longitude
        )

        RouteService._validate_waypoint_values(
            altitude,
            speed,
            heading
        )

        session = SessionLocal()

        try:
            statement = (
                select(Route)
                .options(
                    selectinload(Route.waypoints)
                )
                .where(Route.id == route_id)
            )

            route = session.scalar(statement)

            if route is None:
                raise InvalidRouteError(
                    f"La ruta con ID {route_id} no existe."
                )

            if route.status != RouteStatus.DRAFT:
                raise InvalidRouteError(
                    f"No se pueden modificar waypoints de "
                    f"{route.route_code} porque está en estado "
                    f"{route.status.value}."
                )

            if sequence is None:
                if route.waypoints:
                    sequence = (
                        max(
                            waypoint.sequence
                            for waypoint in route.waypoints
                        )
                        + 1
                    )
                else:
                    sequence = 1

            if sequence < 1:
                raise InvalidRouteError(
                    "La secuencia debe ser mayor o igual a 1."
                )

            if any(
                waypoint.sequence == sequence
                for waypoint in route.waypoints
            ):
                raise InvalidRouteError(
                    f"Ya existe un waypoint con "
                    f"sequence={sequence} en esta ruta."
                )

            waypoint = Waypoint(
                route_id=route_id,
                sequence=sequence,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                speed=speed,
                heading=heading,
                action=(
                    action.strip()
                    if action
                    else None
                ),
            )

            session.add(waypoint)
            session.commit()
            session.refresh(waypoint)

            return RouteService._serialize_waypoint(
                waypoint
            )

        except InvalidRouteError:
            session.rollback()
            raise

        except SQLAlchemyError as exc:
            session.rollback()

            raise RoutePersistenceError(
                f"No fue posible añadir el waypoint: {exc}"
            ) from exc

        finally:
            session.close()
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
            
    @staticmethod
    def _validate_route_ready(route: Route) -> None:
        """
        Verifica que una ruta cumpla las condiciones mínimas
        necesarias para pasar a estado READY.
        """

        waypoints = route.waypoints

        if len(waypoints) < 2:
            raise InvalidRouteError(
                "La ruta necesita al menos 2 waypoints."
            )

        # -------------------------------------------------
        # Secuencias continuas
        # -------------------------------------------------

        sequences = [
            waypoint.sequence
            for waypoint in waypoints
        ]

        expected_sequences = list(
            range(1, len(waypoints) + 1)
        )

        if sequences != expected_sequences:
            raise InvalidRouteError(
                "Las secuencias de los waypoints deben ser "
                "continuas desde 1 hasta N."
            )

        # -------------------------------------------------
        # Validación individual
        # -------------------------------------------------

        for waypoint in waypoints:

            RouteService._validate_coordinates(
                waypoint.latitude,
                waypoint.longitude
            )

            if waypoint.altitude is None:
                raise InvalidRouteError(
                    f"El waypoint {waypoint.sequence} "
                    "no tiene altitud objetivo."
                )

            if waypoint.altitude <= 0:
                raise InvalidRouteError(
                    f"La altitud del waypoint "
                    f"{waypoint.sequence} debe ser mayor que 0."
                )

            if (
                waypoint.speed is not None
                and waypoint.speed <= 0
            ):
                raise InvalidRouteError(
                    f"La velocidad del waypoint "
                    f"{waypoint.sequence} debe ser mayor que 0."
                )

            if (
                waypoint.heading is not None
                and not (0 <= waypoint.heading <= 360)
            ):
                raise InvalidRouteError(
                    f"El heading del waypoint "
                    f"{waypoint.sequence} debe estar "
                    "entre 0 y 360 grados."
                )

        # -------------------------------------------------
        # Coordenadas consecutivas duplicadas
        # -------------------------------------------------

        for previous, current in zip(
            waypoints,
            waypoints[1:]
        ):
            if (
                previous.latitude == current.latitude
                and
                previous.longitude == current.longitude
            ):
                raise InvalidRouteError(
                    f"Los waypoints {previous.sequence} y "
                    f"{current.sequence} tienen las mismas "
                    "coordenadas."
                )
                
    @staticmethod
    def publish_route(
        route_id: int
    ) -> dict:
        """
        Valida una ruta DRAFT y, si cumple todas las
        condiciones, la cambia a READY.
        """

        session = SessionLocal()

        try:

            statement = (
                select(Route)
                .options(
                    selectinload(Route.waypoints)
                )
                .where(
                    Route.id == route_id
                )
            )

            route = session.scalar(statement)

            if route is None:
                raise InvalidRouteError(
                    f"La ruta con ID {route_id} no existe."
                )

            if route.status != RouteStatus.DRAFT:
                raise InvalidRouteError(
                    f"La ruta {route.route_code} no puede "
                    f"publicarse desde el estado "
                    f"{route.status.value}."
                )

            RouteService._validate_route_ready(
                route
            )

            route.status = RouteStatus.READY
            route.updated_at = datetime.now(
                timezone.utc
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
                f"No fue posible publicar la ruta: {exc}"
            ) from exc

        finally:
            session.close()
            
    @staticmethod
    def list_routes(
        limit: int = 50,
        status: RouteStatus | None = None
    ) -> list[dict]:
        """
        Recupera las rutas más recientes.

        Opcionalmente permite filtrar por estado.
        """

        session = SessionLocal()

        try:
            limit = max(
                1,
                min(limit, 500)
            )

            statement = (
                select(Route)
                .options(
                    selectinload(
                        Route.waypoints
                    )
                )
                .order_by(
                    Route.id.desc()
                )
                .limit(limit)
            )

            if status is not None:
                statement = statement.where(
                    Route.status == status
                )

            routes = session.scalars(
                statement
            ).all()

            return [
                RouteService._serialize(route)
                for route in routes
            ]

        except SQLAlchemyError as exc:
            raise RoutePersistenceError(
                f"No fue posible listar las rutas: {exc}"
            ) from exc

        finally:
            session.close()
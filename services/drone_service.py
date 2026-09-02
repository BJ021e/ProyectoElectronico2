from __future__ import annotations

from threading import RLock

from drone import (
    DroneProvider,
    DroneSimulator,
    DroneSimulatorError,
    DroneState,
)

from services.route_service import (
    RouteService,
    RoutePersistenceError,
)


class DroneServiceError(Exception):
    """
    Error general de la capa operacional del dron.
    """

    pass


class DroneProviderNotConfiguredError(
    DroneServiceError
):
    """
    No existe todavía un proveedor de dron activo.
    """

    pass


class InvalidDroneProviderError(
    DroneServiceError
):
    """
    El proveedor indicado no cumple DroneProvider.
    """

    pass


class DroneService:
    """
    Punto central de acceso al proveedor de dron activo.

    La aplicación debe consultar DroneService y no
    depender directamente de DroneSimulator o de una
    futura implementación DJI.
    """

    _provider: DroneProvider | None = None

    _lock = RLock()


    @classmethod
    def set_provider(
        cls,
        provider: DroneProvider
    ) -> None:
        """
        Cambia el proveedor activo.
        """

        if not isinstance(
            provider,
            DroneProvider
        ):
            raise InvalidDroneProviderError(
                "El proveedor no cumple "
                "el contrato DroneProvider."
            )

        with cls._lock:
            cls._provider = provider


    @classmethod
    def clear_provider(cls) -> None:
        """
        Elimina el proveedor activo.
        """

        with cls._lock:
            cls._provider = None


    @classmethod
    def has_provider(cls) -> bool:
        """
        Indica si existe un proveedor configurado.
        """

        with cls._lock:
            return cls._provider is not None


    @classmethod
    def get_provider_name(
        cls
    ) -> str | None:
        """
        Devuelve el nombre del proveedor activo.
        """

        with cls._lock:

            if cls._provider is None:
                return None

            return cls._provider.name


    @classmethod
    def _require_provider(
        cls
    ) -> DroneProvider:
        """
        Recupera el proveedor o genera un error
        controlado si todavía no existe.
        """

        if cls._provider is None:
            raise DroneProviderNotConfiguredError(
                "No existe un proveedor de dron "
                "configurado."
            )

        return cls._provider


    @classmethod
    def get_state(cls) -> DroneState:
        """
        Obtiene el estado normalizado del proveedor
        actualmente seleccionado.
        """

        with cls._lock:

            provider = (
                cls._require_provider()
            )

            return provider.get_state()


    @classmethod
    def get_state_dict(cls) -> dict:
        """
        Versión serializable para futuras APIs.
        """

        return cls.get_state().to_dict()


    # =================================================
    # SIMULADOR
    # =================================================

    @classmethod
    def configure_simulator(
        cls,
        route_id: int,
        *,
        step_fraction: float = 0.20,
        initial_battery: float = 100.0,
    ) -> DroneState:
        """
        Crea un DroneSimulator, carga una Route
        persistente y lo establece como proveedor
        activo.

        El simulador queda configurado pero todavía
        desconectado.
        """

        try:

            route = RouteService.get_route(
                route_id
            )

        except RoutePersistenceError as exc:

            raise DroneServiceError(
                f"No fue posible cargar la ruta: {exc}"
            ) from exc


        if route is None:
            raise DroneServiceError(
                f"La ruta con ID {route_id} no existe."
            )


        waypoints = route.get(
            "waypoints",
            []
        )


        simulator = DroneSimulator(
            step_fraction=step_fraction,
            initial_battery=initial_battery,
        )


        try:

            simulator.load_route(
                waypoints
            )

        except DroneSimulatorError as exc:

            raise DroneServiceError(
                f"No fue posible configurar "
                f"el simulador: {exc}"
            ) from exc


        cls.set_provider(
            simulator
        )


        return simulator.get_state()


    @classmethod
    def _require_simulator(
        cls
    ) -> DroneSimulator:
        """
        Recupera el proveedor activo y comprueba
        que sea específicamente DroneSimulator.
        """

        provider = cls._require_provider()


        if not isinstance(
            provider,
            DroneSimulator
        ):
            raise DroneServiceError(
                "El proveedor activo no es "
                "DroneSimulator."
            )


        return provider


    @classmethod
    def simulator_connect(
        cls
    ) -> DroneState:

        with cls._lock:

            simulator = (
                cls._require_simulator()
            )

            return simulator.connect()


    @classmethod
    def simulator_disconnect(
        cls
    ) -> DroneState:

        with cls._lock:

            simulator = (
                cls._require_simulator()
            )

            return simulator.disconnect()


    @classmethod
    def simulator_start(
        cls
    ) -> DroneState:

        with cls._lock:

            simulator = (
                cls._require_simulator()
            )

            try:

                return simulator.start()

            except DroneSimulatorError as exc:

                raise DroneServiceError(
                    str(exc)
                ) from exc


    @classmethod
    def simulator_advance(
        cls
    ) -> DroneState:

        with cls._lock:

            simulator = (
                cls._require_simulator()
            )

            try:

                return simulator.advance()

            except DroneSimulatorError as exc:

                raise DroneServiceError(
                    str(exc)
                ) from exc


    @classmethod
    def simulator_reset(
        cls
    ) -> DroneState:

        with cls._lock:

            simulator = (
                cls._require_simulator()
            )

            return simulator.reset()


    @classmethod
    def simulator_is_running(
        cls
    ) -> bool:

        with cls._lock:

            simulator = (
                cls._require_simulator()
            )

            return simulator.is_running
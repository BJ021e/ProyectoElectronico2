from __future__ import annotations

from threading import (
    Event,
    RLock,
    Thread,
    current_thread,
)

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
    _active_route_id: int | None = None

    _lock = RLock()

    _simulation_thread: Thread | None = None

    _simulation_stop_event = Event()

    _simulation_interval: float = 1.0

    _simulation_last_error: str | None = None
    
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
        cls.simulator_stop_auto()
        
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
        
        with cls._lock:
            cls._active_route_id = route_id

        return simulator.get_state()

    @classmethod
    def get_active_route_id(
        cls
    ) -> int | None:

        with cls._lock:
            return cls._active_route_id
        
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

        cls.simulator_stop_auto()


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

        cls.simulator_stop_auto()


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
    
    @classmethod
    def _simulation_worker(cls) -> None:
        """
        Worker interno que hace avanzar el simulador
        periódicamente.

        El frontend no controla cada tick.
        """

        try:

            while True:

                # Esperamos antes del siguiente tick.
                # Event.wait() permite interrumpir
                # inmediatamente la espera.
                should_stop = (
                    cls._simulation_stop_event.wait(
                        cls._simulation_interval
                    )
                )


                if should_stop:
                    break


                with cls._lock:

                    provider = cls._provider


                    if not isinstance(
                        provider,
                        DroneSimulator
                    ):
                        break


                    if not provider.is_running:
                        break


                    try:

                        provider.advance()

                    except DroneSimulatorError as exc:

                        cls._simulation_last_error = (
                            str(exc)
                        )

                        break


                    # advance() puede haber alcanzado
                    # el waypoint final.
                    if not provider.is_running:
                        break


        finally:

            with cls._lock:

                if (
                    cls._simulation_thread
                    is current_thread()
                ):
                    cls._simulation_thread = None
                    
    @classmethod
    def simulator_auto_status(
        cls
    ) -> dict:
        """
        Estado del mecanismo automático de simulación.
        """

        with cls._lock:

            thread = (
                cls._simulation_thread
            )


            auto_running = (
                thread is not None
                and thread.is_alive()
            )


            simulator_running = False


            if isinstance(
                cls._provider,
                DroneSimulator
            ):

                simulator_running = (
                    cls._provider.is_running
                )


            return {
                "auto_running":
                    auto_running,

                "simulator_running":
                    simulator_running,

                "interval_seconds":
                    cls._simulation_interval,

                "last_error":
                    cls._simulation_last_error,
                
                "route_id": 
                    cls._active_route_id,
            }
            
    @classmethod
    def simulator_start_auto(
        cls,
        interval_seconds: float = 1.0
    ) -> dict:
        """
        Inicia el worker automático que hace avanzar
        periódicamente el DroneSimulator.
        """

        try:

            interval_seconds = float(
                interval_seconds
            )

        except (
            TypeError,
            ValueError
        ) as exc:

            raise DroneServiceError(
                "interval_seconds debe ser numérico."
            ) from exc


        if interval_seconds <= 0:

            raise DroneServiceError(
                "interval_seconds debe ser mayor que 0."
            )


        with cls._lock:

            simulator = (
                cls._require_simulator()
            )


            if not simulator.is_running:

                raise DroneServiceError(
                    "El simulador debe estar iniciado "
                    "antes de activar el avance automático."
                )


            if (
                cls._simulation_thread
                is not None
                and
                cls._simulation_thread.is_alive()
            ):

                raise DroneServiceError(
                    "La simulación automática "
                    "ya está ejecutándose."
                )


            cls._simulation_interval = (
                interval_seconds
            )


            cls._simulation_last_error = (
                None
            )


            # Creamos un Event limpio.
            cls._simulation_stop_event = (
                Event()
            )


            thread = Thread(
                target=cls._simulation_worker,
                name="DroneSimulatorWorker",
                daemon=True,
            )


            cls._simulation_thread = thread


            thread.start()


        return cls.simulator_auto_status()

    @classmethod
    def simulator_stop_auto(
        cls
    ) -> dict:
        """
        Detiene el worker automático sin resetear
        la posición actual del simulador.
        """

        with cls._lock:

            thread = (
                cls._simulation_thread
            )


            if (
                thread is None
                or
                not thread.is_alive()
            ):

                return cls.simulator_auto_status()


            stop_event = (
                cls._simulation_stop_event
            )


        # No hacemos join() dentro del lock.
        # El worker podría necesitar el mismo lock
        # para finalizar.
        stop_event.set()


        thread.join(
            timeout=2.0
        )


        return cls.simulator_auto_status()
    
    
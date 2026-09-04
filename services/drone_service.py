from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)

from threading import (
    RLock,
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

from services.flight_service import (
    FlightService,
    FlightPersistenceError,
    InvalidFlightTransitionError,
)

from services.flight_route_service import (
    FlightRouteService,
    InvalidFlightRouteAssignmentError,
)

from services.telemetry_service import (
    TelemetryService,
    InvalidTelemetryError,
    TelemetryPersistenceError,
)

from drone.simulation_runner import (
    SimulationRunner,
    SimulationRunnerError,
)

from drone.mission_controller import (
    MissionController,
    MissionControllerError,
)

from drone.simulator_mission_controller import (
    SimulatorMissionController,
)

from drone.integration_status import IntegrationStatus

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

    _active_flight_id: int | None = None
    
    _simulation_runner: SimulationRunner | None = None
    
    _mission_controller: MissionController | None = None
    
    _last_telemetry_at: datetime | None = None

    _integration_last_error: str | None = None

    @classmethod
    def set_provider(
        cls,
        provider: DroneProvider
    ) -> None:
        """
        Cambia el proveedor activo.

        El runtime específico del proveedor anterior
        se libera antes de instalar el nuevo.
        """

        if not isinstance(
            provider,
            DroneProvider
        ):

            raise InvalidDroneProviderError(
                "El proveedor no cumple "
                "el contrato DroneProvider."
            )

        cls._ensure_provider_change_allowed()
        
        with cls._lock:

            previous_runner = (
                cls._simulation_runner
            )


        if previous_runner is not None:

            previous_runner.stop()


        with cls._lock:

            cls._provider = provider

            cls._simulation_runner = None
            
            cls._mission_controller = None
            
            cls._last_telemetry_at = None

            cls._integration_last_error = None

    @classmethod
    def _ensure_provider_change_allowed(
        cls
    ) -> None:
        """
        Impide sustituir o eliminar el proveedor
        mientras exista una operación abierta.
        """

        with cls._lock:

            flight_id = (
                cls._active_flight_id
            )


        if flight_id is None:

            return


        try:

            flight = (
                FlightService.get_flight(
                    flight_id
                )
            )

        except FlightPersistenceError as exc:

            raise DroneServiceError(
                "No fue posible validar "
                f"el Flight {flight_id} antes "
                "de cambiar el proveedor."
            ) from exc


        if flight["status"] in {
            "CREATED",
            "ACTIVE",
        }:

            raise DroneServiceError(
                "No se puede cambiar el proveedor "
                f"mientras el vuelo "
                f"{flight['flight_code']} "
                f"se encuentre en estado "
                f"{flight['status']}."
            )

    @classmethod
    def clear_provider(
        cls
    ) -> None:
        """
        Elimina el proveedor activo y libera
        cualquier runtime asociado.
        """

        cls._ensure_provider_change_allowed()
         
        with cls._lock:

            runner = (
                cls._simulation_runner
            )


        if runner is not None:

            runner.stop()


        with cls._lock:

            cls._provider = None

            cls._simulation_runner = None
            
            cls._mission_controller = None
            
            cls._last_telemetry_at = None

            cls._integration_last_error = None


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
    def configure_operation(
        cls,
        *,
        provider: DroneProvider,
        mission_controller: MissionController,
        route_id: int,
    ) -> DroneState:
        """
        Configura atómicamente los componentes técnicos
        necesarios para ejecutar una operación.

        DroneService carga la Route persistente, mientras
        que MissionController se encarga de traducirla
        al mecanismo técnico correspondiente.
        """

        if not isinstance(
            provider,
            DroneProvider
        ):

            raise InvalidDroneProviderError(
                "El proveedor no cumple "
                "el contrato DroneProvider."
            )


        if not isinstance(
            mission_controller,
            MissionController
        ):

            raise DroneServiceError(
                "El controlador no cumple "
                "el contrato MissionController."
            )


        if (
            provider.name
            !=
            mission_controller.name
        ):

            raise DroneServiceError(
                "El proveedor y el controlador "
                "de misión no son compatibles: "
                f"{provider.name} != "
                f"{mission_controller.name}."
            )


        cls._ensure_provider_change_allowed()


        try:

            route = RouteService.get_route(
                route_id
            )

        except RoutePersistenceError as exc:

            raise DroneServiceError(
                f"No fue posible cargar "
                f"la ruta {route_id}: {exc}"
            ) from exc


        if route is None:

            raise DroneServiceError(
                f"La ruta con ID "
                f"{route_id} no existe."
            )


        waypoints = (
            route.get(
                "waypoints",
                []
            )
        )


        try:

            mission_controller.configure(
                waypoints
            )

        except MissionControllerError as exc:

            raise DroneServiceError(
                "No fue posible configurar "
                f"la misión: {exc}"
            ) from exc


        #
        # set_provider() libera correctamente
        # el runtime anterior.
        #
        cls.set_provider(
            provider
        )


        with cls._lock:

            cls._mission_controller = (
                mission_controller
            )

            cls._active_route_id = (
                route_id
            )


        return provider.get_state()
    
    @classmethod
    def configure_simulator(
        cls,
        route_id: int,
        *,
        step_fraction: float = 0.20,
        initial_battery: float = 100.0,
    ) -> DroneState:
        """
        Construye los componentes específicos
        de simulación y delega la configuración
        operacional común.
        """

        simulator = DroneSimulator(
            step_fraction=step_fraction,
            initial_battery=initial_battery,
        )


        runner = SimulationRunner(
            simulator=simulator,
            on_state=cls._handle_mission_state,
        )


        controller = SimulatorMissionController(
            simulator=simulator,
            runner=runner,
        )


        state = cls.configure_operation(
            provider=simulator,
            mission_controller=controller,
            route_id=route_id,
        )


        with cls._lock:

            cls._simulation_runner = runner


        return state

    @classmethod
    def get_active_route_id(
        cls
    ) -> int | None:

        with cls._lock:
            return cls._active_route_id
    
    @classmethod
    def get_active_flight_id(
        cls
    ) -> int | None:

        with cls._lock:
            return cls._active_flight_id
    
    
    @classmethod
    def _activate_active_flight(
        cls,
        state: DroneState,
    ) -> dict | None:
        """
        Activa el Flight operacional asociado y
        persiste su estado inicial.

        Esta lógica pertenece a DroneService,
        no al controlador técnico de la misión.
        """

        with cls._lock:

            flight_id = (
                cls._active_flight_id
            )


        if flight_id is None:

            return None


        try:

            flight = (
                FlightService.get_flight(
                    flight_id
                )
            )


            if flight is None:

                raise DroneServiceError(
                    f"El Flight con ID "
                    f"{flight_id} no existe."
                )


            status = (
                flight["status"]
            )


            if status == "CREATED":

                flight = (
                    FlightService.start_flight(
                        flight_id
                    )
                )


            elif status != "ACTIVE":

                raise DroneServiceError(
                    "No se puede iniciar la "
                    f"operación del vuelo "
                    f"{flight['flight_code']} "
                    f"desde el estado "
                    f"{status}."
                )


            cls._persist_active_flight_state(
                state
            )


            return (
                FlightService.get_flight(
                    flight_id
                )
            )


        except (
            FlightPersistenceError,
            InvalidFlightTransitionError,
            ValueError,
        ) as exc:

            raise DroneServiceError(
                "No fue posible iniciar "
                f"el Flight persistente: {exc}"
            ) from exc
    
    @classmethod
    def cancel_active_operation(
        cls
    ) -> dict:
        """
        Cancela la operación persistente actual.

        La telemetría ya registrada se conserva.
        """

        with cls._lock:
            flight_id = cls._active_flight_id


        if flight_id is None:

            raise DroneServiceError(
                "No existe una operación activa para cancelar."
            )


        try:

            flight = FlightService.get_flight(
                flight_id
            )

        except FlightPersistenceError as exc:

            raise DroneServiceError(
                "No fue posible consultar "
                f"el Flight {flight_id}: {exc}"
            ) from exc


        if flight is None:

            raise DroneServiceError(
                f"El Flight con ID {flight_id} "
                "no existe."
            )


        status = flight["status"]


        if status == "CANCELLED":

            return cls.get_operation_context()


        if status not in {
            "CREATED",
            "ACTIVE",
        }:

            raise DroneServiceError(
                f"No se puede cancelar el vuelo "
                f"{flight['flight_code']} "
                f"desde el estado {status}."
            )


        #
        # Primero detenemos cualquier evolución
        # automática del simulador.
        #
        cls.simulator_stop_auto()


        try:

            cancelled_flight = (
                FlightService.cancel_flight(
                    flight_id
                )
            )

        except (
            FlightPersistenceError,
            InvalidFlightTransitionError,
        ) as exc:

            raise DroneServiceError(
                "No fue posible cancelar "
                f"el Flight {flight_id}: {exc}"
            ) from exc


        return {
            "status": "cancelled",

            "flight": cancelled_flight,

            "context":
                cls.get_operation_context(),
        }
        
        
    @classmethod
    def prepare_simulated_flight(
        cls,
        route_id: int,
        *,
        name: str = "Vuelo simulado",
        step_fraction: float = 0.20,
        initial_battery: float = 100.0,
    ) -> dict:
        """
        Prepara una operación utilizando
        el proveedor de simulación.
        """

        cls._validate_new_operation_allowed()


        state = cls.configure_simulator(
            route_id,
            step_fraction=step_fraction,
            initial_battery=initial_battery,
        )


        return cls._register_prepared_flight(
            route_id=route_id,
            name=name,
            state=state,
        )
    
    @classmethod
    def _register_prepared_flight(
        cls,
        *,
        route_id: int,
        name: str,
        state: DroneState,
    ) -> dict:
        """
        Crea el Flight persistente, le asigna la Route
        configurada y registra el contexto operacional.

        No conoce el proveedor técnico utilizado.
        """

        try:

            flight = FlightService.create_flight(
                name=name
            )


            flight_id = int(
                flight["id"]
            )


            assignment = (
                FlightRouteService.assign_route(
                    flight_id,
                    route_id,
                )
            )


        except (
            FlightPersistenceError,
            InvalidFlightRouteAssignmentError,
        ) as exc:

            with cls._lock:

                cls._active_flight_id = None


            raise DroneServiceError(
                "No fue posible registrar "
                f"la operación preparada: {exc}"
            ) from exc


        with cls._lock:

            cls._active_flight_id = (
                flight_id
            )

            cls._active_route_id = (
                route_id
            )


        return {
            "flight": flight,

            "assignment": assignment,

            "route_id": route_id,

            "provider":
                cls.get_provider_name(),

            "state":
                state.to_dict(),
        }
    
    @classmethod
    def prepare_operation(
        cls,
        *,
        provider: DroneProvider,
        mission_controller: MissionController,
        route_id: int,
        name: str = "Operación de vuelo",
    ) -> dict:
        """
        Prepara una operación independientemente
        del proveedor técnico utilizado.
        """

        cls._validate_new_operation_allowed()


        state = cls.configure_operation(
            provider=provider,
            mission_controller=mission_controller,
            route_id=route_id,
        )


        return cls._register_prepared_flight(
            route_id=route_id,
            name=name,
            state=state,
        )
            
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
    def _require_mission_controller(
        cls
    ) -> MissionController:
        """
        Devuelve el controlador técnico de misión
        actualmente configurado.
        """

        with cls._lock:

            controller = (
                cls._mission_controller
            )


        if controller is None:

            raise DroneServiceError(
                "No existe un controlador "
                "de misión configurado."
            )


        return controller
    
    @classmethod
    def _require_simulation_runner(
        cls
    ) -> SimulationRunner:
        """
        Devuelve el SimulationRunner configurado.

        Lanza DroneServiceError si todavía
        no existe un runner de simulación.
        """

        with cls._lock:

            runner = (
                cls._simulation_runner
            )


        if runner is None:

            raise DroneServiceError(
                "El motor automático de simulación "
                "no está configurado."
            )


        return runner
    
    @classmethod
    def simulator_connect(
        cls
    ) -> DroneState:

        cls._require_simulator()

        return cls.connect_provider()


    @classmethod
    def simulator_disconnect(
        cls
    ) -> DroneState:
        """
        Detiene el runtime automático del simulador
        y desconecta el proveedor simulado.
        """

        cls._require_simulator()


        cls.simulator_stop_auto()


        return cls.disconnect_provider()


    @classmethod
    def simulator_start(
        cls
    ) -> DroneState:
        """
        Inicia técnicamente el DroneSimulator
        y sincroniza el Flight operacional asociado.
        """

        simulator = (
            cls._require_simulator()
        )


        try:

            state = (
                simulator.start()
            )

        except DroneSimulatorError as exc:

            raise DroneServiceError(
                str(exc)
            ) from exc


        cls._activate_active_flight(
            state
        )


        return state

    @classmethod
    def simulator_advance(
        cls
    ) -> DroneState:

        with cls._lock:

            simulator = (
                cls._require_simulator()
            )

            try:

                state = (
                    simulator.advance()
                )

            except DroneSimulatorError as exc:

                raise DroneServiceError(
                    str(exc)
                ) from exc

            mission_running = (
                simulator.is_running
            )


        cls._handle_mission_state(
            state,
            mission_running,
        )


        return state

    @classmethod
    def simulator_reset(
        cls
    ) -> DroneState:
        """
        Reinicia el simulador solamente cuando
        no existe un Flight ACTIVE o COMPLETED
        asociado a la operación.
        """

        # ------------------------------------------
        # 1. Obtener Flight asociado
        # ------------------------------------------

        with cls._lock:
            flight_id = cls._active_flight_id


        # ------------------------------------------
        # 2. Validar estado persistente
        # ------------------------------------------

        if flight_id is not None:

            try:

                flight = FlightService.get_flight(
                    flight_id
                )

            except FlightPersistenceError as exc:

                raise DroneServiceError(
                    "No fue posible validar "
                    f"el Flight activo: {exc}"
                ) from exc


            if (
                flight is not None
                and
                flight["status"] in {
                    "ACTIVE",
                    "COMPLETED",
                }
            ):

                raise DroneServiceError(
                    "No se puede resetear el simulador "
                    f"mientras existe el vuelo "
                    f"{flight['flight_code']} "
                    f"en estado {flight['status']}. "
                    "Prepara una nueva operación."
                )


        # ------------------------------------------
        # 3. Solo si pasó la validación,
        #    detener ejecución automática
        # ------------------------------------------

        cls.simulator_stop_auto()


        # ------------------------------------------
        # 4. Reset físico/lógico del simulador
        # ------------------------------------------

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
    def _persist_active_flight_state(
        cls,
        state: DroneState
    ) -> dict | None:
        """
        Persiste un DroneState como TelemetryPoint
        cuando existe un Flight operacional activo.

        Si no existe Flight asociado, no persiste nada.
        """

        with cls._lock:

            flight_id = (
                cls._active_flight_id
            )


        if flight_id is None:
            return None


        if (
            state.latitude is None
            or
            state.longitude is None
        ):
            return None


        try:

            telemetry_point = (
                TelemetryService.add_point(
                    flight_id,

                    latitude=
                        state.latitude,

                    longitude=
                        state.longitude,

                    altitude=
                        state.altitude,

                    speed=
                        state.speed,

                    heading=
                        state.heading,

                    battery=
                        state.battery,

                    gps_sats=
                        state.gps_sats,

                    flight_mode=
                        state.flight_mode,

                    recorded_at=
                        state.recorded_at,
                )
            )


        except (
            InvalidTelemetryError,
            TelemetryPersistenceError,
        ) as exc:

            raise DroneServiceError(
                "No fue posible persistir "
                f"la telemetría del vuelo "
                f"{flight_id}: {exc}"
            ) from exc


        cls._mark_telemetry_received(
            state
        )


        return telemetry_point
         
                    
    @classmethod
    def simulator_auto_status(
        cls
    ) -> dict:
        """
        Devuelve el estado del runtime
        automático de simulación junto al
        contexto operacional.
        """

        with cls._lock:

            runner = (
                cls._simulation_runner
            )

            route_id = (
                cls._active_route_id
            )

            flight_id = (
                cls._active_flight_id
            )


        if runner is None:

            runtime = {
                "auto_running": False,
                "simulator_running": False,
                "interval_seconds": 1.0,
                "last_error": None,
            }

        else:

            runtime = (
                runner.status()
            )


        return {
            **runtime,

            "route_id":
                route_id,

            "flight_id":
                flight_id,
        }
            
    @classmethod
    def simulator_start_auto(
        cls,
        interval_seconds: float = 1.0,
    ) -> dict:
        """
        Inicia el motor automático
        de simulación.
        """

        runner = (
            cls._require_simulation_runner()
        )


        try:

            runner.start(
                interval_seconds
            )

        except SimulationRunnerError as exc:

            raise DroneServiceError(
                str(exc)
            ) from exc


        return cls.simulator_auto_status()

    @classmethod
    def simulator_stop_auto(
        cls
    ) -> dict:
        """
        Detiene el motor automático sin
        resetear la posición simulada.
        """

        with cls._lock:

            runner = (
                cls._simulation_runner
            )


        if runner is not None:

            runner.stop()


        return cls.simulator_auto_status()
    
    @classmethod
    def _handle_mission_state(
        cls,
        state: DroneState,
        mission_running: bool,
    ) -> None:
        """
        Procesa un nuevo estado producido durante
        la ejecución técnica de una misión.

        Esta función concentra la lógica operacional
        común de persistencia y finalización del Flight,
        independientemente del origen de telemetría.
        """

        cls._persist_active_flight_state(
            state
        )


        if not mission_running:

            cls._complete_active_flight()
            
    @classmethod
    def _complete_active_flight(
        cls
    ) -> dict | None:
        """
        Finaliza el Flight operacional actualmente asociado.

        Si no existe Flight activo en el contexto,
        no realiza ninguna operación.
        """

        with cls._lock:
            flight_id = cls._active_flight_id


        if flight_id is None:
            return None


        try:

            flight = FlightService.get_flight(
                flight_id
            )


            if flight is None:

                raise DroneServiceError(
                    f"El Flight con ID {flight_id} "
                    "no existe."
                )


            status = flight["status"]


            if status == "COMPLETED":

                return flight


            if status != "ACTIVE":

                raise DroneServiceError(
                    f"No se puede completar el vuelo "
                    f"{flight['flight_code']} "
                    f"desde el estado {status}."
                )


            return FlightService.finish_flight(
                flight_id
            )


        except (
            FlightPersistenceError,
            InvalidFlightTransitionError,
        ) as exc:

            raise DroneServiceError(
                "No fue posible finalizar "
                f"el Flight {flight_id}: {exc}"
            ) from exc
            
    @classmethod
    def _validate_new_operation_allowed(
        cls
    ) -> None:
        """
        Evita reemplazar una operación que todavía
        se encuentra preparada o activa.
        """

        with cls._lock:
            flight_id = cls._active_flight_id


        if flight_id is None:
            return


        try:

            flight = FlightService.get_flight(
                flight_id
            )

        except FlightPersistenceError as exc:

            raise DroneServiceError(
                "No fue posible validar la "
                f"operación actual: {exc}"
            ) from exc


        if flight is None:
            return


        if flight["status"] in {
            "CREATED",
            "ACTIVE",
        }:

            raise DroneServiceError(
                f"El vuelo {flight['flight_code']} "
                "todavía se encuentra "
                f"en estado {flight['status']}. "
                "No se puede preparar otra operación."
            )
    
    @classmethod
    def get_operation_context(
        cls
    ) -> dict:
        """
        Devuelve el contexto operacional actual
        necesario para reconstruir la interfaz.
        """

        with cls._lock:

            flight_id = cls._active_flight_id

            route_id = cls._active_route_id

            provider_name = (
                cls._provider.name
                if cls._provider is not None
                else None
            )


        flight = None


        if flight_id is not None:

            try:

                flight = FlightService.get_flight(
                    flight_id
                )

            except FlightPersistenceError as exc:

                raise DroneServiceError(
                    "No fue posible recuperar "
                    f"el Flight activo: {exc}"
                ) from exc


        return {
            "provider": provider_name,

            "route_id": route_id,

            "flight_id": flight_id,

            "flight": flight,

            # Nuevo contrato genérico.
            "mission":
                cls.get_mission_status(),
        }
        
    
    @classmethod
    def get_mission_status(
        cls
    ) -> dict:
        """
        Devuelve el estado técnico normalizado
        del controlador de misión actual.

        La respuesta no expone detalles internos
        del simulador.
        """

        with cls._lock:

            controller = (
                cls._mission_controller
            )


        if controller is None:

            return {
                "configured": False,
                "running": False,
                "paused": False,
                "last_error": None,
                "controller": None,
            }


        try:

            status = (
                controller.status()
            )

        except MissionControllerError as exc:

            raise DroneServiceError(
                "No fue posible consultar "
                f"el estado de la misión: {exc}"
            ) from exc


        return {
            "configured": True,

            "running":
                bool(
                    status.get(
                        "running",
                        False
                    )
                ),

            "paused":
                bool(
                    status.get(
                        "paused",
                        False
                    )
                ),

            "last_error":
                status.get(
                    "last_error"
                ),

            "controller":
                controller.name,
        }
    
    @classmethod
    def connect_provider(
        cls
    ) -> DroneState:

        provider = (
            cls._require_provider()
        )


        try:

            return provider.connect()


        except Exception as exc:

            raise DroneServiceError(
                "No fue posible conectar "
                f"el proveedor {provider.name}: {exc}"
            ) from exc
            
    @classmethod
    def disconnect_provider(
        cls
    ) -> DroneState:

        provider = (
            cls._require_provider()
        )


        try:

            return provider.disconnect()


        except Exception as exc:

            raise DroneServiceError(
                "No fue posible desconectar "
                f"el proveedor {provider.name}: {exc}"
            ) from exc
    
    @classmethod
    def connect_operation(
        cls
    ) -> dict:
        """
        Conecta el proveedor asociado a la operación
        actualmente preparada.
        """

        with cls._lock:
            flight_id = cls._active_flight_id
            route_id = cls._active_route_id


        if flight_id is None:

            raise DroneServiceError(
                "No existe una operación preparada."
            )


        state = cls.connect_provider()


        return {
            "status": "connected",
            "state": state.to_dict(),
            "flight_id": flight_id,
            "route_id": route_id,
        }
        
    @classmethod
    def disconnect_operation(
        cls
    ) -> dict:
        """
        Desconecta el proveedor cuando la operación
        se encuentra en un estado compatible.
        """

        with cls._lock:
            flight_id = cls._active_flight_id


        if flight_id is None:

            raise DroneServiceError(
                "No existe una operación preparada."
            )


        try:

            flight = FlightService.get_flight(
                flight_id
            )

        except FlightPersistenceError as exc:

            raise DroneServiceError(
                "No fue posible consultar "
                f"el Flight {flight_id}: {exc}"
            ) from exc


        if flight["status"] == "ACTIVE":

            raise DroneServiceError(
                "No se puede desconectar el proveedor "
                "mientras existe una misión ACTIVE."
            )


        state = cls.disconnect_provider()


        return {
            "status": "disconnected",
            "state": state.to_dict(),
            "flight_id": flight_id,
        }
        
    @classmethod
    def start_operation(
        cls,
        interval_seconds: float = 0.5,
    ) -> dict:
        """
        Inicia la operación preparada.

        La implementación específica depende
        del proveedor configurado.
        """

        with cls._lock:

            flight_id = cls._active_flight_id

            provider = cls._provider


        if flight_id is None:

            raise DroneServiceError(
                "No existe una operación preparada."
            )


        try:

            flight = FlightService.get_flight(
                flight_id
            )

        except FlightPersistenceError as exc:

            raise DroneServiceError(
                "No fue posible consultar "
                f"el Flight {flight_id}: {exc}"
            ) from exc


        if flight["status"] != "CREATED":

            raise DroneServiceError(
                "Solo se puede iniciar una operación "
                f"en estado CREATED. Estado actual: "
                f"{flight['status']}."
            )


        controller = (
            cls._require_mission_controller()
        )


        try:

            state = (
                controller.initialize()
            )


            # Sincronizamos el estado persistente del Flight:
            # CREATED -> ACTIVE y persistimos el estado inicial.
            cls._activate_active_flight(
                state
            )


            # Iniciamos la ejecución continua de la misión.
            runtime = (
                controller.start(
                    interval_seconds
                )
            )


        except MissionControllerError as exc:

            raise DroneServiceError(
                "No fue posible iniciar "
                f"la misión: {exc}"
            ) from exc


        return {
            "status": "started",

            "provider":
                provider.name,

            "state":
                state.to_dict(),

            "runtime":
                runtime,

            "flight":
                FlightService.get_flight(
                    flight_id
                ),
        }
        
    @classmethod
    def pause_operation(
        cls
    ) -> dict:
        """
        Pausa temporalmente la ejecución de
        una operación ACTIVE.
        """

        with cls._lock:

            flight_id = cls._active_flight_id


        if flight_id is None:

            raise DroneServiceError(
                "No existe una operación activa."
            )


        flight = FlightService.get_flight(
            flight_id
        )


        if flight["status"] != "ACTIVE":

            raise DroneServiceError(
                "Solo se puede pausar una operación ACTIVE."
            )

        controller = (
            cls._require_mission_controller()
        )


        try:

            runtime = (
                controller.pause()
            )

        except MissionControllerError as exc:

            raise DroneServiceError(
                f"No fue posible pausar "
                f"la misión: {exc}"
            ) from exc


        return {
            "status": "paused",

            "flight":
                flight,

            "runtime":
                runtime,
        }
        
        
    @classmethod
    def resume_operation(
        cls,
        interval_seconds: float = 0.5,
    ) -> dict:
        """
        Reanuda una operación ACTIVE previamente
        pausada.
        """

        with cls._lock:

            flight_id = cls._active_flight_id


        if flight_id is None:

            raise DroneServiceError(
                "No existe una operación activa."
            )


        flight = FlightService.get_flight(
            flight_id
        )


        if flight["status"] != "ACTIVE":

            raise DroneServiceError(
                "Solo se puede reanudar una operación ACTIVE."
            )


        controller = (
            cls._require_mission_controller()
        )


        try:

            runtime = (
                controller.resume(
                    interval_seconds
                )
            )

        except MissionControllerError as exc:

            raise DroneServiceError(
                f"No fue posible reanudar "
                f"la misión: {exc}"
            ) from exc


        return {
            "status": "resumed",

            "flight":
                flight,

            "runtime":
                runtime,
        }

    @staticmethod
    def _state_has_telemetry(
        state: DroneState,
    ) -> bool:
        """
        Determina si DroneState contiene al menos
        un dato operacional de telemetría.

        Evita considerar como telemetría un estado
        vacío de conexión/desconexión.
        """

        return any(
            value is not None
            for value in (
                state.latitude,
                state.longitude,
                state.altitude,
                state.speed,
                state.heading,
                state.battery,
                state.gps_sats,
                state.flight_mode,
            )
        )
        
    @classmethod
    def _mark_telemetry_received(
        cls,
        state: DroneState,
    ) -> None:

        if not cls._state_has_telemetry(
            state
        ):

            return


        with cls._lock:

            cls._last_telemetry_at = (
                state.recorded_at
            )

            cls._integration_last_error = None    
    
    @classmethod
    def get_integration_status(
        cls,
        *,
        stale_after_seconds: float = 5.0,
    ) -> IntegrationStatus:
        """
        Devuelve el diagnóstico técnico normalizado
        de la integración activa.

        No modifica el estado del Flight.
        """

        try:

            stale_after_seconds = float(
                stale_after_seconds
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise DroneServiceError(
                "stale_after_seconds debe "
                "ser numérico."
            ) from exc


        if stale_after_seconds <= 0:

            raise DroneServiceError(
                "stale_after_seconds debe "
                "ser mayor que 0."
            )


        with cls._lock:

            provider = cls._provider

            controller = (
                cls._mission_controller
            )

            last_telemetry_at = (
                cls._last_telemetry_at
            )

            integration_error = (
                cls._integration_last_error
            )


        #
        # No existe integración configurada.
        #
        if provider is None:

            return IntegrationStatus(
                provider=None,

                configured=False,

                transport_connected=False,

                aircraft_online=False,

                telemetry_available=False,

                telemetry_fresh=False,

                last_telemetry_at=None,

                telemetry_age_seconds=None,

                last_error=integration_error,

                health="NOT_CONFIGURED",
            )


        #
        # Consultamos el estado técnico actual
        # del proveedor.
        #
        try:

            state = provider.get_state()

        except Exception as exc:

            return IntegrationStatus(
                provider=provider.name,

                configured=True,

                transport_connected=False,

                aircraft_online=False,

                telemetry_available=(
                    last_telemetry_at
                    is not None
                ),

                telemetry_fresh=False,

                last_telemetry_at=(
                    last_telemetry_at
                ),

                telemetry_age_seconds=None,

                last_error=str(exc),

                health="ERROR",
            )


        now = datetime.now(
            timezone.utc
        )


        telemetry_age = None


        if last_telemetry_at is not None:

            telemetry_age = max(
                0.0,

                (
                    now
                    -
                    last_telemetry_at
                ).total_seconds(),
            )


        telemetry_available = (
            last_telemetry_at
            is not None
        )


        telemetry_fresh = (
            telemetry_age is not None
            and
            telemetry_age
            <=
            stale_after_seconds
        )


        last_error = integration_error


        #
        # MissionController también puede informar
        # errores técnicos.
        #
        if controller is not None:

            try:

                mission_status = (
                    controller.status()
                )

                controller_error = (
                    mission_status.get(
                        "last_error"
                    )
                )


                if controller_error:

                    last_error = (
                        str(controller_error)
                    )

            except Exception as exc:

                last_error = str(exc)


        #
        # Health general.
        #
        if last_error:

            health = "ERROR"

        elif not state.connected:

            health = "OFFLINE"

        elif not state.aircraft_online:

            health = "DEGRADED"

        elif not telemetry_available:

            health = "CONNECTED"

        elif not telemetry_fresh:

            health = "DEGRADED"

        else:

            health = "ONLINE"


        return IntegrationStatus(
            provider=provider.name,

            configured=True,

            transport_connected=bool(
                state.connected
            ),

            aircraft_online=bool(
                state.aircraft_online
            ),

            telemetry_available=(
                telemetry_available
            ),

            telemetry_fresh=(
                telemetry_fresh
            ),

            last_telemetry_at=(
                last_telemetry_at
            ),

            telemetry_age_seconds=(
                telemetry_age
            ),

            last_error=last_error,

            health=health,
        )
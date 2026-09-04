from drone.dji_backend import DJIBackend
from drone.dji_mission_controller import (
    DJIMissionController,
)
from drone.dji_provider import DJIProvider
from drone.dji_test_backend import DJITestBackend
from drone.mission_controller import MissionController
from drone.provider import DroneProvider
from drone.simulation_runner import SimulationRunner
from drone.simulator import DroneSimulator
from drone.simulator_mission_controller import (
    SimulatorMissionController,
)


def test_drone_simulator_implements_provider():
    simulator = DroneSimulator()

    assert isinstance(
        simulator,
        DroneProvider,
    )


def test_simulator_controller_implements_contract():
    simulator = DroneSimulator()

    runner = SimulationRunner(
        simulator=simulator,
        on_state=lambda state, running: None,
    )

    controller = SimulatorMissionController(
        simulator=simulator,
        runner=runner,
    )

    assert isinstance(
        controller,
        MissionController,
    )


def test_dji_test_backend_implements_backend_contract():
    backend = DJITestBackend()

    assert isinstance(
        backend,
        DJIBackend,
    )


def test_dji_provider_implements_provider_contract():
    backend = DJITestBackend()

    provider = DJIProvider(
        backend
    )

    assert isinstance(
        provider,
        DroneProvider,
    )


def test_dji_controller_implements_mission_contract():
    backend = DJITestBackend()

    controller = DJIMissionController(
        backend
    )

    assert isinstance(
        controller,
        MissionController,
    )


def test_dji_provider_and_controller_share_backend():
    backend = DJITestBackend()

    provider = DJIProvider(
        backend
    )

    controller = DJIMissionController(
        backend
    )

    assert provider._backend is backend
    assert controller._backend is backend
    assert provider._backend is controller._backend
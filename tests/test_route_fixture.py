from services.route_service import RouteService


def test_ready_route_fixture(
    ready_route
):

    assert (
        ready_route["status"]
        ==
        "READY"
    )

    assert (
        ready_route["waypoint_count"]
        ==
        6
    )


    route = RouteService.get_route(
        ready_route["id"]
    )


    assert route is not None

    assert (
        len(route["waypoints"])
        ==
        6
    )


    assert (
        route["waypoints"][0]["sequence"]
        ==
        1
    )

    assert (
        route["waypoints"][-1]["sequence"]
        ==
        6
    )
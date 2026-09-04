from __future__ import annotations

import time
from collections.abc import Callable


def wait_until(
    condition: Callable[[], bool],
    *,
    timeout: float = 3.0,
    interval: float = 0.02,
) -> None:
    """
    Espera hasta que condition() sea True.

    Falla mediante TimeoutError cuando la
    condición no se cumple dentro del límite.
    """

    deadline = (
        time.monotonic()
        +
        timeout
    )


    while (
        time.monotonic()
        <
        deadline
    ):

        if condition():

            return


        time.sleep(
            interval
        )


    raise TimeoutError(
        "La condición esperada "
        "no se cumplió dentro "
        f"de {timeout} segundos."
    )
from __future__ import annotations

from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
)

from threading import Lock

from collections.abc import Callable


class ProcessingExecutorError(
    Exception
):
    pass


class ProcessingJobAlreadySubmittedError(
    ProcessingExecutorError
):
    pass


class ProcessingExecutor:
    """
    Executor local para trabajos geoespaciales.

    Está deliberadamente limitado a un worker
    para evitar ejecutar dos reconstrucciones
    fotogramétricas pesadas simultáneamente
    durante PE2.
    """

    def __init__(
        self,
        *,
        max_workers: int = 1,
    ) -> None:

        if max_workers < 1:
            raise ValueError(
                "max_workers debe ser >= 1."
            )

        self._executor = (
            ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix=(
                    "photogrammetry"
                ),
            )
        )

        self._lock = Lock()

        self._futures: dict[
            int,
            Future,
        ] = {}

    def submit(
        self,
        *,
        job_id: int,
        task: Callable[
            [],
            object,
        ],
    ) -> Future:

        normalized_job_id = int(
            job_id
        )

        with self._lock:

            existing = (
                self._futures.get(
                    normalized_job_id
                )
            )

            if (
                existing is not None
                and not existing.done()
            ):
                raise (
                    ProcessingJobAlreadySubmittedError(
                        "El trabajo "
                        f"{normalized_job_id} "
                        "ya está en ejecución "
                        "o pendiente."
                    )
                )

            future = (
                self._executor.submit(
                    task
                )
            )

            self._futures[
                normalized_job_id
            ] = future

        # IMPORTANTE:
        # Registrar el callback fuera del Lock.
        #
        # Si la tarea ya terminó,
        # add_done_callback() puede ejecutar
        # el callback inmediatamente.
        future.add_done_callback(
            lambda completed_future,
            current_job_id=(
                normalized_job_id
            ):
                self._remove_completed(
                    job_id=(
                        current_job_id
                    ),
                    future=(
                        completed_future
                    ),
                )
        )

        return future

    def _remove_completed(
        self,
        *,
        job_id: int,
        future: Future,
    ) -> None:

        with self._lock:

            current = (
                self._futures.get(
                    job_id
                )
            )

            if current is future:
                self._futures.pop(
                    job_id,
                    None,
                )

    def is_submitted(
        self,
        job_id: int,
    ) -> bool:

        normalized_job_id = int(
            job_id
        )

        with self._lock:

            future = (
                self._futures.get(
                    normalized_job_id
                )
            )

            return (
                future is not None
                and not future.done()
            )

    def active_job_ids(
        self,
    ) -> tuple[int, ...]:

        with self._lock:

            return tuple(
                sorted(
                    job_id
                    for (
                        job_id,
                        future,
                    )
                    in self._futures.items()
                    if not future.done()
                )
            )

    def shutdown(
        self,
        *,
        wait: bool = True,
    ) -> None:

        self._executor.shutdown(
            wait=wait,
        )
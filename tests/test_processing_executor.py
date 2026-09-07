from threading import Event

import pytest

from services.processing_executor import (
    ProcessingExecutor,
    ProcessingJobAlreadySubmittedError,
)


def test_processing_executor_executes_task():

    executor = ProcessingExecutor(
        max_workers=1
    )

    try:

        future = executor.submit(
            job_id=1,
            task=lambda: "completed",
        )

        assert (
            future.result(
                timeout=2
            )
            == "completed"
        )

    finally:

        executor.shutdown()


def test_processing_executor_reports_active_job():

    executor = ProcessingExecutor(
        max_workers=1
    )

    started = Event()
    release = Event()

    def task():

        started.set()

        release.wait(
            timeout=2
        )

        return "done"

    try:

        future = executor.submit(
            job_id=10,
            task=task,
        )

        assert started.wait(
            timeout=2
        )

        assert executor.is_submitted(
            10
        )

        assert 10 in (
            executor.active_job_ids()
        )

        release.set()

        assert (
            future.result(
                timeout=2
            )
            == "done"
        )

    finally:

        release.set()

        executor.shutdown()


def test_processing_executor_rejects_duplicate_active_job():

    executor = ProcessingExecutor(
        max_workers=1
    )

    started = Event()
    release = Event()

    def task():

        started.set()

        release.wait(
            timeout=2
        )

    try:

        executor.submit(
            job_id=20,
            task=task,
        )

        assert started.wait(
            timeout=2
        )

        with pytest.raises(
            ProcessingJobAlreadySubmittedError
        ):

            executor.submit(
                job_id=20,
                task=lambda: None,
            )

    finally:

        release.set()

        executor.shutdown()


def test_processing_executor_removes_completed_job():

    executor = ProcessingExecutor(
        max_workers=1
    )

    try:

        future = executor.submit(
            job_id=30,
            task=lambda: None,
        )

        future.result(
            timeout=2
        )

        assert not (
            executor.is_submitted(
                30
            )
        )

    finally:

        executor.shutdown()


def test_processing_executor_rejects_invalid_worker_count():

    with pytest.raises(
        ValueError
    ):

        ProcessingExecutor(
            max_workers=0
        )
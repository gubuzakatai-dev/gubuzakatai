from secondbrain.app import (
    CONFIRMATION_INTERVAL_SECONDS,
    CONFIRMATION_JOB_NAME,
    LINK_METADATA_INTERVAL_SECONDS,
    LINK_METADATA_JOB_NAME,
    register_confirmation_job,
    register_link_metadata_job,
)


class FakeJobQueue:
    def __init__(self) -> None:
        self.jobs: list[dict[str, object]] = []

    def run_repeating(self, callback: object, *, interval: int, first: int, name: str) -> None:
        self.jobs.append(
            {
                "callback": callback,
                "interval": interval,
                "first": first,
                "name": name,
            }
        )


class FakeApplication:
    def __init__(self) -> None:
        self.job_queue = FakeJobQueue()


class FakeLinkMetadataService:
    def process_next(self) -> bool:
        return False


def test_register_link_metadata_job_schedules_periodic_processing() -> None:
    application = FakeApplication()

    register_link_metadata_job(application, FakeLinkMetadataService())  # type: ignore[arg-type]

    assert application.job_queue.jobs[0]["name"] == LINK_METADATA_JOB_NAME
    assert application.job_queue.jobs[0]["interval"] == LINK_METADATA_INTERVAL_SECONDS
    assert application.job_queue.jobs[0]["first"] == LINK_METADATA_INTERVAL_SECONDS


def test_register_confirmation_job_schedules_periodic_processing() -> None:
    application = FakeApplication()

    register_confirmation_job(application, 10, object())  # type: ignore[arg-type]

    assert application.job_queue.jobs[0]["name"] == CONFIRMATION_JOB_NAME
    assert application.job_queue.jobs[0]["interval"] == CONFIRMATION_INTERVAL_SECONDS
    assert application.job_queue.jobs[0]["first"] == CONFIRMATION_INTERVAL_SECONDS

from secondbrain.app import (
    CONFIRMATION_INTERVAL_SECONDS,
    CONFIRMATION_JOB_NAME,
    EVENING_REMINDER_INTERVAL_SECONDS,
    LINK_METADATA_INTERVAL_SECONDS,
    LINK_METADATA_JOB_NAME,
    TASK_DAILY_ROLLOVER_INTERVAL_SECONDS,
    register_confirmation_job,
    register_evening_reminder_job,
    register_link_metadata_job,
    register_task_daily_rollover_job,
)
from secondbrain.services.evening_reminder import EVENING_REMINDER_JOB_NAME
from secondbrain.services.tasks import TASK_DAILY_ROLLOVER_JOB_NAME


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


class FakeEveningReminderService:
    def prepare_due_reminder(self) -> None:
        return None


class FakeTaskService:
    def process_today_rollover(self) -> None:
        return None


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


def test_register_evening_reminder_job_schedules_periodic_processing() -> None:
    application = FakeApplication()

    register_evening_reminder_job(application, 10, FakeEveningReminderService())  # type: ignore[arg-type]

    assert application.job_queue.jobs[0]["name"] == EVENING_REMINDER_JOB_NAME
    assert application.job_queue.jobs[0]["interval"] == EVENING_REMINDER_INTERVAL_SECONDS
    assert application.job_queue.jobs[0]["first"] == 0


def test_register_task_daily_rollover_job_schedules_periodic_processing() -> None:
    application = FakeApplication()

    register_task_daily_rollover_job(application, FakeTaskService())  # type: ignore[arg-type]

    assert application.job_queue.jobs[0]["name"] == TASK_DAILY_ROLLOVER_JOB_NAME
    assert application.job_queue.jobs[0]["interval"] == TASK_DAILY_ROLLOVER_INTERVAL_SECONDS
    assert application.job_queue.jobs[0]["first"] == 0

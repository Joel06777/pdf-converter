from celery import Celery

from . import jobs
from .config import settings
from .processing import run_job

celery_app = Celery("converter", broker=settings.redis_url or "memory://", backend=None)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # un trabajo pesado por proceso a la vez
    task_time_limit=settings.task_time_limit,
    broker_connection_retry_on_startup=True,
    beat_schedule={"cleanup": {"task": "app.worker.cleanup", "schedule": 300.0}},
)


@celery_app.task(name="app.worker.convert_job")
def convert_job(job_id: str) -> None:
    run_job(job_id)


@celery_app.task(name="app.worker.cleanup")
def cleanup() -> int:
    return jobs.cleanup_expired()

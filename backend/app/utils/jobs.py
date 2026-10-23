from typing import Optional
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from .. import models

MAX_ERROR_LENGTH = 2000


def get_job(db: Session, job_id: Optional[int] = None, celery_task_id: Optional[str] = None) -> Optional[models.Job]:
    if job_id is not None:
        return db.query(models.Job).filter(models.Job.id == job_id).first()
    if celery_task_id:
        return db.query(models.Job).filter(models.Job.celery_task_id == celery_task_id).first()
    return None


def update_job(
    db: Session,
    job: Optional[models.Job],
    status: Optional[str] = None,
    progress: Optional[float] = None,
    error: Optional[str] = None,
) -> None:
    """Update a job's status/progress/error and commit. A missing job is ignored."""
    if job is None:
        return
    if status is not None:
        job.status = status
    if progress is not None:
        job.progress = progress
    if error is not None:
        job.error_message = error[:MAX_ERROR_LENGTH]
    db.commit()


def ensure_job_columns(engine: Engine) -> None:
    """Add jobs.error_message to databases created before it existed.

    Tables are created with create_all, which never alters existing tables.
    """
    columns = {c["name"] for c in inspect(engine).get_columns("jobs")}
    if "error_message" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN error_message TEXT NULL"))

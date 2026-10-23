import os
from unittest import mock

from sqlalchemy import create_engine, inspect, text

from app import models
from app.api import channels as channels_api
from app.tasks.download import process_channel_task
from app.utils import jobs as jobs_util, youtube
from tests.support import DbTestCase


class EnsureJobColumnsTest(DbTestCase):
    def test_adds_error_message_to_existing_table_and_keeps_rows(self):
        engine = create_engine(f"sqlite:///{os.path.join(self.tmp, 'old.db')}")
        self.addCleanup(engine.dispose)
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE jobs (id INTEGER PRIMARY KEY, job_type VARCHAR(50), entity_id VARCHAR(255), "
                "celery_task_id VARCHAR(255), status VARCHAR(50), progress FLOAT, error_log_path VARCHAR(500), "
                "created_at DATETIME, updated_at DATETIME)"
            ))
            conn.execute(text("INSERT INTO jobs (id, job_type, entity_id, status, progress) VALUES (7, 'transcription', 'channel_1', 'failed', 0)"))

        jobs_util.ensure_job_columns(engine)
        jobs_util.ensure_job_columns(engine)  # second call is a no-op

        self.assertIn("error_message", [c["name"] for c in inspect(engine).get_columns("jobs")])
        with engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT id, status, error_message FROM jobs")).fetchall(), [(7, "failed", None)])

    def test_error_is_truncated(self):
        db = self.Session()
        try:
            job = models.Job(job_type="export", entity_id="x", status="pending")
            db.add(job)
            db.commit()
            jobs_util.update_job(db, job, status="failed", error="e" * 5000)
            self.assertEqual(len(job.error_message), jobs_util.MAX_ERROR_LENGTH)
        finally:
            db.close()


class ChannelJobLifecycleTest(DbTestCase):
    def setUp(self):
        super().setUp()
        self.add_video()  # creates channel 1

    def add_channel_job(self, task_id: str) -> int:
        db = self.Session()
        try:
            job = models.Job(job_type="channel_process", entity_id="1", status="pending", celery_task_id=task_id)
            db.add(job)
            db.commit()
            return job.id
        finally:
            db.close()

    def get_job(self, job_id: int) -> models.Job:
        db = self.Session()
        try:
            return db.query(models.Job).filter(models.Job.id == job_id).one()
        finally:
            db.close()

    def test_success_marks_job_completed(self):
        job_id = self.add_channel_job("task-ok")
        with mock.patch.object(youtube, "get_channel_videos", return_value=([], "Test")):
            process_channel_task.apply(args=(1,), task_id="task-ok")

        job = self.get_job(job_id)
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.progress, 100)
        self.assertIsNone(job.error_message)

    def test_failure_marks_job_failed_with_error(self):
        job_id = self.add_channel_job("task-bad")
        with mock.patch.object(youtube, "get_channel_videos", side_effect=RuntimeError("discovery blew up")):
            process_channel_task.apply(args=(1,), task_id="task-bad")

        job = self.get_job(job_id)
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.error_message, "discovery blew up")

    def test_trigger_creates_job_before_queueing(self):
        seen = {}

        def fake_apply_async(args, task_id):
            db = self.Session()
            try:
                seen["job"] = db.query(models.Job).filter(models.Job.celery_task_id == task_id).one_or_none()
            finally:
                db.close()

        db = self.Session()
        try:
            with mock.patch.object(channels_api.process_channel_task, "apply_async", side_effect=fake_apply_async):
                response = channels_api.trigger_process_channel(1, db=db)
        finally:
            db.close()

        self.assertIsNotNone(seen["job"])
        self.assertEqual(seen["job"].status, "pending")
        self.assertEqual(seen["job"].celery_task_id, response["task_id"])

import os
import threading
from types import SimpleNamespace
from unittest import mock

from google.genai import errors

from app import models, schemas
from app.api import transcribe as transcribe_api
from app.tasks import transcribe
from app.utils import settings as settings_util
from tests.support import DbTestCase, write_tone

MODEL = "gemini-test-model"
RETIRED_MESSAGE = "This model models/gemini-2.0-flash is no longer available to new users."


def api_error(code: int, status: str, message: str = "boom") -> errors.APIError:
    cls = errors.ClientError if code < 500 else errors.ServerError
    return cls(code, {"error": {"code": code, "message": message, "status": status}})


class FakeModels:
    def __init__(self, count_tokens_error=None, generate=None):
        self.count_tokens_error = count_tokens_error
        self.generate = generate or (lambda call_no: SimpleNamespace(text=f"transcript {call_no}"))
        self.count_tokens_calls = []
        self.generate_calls = []
        self._lock = threading.Lock()

    def count_tokens(self, model, contents):
        self.count_tokens_calls.append(model)
        if self.count_tokens_error:
            raise self.count_tokens_error
        return SimpleNamespace(total_tokens=1)

    def generate_content(self, model, contents):
        with self._lock:
            self.generate_calls.append(model)
            call_no = len(self.generate_calls)
        return self.generate(call_no)


class TranscribeTaskTest(DbTestCase):
    def setUp(self):
        super().setUp()
        self.fake_models = FakeModels()
        self.client_factory = mock.Mock(return_value=SimpleNamespace(models=self.fake_models))
        settings = dict(settings_util.DEFAULT_SETTINGS, transcription_model=MODEL)
        for p in [
            mock.patch.object(transcribe.genai, "Client", self.client_factory),
            mock.patch.object(transcribe.settings_util, "get_settings", return_value=settings),
            mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
        ]:
            p.start()
            self.addCleanup(p.stop)

    def add_chunks(self, count: int, transcript: str = "") -> list:
        video_pk = self.add_video()
        db = self.Session()
        try:
            ids = []
            for i in range(count):
                path = write_tone(os.path.join(self.tmp, f"chunk_{i}.wav"), duration_ms=200)
                chunk = models.AudioChunk(
                    chunk_id=f"chunk_{i}", video_id=video_pk, file_path=path,
                    duration=0.2, start_time=i, end_time=i + 0.2, transcript_text=transcript,
                )
                db.add(chunk)
                db.flush()
                ids.append(chunk.id)
            db.commit()
            return ids
        finally:
            db.close()

    def add_job(self) -> int:
        db = self.Session()
        try:
            job = models.Job(job_type="transcription", entity_id="channel_1", status="pending")
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

    def transcripts(self) -> list:
        db = self.Session()
        try:
            return [c.transcript_text for c in db.query(models.AudioChunk).order_by(models.AudioChunk.id)]
        finally:
            db.close()

    def run_task(self, job_id=None, force=False) -> str:
        return transcribe.transcribe_channel_task.apply(args=(1, force, job_id)).get()

    def test_default_model_is_not_retired(self):
        self.assertNotEqual(settings_util.DEFAULT_SETTINGS["transcription_model"], "gemini-2.0-flash")
        self.assertEqual(schemas.Settings().transcription_model, settings_util.DEFAULT_SETTINGS["transcription_model"])

    def test_preflight_404_fails_job_without_sending_audio(self):
        self.add_chunks(114)
        job_id = self.add_job()
        self.fake_models.count_tokens_error = api_error(404, "NOT_FOUND", RETIRED_MESSAGE)

        result = self.run_task(job_id)

        self.assertIn("404", result)
        self.assertEqual(self.fake_models.generate_calls, [])
        job = self.get_job(job_id)
        self.assertEqual(job.status, "failed")
        self.assertIn("404 NOT_FOUND", job.error_message)
        self.assertIn("gemini-2.0-flash is no longer available", job.error_message)
        self.assertEqual(self.transcripts(), [""] * 114)

    def test_fatal_error_mid_run_stops_remaining_chunks(self):
        self.add_chunks(114)
        job_id = self.add_job()

        def retired(call_no):
            raise api_error(404, "NOT_FOUND", RETIRED_MESSAGE)
        self.fake_models.generate = retired

        result = self.run_task(job_id)

        # Only requests already in flight when the first 404 lands may be sent (5 workers).
        self.assertLessEqual(len(self.fake_models.generate_calls), 5)
        self.assertIn("Not attempted", result)
        job = self.get_job(job_id)
        self.assertEqual(job.status, "failed")
        self.assertTrue(job.error_message.startswith("Stopped: Gemini API error 404 NOT_FOUND"))
        # Progress reflects chunks actually sent, not the cancelled remainder.
        self.assertLessEqual(job.progress, round(100 * 5 / 114, 1))
        self.assertEqual(self.transcripts(), [""] * 114)

    def test_quota_error_is_fatal(self):
        self.add_chunks(20)
        job_id = self.add_job()

        def quota(call_no):
            raise api_error(429, "RESOURCE_EXHAUSTED")
        self.fake_models.generate = quota

        self.run_task(job_id)

        self.assertLessEqual(len(self.fake_models.generate_calls), 5)
        self.assertEqual(self.get_job(job_id).status, "failed")

    def test_success_uses_configured_model_and_completes_job(self):
        self.add_chunks(3)
        job_id = self.add_job()

        result = self.run_task(job_id)

        self.assertIn("Success: 3, Failed: 0", result)
        self.assertEqual(self.fake_models.count_tokens_calls, [MODEL])
        self.assertEqual(self.fake_models.generate_calls, [MODEL] * 3)
        self.assertEqual(self.client_factory.call_count, 1)
        self.assertTrue(all(t.startswith("transcript ") for t in self.transcripts()))
        job = self.get_job(job_id)
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.progress, 100)
        self.assertIsNone(job.error_message)

    def test_chunk_ids_limits_run_to_one_chunk(self):
        ids = self.add_chunks(5)
        job_id = self.add_job()

        result = transcribe.transcribe_channel_task.apply(args=(1, False, job_id, [ids[2]])).get()

        self.assertIn("Success: 1, Failed: 0", result)
        self.assertEqual(len(self.fake_models.generate_calls), 1)
        self.assertEqual(self.transcripts(), ["", "", "transcript 1", "", ""])
        self.assertEqual(self.get_job(job_id).status, "completed")

    def test_transient_error_does_not_stop_job_but_marks_it_failed(self):
        self.add_chunks(4)
        job_id = self.add_job()

        def flaky(call_no):
            if call_no == 1:
                raise api_error(503, "UNAVAILABLE")
            return SimpleNamespace(text="ok")
        self.fake_models.generate = flaky

        result = self.run_task(job_id)

        self.assertEqual(len(self.fake_models.generate_calls), 4)
        self.assertIn("Success: 3, Failed: 1", result)
        self.assertEqual(sorted(self.transcripts()), ["", "ok", "ok", "ok"])
        job = self.get_job(job_id)
        self.assertEqual(job.status, "failed")
        self.assertIn("1 of 4 chunks failed", job.error_message)
        self.assertIn("503 UNAVAILABLE", job.error_message)

    def test_repeated_unavailable_stops_job(self):
        self.add_chunks(114)
        job_id = self.add_job()

        def overloaded(call_no):
            raise api_error(503, "UNAVAILABLE", "This model is currently experiencing high demand.")
        self.fake_models.generate = overloaded

        result = self.run_task(job_id)

        # 5 in flight plus at most one new request after each of the first two 503s.
        self.assertLessEqual(len(self.fake_models.generate_calls), 5 + transcribe.MAX_CONSECUTIVE_UNAVAILABLE - 1)
        self.assertIn("consecutive", result)
        self.assertIn("Not attempted", result)
        self.assertEqual(self.get_job(job_id).status, "failed")
        self.assertEqual(self.transcripts(), [""] * 114)

    def test_success_resets_unavailable_count(self):
        run = transcribe.TranscriptionRun()
        for _ in range(transcribe.MAX_CONSECUTIVE_UNAVAILABLE - 1):
            self.assertFalse(run.record_unavailable())
        run.record_success()
        for _ in range(transcribe.MAX_CONSECUTIVE_UNAVAILABLE - 1):
            self.assertFalse(run.record_unavailable())
        self.assertTrue(run.record_unavailable())

    def test_existing_transcripts_are_not_resent_or_overwritten(self):
        self.add_chunks(2, transcript="already done")
        job_id = self.add_job()

        result = self.run_task(job_id)

        self.assertEqual(result, "No chunks to transcribe")
        self.assertEqual(self.fake_models.count_tokens_calls, [])
        self.assertEqual(self.fake_models.generate_calls, [])
        self.assertEqual(self.transcripts(), ["already done"] * 2)
        self.assertEqual(self.get_job(job_id).status, "completed")

    def test_missing_api_key_fails_job(self):
        self.add_chunks(1)
        job_id = self.add_job()

        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            result = self.run_task(job_id)

        self.assertIn("GEMINI_API_KEY missing", result)
        self.client_factory.assert_not_called()
        job = self.get_job(job_id)
        self.assertEqual(job.status, "failed")
        self.assertIn("GEMINI_API_KEY", job.error_message)

    def test_runs_without_job_id(self):
        self.add_chunks(1)

        result = self.run_task(job_id=None)

        self.assertIn("Success: 1", result)


class TranscribeApiTest(DbTestCase):
    def test_trigger_passes_job_id_to_task(self):
        self.add_video()
        db = self.Session()
        try:
            with mock.patch.object(transcribe_api.transcribe.transcribe_channel_task, "delay") as delay:
                delay.return_value = SimpleNamespace(id="celery-123")
                transcribe_api.trigger_transcription(schemas.TranscribeRequest(channel_ids=[1]), db=db)
            job = db.query(models.Job).one()
        finally:
            db.close()

        delay.assert_called_once_with(1, False, job.id, None)
        self.assertEqual(job.celery_task_id, "celery-123")
        self.assertEqual(job.status, "pending")

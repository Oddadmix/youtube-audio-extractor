import os
import unittest
from unittest import mock

from app import models
from app.tasks.process import split_audio_task
from app.utils import settings as settings_util
from tests.support import DbTestCase, write_tone


class SplitAudioTaskTests(DbTestCase):
    def setUp(self):
        super().setUp()
        settings = mock.patch(
            "app.tasks.process.settings_util.get_settings",
            return_value=dict(settings_util.DEFAULT_SETTINGS),
        )
        settings.start()
        self.addCleanup(settings.stop)

        self.pk = self.add_video(status="processing")
        video = self.get_video(self.pk)
        os.makedirs(self.video_dir(video))
        self.source = write_tone(os.path.join(self.video_dir(video), f"{video.video_id}_audio.wav"), 3000)

    def test_no_chunks_marks_failed_and_keeps_source(self):
        with mock.patch("app.tasks.process.audio.split_audio_on_vad", return_value=[]):
            split_audio_task.run(self.pk)

        video = self.get_video(self.pk)
        self.assertEqual(video.status, "failed")
        self.assertIn("No speech chunks", video.error_message)
        self.assertTrue(os.path.exists(self.source))

    def test_split_exception_marks_failed_and_keeps_source(self):
        with mock.patch("app.tasks.process.audio.split_audio_on_vad", side_effect=RuntimeError("boom")):
            split_audio_task.run(self.pk)

        self.assertEqual(self.get_video(self.pk).status, "failed")
        self.assertTrue(os.path.exists(self.source))

    def test_chunks_saved_marks_completed_and_removes_source(self):
        chunk_path = write_tone(os.path.join(os.path.dirname(self.source), "vid00000001_chunk_0.wav"))
        chunks = [{
            "chunk_id": "vid00000001_chunk_0",
            "file_path": chunk_path,
            "duration": 1.0,
            "start_time": 0.0,
            "end_time": 1.0,
        }]
        speaker = mock.MagicMock(id=None, name="Speaker 1")
        with mock.patch("app.tasks.process.audio.split_audio_on_vad", return_value=chunks), \
                mock.patch("app.utils.speaker.identify_or_create_speaker", return_value=speaker):
            split_audio_task.run(self.pk)

        self.assertEqual(self.get_video(self.pk).status, "completed")
        self.assertFalse(os.path.exists(self.source))
        self.assertTrue(os.path.exists(chunk_path))
        db = self.Session()
        try:
            self.assertEqual(db.query(models.AudioChunk).count(), 1)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()

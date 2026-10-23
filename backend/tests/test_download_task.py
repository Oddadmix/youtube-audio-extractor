import os
import unittest
from unittest import mock

from celery.exceptions import Retry

from app.tasks.download import download_video_task
from app.utils import youtube
from tests.support import DbTestCase, write_tone


class DownloadVideoTaskTests(DbTestCase):
    def setUp(self):
        super().setUp()
        retry = mock.patch.object(download_video_task, "retry", side_effect=Retry())
        self.retry = retry.start()
        self.addCleanup(retry.stop)
        transcript = mock.patch.object(youtube, "download_transcript", return_value=None)
        transcript.start()
        self.addCleanup(transcript.stop)

    def run_task(self, video_pk):
        return download_video_task.run(video_pk)

    def test_success_queues_split_and_marks_processing(self):
        pk = self.add_video()

        def fake_download(video_id, output_path):
            return write_tone(os.path.join(output_path, f"{video_id}_audio.wav"))

        split = mock.MagicMock()
        split.delay.return_value.id = "split-task-id"
        with mock.patch.object(youtube, "download_audio", side_effect=fake_download), \
                mock.patch("app.tasks.process.split_audio_task", split):
            self.run_task(pk)

        video = self.get_video(pk)
        self.assertEqual(video.status, "processing")
        self.assertEqual(video.celery_task_id, "split-task-id")
        split.delay.assert_called_once_with(pk)
        self.retry.assert_not_called()
        self.assertTrue(os.path.exists(os.path.join(self.video_dir(video), f"{video.video_id}_audio.wav")))

    def test_transient_failure_persists_retry_state_before_retrying(self):
        pk = self.add_video()
        with mock.patch.object(youtube, "download_audio", return_value=None):
            with self.assertRaises(Retry):
                self.run_task(pk)

        video = self.get_video(pk)
        self.assertEqual(video.status, "pending")
        self.assertEqual(video.retry_count, 1)
        self.assertEqual(video.error_message, "Failed to download audio")
        self.assertEqual(self.retry.call_args.kwargs["countdown"], 120)

    def test_third_failure_is_final_and_persisted(self):
        pk = self.add_video(retry_count=2)
        with mock.patch.object(youtube, "download_audio", return_value=None):
            result = self.run_task(pk)

        video = self.get_video(pk)
        self.assertEqual(video.status, "failed")
        self.assertEqual(video.retry_count, 3)
        self.assertEqual(result, "Failed to download audio")
        self.retry.assert_not_called()

    def test_real_celery_retries_stop_after_three_attempts(self):
        self.retry.stop()
        pk = self.add_video()
        states = []
        with mock.patch.object(youtube, "download_audio", return_value=None) as download:
            # Re-deliver like the worker does after each Retry, capped to catch runaway loops.
            for retries in range(10):
                result = download_video_task.apply(args=[pk], retries=retries)
                states.append(result.state)
                if result.state != "RETRY":
                    break

        self.assertEqual(states, ["RETRY", "RETRY", "SUCCESS"])
        self.assertEqual(download.call_count, 3)
        video = self.get_video(pk)
        self.assertEqual(video.status, "failed")
        self.assertEqual(video.retry_count, 3)

    def test_celery_retry_budget_exhausted_is_final(self):
        pk = self.add_video()
        download_video_task.push_request(retries=download_video_task.max_retries)
        self.addCleanup(download_video_task.pop_request)
        with mock.patch.object(youtube, "download_audio", return_value=None):
            self.run_task(pk)

        self.assertEqual(self.get_video(pk).status, "failed")
        self.retry.assert_not_called()

    def test_unavailable_video_fails_without_retry_or_pausing_others(self):
        pk = self.add_video()
        other = self.add_video(video_id="vid00000002")
        error = youtube.YouTubeAccessError("Private video", blocked=False)
        with mock.patch.object(youtube, "download_audio", side_effect=error):
            self.run_task(pk)

        self.assertEqual(self.get_video(pk).status, "failed")
        self.assertEqual(self.get_video(other).status, "pending")
        self.retry.assert_not_called()

    def test_bot_detection_pauses_pending_videos_without_retry(self):
        pk = self.add_video()
        other = self.add_video(video_id="vid00000002")
        error = youtube.YouTubeAccessError("Sign in to confirm you're not a bot", blocked=True)
        with mock.patch.object(youtube, "download_audio", side_effect=error):
            result = self.run_task(pk)

        video = self.get_video(pk)
        self.assertEqual(video.status, "failed")
        self.assertIn("System Paused", video.error_message)
        self.assertEqual(self.get_video(other).status, "failed")
        self.assertTrue(result.startswith("System Paused"))
        self.retry.assert_not_called()


if __name__ == "__main__":
    unittest.main()

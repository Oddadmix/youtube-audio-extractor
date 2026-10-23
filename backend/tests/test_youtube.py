import os
import shutil
import tempfile
import unittest
from unittest import mock

import yt_dlp

from app.utils import youtube
from tests.support import write_tone


class FakeYoutubeDL:
    """Stands in for yt_dlp.YoutubeDL; never touches the network."""

    def __init__(self, options, on_extract):
        self.options = options
        self.on_extract = on_extract

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        return self.on_extract(self.options, url, download)


def fake_ydl(on_extract, captured=None):
    def factory(options):
        if captured is not None:
            captured.append(options)
        return FakeYoutubeDL(options, on_extract)
    return factory


class ClassifyErrorTests(unittest.TestCase):
    def test_bot_check_is_blocked(self):
        err = youtube.classify_youtube_error(
            "ERROR: [youtube] abc: Sign in to confirm you\u2019re not a bot. Use --cookies-from-browser"
        )
        self.assertIsInstance(err, youtube.YouTubeAccessError)
        self.assertTrue(err.blocked)

    def test_rate_limit_is_blocked(self):
        self.assertTrue(youtube.classify_youtube_error("HTTP Error 429: Too Many Requests").blocked)

    def test_private_video_is_unavailable_not_blocked(self):
        err = youtube.classify_youtube_error("ERROR: [youtube] abc: Private video. Sign in if you've been granted access")
        self.assertIsNotNone(err)
        self.assertFalse(err.blocked)

    def test_transient_error_is_not_classified(self):
        self.assertIsNone(youtube.classify_youtube_error("ERROR: unable to download video data: Connection reset by peer"))


class DiscoveryTests(unittest.TestCase):
    def test_default_limit_is_one(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("YT_DISCOVERY_LIMIT", None)
            self.assertEqual(youtube.get_discovery_limit(), 1)

    def test_limit_from_env_and_invalid_values(self):
        for raw, expected in (("5", 5), ("0", 1), ("-3", 1), ("abc", 1)):
            with mock.patch.dict(os.environ, {"YT_DISCOVERY_LIMIT": raw}):
                self.assertEqual(youtube.get_discovery_limit(), expected, raw)

    def test_get_channel_videos_maps_entries_and_respects_limit(self):
        captured = []

        def on_extract(options, url, download):
            self.assertEqual(url, "https://www.youtube.com/@ExampleChannel/videos")
            self.assertFalse(download)
            return {
                "channel": "Example Channel",
                "entries": [
                    {"id": "first000001", "title": "First", "duration": 1912.0, "upload_date": None},
                    None,
                    {"title": "missing id"},
                    {"id": "second00001", "title": None, "duration": 60},
                ],
            }

        with mock.patch.dict(os.environ, {"YT_DISCOVERY_LIMIT": "3"}), \
                mock.patch.object(yt_dlp, "YoutubeDL", fake_ydl(on_extract, captured)):
            videos, name = youtube.get_channel_videos("https://www.youtube.com/@ExampleChannel/")

        self.assertEqual(captured[0]["playlist_items"], "1-3")
        self.assertTrue(captured[0]["extract_flat"])
        self.assertEqual(name, "Example Channel")
        self.assertEqual([v["video_id"] for v in videos], ["first000001", "second00001"])
        self.assertEqual(videos[1]["title"], "Untitled video")
        self.assertEqual(set(videos[0]), {"video_id", "title", "duration", "upload_date"})

    def test_get_channel_videos_raises_on_failure(self):
        def on_extract(options, url, download):
            raise yt_dlp.utils.DownloadError("ERROR: channel does not exist")

        with mock.patch.object(yt_dlp, "YoutubeDL", fake_ydl(on_extract)):
            with self.assertRaises(yt_dlp.utils.DownloadError):
                youtube.get_channel_videos("https://www.youtube.com/@missing")


class DownloadAudioTests(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)

    def test_success_converts_to_wav_and_removes_temp(self):
        def on_extract(options, url, download):
            self.assertTrue(download)
            self.assertEqual(url, "https://www.youtube.com/watch?v=vid00000001")
            write_tone(options["outtmpl"].replace("%(ext)s", "m4a"), 1500)
            return {"id": "vid00000001"}

        with mock.patch.object(yt_dlp, "YoutubeDL", fake_ydl(on_extract)):
            path = youtube.download_audio("vid00000001", self.out)

        self.assertEqual(path, os.path.join(self.out, "vid00000001_audio.wav"))
        self.assertTrue(os.path.getsize(path) > 0)
        self.assertEqual(os.listdir(self.out), ["vid00000001_audio.wav"])

    def test_32_bit_download_is_written_as_16_bit_wav(self):
        from pydub import AudioSegment

        def on_extract(options, url, download):
            write_tone(options["outtmpl"].replace("%(ext)s", "webm"), sample_width=4)
            return {"id": "vid00000001"}

        with mock.patch.object(yt_dlp, "YoutubeDL", fake_ydl(on_extract)):
            path = youtube.download_audio("vid00000001", self.out)

        self.assertEqual(AudioSegment.from_file(path).sample_width, 2)

    def test_stale_temp_file_is_not_used(self):
        stale = os.path.join(self.out, "vid00000001_temp.webm")
        with open(stale, "wb") as f:
            f.write(b"not audio")

        def on_extract(options, url, download):
            self.assertFalse(os.path.exists(stale))
            write_tone(options["outtmpl"].replace("%(ext)s", "m4a"))
            return {"id": "vid00000001"}

        with mock.patch.object(yt_dlp, "YoutubeDL", fake_ydl(on_extract)):
            self.assertIsNotNone(youtube.download_audio("vid00000001", self.out))

    def test_bot_detection_raises_access_error_and_cleans_up(self):
        def on_extract(options, url, download):
            open(options["outtmpl"].replace("%(ext)s", "m4a.part"), "wb").close()
            raise yt_dlp.utils.DownloadError("ERROR: [youtube] x: Sign in to confirm you're not a bot")

        with mock.patch.object(yt_dlp, "YoutubeDL", fake_ydl(on_extract)):
            with self.assertRaises(youtube.YouTubeAccessError) as ctx:
                youtube.download_audio("vid00000001", self.out)

        self.assertTrue(ctx.exception.blocked)
        self.assertEqual(os.listdir(self.out), [])

    def test_transient_error_returns_none(self):
        def on_extract(options, url, download):
            raise yt_dlp.utils.DownloadError("ERROR: Connection reset by peer")

        with mock.patch.object(yt_dlp, "YoutubeDL", fake_ydl(on_extract)):
            self.assertIsNone(youtube.download_audio("vid00000001", self.out))

    def test_missing_output_returns_none(self):
        with mock.patch.object(yt_dlp, "YoutubeDL", fake_ydl(lambda o, u, d: {"id": "x"})):
            self.assertIsNone(youtube.download_audio("vid00000001", self.out))


if __name__ == "__main__":
    unittest.main()

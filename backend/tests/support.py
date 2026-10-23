import os
import shutil
import tempfile
import unittest
from unittest import mock

from pydub.generators import Sine
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models


def write_tone(path: str, duration_ms: int = 1000, sample_width: int = 2) -> str:
    tone = Sine(440).to_audio_segment(duration=duration_ms).set_frame_rate(16000).set_channels(1)
    tone.set_sample_width(sample_width).export(path, format="wav").close()
    return path


class DbTestCase(unittest.TestCase):
    """Runs tasks against a throwaway SQLite file and DATA_PATH, never the real MySQL or data/."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.tmp, "data")
        os.makedirs(self.data_dir)

        engine = create_engine(f"sqlite:///{os.path.join(self.tmp, 'test.db')}")
        models.Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, expire_on_commit=False)

        patches = [
            mock.patch("app.database.SessionLocal", self.Session),
            mock.patch.dict(os.environ, {"DATA_PATH": self.data_dir}),
            mock.patch("app.utils.slack.notify_slack", return_value=False),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(engine.dispose)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def add_video(self, video_id: str = "vid00000001", status: str = "pending", retry_count: int = 0) -> int:
        db = self.Session()
        try:
            channel = db.query(models.Channel).first()
            if not channel:
                channel = models.Channel(url="https://www.youtube.com/@test", name="Test")
                db.add(channel)
                db.flush()
            video = models.Video(
                video_id=video_id,
                channel_id=channel.id,
                title="Test video",
                duration=10.0,
                status=status,
                retry_count=retry_count,
            )
            db.add(video)
            db.commit()
            return video.id
        finally:
            db.close()

    def get_video(self, video_pk: int) -> models.Video:
        db = self.Session()
        try:
            return db.query(models.Video).filter(models.Video.id == video_pk).one()
        finally:
            db.close()

    def video_dir(self, video: models.Video) -> str:
        return os.path.join(self.data_dir, "channels", str(video.channel_id), "videos", video.video_id)

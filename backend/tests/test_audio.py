import os
import shutil
import tempfile
import unittest

from app.utils import audio
from tests.support import write_tone


class LoadAudioAsTensorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_normalizes_by_actual_bit_depth(self):
        peaks = {}
        for width in (2, 4):
            path = write_tone(os.path.join(self.tmp, f"tone_{width}.wav"), sample_width=width)
            peaks[width] = float(audio.load_audio_as_tensor(path).abs().max())

        self.assertLessEqual(peaks[4], 1.0)
        self.assertAlmostEqual(peaks[4], peaks[2], places=3)


if __name__ == "__main__":
    unittest.main()

import os
import unittest

import pyarrow.parquet as pq

from app import models
from app.tasks.export import export_dataset_task
from tests.support import DbTestCase, write_tone


class ExportTaskTests(DbTestCase):
    def setUp(self):
        super().setUp()
        pk = self.add_video(status="completed")
        video = self.get_video(pk)
        os.makedirs(self.video_dir(video))
        self.chunk_files = {}
        db = self.Session()
        try:
            for i, text in enumerate(["مرحبا", "كيف الحال"]):
                chunk_id = f"{video.video_id}_chunk_{i}"
                path = write_tone(os.path.join(self.video_dir(video), f"{chunk_id}.wav"), 1000 + 500 * i)
                self.chunk_files[chunk_id] = (path, text)
                db.add(models.AudioChunk(
                    chunk_id=chunk_id, video_id=pk, file_path=path,
                    duration=1.0 + 0.5 * i, start_time=0.0, end_time=1.0, transcript_text=text,
                ))
            self.job_id = models.Job(job_type="export", entity_id="hf_dataset", status="pending")
            db.add(self.job_id)
            db.commit()
            self.job_id = self.job_id.id
        finally:
            db.close()

    def test_local_export_writes_parquet_with_embedded_audio(self):
        export_dataset_task.run(self.job_id)

        db = self.Session()
        try:
            self.assertEqual(db.query(models.Job).get(self.job_id).status, "completed")
        finally:
            db.close()

        parquet_path = os.path.join(self.data_dir, "hf_dataset.parquet")
        self.assertTrue(os.path.exists(parquet_path), "file served by /api/export/download is missing")
        rows = pq.read_table(parquet_path).to_pylist()
        self.assertEqual(len(rows), 2)
        for row in rows:
            path, text = self.chunk_files[row["chunk_id"]]
            self.assertEqual(row["transcript_text"], text)
            with open(path, "rb") as f:
                self.assertEqual(row["audio"]["bytes"], f.read())


if __name__ == "__main__":
    unittest.main()

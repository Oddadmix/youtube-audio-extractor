from celery import Celery
import os
from dotenv import load_dotenv

load_dotenv()

# CRITICAL: Set PyTorch multiprocessing to spawn mode BEFORE any torch imports
# This prevents SIGSEGV crashes with PyTorch models in Celery fork workers
try:
    import torch.multiprocessing as mp
    mp.set_start_method('spawn', force=True)
except RuntimeError:
    pass  # Already set

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "youtube_audio_extractor",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    include=["app.tasks.download", "app.tasks.process", "app.tasks.export", "app.tasks.transcribe"]
)


celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_send_sent_event=True,
    task_acks_late=True,
    worker_concurrency=3,  # Number of threads when using threads pool
    worker_pool='threads',  # Use threads instead of fork to avoid PyTorch SIGSEGV
    worker_max_tasks_per_child=10,  # Restart workers after 10 tasks to prevent memory leaks
    task_prefetch_multiplier=1
)



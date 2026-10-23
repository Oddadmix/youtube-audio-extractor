import os
import logging
import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from typing import Optional
from ..celery_app import celery_app
from .. import models, database
from ..utils import jobs as jobs_util, logging as activity_log, settings as settings_util
from google import genai
from google.genai import errors, types

logger = logging.getLogger(__name__)

# API errors that will fail every remaining chunk the same way (bad key, no access,
# retired model, quota exhausted), so the job stops instead of sending the rest.
FATAL_STATUS_CODES = {401, 403, 404, 429}
# The SDK already retries each 503 internally, so a few in a row means the model is
# overloaded for now; stop rather than spend ~1 minute failing every remaining chunk.
MAX_CONSECUTIVE_UNAVAILABLE = 3


class FatalTranscriptionError(Exception):
    pass


class TranscriptionRun:
    """Stop signal, consecutive-503 counter and first chunk error shared by the worker threads."""

    def __init__(self):
        self.stop = threading.Event()
        self._lock = threading.Lock()
        self._consecutive_unavailable = 0
        self.first_error: Optional[str] = None

    def record_error(self, message: str):
        with self._lock:
            if self.first_error is None:
                self.first_error = message

    def record_success(self):
        with self._lock:
            self._consecutive_unavailable = 0

    def record_unavailable(self) -> bool:
        """Returns True once the consecutive-503 limit is reached."""
        with self._lock:
            self._consecutive_unavailable += 1
            return self._consecutive_unavailable >= MAX_CONSECUTIVE_UNAVAILABLE


def _describe_api_error(e: errors.APIError) -> str:
    return f"Gemini API error {e.code} {e.status}: {e.message}"


def process_chunk_transcription(
    chunk_id: int,
    file_path: str,
    client: genai.Client,
    model_name: str,
    prompt: str,
    run: TranscriptionRun,
) -> Optional[bool]:
    """
    Helper function to transcribe a single chunk.
    Creates its own DB session to be thread-safe.
    Returns None when skipped because the job was stopped.
    Raises FatalTranscriptionError (and sets ``run.stop``) on errors that affect every chunk.
    """
    if run.stop.is_set():
        return None

    db = database.SessionLocal()
    try:
        if not os.path.exists(file_path):
            logger.warning(f"Audio file not found: {file_path}")
            run.record_error(f"chunk {chunk_id}: audio file not found")
            return False

        with open(file_path, "rb") as f:
            audio_data = f.read()

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=audio_data, mime_type="audio/wav"),
                    prompt
                ]
            )
        except errors.APIError as e:
            if e.code in FATAL_STATUS_CODES:
                run.stop.set()
                raise FatalTranscriptionError(_describe_api_error(e)) from e
            if e.code == 503 and run.record_unavailable():
                run.stop.set()
                raise FatalTranscriptionError(
                    f"{_describe_api_error(e)} ({MAX_CONSECUTIVE_UNAVAILABLE} consecutive)"
                ) from e
            raise

        run.record_success()
        transcribed_text = response.text
        if transcribed_text:
            # Re-fetch chunk in this session to update
            chunk = db.query(models.AudioChunk).filter(models.AudioChunk.id == chunk_id).first()
            if chunk:
                chunk.transcript_text = transcribed_text
                db.commit()
                return True
        else:
            logger.warning(f"Empty response for chunk {chunk_id}")
            run.record_error(f"chunk {chunk_id}: empty response from Gemini")
        return False

    except FatalTranscriptionError:
        raise
    except Exception as e:
        logger.error(f"Error processing chunk {chunk_id}: {e}")
        detail = _describe_api_error(e) if isinstance(e, errors.APIError) else str(e)
        run.record_error(f"chunk {chunk_id}: {detail}")
        return False
    finally:
        db.close()


@celery_app.task(bind=True)
def transcribe_channel_task(
    self,
    channel_id: int,
    force_retranscribe: bool = False,
    job_id: Optional[int] = None,
    chunk_ids: Optional[list[int]] = None,
):
    """
    Transcribe all audio chunks for a given channel using Gemini API with parallel workers.
    ``chunk_ids`` restricts the run to those chunks of the channel.
    """
    db = database.SessionLocal()
    job = jobs_util.get_job(db, job_id=job_id)
    try:
        jobs_util.update_job(db, job, status="processing", progress=0)

        # Check API Key
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.error("GEMINI_API_KEY not found in environment variables.")
            jobs_util.update_job(db, job, status="failed", error="GEMINI_API_KEY is not set on the worker.")
            return "Failed: GEMINI_API_KEY missing"

        channel = db.query(models.Channel).filter(models.Channel.id == channel_id).first()
        if not channel:
            jobs_util.update_job(db, job, status="failed", error=f"Channel {channel_id} not found.")
            return "Channel not found"

        settings = settings_util.get_settings()
        model_name = settings.get("transcription_model") or settings_util.DEFAULT_SETTINGS["transcription_model"]
        prompt = settings.get("transcription_prompt", "Transcribe this audio file accurately in Egyptian Arabic.")

        activity_log.log_activity(db, f"Starting parallel transcription for channel: {channel.name or channel.url} (model: {model_name})", channel_id=channel_id)

        # Get chunks
        chunks_query = db.query(models.AudioChunk).join(models.Video).filter(models.Video.channel_id == channel_id)

        if not force_retranscribe:
            chunks_query = chunks_query.filter(
                (models.AudioChunk.transcript_text == None) | (models.AudioChunk.transcript_text == "")
            )
        if chunk_ids is not None:
            chunks_query = chunks_query.filter(models.AudioChunk.id.in_(chunk_ids))

        # We fetch only necessary data (id, file_path) to pass to threads
        # This prevents detached instance issues
        chunks_data = [(c.id, c.file_path) for c in chunks_query.all()]

        if not chunks_data:
            activity_log.log_activity(db, "No chunks to transcribe.", channel_id=channel_id)
            jobs_util.update_job(db, job, status="completed", progress=100)
            return "No chunks to transcribe"

        client = genai.Client(api_key=api_key)

        # countTokens is free and fails the same way generateContent would for a
        # bad key or a retired model, so check once before sending any audio.
        try:
            client.models.count_tokens(model=model_name, contents=[prompt])
        except errors.APIError as e:
            message = f"Transcription not started: {_describe_api_error(e)}"
            logger.error(message)
            activity_log.log_activity(db, message, channel_id=channel_id, level="error")
            jobs_util.update_job(db, job, status="failed", error=message)
            return f"Failed: {message}"

        logger.info(f"Found {len(chunks_data)} chunks to transcribe for channel {channel_id} with {model_name}")
        logger.info(f"Using transcription prompt: {prompt[:50]}...")

        success_count = 0
        fail_count = 0
        skipped = 0
        total = len(chunks_data)
        fatal_error: Optional[str] = None
        run = TranscriptionRun()

        # Use ThreadPoolExecutor for concurrency
        workers = 5  # As requested: 4 to 5 workers
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_chunk = {
                executor.submit(process_chunk_transcription, cid, path, client, model_name, prompt, run): cid
                for cid, path in chunks_data
            }

            for i, future in enumerate(as_completed(future_to_chunk)):
                try:
                    result = future.result()
                    if result is None:
                        skipped += 1
                    elif result:
                        success_count += 1
                    else:
                        fail_count += 1
                except CancelledError:
                    skipped += 1
                except FatalTranscriptionError as exc:
                    fail_count += 1
                    if fatal_error is None:
                        fatal_error = str(exc)
                        logger.error(f"Stopping transcription for channel {channel_id}: {exc}")
                        for f in future_to_chunk:
                            f.cancel()
                except Exception as exc:
                    logger.error(f"Chunk processing generated an exception: {exc}")
                    fail_count += 1

                # Log progress every 10 chunks or so
                if (i + 1) % 10 == 0:
                    logger.info(f"Progress: {i + 1}/{total} chunks processed.")
                    jobs_util.update_job(db, job, progress=round(100 * (success_count + fail_count) / total, 1))

        summary = f"Success: {success_count}, Failed: {fail_count}, Not attempted: {skipped}"

        if fatal_error:
            message = f"Stopped: {fatal_error}. {summary}"
            activity_log.log_activity(db, f"Transcription {message}", channel_id=channel_id, level="error")
            progress = round(100 * (success_count + fail_count) / total, 1)
            jobs_util.update_job(db, job, status="failed", progress=progress, error=message)
            return f"Failed: {fatal_error}. {summary}"

        level = "info" if fail_count == 0 else "warning"
        activity_log.log_activity(db, f"Transcription completed. {summary}", channel_id=channel_id, level=level)
        if fail_count:
            # Re-running only retries chunks that still have no transcript.
            error = f"{fail_count} of {total} chunks failed (first error: {run.first_error or 'empty response'}). {summary}"
            jobs_util.update_job(db, job, status="failed", progress=100, error=error)
        else:
            jobs_util.update_job(db, job, status="completed", progress=100)
        return f"Transcription completed. {summary}"

    except Exception as e:
        db.rollback()
        logger.error(f"Transcription task failed: {e}")
        try:
            jobs_util.update_job(db, job, status="failed", error=f"Unexpected error: {e}")
        except Exception:
            db.rollback()
        return f"Task Failed: {str(e)}"
    finally:
        db.close()

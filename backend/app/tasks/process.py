import os
from ..celery_app import celery_app
from .. import models, database
from ..utils import audio, logging as activity_log, settings as settings_util
import logging

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, loglevel="INFO", time_limit=65, soft_time_limit=60)
def split_audio_task(self, video_id: int):
    """Split video audio into chunks based on silence."""
    pid = os.getpid()
    logger.info(f"[PID {pid}] --- split_audio_task STARTED for video_id: {video_id} ---")
    db = database.SessionLocal()
    try:
        video = db.query(models.Video).filter(models.Video.id == video_id).first()
        if not video:
            return "Video not found"
        
        activity_log.log_activity(db, "Starting audio splitting...", video_id=video_id)
        video.status = "processing"
        # Clear existing chunks for this video to allow clean re-chunking
        db.query(models.AudioChunk).filter(models.AudioChunk.video_id == video.id).delete()
        db.commit()
    
        base_data_dir = os.getenv("DATA_PATH", os.path.join(os.getcwd(), "data"))
        logger.info(f"Checking data path: {base_data_dir}")
        if not os.path.exists(base_data_dir):
            error_msg = f"Data path not found: {base_data_dir}. Is external drive mounted?"
            logger.error(error_msg)
            video.status = "failed"
            video.error_message = error_msg
            db.commit()
            return error_msg
            
        data_dir = os.path.join(base_data_dir, "channels", str(video.channel_id), "videos", str(video.video_id))
        audio_path = os.path.join(data_dir, f"{video.video_id}_audio.wav")
        if not os.path.exists(audio_path):
            # Check for other extensions (legacy)
            for ext in ['mp4', 'webm', 'm4a', 'mp3']:
                test_path = os.path.join(data_dir, f"{video.video_id}_audio.{ext}")
                if os.path.exists(test_path):
                    audio_path = test_path
                    break
        
        if not os.path.exists(audio_path):
            video.status = "failed"
            video.error_message = "Audio file not found for splitting"
            db.commit()
            return "Audio not found"
            
        # Load persisted settings
        processing_settings = settings_util.get_settings()
        
        # Get channel_id for hierarchical directory structure
        channel_id = video.channel_id if video.channel_id else None
        
        logger.info(f"Calling audio.split_audio_on_vad for video {video.video_id}")
        chunks = audio.split_audio_on_vad(
            audio_path=audio_path,
            output_dir=base_data_dir,
            video_id=video.video_id,
            channel_id=channel_id,
            sample_rate=processing_settings.get("sample_rate", 16000),
            silence_thresh=processing_settings.get("silence_thresh", -40),
            min_silence_len=processing_settings.get("min_silence_len", 700),
            min_chunk_len=processing_settings.get("min_chunk_len", 1000),
            max_chunk_len=processing_settings.get("max_chunk_len", 20000),
            vad_threshold=processing_settings.get("vad_threshold", 0.25),
            min_speech_duration_ms=processing_settings.get("min_speech_duration_ms", 250)
        )
        
        # Load transcript to align (simplified: for now just placeholder alignment)
        # transcript_path = os.path.join(data_dir, f"{video.video_id}_transcript.txt")
        transcript_text = ""
        # logger.info(f"Attempting to load transcript from: {transcript_path}")
        # if os.path.exists(transcript_path):
        #     with open(transcript_path, "r", encoding="utf-8") as f:
        #         transcript_text = f.read()
        #     logger.info(f"Transcript loaded for video {video.video_id}. Length: {len(transcript_text)} characters.")
        # else:
        #     logger.warning(f"Transcript file not found for video {video.video_id} at {transcript_path}. Proceeding without transcript.")

        valid_chunks_count = 0
        for c_data in chunks:
            valid_chunks_count += 1
            
            # Identify or create speaker for this chunk
            from ..utils import speaker as speaker_util
            from ..utils import slack
            try:
                speaker = speaker_util.identify_or_create_speaker(
                    db,
                    c_data["file_path"],
                    threshold=processing_settings.get("speaker_similarity_threshold", 0.75)
                )
                speaker_id = speaker.id
                logger.info(f"Chunk assigned to {speaker.name}")
            except Exception as speaker_err:
                error_msg = f"Speaker identification failed for chunk {c_data['chunk_id']}: {str(speaker_err)}"
                logger.error(error_msg)
                
                # Send Slack alert
                slack.notify_slack(
                    f"⚠️ *Speaker ID Failed*\n"
                    f"Video: {video.video_id}\n"
                    f"Chunk: {c_data['chunk_id']}\n"
                    f"Error: {str(speaker_err)}"
                )
                
                # Continue with NULL speaker_id
                speaker_id = None
            
            chunk = models.AudioChunk(
                chunk_id=c_data["chunk_id"],
                video_id=video.id,
                file_path=c_data["file_path"],
                duration=c_data["duration"],
                start_time=c_data["start_time"],
                end_time=c_data["end_time"],
                transcript_text="",
                speaker_id=speaker_id
            )
            db.add(chunk)
            
        activity_log.log_activity(db, f"Audio split into {valid_chunks_count} VAD-verified chunks.", video_id=video_id)
        video.status = "completed"
        db.commit()
        
        # Automated cleanup of source files after successful processing
        try:
            patterns = [
                f"{video.video_id}_audio.wav",
                f"{video.video_id}_audio.mp4",
                f"{video.video_id}_audio.webm",
                f"{video.video_id}_audio.m4a",
                f"{video.video_id}_audio.mp3"
            ]
            for pattern in patterns:
                file_path = os.path.join(data_dir, pattern)
                if os.path.exists(file_path):
                    os.remove(file_path)
            logger.info(f"Automated cleanup: Deleted source files for video {video.video_id}")
        except Exception as cleanup_err:
            logger.warning(f"Automated cleanup failed for video {video.video_id}: {cleanup_err}")
            
        logger.info(f"[PID {pid}] --- split_audio_task FINISHED for video_id: {video_id} ---")
            
    except Exception as e:
        db.rollback()
        if 'video' in locals() and video:
            activity_log.log_activity(db, f"Audio splitting failed: {str(e)}", video_id=video_id, level="error")
            video.status = "failed"
            video.error_message = str(e)
            db.commit()
        return str(e)
    finally:
        # Final cleanup attempt in finally to ensure it runs even if commit fails
        if 'video' in locals() and video and video.status in ["completed", "failed"]:
            try:
                patterns = [
                    f"{video.video_id}_audio.wav",
                    f"{video.video_id}_audio.mp4",
                    f"{video.video_id}_audio.webm",
                    f"{video.video_id}_audio.m4a",
                    f"{video.video_id}_audio.mp3"
                ]
                base_data_dir = os.getenv("DATA_PATH", os.path.join(os.getcwd(), "data"))
                data_dir = os.path.join(base_data_dir, "channels", str(video.channel_id), "videos", str(video.video_id))
                for pattern in patterns:
                    file_path = os.path.join(data_dir, pattern)
                    if os.path.exists(file_path):
                        os.remove(file_path)
            except Exception:
                db.close()
                logger.error(f"Failed to cleanup source files for video {video_id}")
                raise Exception("Failed to cleanup source files for video {video_id}")
        db.close()
        
    return f"Processed chunks for video {video_id}"

@celery_app.task(bind=True, loglevel="INFO", time_limit=65, soft_time_limit=60)
def reprocess_long_chunks_task(self):
    """Identify and split chunks that exceed the current max_chunk_len."""
    db = database.SessionLocal()
    try:
        settings = settings_util.get_settings()
        max_chunk_len = settings.get("max_chunk_len", 20000)
        
        # Find chunks longer than max_chunk_len + 1s tolerance
        long_chunks = db.query(models.AudioChunk).filter(models.AudioChunk.duration > (max_chunk_len / 1000.0 + 1)).all()
        
        if not long_chunks:
            return "No lengthy chunks found."
            
        activity_log.log_activity(db, f"Starting refinement for {len(long_chunks)} lengthy chunks...", level="info")
        
        processed_ids = []
        for chunk in long_chunks:
            video_id = chunk.video.video_id
            old_file_path = chunk.file_path
            old_transcript = chunk.transcript_text
            
            # Split this specific chunk - filter settings to only allowed kwargs
            allowed_keys = ['sample_rate', 'silence_thresh', 'min_silence_len', 'min_chunk_len', 'max_chunk_len']
            split_kwargs = {k: v for k, v in settings.items() if k in allowed_keys}
            
            # Get channel_id for hierarchical directory structure
            channel_id = chunk.video.channel_id if chunk.video.channel_id else None
            
            base_data_dir = os.getenv("DATA_PATH", os.path.join(os.getcwd(), "data"))
            
            new_sub_chunks = audio.split_audio_on_vad(
                audio_path=old_file_path,
                output_dir=base_data_dir,
                video_id=f"{chunk.chunk_id}_ref", # Ensure unique prefix
                channel_id=channel_id,
                **split_kwargs
            )
            
            if new_sub_chunks:
                # Add new sub-chunks
                for i, c_data in enumerate(new_sub_chunks):
                    # Identify speaker for each sub-chunk
                    from ..utils import speaker as speaker_util
                    from ..utils import slack
                    
                    # Get settings for threshold
                    settings = settings_util.get_settings()
                    
                    try:
                        speaker = speaker_util.identify_or_create_speaker(
                            db,
                            c_data["file_path"],
                            threshold=settings.get("speaker_similarity_threshold", 0.75)
                        )
                        speaker_id = speaker.id
                    except Exception as speaker_err:
                        error_msg = f"Speaker identification failed for refined chunk: {str(speaker_err)}"
                        logger.error(error_msg)
                        
                        # Send Slack alert
                        slack.notify_slack(
                            f"⚠️ *Speaker ID Failed (Refinement)*\n"
                            f"Chunk: {c_data['chunk_id']}\n"
                            f"Error: {str(speaker_err)}"
                        )
                        
                        speaker_id = None
                    
                    new_chunk = models.AudioChunk(
                        chunk_id=c_data["chunk_id"],
                        video_id=chunk.video_id,
                        file_path=c_data["file_path"],
                        duration=c_data["duration"],
                        start_time=chunk.start_time + c_data["start_time"], # Relative offset
                        end_time=chunk.start_time + c_data["end_time"],     # Relative offset
                        transcript_text=old_transcript, # Inherit transcript fragment
                        speaker_id=speaker_id
                    )
                    db.add(new_chunk)
                
                # Mark old chunk for deletion
                db.delete(chunk)
                # Remove old file
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)
                
                processed_ids.append(chunk.chunk_id)
                db.commit()
                
        activity_log.log_activity(db, f"Chunk refinement completed. Re-split {len(processed_ids)} giant chunks.", level="success")
        
        return f"Refined {len(processed_ids)} chunks."
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error in reprocess_long_chunks: {e}")
        activity_log.log_activity(db, f"Chunk refinement failed: {str(e)}", level="error")
        db.close()
        raise Exception(str(e))
    db.close()
    return f"Refined {len(processed_ids)} chunks."

@celery_app.task(bind=True, loglevel="INFO", time_limit=65, soft_time_limit=60)
def refine_vad_task(self, video_id: int):
    """Refine existing chunks using VAD."""
    pid = os.getpid()
    logger.info(f"[PID {pid}] --- refine_vad_task STARTED for video_id: {video_id} ---")
    db = database.SessionLocal()
    try:
        video = db.query(models.Video).filter(models.Video.id == video_id).first()
        if not video:
            return "Video not found"
            
        activity_log.log_activity(db, "Starting VAD refinement...", video_id=video_id)
        
        chunks = db.query(models.AudioChunk).filter(models.AudioChunk.video_id == video.id).all()
        removed_count = 0
        total_count = len(chunks)
        
        for chunk in chunks:
            if not os.path.exists(chunk.file_path):
                # If file missing, remove from DB anyway
                db.delete(chunk)
                continue
                
            is_valid = audio.validate_speech(chunk.file_path)
            if not is_valid:
                # Remove file and DB entry
                try:
                    os.remove(chunk.file_path)
                except Exception:
                    pass
                db.delete(chunk)
                removed_count += 1
        
        db.commit()
        activity_log.log_activity(db, f"VAD Verification completed. Removed {removed_count}/{total_count} chunks.", video_id=video_id, level="success")
        logger.info(f"[PID {pid}] --- refine_vad_task FINISHED for video_id: {video_id} ---")
        return f"Removed {removed_count} chunks"
    except Exception as e:
        db.rollback()
        activity_log.log_activity(db, f"VAD refinement failed: {str(e)}", video_id=video_id, level="error")
        db.close()
        raise Exception(str(e))

    return f"Removed {removed_count} chunks"
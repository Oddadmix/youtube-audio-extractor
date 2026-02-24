import os
from typing import Optional
from ..celery_app import celery_app
from .. import models, database
from ..utils import dataset, logging as activity_log, slack
import logging

logger = logging.getLogger(__name__)

@celery_app.task(bind=True)
def export_dataset_task(self, job_id: int, repo_id: Optional[str] = None, hf_token: Optional[str] = None, private: bool = True, channel_ids: Optional[list[int]] = None, channel_names: Optional[dict[str, str]] = None, include_archived: bool = False):
    """Export processed chunks to a HuggingFace dataset with channel-based subsets."""
    db = database.SessionLocal()
    try:
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        if not job:
            return "Job not found"
        
        activity_log.log_activity(db, f"Starting dataset export...", level="info")
        job.status = "processing"
        db.commit()
    
        # Get channels
        query = db.query(models.Channel)
        
        # Filter archived channels unless explicitly included
        if not include_archived:
            query = query.filter(models.Channel.archived == False)
            
        if channel_ids:
            query = query.filter(models.Channel.id.in_(channel_ids))
            
        channels = query.all()
        
        if not channels:
            raise Exception("No channels found in database")
        
        chunks_by_channel = {}
        total_chunks = 0
        
        for channel in channels:
            # Get all chunks for videos in this channel
            chunks = db.query(models.AudioChunk).join(
                models.Video
            ).filter(
                models.Video.channel_id == channel.id
            ).all()
            
            if not chunks:
                logger.warning(f"No chunks found for channel: {channel.name or channel.url}")
                continue
            
            # Determine folder name for channel subset
            channel_name = channel.name or f"channel_{channel.id}"
            
            # Override with custom name if provided
            if channel_names and str(channel.id) in channel_names:
                custom_name = channel_names[str(channel.id)].strip()
                if custom_name:
                    import re
                    # Sanitize folder name: remove special chars, replace spaces with underscores, lower case
                    # Allow alphanumeric, underscore, hyphen
                    custom_name = re.sub(r'[^a-zA-Z0-9_\-]', '', custom_name.replace(' ', '_'))
                    if custom_name:
                        channel_name = custom_name
            
            chunks_data = []
            
            for chunk in chunks:
                chunks_data.append({
                    "chunk_id": chunk.chunk_id,
                    "audio": chunk.file_path,
                    "transcript_text": chunk.transcript_text,
                    "duration": chunk.duration,
                    "original_video_id": chunk.video.video_id,
                    "channel_name": channel_name,
                    "channel_url": channel.url,
                    "speaker_id": chunk.speaker_id if chunk.speaker_id else None,
                    "speaker_name": chunk.speaker.name if chunk.speaker else None
                })
            
            chunks_by_channel[channel_name] = chunks_data
            total_chunks += len(chunks_data)
            logger.info(f"Channel '{channel_name}': {len(chunks_data)} chunks")
        
        if not chunks_by_channel:
            raise Exception("No chunks found for any channel")
        
        activity_log.log_activity(
            db, 
            f"Creating dataset with {len(chunks_by_channel)} channel subsets ({total_chunks} total chunks)...", 
            level="info"
        )
        
        # Create dataset with channel-based subsets
        hf_dataset = dataset.create_hf_dataset_with_subsets(chunks_by_channel)
        if not hf_dataset:
            raise Exception("Failed to create dataset object")
        
        if repo_id and hf_token:
            activity_log.log_activity(db, f"Pushing dataset to Hub: {repo_id}...", level="info")
            success = dataset.push_to_hub(hf_dataset, repo_id, hf_token, private=private)
            if not success:
                raise Exception("Failed to push dataset to HuggingFace Hub. Check logs for details.")
            
            activity_log.log_activity(db, f"Successfully pushed to HuggingFace Hub!", level="success")
            
            # Send Slack notification on success
            subset_list = "\n".join([f"  • {name} ({len(data)} chunks)" for name, data in chunks_by_channel.items()])
            slack.notify_slack(
                f"✅ *Dataset Export Completed*\n"
                f"Repository: {repo_id}\n"
                f"Total Chunks: {total_chunks}\n"
                f"Channel Subsets ({len(chunks_by_channel)}):\n{subset_list}\n"
                f"Private: {private}"
            )
            # Only save locally if NOT pushing to Hub
            data_dir = os.getenv("DATA_PATH", os.path.join(os.getcwd(), "data"))
            export_path = os.path.join(data_dir, "hf_dataset")
            local_path, parquet_path = dataset.save_dataset_locally(hf_dataset, export_path)
            activity_log.log_activity(db, f"Dataset saved locally at {parquet_path}", level="info")
            
        job.status = "completed"
        job.progress = 100
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error exporting dataset: {e}", exc_info=True)
        if 'job' in locals() and job:
            activity_log.log_activity(db, f"Dataset export failed: {str(e)}", level="error")
            job.status = "failed"
            db.commit()
            
            # Send Slack notification on failure
            slack.notify_slack(
                f"🚨 *Dataset Export Failed*\n"
                f"Error: {str(e)}"
            )
        return str(e)
    finally:
        db.close()
        
    return "Export completed"

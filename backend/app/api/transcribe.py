from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from .. import database, models, schemas
from ..tasks import transcribe
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/", response_model=dict)
def trigger_transcription(
    request: schemas.TranscribeRequest,
    db: Session = Depends(database.get_db),
):
    """
    Trigger transcription for specific channels.
    """
    if not request.channel_ids:
        raise HTTPException(status_code=400, detail="No channel IDs provided")
    
    # Verify channels exist
    channels = db.query(models.Channel).filter(models.Channel.id.in_(request.channel_ids)).all()
    if len(channels) != len(request.channel_ids):
        found_ids = [c.id for c in channels]
        missing = set(request.channel_ids) - set(found_ids)
        raise HTTPException(status_code=404, detail=f"Channels not found: {missing}")

    task_ids = []
    for channel in channels:
        # Create a Job entry for tracking (optional but good practice)
        job = models.Job(job_type="transcription", entity_id=f"channel_{channel.id}", status="pending")
        db.add(job)
        db.commit()
        db.refresh(job)
        
        # Trigger Celery task
        # We pass force_retranscribe from request
        task = transcribe.transcribe_channel_task.delay(channel.id, request.force_retranscribe, job.id, request.chunk_ids)
        
        job.celery_task_id = task.id
        db.commit()
        
        task_ids.append(task.id)
        
    return {
        "message": f"Started {len(channels)} transcription tasks",
        "task_ids": task_ids
    }

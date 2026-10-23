from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
import logging
import uuid
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas, database
from ..tasks.download import process_channel_task

logger = logging.getLogger(__name__)

router = APIRouter()


def _queue_channel_processing(db: Session, channel_id: int) -> str:
    """Create the job row before queueing so the task can always find and update it."""
    task_id = str(uuid.uuid4())
    db.add(models.Job(job_type="channel_process", entity_id=str(channel_id), status="pending", celery_task_id=task_id))
    db.commit()
    process_channel_task.apply_async(args=[channel_id], task_id=task_id)
    return task_id


@router.post("/", response_model=schemas.Channel)
def create_channel(channel: schemas.ChannelCreate, db: Session = Depends(database.get_db)):
    db_channel = models.Channel(url=str(channel.url), name=channel.name)
    db.add(db_channel)
    try:
        db.commit()
    except:
        db.rollback()
        raise HTTPException(status_code=400, detail="Channel already exists")
    db.refresh(db_channel)
    db_channel.celery_task_id = _queue_channel_processing(db, db_channel.id)
    db.commit()
    return db_channel

@router.post("/upload", response_model=List[schemas.Channel])
async def upload_channels(file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    content = await file.read()
    urls = content.decode("utf-8").splitlines()
    created_channels = []
    for url in urls:
        if not url.strip():
            continue
        db_channel = models.Channel(url=url.strip())
        db.add(db_channel)
        try:
            db.commit()
            db.refresh(db_channel)
            db_channel.celery_task_id = _queue_channel_processing(db, db_channel.id)
            db.commit()
            created_channels.append(db_channel)
        except:
            db.rollback()
    return created_channels

@router.get("/", response_model=List[schemas.Channel])
def read_channels(skip: int = 0, limit: int = 100, include_archived: bool = False, db: Session = Depends(database.get_db)):
    query = db.query(models.Channel)
    if not include_archived:
        query = query.filter(models.Channel.archived == False)
    return query.offset(skip).limit(limit).all()

@router.post("/{channel_id}/process")
def trigger_process_channel(channel_id: int, db: Session = Depends(database.get_db)):
    channel = db.query(models.Channel).filter(models.Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    task_id = _queue_channel_processing(db, channel_id)
    channel.celery_task_id = task_id
    db.commit()
    return {"message": "Processing triggered", "task_id": task_id}

@router.post("/{channel_id}/stop")
def stop_process_channel(channel_id: int, db: Session = Depends(database.get_db)):
    channel = db.query(models.Channel).filter(models.Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    if channel.celery_task_id:
        from ..celery_app import celery_app
        try:
            celery_app.control.revoke(channel.celery_task_id, terminate=True)
        except Exception as e:
            logger.warning(f"Could not revoke task {channel.celery_task_id}: {e}")
    
    channel.celery_task_id = None
    channel.status = "failed"
    db.commit()
    return {"message": "Processing stopped (force cleared)"}

@router.post("/{channel_id}/reset")
def reset_channel(channel_id: int, db: Session = Depends(database.get_db)):
    channel = db.query(models.Channel).filter(models.Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    channel.status = "pending"
    channel.celery_task_id = None
    db.commit()
    return {"message": "Channel reset"}

@router.patch("/{channel_id}/archive")
def archive_channel(channel_id: int, db: Session = Depends(database.get_db)):
    """Archive a channel."""
    channel = db.query(models.Channel).filter(models.Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    channel.archived = True
    db.commit()
    return {"message": "Channel archived successfully"}

@router.patch("/{channel_id}/unarchive")  
def unarchive_channel(channel_id: int, db: Session = Depends(database.get_db)):
    """Unarchive a channel."""
    channel = db.query(models.Channel).filter(models.Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    channel.archived = False
    db.commit()
    return {"message": "Channel unarchived successfully"}

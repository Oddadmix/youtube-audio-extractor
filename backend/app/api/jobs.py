from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas, database

router = APIRouter()

@router.get("/", response_model=List[schemas.Job])
def read_jobs(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(models.Job).order_by(models.Job.created_at.desc()).offset(skip).limit(limit).all()

@router.get("/{job_id}", response_model=schemas.Job)
def read_job(job_id: int, db: Session = Depends(database.get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.post("/clear")
def clear_all_tasks(db: Session = Depends(database.get_db)):
    """Clear all pending tasks from Celery and revoke active ones."""
    from ..celery_app import celery_app
    
    # 1. Purge the queue (removes waiting tasks)
    purged_count = celery_app.control.purge()
    
    # 2. Revoke active/processing tasks found in database
    # Get all pending/processing videos and channels
    revoked_count = 0
    
    # Videos
    videos = db.query(models.Video).filter(models.Video.status.in_(["pending", "downloading", "processing"])).all()
    for video in videos:
        if video.celery_task_id:
            try:
                celery_app.control.revoke(video.celery_task_id, terminate=True)
                revoked_count += 1
            except:
                pass
        video.status = "failed"
        video.error_message = "Task cleared by user"
        video.celery_task_id = None
    
    # Channels
    channels = db.query(models.Channel).filter(models.Channel.status.in_(["pending", "processing"])).all()
    for channel in channels:
        if channel.celery_task_id:
            try:
                celery_app.control.revoke(channel.celery_task_id, terminate=True)
                revoked_count += 1
            except:
                pass
        channel.status = "failed"
        channel.celery_task_id = None
        
    # Jobs (Exports, etc)
    jobs = db.query(models.Job).filter(models.Job.status.in_(["pending", "processing"])).all()
    for job in jobs:
        if job.celery_task_id:
            try:
                celery_app.control.revoke(job.celery_task_id, terminate=True)
                revoked_count += 1
            except:
                pass
        job.status = "failed"
            
    db.commit()
    
    return {
        "message": f"Queue cleared. {purged_count} waiting tasks removed. {revoked_count} active tasks revoked."
    }

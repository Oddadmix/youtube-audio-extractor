from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from .. import models, schemas, database
import os
import uuid

from ..tasks.process import reprocess_long_chunks_task

router = APIRouter()

@router.post("/reprocess-lengthy")
def trigger_reprocess_lengthy(db: Session = Depends(database.get_db)):
    # Create the job row before queueing so the task can always find and update it.
    job = models.Job(job_type="maintenance", entity_id="chunk_refinement", status="pending", celery_task_id=str(uuid.uuid4()))
    db.add(job)
    db.commit()
    db.refresh(job)

    reprocess_long_chunks_task.apply_async(task_id=job.celery_task_id)

    return {"job_id": job.id, "message": "Chunk refinement started"}

@router.get("/stats", response_model=schemas.ChunkStats)
def get_chunk_stats(include_archived: bool = False, db: Session = Depends(database.get_db)):
    query = db.query(models.AudioChunk.duration).join(models.Video).join(models.Channel)
    
    if not include_archived:
        query = query.filter(models.Channel.archived == False)
        
    durations = [c[0] for c in query.all()]
    
    if not durations:
        return {
            "count": 0,
            "avg_duration": 0,
            "p90_duration": 0,
            "p95_duration": 0,
            "min_duration": 0,
            "max_duration": 0,
            "total_duration": 0
        }
    
    import numpy as np
    return {
        "count": len(durations),
        "avg_duration": float(np.mean(durations)),
        "p90_duration": float(np.percentile(durations, 90)),
        "p95_duration": float(np.percentile(durations, 95)),
        "min_duration": float(np.min(durations)),
        "max_duration": float(np.max(durations)),
        "total_duration": float(np.sum(durations))
    }

@router.get("/", response_model=schemas.PaginatedChunks)
def read_chunks(
    video_id: Optional[int] = None,
    page: int = 1,
    size: int = 20,
    include_archived: bool = False,
    db: Session = Depends(database.get_db)
):
    query = db.query(models.AudioChunk).join(models.Video).join(models.Channel)
    
    if not include_archived:
        query = query.filter(models.Channel.archived == False)
        
    if video_id:
        query = query.filter(models.AudioChunk.video_id == video_id)
    
    total = query.count()
    pages = (total + size - 1) // size
    skip = (page - 1) * size
    items = query.order_by(models.AudioChunk.created_at.desc()).offset(skip).limit(size).all()
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages
    }

@router.get("/{chunk_id}/audio")
def get_chunk_audio(chunk_id: str, db: Session = Depends(database.get_db)):
    chunk = db.query(models.AudioChunk).filter(models.AudioChunk.chunk_id == chunk_id).first()
    if not chunk or not os.path.exists(chunk.file_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(chunk.file_path, media_type="audio/wav")

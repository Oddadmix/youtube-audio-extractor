from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from . import models, schemas, database
from .api import channels, videos, chunks, jobs, export, logs, settings
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Egyptian ASR Dataset Builder")

# Create database tables
models.Base.metadata.create_all(bind=database.engine)
from .utils.jobs import ensure_job_columns
ensure_job_columns(database.engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(channels.router, prefix="/api/channels", tags=["channels"])
app.include_router(videos.router, prefix="/api/videos", tags=["videos"])
app.include_router(chunks.router, prefix="/api/chunks", tags=["chunks"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(export.router, prefix="/api/export", tags=["export"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
from .api import transcribe
app.include_router(transcribe.router, prefix="/api/transcribe", tags=["transcribe"])

@app.get("/")
async def root():
    return {"message": "Egyptian ASR Dataset Builder API"}

@app.get("/api/stats")
async def get_stats(include_archived: bool = False, db: Session = Depends(database.get_db)):
    video_query = db.query(models.Video).join(models.Channel)
    if not include_archived:
        video_query = video_query.filter(models.Channel.archived == False)
        
    total_videos = video_query.count()
    processed_videos = video_query.filter(models.Video.status == "completed").count()
    failed_videos = video_query.filter(models.Video.status == "failed").count()
    
    chunk_query = db.query(models.AudioChunk).join(models.Video).join(models.Channel)
    if not include_archived:
        chunk_query = chunk_query.filter(models.Channel.archived == False)
        
    total_chunks = chunk_query.count()
    
    # Calculate total duration
    total_duration = chunk_query.with_entities(models.func.sum(models.AudioChunk.duration)).scalar() or 0
    
    return {
        "total_videos": total_videos,
        "processed_videos": processed_videos,
        "failed_videos": failed_videos,
        "total_chunks": total_chunks,
        "total_duration_hours": total_duration / 3600
    }

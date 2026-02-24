from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Text, LargeBinary, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
import enum

class Status(str, enum.Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class JobType(str, enum.Enum):
    DOWNLOAD = "download"
    SPLIT = "split"
    EXPORT = "export"

class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(255), unique=True, index=True)
    name = Column(String(255), nullable=True)
    status = Column(String(50), default=Status.PENDING)
    celery_task_id = Column(String(255), nullable=True)
    archived = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    videos = relationship("Video", back_populates="channel")

class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(String(255), unique=True, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"))
    title = Column(String(255))
    duration = Column(Float)
    upload_date = Column(String(50), nullable=True)
    status = Column(String(50), default=Status.PENDING)
    retry_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    celery_task_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    channel = relationship("Channel", back_populates="videos")
    chunks = relationship("AudioChunk", back_populates="video")

class Speaker(Base):
    __tablename__ = "speakers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    embedding = Column(LargeBinary, nullable=False)  # Store numpy array as binary
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    chunks = relationship("AudioChunk", back_populates="speaker")

class AudioChunk(Base):
    __tablename__ = "audio_chunks"

    id = Column(Integer, primary_key=True, index=True)
    chunk_id = Column(String(255), unique=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"))
    speaker_id = Column(Integer, ForeignKey("speakers.id"), nullable=True)
    file_path = Column(String(500))
    duration = Column(Float)
    start_time = Column(Float)
    end_time = Column(Float)
    transcript_text = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    video = relationship("Video", back_populates="chunks")
    speaker = relationship("Speaker", back_populates="chunks")

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_type = Column(String(50)) # download, split, export
    entity_id = Column(String(255)) # video_id or export_id
    celery_task_id = Column(String(255), nullable=True)
    status = Column(String(50), default=Status.PENDING)
    progress = Column(Float, default=0)
    error_log_path = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=True)
    message = Column(Text)
    level = Column(String(50), default="info") # info, warning, error
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    video = relationship("Video")
    channel = relationship("Channel")

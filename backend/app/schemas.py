from pydantic import BaseModel, HttpUrl
from typing import List, Optional
from datetime import datetime

class ChannelBase(BaseModel):
    url: str # More permissive than HttpUrl
    name: Optional[str] = None

class ChannelCreate(ChannelBase):
    pass

class ExportRequest(BaseModel):
    repo_id: Optional[str] = None
    hf_token: Optional[str] = None
    private: bool = True
    channel_ids: Optional[List[int]] = None
    channel_names: Optional[dict[str, str]] = None

class TranscribeRequest(BaseModel):
    channel_ids: List[int]
    force_retranscribe: bool = False

class Channel(ChannelBase):
    id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class VideoBase(BaseModel):
    video_id: str
    title: str
    duration: float
    upload_date: Optional[str] = None

class Video(VideoBase):
    id: int
    channel_id: int
    status: str
    retry_count: int
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    channel: Optional[Channel] = None

    class Config:
        from_attributes = True

class AudioChunkBase(BaseModel):
    chunk_id: str
    video_id: int
    file_path: str
    duration: float
    start_time: float
    end_time: float
    transcript_text: str
    speaker_id: Optional[int] = None

class Speaker(BaseModel):
    id: int
    name: str
    created_at: datetime

    class Config:
        from_attributes = True

class AudioChunk(AudioChunkBase):
    id: int
    created_at: datetime
    speaker: Optional[Speaker] = None

    class Config:
        from_attributes = True

class JobBase(BaseModel):
    job_type: str
    entity_id: str

class Job(JobBase):
    id: int
    celery_task_id: Optional[str] = None
    status: str
    progress: float
    error_log_path: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class Settings(BaseModel):
    sample_rate: int = 16000
    silence_thresh: int = -40
    min_silence_len: int = 700
    min_chunk_len: int = 1000
    max_chunk_len: int = 20000
    retry_count: int = 3
    transcription_prompt: str = """Transcribe this audio file accurately in Egyptian Arabic. 
- Use Egyptian dialect spelling (Ammiya).
- Don't convert to formal Arabic.
- Use punctuation appropriately based on the audio.
- Only provide the transcribed text without additional commentary."""
    vad_threshold: float = 0.25
    min_speech_duration_ms: int = 250
    speaker_similarity_threshold: float = 0.75  # Threshold for speaker matching (0.0-1.0)

class ActivityLogBase(BaseModel):
    video_id: Optional[int] = None
    channel_id: Optional[int] = None
    message: str
    level: str = "info"

class ActivityLog(ActivityLogBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class PaginatedVideos(BaseModel):
    items: List[Video]
    total: int
    page: int
    size: int
    pages: int

class PaginatedChunks(BaseModel):
    items: List[AudioChunk]
    total: int
    page: int
    size: int
    pages: int

class ChunkStats(BaseModel):
    count: int
    avg_duration: float
    p90_duration: float
    p95_duration: float
    min_duration: float
    max_duration: float
    total_duration: float

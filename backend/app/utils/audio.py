import os
from pydub import AudioSegment, silence
from typing import List, Dict, Any
import logging
import time
import threading

logger = logging.getLogger(__name__)
logger.info("audio.py module loaded")

# Thread lock for VAD model access (needed with threads pool)
_vad_lock = threading.Lock()

def load_audio_as_tensor(audio_path: str, sampling_rate: int = 16000):
    """
    Load audio file using Pydub and convert to torch tensor.
    Bypasses torchaudio.load to avoid backend issues (libtorchcodec).
    """
    import torch
    import numpy as np
    import os
    import time
    
    pid = os.getpid()
    logger.info(f"[PID {pid}] load_audio_as_tensor started for {audio_path}")
    start_time = time.time()
    
    # Load with pydub (very stable)
    audio = AudioSegment.from_file(audio_path)
    logger.info(f"[PID {pid}] Audio loaded with Pydub (Time: {time.time() - start_time:.2f}s)")
    
    audio = audio.set_frame_rate(sampling_rate).set_channels(1)
    
    # Get raw samples as numpy array
    samples = np.array(audio.get_array_of_samples())
    
    # Convert to float32 and normalize to [-1, 1]
    samples = samples.astype(np.float32) / 32768.0
    
    tensor = torch.from_numpy(samples)
    logger.info(f"[PID {pid}] Converted to tensor. Shape: {tensor.shape} (Total load time: {time.time() - start_time:.2f}s)")
    logger.info(f"[PID {pid}] load_audio_as_tensor FINISHED for {audio_path}")
    return tensor

def split_audio_on_vad(
    audio_path: str,
    output_dir: str,
    video_id: str,
    channel_id: int = None,
    min_silence_len: int = 700,
    silence_thresh: int = -40,
    min_chunk_len: int = 1000,
    max_chunk_len: int = 20000,
    sample_rate: int = 16000,
    vad_threshold: float = 0.25,
    min_speech_duration_ms: int = 250
) -> List[Dict[str, Any]]:
    """Split audio into chunks based on VAD speech detection."""
    pid = os.getpid()
    try:
        start_time_proc = time.time()
        logger.info(f"[PID {pid}] --- split_audio_on_vad STARTED for {video_id} at {time.ctime()} ---")
        
        # Load VAD model and utils
        logger.info("Checking VAD model singleton...")
        model, utils = get_vad_model()
        (get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks) = utils
        logger.info(f"VAD model and utils ready. (Time: {time.time() - start_time_proc:.2f}s)")
        
        # Read audio for VAD using our robust Pydub loader
        import torch
        logger.info(f"Reading audio for VAD: {audio_path}")
        read_start = time.time()
        wav = load_audio_as_tensor(audio_path, sampling_rate=sample_rate)
        logger.info(f"Audio read successful. Samples: {len(wav)}, Sample rate: {sample_rate} (Time: {time.time() - read_start:.2f}s)")
        
        logger.info(f"Running VAD on {audio_path} ({len(wav)/sample_rate:.2f}s)...")
        # Get speech timestamps using VAD with inference mode for speed
        # Use thread lock to prevent state corruption in threads pool
        with _vad_lock:
            # Reset model state to prevent contamination from previous calls
            model.reset_states()
            
            with torch.inference_mode():
                speech_timestamps = get_speech_timestamps(
                    wav,
                    model,
                    sampling_rate=int(sample_rate),  # Ensure int type
                    threshold=float(vad_threshold),  # Ensure float32 type
                    min_speech_duration_ms=int(min_speech_duration_ms),  # Ensure int type
                    min_silence_duration_ms=int(min_silence_len)  # Ensure int type
                )
        logger.info(f"VAD completed, found {len(speech_timestamps)} segments.")
        
        # Convert timestamps from samples to milliseconds for consistency with Pydub
        nonsilent_ranges = []
        for ts in speech_timestamps:
            start_ms = int((ts['start'] / sample_rate) * 1000)
            end_ms = int((ts['end'] / sample_rate) * 1000)
            nonsilent_ranges.append((start_ms, end_ms))
            
        # Load with Pydub for exporting/processing
        logger.info(f"Loading audio with Pydub for exporting: {audio_path}")
        audio = AudioSegment.from_file(audio_path)
        logger.info("Audio loaded with Pydub.")
        audio = audio.set_frame_rate(sample_rate).set_channels(1)
        
        processed_chunks = []
        if not nonsilent_ranges:
            return []

        current_group = []
        current_group_duration = 0
        
        def save_chunk(group, index):
            if not group: return
            start_time = group[0][0]
            end_time = group[-1][1]
            # Add more padding to prevent cut-offs
            start_pad = max(0, start_time - 500)
            end_pad = min(len(audio), end_time + 500)
            
            chunk_audio = audio[start_pad:end_pad]
            chunk_id = f"{video_id}_chunk_{index}"
            file_name = f"{chunk_id}.wav"
            
            # Use hierarchical structure if channel_id is provided
            if channel_id is not None:
                chunk_dir = os.path.join(output_dir, 'channels', str(channel_id), 'videos', str(video_id))
                os.makedirs(chunk_dir, exist_ok=True)
                file_path = os.path.join(chunk_dir, file_name)
            else:
                # Fallback to flat structure
                file_path = os.path.join(output_dir, file_name)
            
            chunk_audio.export(file_path, format="wav")
            
            processed_chunks.append({
                "chunk_id": chunk_id,
                "file_path": file_path,
                "duration": len(chunk_audio) / 1000.0,
                "start_time": start_pad / 1000.0,
                "end_time": end_pad / 1000.0
            })

        chunk_idx = 0
        import random
        
        # Determine randomized target for the first chunk
        current_target_len = random.randint(min_chunk_len, max_chunk_len)

        for start, end in nonsilent_ranges:
            seg_duration = end - start
            
            # If the segment itself is longer than current_target_len, 
            # we must split it even without silence
            if seg_duration > max_chunk_len:
                if current_group:
                    save_chunk(current_group, chunk_idx)
                    chunk_idx += 1
                    current_group = []
                    current_group_duration = 0
                
                # Split this long segment into sub-chunks with random sizes
                sub_start = start
                while sub_start < end:
                    target = random.randint(min_chunk_len, max_chunk_len)
                    sub_end = min(sub_start + target, end)
                    
                    if (sub_end - sub_start) >= min_chunk_len or sub_end == end:
                        save_chunk([(sub_start, sub_end)], chunk_idx)
                        chunk_idx += 1
                    sub_start = sub_end
                
                current_target_len = random.randint(min_chunk_len, max_chunk_len)
                continue

            # Regular grouping logic
            if current_group_duration + seg_duration > current_target_len and current_group_duration >= min_chunk_len:
                save_chunk(current_group, chunk_idx)
                chunk_idx += 1
                current_group = [(start, end)]
                current_group_duration = seg_duration
                current_target_len = random.randint(min_chunk_len, max_chunk_len)
            else:
                current_group.append((start, end))
                current_group_duration += seg_duration
                
        # Save last group
        if current_group:
            save_chunk(current_group, chunk_idx)
            
        logger.info(f"[PID {pid}] --- split_audio_on_vad FINISHED for {video_id}. Found {len(processed_chunks)} chunks. Total Time: {time.time() - start_time_proc:.2f}s ---")
        return processed_chunks
    except Exception as e:
        logger.error(f"Error splitting audio for {video_id}: {e}")
        return []

# Alias for backwards compatibility
split_audio_on_silence = split_audio_on_vad

def get_audio_duration(file_path: str) -> float:
    """Get duration of audio file in seconds."""
    try:
        audio = AudioSegment.from_file(file_path)
        return len(audio) / 1000.0
    except Exception:
        return 0.0

# VAD Model Singleton
_vad_model = None
_vad_utils = None

def get_vad_model():
    """Load Silero VAD model."""
    global _vad_model, _vad_utils
    pid = os.getpid()
    if _vad_model is None:
        import torch
        logger.info(f"[PID {pid}] Loading Silero VAD model for the first time...")
        # Optimize CPU threads for inference
        # CRITICAL: With concurrent Celery workers, we MUST use single thread per worker
        # to avoid CPU thrashing and deadlocks on file locks/resources.
        threads = 1
        torch.set_num_threads(threads)
        logger.info(f"[PID {pid}] Setting torch threads to {threads}")
        
        # Load from torch hub
        model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                      model='silero_vad',
                                      force_reload=False,
                                      trust_repo=True)
        _vad_model = model
        _vad_utils = utils
        logger.info(f"[PID {pid}] VAD model loaded successfully.")
    logger.info(f"[PID {pid}] get_vad_model FINISHED.")
    return _vad_model, _vad_utils

def validate_speech(audio_path: str, min_speech_ratio: float = 0.2) -> bool:
    """
    Check if audio file contains enough speech using Silero VAD.
    Returns True if valid speech is detected, False otherwise.
    """
    import torch
    import torchaudio
    
    try:
        model, utils = get_vad_model()
        (get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks) = utils
        
        # Read audio using robust Pydub loader
        wav = load_audio_as_tensor(audio_path, sampling_rate=16000)
        
        # Get speech timestamps with thread lock
        with _vad_lock:
            # Reset model state
            model.reset_states()
            
            with torch.inference_mode():
                speech_timestamps = get_speech_timestamps(
                    wav, 
                    model,
                    sampling_rate=int(16000),  # Ensure int type
                    threshold=float(0.5),  # Ensure float type
                    min_speech_duration_ms=int(250),  # Ensure int type
                    min_silence_duration_ms=int(100)  # Ensure int type
                )
        
        if not speech_timestamps:
            return False
            
        # Calculate total speech duration
        total_speech_samples = sum([t['end'] - t['start'] for t in speech_timestamps])
        total_samples = len(wav)
        
        speech_ratio = total_speech_samples / total_samples
        
        # Also ensure we have at least some absolute duration of speech (e.g. 0.5s)
        min_absolute_speech = 16000 * 0.5
        
        if total_speech_samples < min_absolute_speech:
            logger.info(f"Speech validation FAILED for {audio_path}: total speech samples {total_speech_samples} < min {min_absolute_speech}")
            return False
            
        logger.info(f"Speech validation PASSED for {audio_path}: ratio {speech_ratio:.2f}")
        return True # For now, just existence of robust speech segments is enough
        
    except Exception as e:
        logger.error(f"VAD check failed for {audio_path}: {e}")
        # Default to True on error to avoid deleting valid files if VAD fails
        return True

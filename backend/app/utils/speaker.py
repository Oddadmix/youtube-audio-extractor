"""
Speaker identification and embedding extraction utility.

Uses SpeechBrain's ECAPA-TDNN model to extract speaker embeddings from audio chunks
and automatically group chunks by speaker voice similarity.
"""
import os
import logging
import numpy as np
from typing import Optional
import pickle

logger = logging.getLogger(__name__)

# Lazy loading of models to avoid importing on module load
_embedding_model = None
_similarity_metric = None

def load_embedding_model():
    """
    Lazy load SpeechBrain ECAPA-TDNN speaker embedding model.
    Returns the model instance.
    
    Fork-safe: Each worker process will load its own copy of the model.
    """
    global _embedding_model, _similarity_metric
    
    if _embedding_model is None:
        try:
            import torch
            from speechbrain.inference.speaker import EncoderClassifier
            
            # Force CPU mode to avoid CUDA initialization issues in forked processes
            torch.set_num_threads(1)
            
            logger.info("Loading SpeechBrain speaker embedding model...")
            _embedding_model = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir="tmp/speaker_model",
                run_opts={"device": "cpu"}  # Force CPU to avoid CUDA fork issues
            )
            logger.info("Speaker embedding model loaded successfully")
            
            # Import similarity metric
            from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine
            _similarity_metric = sklearn_cosine
            
        except Exception as e:
            logger.error(f"Failed to load speaker embedding model: {e}")
            raise
    
    return _embedding_model

def extract_embedding(audio_path: str) -> np.ndarray:
    """
    Extract speaker embedding from an audio file.
    
    Args:
        audio_path: Path to the audio file
        
    Returns:
        numpy array of shape (192,) containing the speaker embedding
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    try:
        import torchaudio
        model = load_embedding_model()
        
        # Load audio file
        waveform, sample_rate = torchaudio.load(audio_path)
        
        # Resample if needed (ECAPA-TDNN expects 16kHz)
        if sample_rate != 16000:
            resampler = torchaudio.transforms.Resample(sample_rate, 16000)
            waveform = resampler(waveform)
        
        # Extract embedding - encode_batch expects a list of tensors
        embedding = model.encode_batch(waveform)
        
        # Handle different return types (could be list or tensor)
        if isinstance(embedding, list):
            embedding = embedding[0]  # Get first element if it's a list
        
        # Convert to numpy and squeeze to 1D array
        embedding_np = embedding.squeeze().cpu().numpy()
        
        logger.debug(f"Extracted embedding for {audio_path}, shape: {embedding_np.shape}")
        return embedding_np
        
    except Exception as e:
        logger.error(f"Failed to extract embedding from {audio_path}: {e}")
        raise

def compare_embeddings(emb1: np.ndarray, emb2: np.ndarray) -> float:
    """
    Compare two speaker embeddings using cosine similarity.
    
    Args:
        emb1: First embedding vector
        emb2: Second embedding vector
        
    Returns:
        Similarity score between 0 and 1 (higher = more similar)
    """
    try:
        # Reshape for sklearn compatibility (expects 2D arrays)
        emb1_2d = emb1.reshape(1, -1)
        emb2_2d = emb2.reshape(1, -1)
        
        similarity = _similarity_metric(emb1_2d, emb2_2d)[0][0]
        return float(similarity)
    except Exception as e:
        logger.error(f"Failed to compare embeddings: {e}")
        return 0.0

def serialize_embedding(embedding: np.ndarray) -> bytes:
    """
    Serialize numpy embedding to bytes for database storage.
    
    Args:
        embedding: numpy array embedding
        
    Returns:
        Serialized bytes
    """
    return pickle.dumps(embedding)

def deserialize_embedding(embedding_bytes: bytes) -> np.ndarray:
    """
    Deserialize bytes back to numpy embedding.
    
    Args:
        embedding_bytes: Serialized embedding
        
    Returns:
        numpy array embedding
    """
    return pickle.loads(embedding_bytes)

def identify_or_create_speaker(db, audio_path: str, threshold: float = 0.75):
    """
    Identify speaker from audio chunk or create new speaker entry.
    
    Extracts speaker embedding and compares with all existing speakers.
    If similarity exceeds threshold, returns matching speaker.
    Otherwise, creates a new speaker entry.
    
    Args:
        db: Database session
        audio_path: Path to audio chunk
        threshold: Similarity threshold for speaker matching (default: 0.75)
        
    Returns:
        Speaker model instance
    """
    from .. import models
    
    try:
        # Extract embedding from audio
        new_embedding = extract_embedding(audio_path)
        
        # Get all existing speakers
        speakers = db.query(models.Speaker).all()
        
        best_match = None
        best_similarity = 0.0
        
        # Compare with existing speakers
        for speaker in speakers:
            existing_embedding = deserialize_embedding(speaker.embedding)
            similarity = compare_embeddings(new_embedding, existing_embedding)
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = speaker
        
        # If similarity exceeds threshold, return matching speaker
        if best_match and best_similarity >= threshold:
            logger.info(f"Matched to existing speaker: {best_match.name} (similarity: {best_similarity:.3f})")
            return best_match
        
        # Otherwise, create new speaker
        speaker_count = db.query(models.Speaker).count()
        new_speaker = models.Speaker(
            name=f"Speaker {speaker_count + 1}",
            embedding=serialize_embedding(new_embedding)
        )
        db.add(new_speaker)
        db.flush()  # Get the ID without committing
        
        logger.info(f"Created new speaker: {new_speaker.name}")
        return new_speaker
        
    except Exception as e:
        logger.error(f"Failed to identify or create speaker for {audio_path}: {e}")
        raise

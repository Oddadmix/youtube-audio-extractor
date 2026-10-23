import os
import json
from typing import Dict, Any

DATA_PATH = os.getenv("DATA_PATH", os.path.join(os.getcwd(), "data"))
SETTINGS_PATH = os.path.join(DATA_PATH, "settings.json")

DEFAULT_SETTINGS = {
    "sample_rate": 16000,
    "silence_thresh": -40,
    "min_silence_len": 700,
    "min_chunk_len": 5000,
    "max_chunk_len": 30000,
    "retry_count": 3,
    "transcription_prompt": """Transcribe this audio file accurately in Egyptian Arabic. 
- Use Egyptian dialect spelling (Ammiya).
- Don't convert to formal Arabic.
- Use punctuation appropriately based on the audio.
- Only provide the transcribed text without additional commentary.""",
    "transcription_model": os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
    "vad_threshold": 0.25,
    "min_speech_duration_ms": 250,
    "speaker_similarity_threshold": 0.75
}

def get_settings() -> Dict[str, Any]:
    """Load settings from JSON file or return defaults."""
    if not os.path.exists(SETTINGS_PATH):
        # Ensure data directory exists
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS
    
    try:
        with open(SETTINGS_PATH, "r") as f:
            settings = json.load(f)
            # Merge with defaults to ensure all keys exist
            return {**DEFAULT_SETTINGS, **settings}
    except Exception:
        return DEFAULT_SETTINGS

def save_settings(settings: Dict[str, Any]):
    """Save settings to JSON file."""
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=4)

import os
from datasets import Dataset, DatasetDict, Audio, Features, Value, concatenate_datasets
import pandas as pd
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

def create_hf_dataset(chunks_data: List[Dict[str, Any]]):
    """Create a HuggingFace dataset object from processed chunks."""
    try:
        df = pd.DataFrame(chunks_data)
        
        # Define features
        features = Features({
            "chunk_id": Value("string"),
            "audio": Audio(sampling_rate=16000),
            "transcript_text": Value("string"),
            "duration": Value("float32"),
            "original_video_id": Value("string"),
            "speaker_id": Value("int32"),
            "speaker_name": Value("string")
        })
        
        # Create dataset
        dataset = Dataset.from_pandas(df, features=features)
        return dataset
    except Exception as e:
        logger.error(f"Error creating HF dataset: {e}")
        return None

def create_hf_dataset_with_subsets(chunks_by_channel: Dict[str, List[Dict[str, Any]]]):
    """
    Create a HuggingFace DatasetDict with channel-based subsets.
    
    Args:
        chunks_by_channel: Dictionary mapping channel names to their chunks data
        
    Returns:
        DatasetDict with each channel as a separate config/subset
    """
    try:
        dataset_dict = {}
        
        # Define features with channel metadata
        features = Features({
            "chunk_id": Value("string"),
            "audio": Audio(sampling_rate=16000),
            "transcript_text": Value("string"),
            "duration": Value("float32"),
            "original_video_id": Value("string"),
            "channel_name": Value("string"),
            "channel_url": Value("string"),
            "speaker_id": Value("int32"),
            "speaker_name": Value("string")
        })
        
        for channel_name, chunks_data in chunks_by_channel.items():
            if not chunks_data:
                logger.warning(f"No chunks for channel: {channel_name}")
                continue
                
            df = pd.DataFrame(chunks_data)
            
            # Create dataset for this channel
            dataset = Dataset.from_pandas(df, features=features)
            
            # Use sanitized channel name as config name (replace spaces and special chars)
            config_name = sanitize_config_name(channel_name)
            dataset_dict[config_name] = dataset
            
            logger.info(f"Created subset '{config_name}' with {len(chunks_data)} chunks")
        
        if not dataset_dict:
            logger.error("No datasets created - all channels were empty")
            return None
            
        return DatasetDict(dataset_dict)
    except Exception as e:
        logger.error(f"Error creating HF dataset with subsets: {e}", exc_info=True)
        return None

def sanitize_config_name(name: str) -> str:
    """
    Sanitize channel name to be a valid HuggingFace config/split name.
    HuggingFace split names should match '^\w+(\.\w+)*$', which means 
    alphanumeric, underscores, and dots only (no hyphens).
    """
    import re
    # Convert to lowercase
    sanitized = name.lower()
    # Replace spaces and hyphens with underscores
    sanitized = sanitized.replace(" ", "_").replace("-", "_")
    # Remove any other non-alphanumeric and non-underscore characters
    sanitized = re.sub(r'[^a-z0-9_]', '', sanitized)
    # Remove leading/trailing underscores or dots
    sanitized = sanitized.strip("_.")
    # Ensure it starts with a word character if possible
    return sanitized or "unknown"

def _embed_audio(ds):
    """Store audio bytes in the table; otherwise Parquet only holds container-local file paths."""
    from datasets.table import embed_table_storage
    return ds.with_format("arrow").map(embed_table_storage, batched=True).with_format(None)

def save_dataset_locally(dataset, output_path: str):
    """Save dataset to disk in both Arrow and Parquet formats."""
    try:
        # Save arrow format
        dataset.save_to_disk(output_path)
        # Save parquet format; {output_path}.parquet is what /api/export/download serves
        parquet_path = f"{output_path}.parquet"
        
        # Handle both Dataset and DatasetDict
        if isinstance(dataset, DatasetDict):
            # For DatasetDict, save each subset plus one combined file
            subsets = []
            for config_name, ds in dataset.items():
                ds = _embed_audio(ds)
                config_parquet_path = f"{output_path}_{config_name}.parquet"
                ds.to_parquet(config_parquet_path)
                subsets.append(ds)
            concatenate_datasets(subsets).to_parquet(parquet_path)
        else:
            _embed_audio(dataset).to_parquet(parquet_path)
            
        return output_path, parquet_path
    except Exception as e:
        logger.error(f"Error saving dataset locally: {e}")
        return None, None

def push_to_hub(dataset, repo_id: str, token: str, private: bool = True):
    """Push dataset object directly to HuggingFace Hub."""
    try:
        logger.info(f"Pushing dataset to {repo_id} (private={private})...")
        
        # Handle both Dataset and DatasetDict
        if isinstance(dataset, DatasetDict):
            logger.info(f"Pushing DatasetDict with {len(dataset)} subsets: {list(dataset.keys())}")
        
        dataset.push_to_hub(repo_id, token=token, private=private)
        logger.info(f"Successfully pushed dataset to {repo_id}")
        return True
    except Exception as e:
        logger.error(f"Error pushing to Hub: {str(e)}", exc_info=True)
        return False

import os
from pytubefix import YouTube, Channel
from pytubefix.exceptions import VideoUnavailable
from typing import List, Dict, Any, Optional
import json
import logging

logger = logging.getLogger(__name__)

# yt-dlp error fragments (lower-cased) meaning YouTube is blocking this client/IP.
_BLOCKED_MARKERS = (
    "not a bot",
    "http error 429",
    "too many requests",
    "rate-limited",
)

# yt-dlp error fragments (lower-cased) meaning this particular video can't be fetched.
_UNAVAILABLE_MARKERS = (
    "private video",
    "video unavailable",
    "this video is unavailable",
    "members-only",
    "join this channel",
    "confirm your age",
    "age-restricted",
    "not available in your country",
    "removed by the uploader",
    "has been terminated",
    "copyright",
    "live event will begin",
    "premieres in",
)


class YouTubeAccessError(Exception):
    """YouTube refused the request; retrying the same download will not help.

    ``blocked`` is True when YouTube is blocking this client/IP (bot check,
    rate limit) rather than a single video being unavailable.
    """

    def __init__(self, message: str, blocked: bool):
        super().__init__(message)
        self.blocked = blocked


def classify_youtube_error(message: str) -> Optional[YouTubeAccessError]:
    """Return a YouTubeAccessError for non-retryable yt-dlp errors, else None."""
    text = message.lower().replace("\u2019", "'")
    if any(marker in text for marker in _BLOCKED_MARKERS):
        return YouTubeAccessError(message, blocked=True)
    if any(marker in text for marker in _UNAVAILABLE_MARKERS):
        return YouTubeAccessError(message, blocked=False)
    return None


def get_discovery_limit() -> int:
    """Max videos discovered per channel scan (YT_DISCOVERY_LIMIT, default 1)."""
    raw = os.getenv("YT_DISCOVERY_LIMIT", "1")
    try:
        limit = int(raw)
    except ValueError:
        logger.warning(f"Invalid YT_DISCOVERY_LIMIT={raw!r}; using 1")
        return 1
    return max(limit, 1)


def get_channel_videos(channel_url: str) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """Discover the newest videos of a channel using yt-dlp.

    At most ``YT_DISCOVERY_LIMIT`` videos are returned so a channel scan never
    queues a whole channel by accident.
    """
    import yt_dlp

    limit = get_discovery_limit()
    logger.info(f"Fetching up to {limit} video(s) for channel: {channel_url}")

    video_page = channel_url.rstrip("/")
    if not video_page.endswith("/videos"):
        video_page += "/videos"

    options = {
        "extract_flat": True,
        "playlist_items": f"1-{limit}",
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(video_page, download=False)

        if not info:
            raise RuntimeError("YouTube returned no channel information")

        videos = []

        for entry in info.get("entries", []):
            if not entry:
                continue

            video_id = entry.get("id")
            if not video_id:
                continue

            videos.append({
                "video_id": video_id,
                "title": entry.get("title") or "Untitled video",
                "duration": entry.get("duration"),
                "upload_date": entry.get("upload_date"),
            })

        channel_name = info.get("channel") or info.get("title")

        logger.info(f"Discovered {len(videos)} video(s) (limit {limit})")
        return videos, channel_name

    except Exception as e:
        logger.error(f"Video discovery failed: {e}", exc_info=True)
        raise

def _remove_temp_files(output_path: str, prefix: str) -> None:
    for filename in os.listdir(output_path):
        if filename.startswith(prefix):
            try:
                os.remove(os.path.join(output_path, filename))
            except OSError as e:
                logger.warning(f"Could not remove temp file {filename}: {e}")


def download_audio(video_id: str, output_path: str) -> Optional[str]:
    """Download audio using yt-dlp and convert it to WAV.

    Returns the WAV path, or None on a failure that may be transient.
    Raises YouTubeAccessError when YouTube blocks the request or the video is
    unavailable, because retrying cannot succeed.
    """
    import yt_dlp
    from pydub import AudioSegment

    os.makedirs(output_path, exist_ok=True)

    url = f"https://www.youtube.com/watch?v={video_id}"
    temp_prefix = f"{video_id}_temp."
    wav_path = os.path.join(output_path, f"{video_id}_audio.wav")

    options = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(output_path, temp_prefix + "%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 0,
        "fragment_retries": 0,
    }

    # A leftover temp file from an earlier failed attempt must not be picked up.
    _remove_temp_files(output_path, temp_prefix)

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)

        if not info:
            raise RuntimeError("No video information returned")

        temp_files = [
            os.path.join(output_path, filename)
            for filename in os.listdir(output_path)
            if filename.startswith(temp_prefix)
            and not filename.endswith(".part")
        ]

        if not temp_files:
            raise RuntimeError("Downloaded audio file was not found")

        temp_path = temp_files[0]

        # Decoded YouTube audio is 32-bit; 16-bit halves the WAV and chunk sizes.
        audio = AudioSegment.from_file(temp_path).set_sample_width(2)
        audio.export(wav_path, format="wav").close()

        logger.info(f"Successfully created WAV audio: {wav_path}")
        return wav_path

    except Exception as e:
        access_error = classify_youtube_error(str(e))
        if access_error:
            logger.error(f"YouTube refused audio for {video_id}: {e}")
            raise access_error from e
        logger.error(
            f"Error downloading audio for {video_id}: {e}",
            exc_info=True
        )
        return None

    finally:
        _remove_temp_files(output_path, temp_prefix)

def download_transcript(video_id: str, output_path: str) -> Optional[str]:
    """Download Arabic transcript for a YouTube video."""
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        yt = YouTube(url)
        
        # Try to find Arabic captions using caption_tracks
        ar_caption = None
        for track in yt.caption_tracks:
            if track.code == 'ar':
                ar_caption = track
                break
            if track.code == 'a.ar': # Auto-generated
                ar_caption = track
        
        if ar_caption:
            transcript_text = ar_caption.generate_srt_captions()
            file_name = f"{video_id}_transcript.txt"
            full_path = os.path.join(output_path, file_name)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(transcript_text)
            return full_path
        
        return None
    except Exception as e:
        logger.error(f"Error downloading transcript for {video_id}: {e}")
        return None

def save_metadata(video_id: str, metadata: Dict[str, Any], output_path: str):
    """Save video metadata as JSON."""
    file_name = f"{video_id}_metadata.json"
    full_path = os.path.join(output_path, file_name)
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=4)
    return full_path

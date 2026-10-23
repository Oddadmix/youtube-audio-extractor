# Egyptian ASR Dataset Builder

A web application for building Arabic speech (ASR) datasets from YouTube videos:
discover a channel's videos, download the audio, split it into speech chunks,
identify speakers, transcribe the chunks with Google Gemini, and export
audio + transcript pairs as a Hugging Face–compatible Parquet dataset.

> **Content rights.** Only download and process videos you own or have
> permission to use. Respect YouTube's Terms of Service and the rights of the
> people recorded.

## Features
- **Channel discovery** with `yt-dlp` (number of videos per scan is capped by `YT_DISCOVERY_LIMIT`).
- **Audio download** with `yt-dlp`, converted to 16-bit WAV.
- **Speech splitting** with Silero VAD, plus speaker identification.
- **Caption fallback**: existing Arabic YouTube captions are fetched when available.
- **AI transcription** with Google Gemini (model configurable; default `gemini-3.8-flash`).
- **Dataset export** to a local Parquet file (audio embedded) or to the Hugging Face Hub.
- **Dashboard** showing videos, chunks, and job history with status and error messages.
- **Slack notifications** (optional).

## Technical stack
- **Backend**: Python 3.10, FastAPI, SQLAlchemy (MySQL), Celery, Redis.
- **Frontend**: React, TypeScript, Vite.
- **Processing**: yt-dlp (with the Deno JavaScript runtime it needs for YouTube), pydub, Silero VAD, Google Gemini API.

## Requirements
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose v2).
- [Git](https://git-scm.com/).
- A **Google Gemini API key** for transcription ([Google AI Studio](https://aistudio.google.com/apikey)). Usage, quotas, and costs are billed to your own Gemini project.
- Optional: a Hugging Face token (only for pushing datasets to the Hub) and a Slack webhook URL.
- Disk space: plan for several hundred MB per 30-minute video while it is processed (temporary WAV), plus ~120 MB of chunks that are kept.

Everything else (Python, Node, MySQL, Redis, ffmpeg, yt-dlp, Deno) runs inside Docker.

## Setup

### 1. Clone the repository
```bash
git clone https://github.com/Oddadmix/youtube-audio-extractor.git
cd youtube-audio-extractor
```
(If you are testing a branch or fork, clone that instead and `git checkout` the branch.)

### 2. Create your `.env`
```bash
cp .env.example .env
```
Edit `.env` and set at least:

| Variable | What to put there |
| --- | --- |
| `MYSQL_ROOT_PASSWORD` | Any strong password for the MySQL root user. |
| `MYSQL_PASSWORD` | Any strong password for the app's MySQL user (`asr_user`). |
| `DATABASE_URL` | `mysql+pymysql://asr_user:<MYSQL_PASSWORD>@mysql:3306/asr_dataset`, using the **same** password as `MYSQL_PASSWORD` (URL-encode special characters like `@ : / #`). |
| `GEMINI_API_KEY` | Your Gemini API key. |

Never commit `.env`; it is already in `.gitignore`.

### 3. Start the services
```bash
docker compose up -d --build
```
The first build takes several minutes (it installs PyTorch, ffmpeg, and Node packages).
This starts five services: `mysql`, `redis`, `app` (API on port 8000),
`celery-worker` (background jobs), and `frontend` (dashboard on port 5173).

Database tables are created automatically when the `app` service starts. No
manual migration step is needed on a fresh database.

### 4. Check that everything is running
```bash
docker compose ps                    # mysql and redis should be "healthy", others "Up"
curl http://localhost:8000/          # {"message":"Egyptian ASR Dataset Builder API"}
docker compose logs celery-worker | grep "ready"   # worker connected to Redis
```

### 5. Open the dashboard
Go to **http://localhost:5173**.

## How to use

1. **Add a channel**: on the **Channels** page, paste a channel URL (e.g. `https://www.youtube.com/@SomeChannel`) and click **Add**, or bulk-import a `.txt` file with one URL per line.
   Adding a channel **immediately starts processing it**: it discovers up to `YT_DISCOVERY_LIMIT` videos (default 1) and queues them for download. Use **Process** to scan the channel again later.
2. **View discovered videos**: on the **Videos** page. Each video moves through `pending → downloading → processing → completed` (or `failed`, with the reason shown in the video's logs).
3. **Download and split audio**: this happens automatically for each new video. The worker downloads the audio, converts it to WAV, splits it into speech chunks with VAD, identifies speakers, and deletes the large source WAV once chunks are saved. Use **Start/Retry** on a video to re-run it (this downloads it again).
4. **Review chunks**: on the **Chunks** page you can listen to and search the chunks.
5. **Transcribe with Gemini**: on the **Transcription** page, select a channel and click **Start Transcription**. Only chunks without a transcript are sent, unless you tick *Force Retranscribe*. Progress and errors appear in **Transcription History**.
   To test on a single chunk first (one paid request), call the API directly:
   ```bash
   curl -X POST http://localhost:8000/api/transcribe/ \
     -H 'Content-Type: application/json' \
     -d '{"channel_ids": [1], "chunk_ids": [1]}'
   ```
6. **Export**: on the **Export** page, select the channel(s). To save locally, leave *Repo ID* and *HuggingFace Token* empty and start the export; when the job shows `completed` in **Export History**, click **Download Parquet**. To publish instead, fill in both fields to push to the Hub. The export contains every chunk with its embedded audio; chunks that have not been transcribed yet have an empty `transcript_text`.

## Configuration

All settings are environment variables in `.env` (restart with `docker compose up -d` after changing them).

| Variable | Default | Purpose |
| --- | --- | --- |
| `YT_DISCOVERY_LIMIT` | `1` | Max videos discovered per channel scan. Kept at 1 for safe testing; raise it deliberately. |
| `YT_RETRY_COUNT` | `3` | Download attempts per video before it is marked failed. |
| `GEMINI_API_KEY` | none | Required for transcription. |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Default Gemini model. The **Settings** page can override it; once settings are saved there, the saved value wins. The model must accept audio input. |
| `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD` | none | Required; used to initialise the MySQL container. |
| `DATABASE_URL` | none | SQLAlchemy URL; must match the MySQL user/password above. |
| `REDIS_URL` | `redis://redis:6379/0` | Celery broker and result backend. |
| `DATA_PATH` | `./data` | Where audio, chunks, settings, and exports are stored (mounted from `./data` on your machine). |
| `HF_TOKEN` | empty | Optional default token for Hugging Face Hub export. |
| `SLACK_WEBHOOK_URL` | empty | Optional Slack notifications. |

Audio-splitting and transcription-prompt settings are edited on the **Settings** page and saved to `data/settings.json`.

## Troubleshooting

**Where to look first**
- Job status and errors: **Dashboard → Recent Activity**, the **Transcription** and **Export** history tables, and **Videos → View Logs**.
- Worker logs: `docker compose logs -f celery-worker`
- API logs: `docker compose logs -f app`

**YouTube access restrictions** ("Sign in to confirm you're not a bot", HTTP 429, rate limits)
The worker detects these, pauses pending downloads, and does not retry in a loop. Wait before retrying, keep `YT_DISCOVERY_LIMIT` low, and do not try to bypass YouTube's restrictions. Private, removed, or region-blocked videos are marked `failed` without retries.

**Gemini `429 RESOURCE_EXHAUSTED`** (quota exceeded)
The job stops immediately instead of sending the remaining chunks, and its error is shown in Transcription History. Wait for the quota to reset or raise the limits/billing on your Gemini project, then start transcription again; only chunks still missing a transcript are sent.

**Gemini `503 UNAVAILABLE`** ("model is experiencing high demand")
This is temporary. Single 503s fail only that chunk; three in a row stop the job. Retry later.

**Gemini `404 NOT_FOUND`** (model retired or misspelled)
Transcription fails before any audio is sent. Set a supported model in **Settings** or `GEMINI_MODEL`.

**Database connection errors**
- `required variable MYSQL_PASSWORD is missing a value`: set both MySQL passwords in `.env`.
- `Access denied for user 'asr_user'`: the password in `DATABASE_URL` must equal `MYSQL_PASSWORD`. MySQL only applies these passwords when its volume is first created, so changing them later requires updating the user inside MySQL.
- `Can't connect to MySQL server`: check `docker compose ps`; `app` and `celery-worker` wait for MySQL to become healthy.

**Docker startup issues**
- Port already in use: free ports 8000 and 5173, or change the published ports in `docker-compose.yml`.
- After changing `backend/requirements.txt`: `docker compose up -d --build app celery-worker`.
- Code changes in `backend/` are mounted live, but the Celery worker must be restarted: `docker compose restart celery-worker`.
- `docker compose down -v` **deletes the database volume**. Use `docker compose down` (without `-v`) to keep your data.

## Running the tests
The backend tests use a temporary SQLite database and synthetic audio. They make no YouTube or Gemini calls and do not touch your data.
```bash
docker compose exec celery-worker python -m unittest discover -s tests -t .
docker compose exec frontend npx tsc --noEmit -p tsconfig.app.json
```

## Validation status

**Tested successfully**
- 44 automated backend tests pass: YouTube discovery and download (mocked), retry and failure handling, audio splitting, 16/32-bit audio normalisation, job tracking, Gemini error handling (mocked), and local export. The frontend TypeScript check passes.
- A fresh, empty MySQL database initialises correctly, and the API and all Celery tasks start.
- One real end-to-end run: channel discovery, download of a 31 min 52 s video, WAV conversion, VAD splitting, and speaker identification produced 114 chunks.
- One real Gemini transcription of a single chunk through the app (`gemini-3.8-flash`), followed by a local export in which the transcript and embedded audio matched the source exactly.

**Not yet done / known limitations**
1. **Most chunks are not transcribed.** Only 4 of the 114 test chunks have transcripts. The latest bulk transcription stopped on Gemini `429 RESOURCE_EXHAUSTED` (free-tier quota exceeded). Finishing it needs more Gemini requests.
2. **The 114 test chunks were cut before the VAD audio-scaling fix** and should be regenerated (which means re-downloading the video) and reviewed before production use.
3. **Forced cuts overlap by about one second** between neighbouring chunks; this has not been adjusted.
4. **Speaker identification may over-split** one narrator into several speakers.
5. **Some videos have no Arabic captions**, so the caption fallback finds nothing.
6. **YouTube availability, rate limits, and access restrictions can change** at any time.
7. **Transcription cost and quota depend on your own Gemini project.**
8. **Discovery defaults to one video per scan** (`YT_DISCOVERY_LIMIT=1`) for safe testing.
9. **The backend runs on Python 3.10**, which should eventually be upgraded.
10. **Audio and transcription quality still need manual review.** For example, the transcription prompt asks for Egyptian Arabic, but speakers and clips may use other dialects or languages.

## Running without Docker (not re-tested)
The Docker setup above is the tested path. To run locally you need Python 3.10+, Node.js 20+, MySQL, Redis, and ffmpeg. Install `backend/requirements.txt`, then start Redis, `celery -A app.celery_app worker` and `uvicorn app.main:app` from `backend/`, and `npm run dev` from `frontend/`. Set `DATABASE_URL`/`REDIS_URL` to `localhost`, and change the proxy target in `frontend/vite.config.ts` from `http://app:8000` to `http://localhost:8000`.

## Project structure
- `backend/app/`: FastAPI routes (`api/`), Celery tasks (`tasks/`), and helpers (`utils/`).
- `backend/tests/`: automated tests.
- `backend/migrations/`: Alembic migration history. The app creates missing tables at startup and adds the `jobs.error_message` column to older databases.
- `frontend/`: React dashboard.
- `data/`: audio, chunks, settings, and exports (ignored by git).
- `logs/`: logs (ignored by git).

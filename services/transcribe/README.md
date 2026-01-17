# Transcribe Service

Audio/video transcription service using OpenAI Whisper.

## Features

- Transcribe YouTube videos (via yt-dlp)
- Transcribe direct audio/video URLs
- Upload audio/video files for transcription
- Multiple output formats (TXT, SRT)
- Web UI for job management
- REST API for programmatic access

## Quick Start

```bash
cd services/transcribe
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your settings

# Run
python src/api.py
```

## Configuration

See `.env.example` for all configuration options.

Required:
- `DSN` - PostgreSQL connection string
- `S3_ENDPOINT` - MinIO endpoint URL
- `S3_ACCESS_KEY` - MinIO access key
- `S3_SECRET_KEY` - MinIO secret key

## API Endpoints

- `GET /health` - Health check
- `POST /jobs` - Submit new transcription job
- `GET /jobs` - List jobs
- `GET /jobs/{id}` - Get job status
- `DELETE /jobs/{id}` - Cancel/delete job

## Documentation

See [docs/service.md](docs/service.md) for detailed documentation.

## Dependencies

- [ASO Platform](https://github.com/jurgenrgithub/aso-repo) - Dispatcher, EventStore, MinIO
- PostgreSQL - Job queue
- faster-whisper - Transcription engine
- yt-dlp - YouTube downloads

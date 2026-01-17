# Transcribe Service

## Purpose
Audio/video transcription service using Whisper AI. Supports YouTube URLs, direct URLs, and file uploads.

## Components

| Component | Port | Description |
|-----------|------|-------------|
| transcribe-api | 8000 | FastAPI REST API and Web UI |
| transcribe-worker | - | Background job processor |

## Deployment

- **CTID**: 350
- **Install path**: `/opt/aso/transcribe`
- **Systemd units**: `aso-transcribe-api.service`, `aso-transcribe-worker.service`
- **Source repo**: https://github.com/jurgenrgithub/services-repo/services/transcribe

## Data Flow

```
User → Web UI / API → PostgreSQL (job queue)
                           ↓
                    Worker (polls queue)
                           ↓
              Download audio (yt-dlp / direct)
                           ↓
              Transcribe (faster-whisper)
                           ↓
              Upload results → MinIO (S3)
                           ↓
              Update job status → PostgreSQL
```

## Database

- **Database**: `aso_transcribe`
- **Schema**: `aso_transcribe`
- **Tables**:
  - `jobs` - Job queue with status, source, results

## Storage

- **Bucket**: `transcribe`
- **Prefixes**:
  - `inputs/` - Uploaded audio/video files
  - `outputs/` - Transcription results (TXT, SRT)

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `DSN` | - | PostgreSQL connection string |
| `S3_ENDPOINT` | - | MinIO endpoint URL |
| `S3_ACCESS_KEY` | - | MinIO access key |
| `S3_SECRET_KEY` | - | MinIO secret key |
| `S3_BUCKET` | transcribe | S3 bucket name |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | - | OpenTelemetry collector |

## Web UI Features

- **New Job**: Submit YouTube URL, direct URL, or upload file
- **Recent Jobs**: Paginated list with sorting by date/name
- **Job Status**: Progress, transcript preview, copy to clipboard
- **Maintenance**: Storage stats, audit DB vs S3, purge options

## Health Check

```bash
curl http://localhost:8000/health
# {"status":"ok","database":true,"storage":true}
```

## Logs

```bash
journalctl -u aso-transcribe-api -f
journalctl -u aso-transcribe-worker -f
```

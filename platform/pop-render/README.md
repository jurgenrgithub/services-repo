# ASO Render Service

Enterprise-grade RESTful API for artistic image rendering with high-resolution TIFF output. Transforms uploaded images into artistic renderings using configurable styles and print-ready size presets.

## Overview

The ASO Render Service is a production-ready Flask application that provides async image rendering capabilities with professional print output. All renders produce 300 DPI TIFF files suitable for high-quality printing, along with web-optimized JPEG previews.

**Key Features:**
- Async rendering with job status polling
- Multiple artistic styles (watercolor, oil painting, sketch, etc.)
- Standard print size presets (9x12, 12x16, 16x20, 18x24, 24x36)
- High-resolution TIFF output (300 DPI)
- JPEG preview generation (1200px longest edge)
- Presigned URLs for secure downloads (7-day expiry)
- Enterprise monitoring with health checks and Prometheus metrics
- PostgreSQL for job tracking, Redis for queuing, MinIO for object storage

## Architecture

```
┌─────────────┐
│   Client    │
└─────┬───────┘
      │ HTTP
      ▼
┌─────────────────────────────────────────────────────────┐
│               Flask API (Port 8089)                     │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Routes:                                          │  │
│  │  POST   /v1/renders          Create render job   │  │
│  │  GET    /v1/renders/{id}     Get status          │  │
│  │  GET    /v1/renders/{id}/download  Get TIFF URL │  │
│  │  GET    /v1/renders/{id}/preview   Get JPEG URL │  │
│  │  GET    /v1/size-presets     List size presets   │  │
│  │  GET    /health              Health check        │  │
│  │  GET    /metrics             Prometheus metrics  │  │
│  │  GET    /v1/openapi.json     OpenAPI spec        │  │
│  └──────────────────────────────────────────────────┘  │
└────┬──────────────┬──────────────┬─────────────────────┘
     │              │              │
     ▼              ▼              ▼
┌──────────┐  ┌─────────┐  ┌──────────────┐
│PostgreSQL│  │  Redis  │  │    MinIO     │
│  (Jobs)  │  │ (Queue) │  │  (Storage)   │
└──────────┘  └─────────┘  └──────────────┘
                   │
                   ▼
            ┌──────────────┐
            │ RQ Workers   │
            │ (Rendering)  │
            └──────────────┘
```

**Data Flow:**
1. Client uploads image via POST /v1/renders
2. API validates image, stores in MinIO, creates DB record
3. Job queued in Redis for async processing
4. RQ worker picks up job, applies rendering
5. Worker stores TIFF output and JPEG preview in MinIO
6. Client polls GET /v1/renders/{id} for status
7. On completion, client downloads via presigned URLs

## Quick Start

### Prerequisites

- Python 3.9+
- PostgreSQL 13+
- Redis 6+
- MinIO or S3-compatible storage

### Installation

```bash
# Navigate to service directory
cd platform/pop-render/service

# Install dependencies
pip install -r requirements.txt

# Set environment variables (see Configuration section)
export DB_PASSWORD="your-db-password"
export MINIO_ENDPOINT="localhost:9000"
export MINIO_ACCESS_KEY="minioadmin"
export MINIO_SECRET_KEY="minioadmin"

# Initialize database schema
psql -h localhost -U postgres -d aso_render -f ../db/schema.sql
psql -h localhost -U postgres -d aso_render -f ../db/seed.sql

# Run development server
python app.py
```

The API will be available at `http://localhost:8089`.

### Running with Gunicorn (Production)

```bash
gunicorn -w 2 -b 0.0.0.0:8089 --timeout 300 app:app
```

### Running RQ Workers

```bash
# Start worker process for render queue
rq worker render-queue --url redis://localhost:6379/0
```

## API Endpoints

### Render Operations

#### Create Render Job
```http
POST /v1/renders
Content-Type: multipart/form-data

file: <image-file>
style_id: <uuid>
size_preset_id: <uuid>
```

**Response (201 Created):**
```json
{
  "render_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "queued",
  "created_at": "2025-01-24T10:30:00Z"
}
```

#### Get Render Status
```http
GET /v1/renders/{id}
```

**Response (200 OK):**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "completed",
  "asset_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "style": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Watercolor",
    "slug": "watercolor"
  },
  "size_preset": {
    "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "name": "9x12",
    "width_inches": 9.0,
    "height_inches": 12.0,
    "dpi": 300,
    "width_px": 2700,
    "height_px": 3600
  },
  "created_at": "2025-01-24T10:30:00Z",
  "started_at": "2025-01-24T10:30:05Z",
  "completed_at": "2025-01-24T10:32:15Z",
  "duration_ms": 130000,
  "error_message": null
}
```

**Status Values:**
- `queued`: Job is waiting in queue
- `processing`: Job is being rendered
- `completed`: Rendering complete, files available
- `failed`: Rendering failed (see error_message)

#### Download Rendered TIFF
```http
GET /v1/renders/{id}/download
```

**Response (200 OK):**
```json
{
  "url": "https://minio.example.com/render-assets/renders/.../output.tiff?X-Amz-...",
  "expires_in": 604800
}
```

The URL is a presigned MinIO/S3 URL valid for 7 days (604800 seconds). Download the TIFF file directly from this URL.

#### Get JPEG Preview
```http
GET /v1/renders/{id}/preview
```

**Response (200 OK):**
```json
{
  "url": "https://minio.example.com/render-assets/renders/.../preview.jpg?X-Amz-...",
  "expires_in": 604800
}
```

### Size Presets

#### List Available Size Presets
```http
GET /v1/size-presets
```

**Response (200 OK):**
```json
[
  {
    "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "name": "9x12",
    "width_inches": 9.0,
    "height_inches": 12.0,
    "dpi": 300,
    "width_px": 2700,
    "height_px": 3600
  },
  {
    "id": "6ba7b811-9dad-11d1-80b4-00c04fd430c8",
    "name": "12x16",
    "width_inches": 12.0,
    "height_inches": 16.0,
    "dpi": 300,
    "width_px": 3600,
    "height_px": 4800
  }
]
```

### Monitoring

#### Health Check
```http
GET /health
```

**Response (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-24T10:30:00Z",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "storage": "ok"
  }
}
```

Returns 503 if any dependency is unhealthy.

#### Prometheus Metrics
```http
GET /metrics
```

Returns Prometheus text format metrics including:
- HTTP request counts and durations
- Database connection pool stats
- Queue depth and processing rates
- Error rates by endpoint

### Documentation

#### OpenAPI Specification
```http
GET /v1/openapi.json
```

Returns the complete OpenAPI 3.0 specification in JSON format. Use for:
- Generating client SDKs
- Importing into API testing tools (Postman, Insomnia)
- Integration with API gateways

## Usage Examples

### Complete Workflow with curl

```bash
# 1. List available size presets
curl http://localhost:8089/v1/size-presets

# Example response:
# [{"id":"6ba7b810-9dad-11d1-80b4-00c04fd430c8","name":"9x12",...}]

# 2. Upload image and create render job
curl -X POST http://localhost:8089/v1/renders \
  -F "file=@my-photo.jpg" \
  -F "style_id=550e8400-e29b-41d4-a716-446655440000" \
  -F "size_preset_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8"

# Example response:
# {"render_id":"3fa85f64-5717-4562-b3fc-2c963f66afa6","status":"queued",...}

# 3. Poll for render status
curl http://localhost:8089/v1/renders/3fa85f64-5717-4562-b3fc-2c963f66afa6

# Poll every 5-10 seconds until status is "completed"

# 4. Download rendered TIFF
curl http://localhost:8089/v1/renders/3fa85f64-5717-4562-b3fc-2c963f66afa6/download

# Example response:
# {"url":"https://minio.example.com/...","expires_in":604800}

# 5. Download the file from presigned URL
curl -o rendered-output.tiff "https://minio.example.com/render-assets/renders/..."

# 6. (Optional) Get JPEG preview for visual verification
curl http://localhost:8089/v1/renders/3fa85f64-5717-4562-b3fc-2c963f66afa6/preview

# Download preview
curl -o preview.jpg "https://minio.example.com/render-assets/renders/.../preview.jpg?..."
```

### Python Example

```python
import requests
import time

API_BASE = "http://localhost:8089"

# Create render
with open("my-photo.jpg", "rb") as f:
    response = requests.post(
        f"{API_BASE}/v1/renders",
        files={"file": f},
        data={
            "style_id": "550e8400-e29b-41d4-a716-446655440000",
            "size_preset_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
        }
    )

render_id = response.json()["render_id"]
print(f"Render created: {render_id}")

# Poll for completion
while True:
    status_response = requests.get(f"{API_BASE}/v1/renders/{render_id}")
    status_data = status_response.json()

    print(f"Status: {status_data['status']}")

    if status_data["status"] == "completed":
        break
    elif status_data["status"] == "failed":
        print(f"Render failed: {status_data['error_message']}")
        exit(1)

    time.sleep(5)

# Get download URL
download_response = requests.get(f"{API_BASE}/v1/renders/{render_id}/download")
download_url = download_response.json()["url"]

# Download TIFF
tiff_data = requests.get(download_url).content
with open("output.tiff", "wb") as f:
    f.write(tiff_data)

print("Render downloaded successfully!")
```

## Configuration

### Environment Variables

#### Database (PostgreSQL)
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DB_HOST` | No | `localhost` | PostgreSQL hostname |
| `DB_PORT` | No | `5432` | PostgreSQL port |
| `DB_NAME` | No | `aso_render` | Database name |
| `DB_USER` | No | `postgres` | Database user |
| `DB_PASSWORD` | **Yes** | - | Database password |

#### Redis (Job Queue)
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDIS_HOST` | No | `localhost` | Redis hostname |
| `REDIS_PORT` | No | `6379` | Redis port |
| `REDIS_DB` | No | `0` | Redis database number |

#### MinIO/S3 (Object Storage)
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MINIO_ENDPOINT` | **Yes** | - | MinIO endpoint URL (e.g., `localhost:9000`) |
| `MINIO_ACCESS_KEY` | **Yes** | - | MinIO access key |
| `MINIO_SECRET_KEY` | **Yes** | - | MinIO secret key |
| `MINIO_BUCKET` | No | `render-assets` | Bucket name for storing files |

#### Service Configuration
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `API_PORT` | No | `8089` | Flask API port |
| `WORKER_COUNT` | No | `2` | Gunicorn worker count |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |

### Example .env File

```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=aso_render
DB_USER=postgres
DB_PASSWORD=secure-password-here

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=render-assets

# Service
API_PORT=8089
WORKER_COUNT=2
LOG_LEVEL=INFO
```

## Rate Limiting

**Note:** Rate limiting headers are documented in the API but not enforced in the current MVP release. Future releases will implement rate limiting at the API gateway level.

### Rate Limit Headers (Post-MVP)
- `X-RateLimit-Limit`: Maximum requests per hour
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Timestamp when the limit resets

When rate limiting is enabled, clients exceeding limits will receive:
```json
{
  "error": "Rate limit exceeded",
  "status": 429
}
```

## Error Handling

All error responses follow a consistent JSON format:

```json
{
  "error": "Brief error message",
  "message": "Detailed explanation (optional)",
  "status": 400
}
```

### Common Error Codes

| Code | Error | Description |
|------|-------|-------------|
| 400 | Bad Request | Invalid input (missing fields, malformed UUID, unsupported format) |
| 404 | Not Found | Render ID does not exist, or output files not available |
| 409 | Conflict | Render not in correct state (e.g., requesting download before completion) |
| 413 | Payload Too Large | File exceeds 50 MB limit |
| 500 | Internal Server Error | Unexpected server error (database, storage, or processing failure) |
| 503 | Service Unavailable | Health check failed, dependencies unavailable |

### Error Examples

**Missing File:**
```json
{
  "error": "No file provided",
  "status": 400
}
```

**Invalid UUID:**
```json
{
  "error": "Invalid UUID format for render_id",
  "status": 400
}
```

**Render Not Completed:**
```json
{
  "error": "Render not completed (current status: processing)",
  "status": 409
}
```

**File Too Large:**
```json
{
  "error": "File too large (maximum 50MB)",
  "status": 413
}
```

## Deployment

### Docker Deployment

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8089/health || exit 1

EXPOSE 8089

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8089", "--timeout", "300", "app:app"]
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pop-render-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: pop-render-api
  template:
    metadata:
      labels:
        app: pop-render-api
    spec:
      containers:
      - name: api
        image: aso/pop-render-api:latest
        ports:
        - containerPort: 8089
        env:
        - name: DB_HOST
          value: postgres-service
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: password
        - name: REDIS_HOST
          value: redis-service
        - name: MINIO_ENDPOINT
          value: minio-service:9000
        - name: MINIO_ACCESS_KEY
          valueFrom:
            secretKeyRef:
              name: minio-secret
              key: access-key
        - name: MINIO_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: minio-secret
              key: secret-key
        livenessProbe:
          httpGet:
            path: /health/liveness
            port: 8089
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health/readiness
            port: 8089
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: pop-render-api
spec:
  selector:
    app: pop-render-api
  ports:
  - port: 80
    targetPort: 8089
  type: LoadBalancer
```

### Scaling Considerations

**API Tier:**
- Horizontal scaling: Run multiple Flask workers behind load balancer
- Recommended: 2 workers per instance, scale instances based on request volume
- Each worker maintains its own DB connection pool (2-10 connections)

**Worker Tier:**
- Horizontal scaling: Run multiple RQ worker processes
- Rendering is CPU-intensive, scale based on CPU utilization
- Recommended: 1 worker per CPU core

**Database:**
- Connection pooling configured (2-10 connections per API worker)
- Index on `renders.id`, `renders.status`, `assets.id`
- Regular VACUUM to maintain performance

**Storage:**
- MinIO supports horizontal scaling with distributed mode
- Use separate buckets for uploads, renders, and previews for better organization

## Monitoring and Observability

### Health Checks

- `/health` - Comprehensive check (database, Redis, MinIO)
- `/health/readiness` - Kubernetes readiness probe
- `/health/liveness` - Kubernetes liveness probe

### Prometheus Metrics

Exposed at `/metrics` endpoint:

```
# Request metrics
http_requests_total{method="POST",endpoint="/v1/renders",status="201"}
http_request_duration_seconds{endpoint="/v1/renders"}

# Database metrics
db_connections_active
db_connections_idle
db_query_duration_seconds

# Queue metrics
rq_queue_depth{queue="render-queue"}
rq_jobs_processed_total
rq_job_duration_seconds

# Error metrics
http_errors_total{endpoint="/v1/renders",status="500"}
```

### Structured Logging

All logs use structured JSON format with contextual fields:

```json
{
  "timestamp": "2025-01-24T10:30:00Z",
  "level": "INFO",
  "logger": "pop-render",
  "message": "Render created successfully",
  "render_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "asset_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "duration_ms": 245
}
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_renders.py
```

### Database Migrations

```bash
# Apply schema changes
psql -h localhost -U postgres -d aso_render -f db/migrations/001_add_column.sql
```

### Local Development Setup

```bash
# Start dependencies with Docker Compose
docker-compose up -d postgres redis minio

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dev dependencies
pip install -r requirements-dev.txt

# Run service
python app.py
```

## Security

- **Input Validation:** All uploads validated for format, size, and content type
- **Presigned URLs:** Temporary URLs with 7-day expiration, no permanent public access
- **SQL Injection:** Protected via parameterized queries (psycopg2)
- **CORS:** Configure CORS headers based on deployment environment
- **Secrets:** Never log DB_PASSWORD, MINIO_SECRET_KEY, or other credentials
- **Rate Limiting:** Planned for post-MVP (see Rate Limiting section)

## Troubleshooting

### Common Issues

**Issue:** "DB_PASSWORD is required"
- **Solution:** Set `DB_PASSWORD` environment variable before starting service

**Issue:** "Failed to initialize storage client"
- **Solution:** Verify MinIO is running and `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` are correct

**Issue:** Render stuck in "queued" status
- **Solution:** Ensure RQ worker is running: `rq worker render-queue`

**Issue:** "Render not found" for valid ID
- **Solution:** Check database connectivity and verify ID format (must be valid UUID)

**Issue:** Download URL returns 403 Forbidden
- **Solution:** Presigned URLs expire after 7 days. Re-request download URL from API

## Support

For issues, questions, or feature requests:
- File an issue in the project repository
- Contact: platform@aso.example.com
- Documentation: https://api.aso.example.com/v1/openapi.json

## License

Proprietary - ASO Platform © 2025

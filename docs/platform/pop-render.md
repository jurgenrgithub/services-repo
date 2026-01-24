# Pop-Render Service

## Service Overview

The **Pop-Render Service** is an enterprise-grade Flask-based REST API service that provides asynchronous artistic image rendering with high-resolution TIFF output. It transforms source images through multiple artistic rendering algorithms (pipelines) optimized for print production.

**Key Capabilities:**
- Three distinct rendering styles: Pop Poster, Pencil Sketch, and Between The Lines
- High-resolution TIFF output (300 DPI) for professional print production
- Asynchronous job processing with Redis Queue (RQ)
- Comprehensive monitoring with Prometheus metrics
- Scalable architecture supporting horizontal scaling
- Object storage integration with MinIO/S3
- PostgreSQL-backed job tracking and configuration

**Service Details:**
- **Port:** 8089 (configurable via `API_PORT` environment variable)
- **Language:** Python 3.9+
- **Framework:** Flask 3.0.0
- **Repository Location:** `platform/pop-render/`

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Layer                            │
│  (Web UI, Mobile Apps, Catalog Service, Orchestration Service) │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS/REST
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Pop-Render API (Flask)                       │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │  API Routes                                                 │ │
│ │  • POST   /v1/renders              (Create render job)     │ │
│ │  • GET    /v1/renders/{id}         (Get job status)        │ │
│ │  • GET    /v1/renders/{id}/download (Get TIFF URL)         │ │
│ │  • GET    /v1/renders/{id}/preview  (Get JPEG preview)     │ │
│ │  • GET    /v1/size-presets          (List print sizes)     │ │
│ │  • GET    /health                   (Health check)         │ │
│ │  • GET    /metrics                  (Prometheus metrics)   │ │
│ └─────────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │  Core Services                                              │ │
│ │  • Validation Layer  • Storage Client  • Queue Manager     │ │
│ │  • Database Pool     • Health Checks   • Metrics Tracking  │ │
│ └─────────────────────────────────────────────────────────────┘ │
└───┬───────────────────┬───────────────────┬─────────────────────┘
    │                   │                   │
    ▼                   ▼                   ▼
┌──────────┐    ┌────────────┐    ┌─────────────────┐
│PostgreSQL│    │   Redis    │    │  MinIO (S3 API) │
│  (Jobs)  │    │  (Queue)   │    │    (Storage)    │
└──────────┘    └─────┬──────┘    └─────────────────┘
                      │
                      │ Job Polling
                      ▼
            ┌─────────────────────┐
            │   RQ Workers (1-N)  │
            │ ┌─────────────────┐ │
            │ │ Rendering       │ │
            │ │ Pipelines:      │ │
            │ │ • Pop Poster    │ │
            │ │ • Pencil Sketch │ │
            │ │ • Between Lines │ │
            │ └─────────────────┘ │
            └─────────────────────┘
```

## Component Descriptions

### API Layer (Flask)

**File:** `platform/pop-render/service/app.py`

The Flask application provides RESTful endpoints for render job management and monitoring.

**Key Features:**
- Request/response middleware with metrics tracking
- JSON error handling with standardized format
- OpenAPI 3.0 specification at `/v1/openapi.json`
- Gunicorn WSGI server for production deployment
- Request timeout handling (300 seconds for long-running operations)

**Request Lifecycle:**
1. Client sends HTTP request
2. Middleware logs request start time
3. Route handler validates input (UUID format, file constraints)
4. Business logic executes (DB queries, storage operations, queue operations)
5. Response serialized to JSON
6. Middleware tracks metrics (duration, status code)
7. Response returned to client

**Error Handling:**
- 400: Validation errors (invalid UUID, missing parameters, unsupported formats)
- 404: Resource not found
- 409: Conflict (e.g., download before completion)
- 413: Payload too large (>50MB)
- 500: Internal errors (DB, storage, queue failures)
- 503: Service unavailable (health check failures)

### Workers (RQ - Redis Queue)

**File:** `platform/pop-render/service/pipelines/__init__.py`

Background workers process rendering jobs asynchronously using Python RQ.

**Worker Characteristics:**
- **Job Function:** `process_render(render_id, asset_id, style_id, size_preset_id)`
- **Timeout:** 10 minutes per job
- **Queue Name:** `renders`
- **Result TTL:** 24 hours (successful jobs)
- **Failure TTL:** 7 days (failed jobs for debugging)

**Worker Process:**
1. Poll Redis queue for new jobs
2. Fetch job parameters and configuration from DB
3. Download source image from MinIO
4. Instantiate rendering pipeline with algorithm config
5. Process image through pipeline
6. Resize to target dimensions
7. Generate TIFF output (300 DPI, LZW compression)
8. Generate JPEG preview (max 1200px wide, 85% quality)
9. Upload outputs to MinIO
10. Update database with completion status and metrics
11. Clean up temporary files

**Scaling:** Workers can be scaled horizontally by running multiple `rq worker` processes.

### Redis (Job Queue & Cache)

**File:** `platform/pop-render/service/queue.py`

Redis serves as the job queue backend using the RQ library.

**Configuration:**
- **Host:** `REDIS_HOST` (default: localhost)
- **Port:** `REDIS_PORT` (default: 6379)
- **Database:** `REDIS_DB` (default: 0)

**Usage:**
- **Job Queue:** Stores serialized render jobs for async processing
- **Job Status:** Tracks job state (queued, started, finished, failed)
- **Job Results:** Caches job results for 24 hours
- **Failure Tracking:** Retains failed job details for 7 days

**Persistence:** Recommended to enable AOF (Append-Only File) persistence to prevent job loss on Redis restart.

**Health Check:** PING command to verify connectivity.

### MinIO (Object Storage)

**File:** `platform/pop-render/service/storage.py`

MinIO provides S3-compatible object storage for source images and rendered outputs.

**Configuration:**
- **Endpoint:** `MINIO_ENDPOINT` (required, e.g., `localhost:9000`)
- **Access Key:** `MINIO_ACCESS_KEY` (required)
- **Secret Key:** `MINIO_SECRET_KEY` (required)
- **Bucket:** `MINIO_BUCKET` (default: `render-assets`)

**Storage Structure:**
```
render-assets/
├── uploads/{asset_id}/{filename}          # Source images
└── renders/{render_id}/
    ├── output.tiff                        # Rendered TIFF (300 DPI)
    └── preview.jpg                        # JPEG preview (max 1200px)
```

**Operations:**
- **Upload:** Stores source images and rendered outputs with retry logic
- **Download:** Retrieves source images for processing
- **Presigned URLs:** Generates temporary download URLs (7-day expiry)
- **Health Check:** `list_objects_v2` with max 1 object to verify connectivity

**Client Configuration:**
- Signature Version: S3v4
- Connect Timeout: 10 seconds
- Read Timeout: 30 seconds
- Retries: 3 attempts with exponential backoff

### PostgreSQL (Job Tracking & Configuration)

**File:** `platform/pop-render/service/database.py`

PostgreSQL stores job state, rendering configuration, and asset metadata.

**Configuration:**
- **Host:** `DB_HOST` (default: localhost)
- **Port:** `DB_PORT` (default: 5432)
- **Database:** `DB_NAME` (default: aso_render)
- **User:** `DB_USER` (default: postgres)
- **Password:** `DB_PASSWORD` (required)

**Connection Pool:**
- Type: `ThreadedConnectionPool` (thread-safe)
- Min Connections: 2
- Max Connections: 10
- Cursor Type: `RealDictCursor` (returns rows as dictionaries)

**Schema Tables:**

#### `assets`
Stores source image metadata and MinIO references.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| filename | VARCHAR(255) | Original filename |
| minio_key | VARCHAR(512) | MinIO object key (unique) |
| format | VARCHAR(50) | Image format (JPEG, PNG, TIFF, etc.) |
| width_px | INTEGER | Image width in pixels |
| height_px | INTEGER | Image height in pixels |
| file_size_bytes | BIGINT | File size in bytes |
| created_at | TIMESTAMP | Upload timestamp |

#### `styles`
Defines rendering styles with algorithm configuration.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| name | VARCHAR(100) | Display name |
| slug | VARCHAR(100) | URL-safe identifier (unique) |
| algorithm_config | JSONB | Pipeline parameters |
| description | TEXT | Style description |
| created_at | TIMESTAMP | Creation timestamp |

**Seeded Styles:**
- `pop-poster`: K-means posterization with edge detection
- `pencil-sketch`: Grayscale sketch effect
- `between-the-lines`: Line art with directional motion blur

#### `size_presets`
Predefined print sizes at 300 DPI.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| name | VARCHAR(100) | Display name (e.g., "9x12") |
| width_inches | DECIMAL(6,2) | Width in inches |
| height_inches | DECIMAL(6,2) | Height in inches |
| dpi | INTEGER | Resolution (always 300) |
| created_at | TIMESTAMP | Creation timestamp |

**Seeded Presets:**
- 9x12 (2700x3600px)
- 12x16 (3600x4800px)
- 16x20 (4800x6000px)
- 20x24 (6000x7200px)
- 30x40 (9000x12000px)

#### `renders`
Tracks render job lifecycle and outputs.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| asset_id | UUID | Foreign key to assets |
| style_id | UUID | Foreign key to styles |
| size_preset_id | UUID | Foreign key to size_presets |
| status | VARCHAR(20) | Job status (queued/started/completed/failed) |
| rq_job_id | VARCHAR(100) | RQ job identifier |
| output_minio_key | VARCHAR(512) | TIFF output location |
| preview_minio_key | VARCHAR(512) | JPEG preview location |
| started_at | TIMESTAMP | Processing start time |
| completed_at | TIMESTAMP | Processing completion time |
| duration_ms | INTEGER | Total processing duration |
| error_message | TEXT | Error details if failed |
| metadata | JSONB | Additional job metadata |
| created_at | TIMESTAMP | Job creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

**Key Indexes:**
- `idx_renders_status`: Fast filtering by status
- `idx_renders_status_created`: Combined status + timestamp queries
- `idx_renders_rq_job_id`: Lookup by RQ job ID
- `idx_renders_asset_id`, `idx_renders_style_id`, `idx_renders_size_preset_id`: Foreign key lookups

**Health Check:** Executes `SELECT 1` to verify connectivity.

## Data Flows

### 1. Create Render Job Flow

```
Client → API: POST /v1/renders
                {file, style_id, size_preset_id}
  │
  ├─ Validate file (type, size, dimensions)
  ├─ Validate style_id exists in DB
  ├─ Validate size_preset_id exists in DB
  │
  ├─ Upload to MinIO: uploads/{asset_id}/{filename}
  ├─ Insert asset record in PostgreSQL
  ├─ Insert render record (status='queued')
  ├─ Enqueue job in Redis
  │
API → Client: 201 {render_id, status: "queued", created_at}
```

**Validation Rules:**
- File must be present
- File size ≤ 50MB
- Format must be JPEG, PNG, TIFF, BMP, or WEBP
- Dimensions ≤ 10,000 pixels (width and height)
- `style_id` must be valid UUID referencing existing style
- `size_preset_id` must be valid UUID referencing existing preset

### 2. Job Processing Flow

```
RQ Worker polls Redis queue
  │
  ├─ Fetch job: process_render(render_id, asset_id, style_id, size_preset_id)
  ├─ Update DB: status='started', started_at=NOW()
  │
  ├─ Fetch render details from DB (style config, dimensions, asset key)
  ├─ Download source image from MinIO
  │
  ├─ Select pipeline class from PIPELINE_MAP[style_slug]
  ├─ Instantiate pipeline with algorithm_config
  ├─ Execute: output_image = pipeline.render(input_image)
  │
  ├─ Resize to target dimensions (width_inches × dpi, height_inches × dpi)
  ├─ Save TIFF (300 DPI, LZW compression)
  ├─ Generate JPEG preview (max 1200px wide, 85% quality)
  │
  ├─ Upload TIFF to MinIO: renders/{render_id}/output.tiff
  ├─ Upload JPEG to MinIO: renders/{render_id}/preview.jpg
  │
  ├─ Update DB: status='completed', output_minio_key, preview_minio_key,
  │              completed_at=NOW(), duration_ms
  ├─ Track metrics: render_jobs_total, render_duration_seconds
  │
  └─ Cleanup temporary files
```

**Error Handling:**
- On exception: Update DB with status='failed' and error_message
- Track failure metric
- RQ retries based on configuration
- Failed jobs retained for 7 days for debugging

### 3. Status Polling Flow

```
Client → API: GET /v1/renders/{render_id}
  │
  ├─ Validate render_id is valid UUID
  ├─ Query DB for render record with JOINs to styles, size_presets
  │
API → Client: 200 {
                id, status, asset_id, style, size_preset,
                created_at, started_at, completed_at, duration_ms,
                error_message
              }
```

**Status Values:**
- `queued`: Job waiting in Redis queue
- `started`: Worker processing job
- `completed`: Job finished successfully
- `failed`: Job encountered error

### 4. Download Flow

```
Client → API: GET /v1/renders/{render_id}/download
  │
  ├─ Validate render_id is valid UUID
  ├─ Query DB for render record
  ├─ Check status='completed' (409 if not completed)
  ├─ Generate presigned URL from MinIO (7-day expiry)
  │
API → Client: 200 {url, expires_in: 604800}

Client → MinIO: GET presigned URL → Download TIFF file
```

**Preview Flow:**
Same as download but uses `preview_minio_key` instead of `output_minio_key`.

## Request Lifecycle

### Detailed Request Processing

**1. Request Reception**
- Client sends HTTP request to Flask API
- Gunicorn handles connection on port 8089
- Request routed to appropriate handler

**2. Middleware Processing (Before Request)**
```python
@app.before_request
def before_request():
    request._start_time = time.time()
```

**3. Route Handler Execution**
- Extract parameters from request (JSON body, multipart form, URL path)
- Call validation functions
- Execute business logic (DB queries, storage operations)
- Return response object

**4. Middleware Processing (After Request)**
```python
@app.after_request
def after_request(response):
    duration = time.time() - request._start_time
    track_request_metrics(
        method=request.method,
        endpoint=request.endpoint,
        status=response.status_code,
        duration=duration
    )
    return response
```

**5. Response Serialization**
- Convert Python objects to JSON
- Set appropriate HTTP headers
- Return to client

**Typical Request Times:**
- GET /v1/renders/{id}: 5-50ms (DB query)
- POST /v1/renders: 200-2000ms (file upload + storage + queue)
- GET /v1/renders/{id}/download: 10-100ms (presigned URL generation)
- GET /health: 20-200ms (DB + Redis + MinIO checks)

## Integration Points

### Integration with Catalog Service

The catalog service manages user assets and initiates render jobs.

**Integration Pattern:**
```
Catalog Service → Pop-Render API: POST /v1/renders
  {
    file: <uploaded-image>,
    style_id: "uuid-from-catalog",
    size_preset_id: "uuid-from-catalog"
  }

Pop-Render API → Catalog Service: 201 {render_id, status, created_at}

Catalog Service polls: GET /v1/renders/{render_id}
  Until status = "completed"

Catalog Service downloads: GET /v1/renders/{render_id}/download
  Stores presigned URL for user download
```

**Shared Data:**
- Style definitions synchronized via shared database or API
- Size presets synchronized via shared database or API
- Asset metadata linked via `asset_id` references

**Error Scenarios:**
- 400 errors: Catalog retries with corrected parameters
- 500 errors: Catalog implements exponential backoff retry
- 409 errors: Catalog continues polling for completion

### Integration with Orchestration Service

The orchestration service coordinates multi-step workflows involving rendering.

**Integration Pattern:**
```
Orchestration Service initiates workflow:
  1. Call Catalog to validate user permissions
  2. Call Pop-Render to create render job
  3. Poll Pop-Render for completion
  4. On completion, trigger downstream services (email, notifications)

Orchestration monitors via:
  - GET /v1/renders/{id} for status updates
  - GET /metrics for queue depth and performance
  - GET /health for service availability
```

**Event-Driven Integration (Future):**
- Pop-Render could emit events on job completion
- Orchestration subscribes to event stream
- Eliminates polling overhead

### Direct Client Integration

Web and mobile clients can integrate directly for user-initiated renders.

**Client Workflow:**
1. User uploads image via web form
2. Client calls POST /v1/renders with file
3. Client polls GET /v1/renders/{id} every 5-10 seconds
4. On completion, client displays preview via presigned URL
5. User downloads TIFF via presigned URL

**Client Libraries:**
- JavaScript/TypeScript: Fetch API or Axios
- Python: Requests or HTTPX
- Mobile: Native HTTP clients (URLSession, OkHttp)

**Authentication (Future):**
- Bearer token authentication
- API key authentication
- OAuth 2.0 integration

## Configuration Environment Variables

Complete environment variable reference:

### Database (PostgreSQL)

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| DB_HOST | localhost | No | PostgreSQL hostname |
| DB_PORT | 5432 | No | PostgreSQL port |
| DB_NAME | aso_render | No | Database name |
| DB_USER | postgres | No | Database user |
| DB_PASSWORD | - | **Yes** | Database password |

### Redis (Job Queue)

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| REDIS_HOST | localhost | No | Redis hostname |
| REDIS_PORT | 6379 | No | Redis port |
| REDIS_DB | 0 | No | Redis database number |

### MinIO/S3 (Object Storage)

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| MINIO_ENDPOINT | - | **Yes** | MinIO endpoint (host:port) |
| MINIO_ACCESS_KEY | - | **Yes** | MinIO access key |
| MINIO_SECRET_KEY | - | **Yes** | MinIO secret key |
| MINIO_BUCKET | render-assets | No | Storage bucket name |

### Service Configuration

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| API_PORT | 8089 | No | Flask API port |
| WORKER_COUNT | 2 | No | Gunicorn worker count |
| LOG_LEVEL | INFO | No | Logging level (DEBUG/INFO/WARNING/ERROR/CRITICAL) |

### Example Configuration

**.env file:**
```bash
# Database
DB_HOST=postgres.example.com
DB_PORT=5432
DB_NAME=aso_render
DB_USER=render_user
DB_PASSWORD=secure-password-123

# Redis
REDIS_HOST=redis.example.com
REDIS_PORT=6379
REDIS_DB=0

# MinIO
MINIO_ENDPOINT=minio.example.com:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin-secret
MINIO_BUCKET=render-assets

# Service
API_PORT=8089
WORKER_COUNT=4
LOG_LEVEL=INFO
```

**Loading Configuration:**
```bash
# Load from .env file
export $(cat .env | xargs)

# Or pass directly to gunicorn
gunicorn -w 4 -b 0.0.0.0:8089 app:app
```

## Health Check Interpretation

The service provides three health check endpoints for different monitoring purposes.

### 1. Comprehensive Health Check

**Endpoint:** `GET /health`

**Purpose:** Complete dependency health verification

**Response (Healthy):**
```json
{
  "status": "healthy",
  "service": "pop-render",
  "timestamp": "2026-01-24T10:30:00Z",
  "uptime_seconds": 86400,
  "checks": {
    "database": {
      "status": "healthy",
      "latency_ms": 5
    },
    "redis": {
      "status": "healthy",
      "latency_ms": 2
    },
    "storage": {
      "status": "healthy",
      "latency_ms": 15
    }
  }
}
```

**Response (Unhealthy):**
```json
{
  "status": "unhealthy",
  "service": "pop-render",
  "timestamp": "2026-01-24T10:30:00Z",
  "uptime_seconds": 86400,
  "checks": {
    "database": {
      "status": "healthy",
      "latency_ms": 5
    },
    "redis": {
      "status": "unhealthy",
      "error": "Connection refused"
    },
    "storage": {
      "status": "healthy",
      "latency_ms": 15
    }
  }
}
```

**HTTP Status Codes:**
- 200: All dependencies healthy
- 503: One or more dependencies unhealthy

**Interpretation:**
- Use for load balancer health checks
- Use for alerting on dependency failures
- High latency (>100ms) indicates potential issues

### 2. Readiness Check

**Endpoint:** `GET /health/readiness`

**Purpose:** Kubernetes readiness probe (is service ready to accept traffic?)

**Response:**
```json
{
  "status": "ready",
  "service": "pop-render",
  "timestamp": "2026-01-24T10:30:00Z",
  "checks": {
    "database": {
      "status": "healthy",
      "latency_ms": 5
    }
  }
}
```

**HTTP Status Codes:**
- 200: Service ready
- 503: Service not ready

**Interpretation:**
- Only checks critical dependency (database)
- Kubernetes uses this to add/remove pod from service
- Failure triggers temporary removal from load balancer

### 3. Liveness Check

**Endpoint:** `GET /health/liveness`

**Purpose:** Kubernetes liveness probe (is service process alive?)

**Response:**
```json
{
  "status": "alive",
  "service": "pop-render",
  "timestamp": "2026-01-24T10:30:00Z",
  "uptime_seconds": 86400
}
```

**HTTP Status Codes:**
- 200: Service alive

**Interpretation:**
- No dependency checks (lightweight)
- Kubernetes uses this to restart unhealthy pods
- Failure triggers pod restart
- Should almost never fail (indicates process deadlock)

### Health Check Best Practices

**Load Balancer Configuration:**
```
Use: GET /health
Interval: 30 seconds
Timeout: 5 seconds
Unhealthy Threshold: 3 consecutive failures
Healthy Threshold: 2 consecutive successes
```

**Kubernetes Configuration:**
```yaml
livenessProbe:
  httpGet:
    path: /health/liveness
    port: 8089
  initialDelaySeconds: 10
  periodSeconds: 30
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health/readiness
    port: 8089
  initialDelaySeconds: 5
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3
```

**Alerting Thresholds:**
- Database latency > 100ms: Warning
- Database latency > 500ms: Critical
- Redis unavailable: Critical
- Storage latency > 1000ms: Warning
- Storage unavailable: Critical

## Metrics Catalog

Complete Prometheus metrics reference with descriptions.

### HTTP Metrics

#### `http_requests_total`
**Type:** Counter
**Labels:** method, endpoint, status
**Description:** Total number of HTTP requests processed by the API
**Usage:** Track request volume and error rates

**Example Queries:**
```promql
# Request rate by endpoint
rate(http_requests_total[5m])

# Error rate (4xx and 5xx)
rate(http_requests_total{status=~"4..|5.."}[5m])

# Success rate percentage
sum(rate(http_requests_total{status=~"2.."}[5m])) /
sum(rate(http_requests_total[5m])) * 100
```

#### `http_request_duration_seconds`
**Type:** Histogram
**Labels:** method, endpoint
**Buckets:** [0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
**Description:** HTTP request latency distribution in seconds
**Usage:** Track API performance and identify slow endpoints

**Example Queries:**
```promql
# P95 latency by endpoint
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint))

# Average latency
rate(http_request_duration_seconds_sum[5m]) /
rate(http_request_duration_seconds_count[5m])
```

### Database Metrics

#### `db_connections_active`
**Type:** Gauge
**Labels:** None
**Description:** Number of active database connections from the pool
**Usage:** Monitor connection pool utilization

**Alerting:**
- Warning: > 8 connections (80% of max 10)
- Critical: = 10 connections (pool exhausted)

#### `db_query_duration_seconds`
**Type:** Histogram
**Labels:** query_type (SELECT, INSERT, UPDATE, DELETE)
**Buckets:** [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
**Description:** Database query latency distribution
**Usage:** Identify slow queries and database performance issues

**Example Queries:**
```promql
# P99 query latency by type
histogram_quantile(0.99,
  sum(rate(db_query_duration_seconds_bucket[5m])) by (le, query_type))
```

#### `db_errors_total`
**Type:** Counter
**Labels:** error_type
**Description:** Total database errors by type
**Usage:** Track database connectivity and query errors

**Common Error Types:**
- connection_error: Cannot connect to database
- query_error: Query execution failed
- timeout_error: Query exceeded timeout

### Storage Metrics

#### `storage_operations_total`
**Type:** Counter
**Labels:** operation (upload/download/delete), status (success/failure)
**Description:** Total storage operations performed
**Usage:** Track storage usage and error rates

**Example Queries:**
```promql
# Upload failure rate
rate(storage_operations_total{operation="upload",status="failure"}[5m]) /
rate(storage_operations_total{operation="upload"}[5m]) * 100
```

#### `storage_operation_duration_seconds`
**Type:** Histogram
**Labels:** operation
**Buckets:** [0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
**Description:** Storage operation latency distribution
**Usage:** Monitor MinIO performance

#### `storage_bytes_transferred`
**Type:** Counter
**Labels:** direction (upload/download)
**Description:** Total bytes transferred to/from storage
**Usage:** Track bandwidth usage

**Example Queries:**
```promql
# Upload bandwidth (bytes/sec)
rate(storage_bytes_transferred{direction="upload"}[5m])
```

### Render Job Metrics

#### `render_jobs_total`
**Type:** Counter
**Labels:** status (completed/failed), style, service
**Description:** Total render jobs processed
**Usage:** Track rendering volume and success rates

**Example Queries:**
```promql
# Success rate by style
sum(rate(render_jobs_total{status="completed"}[5m])) by (style) /
sum(rate(render_jobs_total[5m])) by (style) * 100

# Total jobs processed today
increase(render_jobs_total[24h])
```

#### `render_duration_seconds`
**Type:** Histogram
**Labels:** style, service
**Buckets:** [1, 5, 10, 30, 60, 120]
**Description:** Render job processing duration distribution
**Usage:** Monitor rendering performance by style

**Example Queries:**
```promql
# P90 render time by style
histogram_quantile(0.90,
  sum(rate(render_duration_seconds_bucket[5m])) by (le, style))
```

#### `renders_in_progress`
**Type:** Gauge
**Labels:** None
**Description:** Number of renders currently being processed
**Usage:** Monitor worker utilization

**Alerting:**
- Warning: > 10 concurrent renders (may indicate worker bottleneck)

### Queue Metrics

#### `render_queue_depth`
**Type:** Gauge
**Labels:** service
**Description:** Number of jobs waiting in render queue
**Usage:** Monitor queue backlog and worker capacity

**Alerting:**
- Warning: > 50 jobs (consider adding workers)
- Critical: > 200 jobs (severe backlog)

**Example Queries:**
```promql
# Average queue depth over 1 hour
avg_over_time(render_queue_depth[1h])
```

### Resource Metrics

#### `render_storage_bytes_total`
**Type:** Gauge
**Labels:** service
**Description:** Total size of render-assets bucket in bytes
**Usage:** Monitor storage capacity and growth

**Example Queries:**
```promql
# Storage size in GB
render_storage_bytes_total / 1024^3

# Daily growth rate
deriv(render_storage_bytes_total[24h]) * 86400 / 1024^3
```

#### `process_resident_memory_bytes`
**Type:** Gauge
**Labels:** service
**Description:** Resident memory size in bytes
**Usage:** Monitor memory usage and detect leaks

**Alerting:**
- Warning: > 1GB (check for memory leaks)
- Critical: > 2GB (pod may be OOM killed)

### Health Metrics

#### `health_check_status`
**Type:** Gauge
**Labels:** dependency (database/redis/storage)
**Description:** Health check status (1=healthy, 0=unhealthy)
**Usage:** Monitor dependency availability

**Alerting:**
```promql
health_check_status{dependency="database"} == 0
health_check_status{dependency="redis"} == 0
health_check_status{dependency="storage"} == 0
```

## Event Emission Schema

The pop-render service emits events through structured logging and Prometheus metrics.

### Structured Logging Events

**Format:** JSON logs sent to stdout/stderr

**Log Entry Schema:**
```json
{
  "timestamp": "2026-01-24T10:30:00.123456Z",
  "level": "INFO|WARNING|ERROR|CRITICAL",
  "logger": "pop-render",
  "message": "Human-readable message",
  "render_id": "uuid",
  "asset_id": "uuid",
  "style": "style-slug",
  "duration_ms": 12345,
  "error": "Error message if applicable",
  "traceback": "Stack trace if error"
}
```

**Event Types:**

#### Job Created
```json
{
  "timestamp": "2026-01-24T10:30:00Z",
  "level": "INFO",
  "logger": "pop-render.api",
  "message": "Render job created",
  "render_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "asset_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "style": "pop-poster",
  "size_preset": "9x12"
}
```

#### Job Started
```json
{
  "timestamp": "2026-01-24T10:30:05Z",
  "level": "INFO",
  "logger": "pop-render.worker",
  "message": "Render job started",
  "render_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "worker_id": "worker-1"
}
```

#### Job Completed
```json
{
  "timestamp": "2026-01-24T10:32:15Z",
  "level": "INFO",
  "logger": "pop-render.worker",
  "message": "Render job completed successfully",
  "render_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "duration_ms": 130000,
  "output_size_bytes": 45678912,
  "preview_size_bytes": 234567
}
```

#### Job Failed
```json
{
  "timestamp": "2026-01-24T10:31:30Z",
  "level": "ERROR",
  "logger": "pop-render.worker",
  "message": "Render job failed",
  "render_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "error": "Pipeline error: Invalid image dimensions",
  "traceback": "Traceback (most recent call last):\n  File..."
}
```

### Prometheus Metric Events

Metrics are continuously emitted and scraped by Prometheus.

**Metric Update Events:**

#### Request Processed
```python
http_requests_total.labels(
    method="POST",
    endpoint="/v1/renders",
    status="201"
).inc()

http_request_duration_seconds.labels(
    method="POST",
    endpoint="/v1/renders"
).observe(0.523)
```

#### Render Job Completed
```python
render_jobs_total.labels(
    status="completed",
    style="pop-poster",
    service="pop-render"
).inc()

render_duration_seconds.labels(
    style="pop-poster",
    service="pop-render"
).observe(130.5)

renders_in_progress.dec()
```

#### Storage Operation
```python
storage_operations_total.labels(
    operation="upload",
    status="success"
).inc()

storage_operation_duration_seconds.labels(
    operation="upload"
).observe(2.34)

storage_bytes_transferred.labels(
    direction="upload"
).inc(45678912)
```

### Event Aggregation

**Log Aggregation:**
- Logs collected by container runtime (Docker/Kubernetes)
- Shipped to centralized logging (ELK, Loki, CloudWatch)
- Indexed by render_id, asset_id, style for searchability

**Metric Aggregation:**
- Prometheus scrapes /metrics endpoint every 15-60 seconds
- Metrics stored in Prometheus TSDB
- Grafana dashboards visualize metrics
- Alertmanager triggers alerts based on metric thresholds

**Event Correlation:**
- Link logs to metrics via render_id
- Trace job lifecycle: created → started → completed/failed
- Debug issues by correlating error logs with metric anomalies

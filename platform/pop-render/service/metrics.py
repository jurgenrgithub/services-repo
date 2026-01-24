"""
Prometheus metrics for ASO Render Service.

Exposes application metrics for monitoring and observability, including
request counters, latency histograms, and custom business metrics.
"""

import logging
from typing import Callable
from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST
from flask import Response
import time

logger = logging.getLogger(__name__)

# ============================================================================
# HTTP Metrics
# ============================================================================

http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status'],
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ============================================================================
# Database Metrics
# ============================================================================

db_connections_active = Gauge(
    'db_connections_active',
    'Number of active database connections',
)

db_query_duration_seconds = Histogram(
    'db_query_duration_seconds',
    'Database query latency in seconds',
    ['query_type'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

db_errors_total = Counter(
    'db_errors_total',
    'Total database errors',
    ['error_type'],
)

# ============================================================================
# Storage Metrics
# ============================================================================

storage_operations_total = Counter(
    'storage_operations_total',
    'Total storage operations',
    ['operation', 'status'],
)

storage_bytes_transferred = Counter(
    'storage_bytes_transferred',
    'Total bytes transferred to/from storage',
    ['direction'],  # upload, download
)

storage_operation_duration_seconds = Histogram(
    'storage_operation_duration_seconds',
    'Storage operation latency in seconds',
    ['operation'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

# ============================================================================
# Render Job Metrics
# ============================================================================

render_jobs_total = Counter(
    'render_jobs_total',
    'Total render jobs',
    ['status'],  # queued, completed, failed
)

render_job_duration_seconds = Histogram(
    'render_job_duration_seconds',
    'Render job processing time in seconds',
    ['style'],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0],
)

render_queue_depth = Gauge(
    'render_queue_depth',
    'Number of jobs waiting in render queue',
)

renders_in_progress = Gauge(
    'renders_in_progress',
    'Number of renders currently being processed',
)

# ============================================================================
# Application Info
# ============================================================================

app_info = Info(
    'app',
    'Application information',
)

app_info.info({
    'service': 'pop-render',
    'version': '1.0.0',
})

# ============================================================================
# Health Metrics
# ============================================================================

health_check_status = Gauge(
    'health_check_status',
    'Health check status (1=healthy, 0=unhealthy)',
    ['dependency'],  # database, redis, storage
)

# ============================================================================
# Flask Endpoint
# ============================================================================

def metrics_endpoint() -> Response:
    """
    Prometheus metrics endpoint handler.

    Returns:
        Flask Response with metrics in Prometheus format
    """
    return Response(
        generate_latest(),
        mimetype=CONTENT_TYPE_LATEST,
    )


# ============================================================================
# Middleware and Decorators
# ============================================================================

def track_request_metrics(method: str, endpoint: str, status: int, duration: float) -> None:
    """
    Track HTTP request metrics.

    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: Request endpoint
        status: HTTP status code
        duration: Request duration in seconds
    """
    http_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
    http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)


def track_db_query(query_type: str, duration: float, error: bool = False) -> None:
    """
    Track database query metrics.

    Args:
        query_type: Type of query (SELECT, INSERT, UPDATE, etc.)
        duration: Query duration in seconds
        error: Whether query resulted in error
    """
    db_query_duration_seconds.labels(query_type=query_type).observe(duration)
    if error:
        db_errors_total.labels(error_type='query_error').inc()


def track_storage_operation(
    operation: str,
    status: str,
    duration: float,
    bytes_transferred: int = 0,
    direction: str = 'upload',
) -> None:
    """
    Track storage operation metrics.

    Args:
        operation: Operation type (upload, download, delete, etc.)
        status: Operation status (success, failure)
        duration: Operation duration in seconds
        bytes_transferred: Number of bytes transferred
        direction: Transfer direction (upload, download)
    """
    storage_operations_total.labels(operation=operation, status=status).inc()
    storage_operation_duration_seconds.labels(operation=operation).observe(duration)
    if bytes_transferred > 0:
        storage_bytes_transferred.labels(direction=direction).inc(bytes_transferred)


def track_render_job(
    status: str,
    style: str = 'unknown',
    duration: float = 0.0,
) -> None:
    """
    Track render job metrics.

    Args:
        status: Job status (queued, completed, failed)
        style: Rendering style used
        duration: Job duration in seconds (for completed jobs)
    """
    render_jobs_total.labels(status=status).inc()
    if status == 'completed' and duration > 0:
        render_job_duration_seconds.labels(style=style).observe(duration)


def update_health_status(dependency: str, is_healthy: bool) -> None:
    """
    Update health check status metric.

    Args:
        dependency: Dependency name (database, redis, storage)
        is_healthy: Health status (True=healthy, False=unhealthy)
    """
    health_check_status.labels(dependency=dependency).set(1 if is_healthy else 0)


# ============================================================================
# Context Manager for Timing
# ============================================================================

class MetricsTimer:
    """
    Context manager for timing operations and recording metrics.

    Usage:
        with MetricsTimer(lambda d: track_storage_operation('upload', 'success', d)):
            # Perform operation
            upload_file()
    """

    def __init__(self, callback: Callable[[float], None]):
        """
        Initialize metrics timer.

        Args:
            callback: Function to call with duration when done
        """
        self.callback = callback
        self.start_time = None

    def __enter__(self):
        """Start timing."""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timing and record metric."""
        if self.start_time:
            duration = time.time() - self.start_time
            self.callback(duration)

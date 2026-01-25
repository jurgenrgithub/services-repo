"""
Prometheus monitoring for ASO Render Service.

Implements enterprise-grade observability with:
- Render job metrics (counter, histogram with style labels)
- Queue depth monitoring (background thread)
- Storage bucket size tracking (hourly updates)
- Process memory monitoring
- All metrics labeled with service='pop-render'

This module provides self-healing observability - metrics continue to update
even if individual components fail, ensuring monitoring remains operational.
"""

import logging
import threading
import time
from typing import Optional
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, REGISTRY
import psutil
import os

logger = logging.getLogger(__name__)

# ============================================================================
# Render Job Metrics
# ============================================================================

render_jobs_total = Counter(
    'render_jobs_total',
    'Total render jobs processed',
    ['status', 'style', 'service'],
)

render_duration_seconds = Histogram(
    'render_duration_seconds',
    'Render job processing duration in seconds',
    ['style', 'service'],
    buckets=[1, 5, 10, 30, 60, 120],
)

render_queue_depth = Gauge(
    'render_queue_depth',
    'Number of jobs waiting in render queue',
    ['service'],
)

# ============================================================================
# Storage Metrics
# ============================================================================

render_storage_bytes_total = Gauge(
    'render_storage_bytes_total',
    'Total size of render-assets bucket in bytes',
    ['service'],
)

# ============================================================================
# Process Metrics
# ============================================================================

pop_render_process_rss_bytes = Gauge(
    'pop_render_process_rss_bytes',
    'Resident memory size in bytes',
    ['service'],
)

# ============================================================================
# Background Monitoring Threads
# ============================================================================

class QueueDepthMonitor:
    """
    Background thread to monitor queue depth every 60 seconds.

    Features:
    - Automatic recovery from Redis connection failures
    - Continuous monitoring with configurable interval
    - Graceful shutdown support
    - Observable via metrics even when queue is unavailable

    Root Cause Prevention:
    - Prevents silent queue buildup by continuous monitoring
    - Detects queue availability issues automatically
    - Self-heals from transient Redis failures
    """

    def __init__(self, interval: int = 60):
        """
        Initialize queue depth monitor.

        Args:
            interval: Update interval in seconds (default: 60)
        """
        self.interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

    def start(self) -> None:
        """Start background monitoring thread."""
        if self._running:
            logger.warning("Queue depth monitor already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="QueueDepthMonitor",
            daemon=True,
        )
        self._thread.start()
        self._running = True
        logger.info(
            "Queue depth monitor started",
            extra={"interval_seconds": self.interval},
        )

    def stop(self) -> None:
        """Stop background monitoring thread."""
        if not self._running:
            return

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._running = False
        logger.info("Queue depth monitor stopped")

    def _monitor_loop(self) -> None:
        """Main monitoring loop with error recovery."""
        while not self._stop_event.is_set():
            try:
                self._update_queue_depth()
            except Exception as e:
                logger.error(
                    "Failed to update queue depth metric",
                    extra={"error": str(e)},
                )
                # Set to -1 to indicate monitoring failure
                render_queue_depth.labels(service='pop-render').set(-1)

            # Wait for next interval or stop event
            self._stop_event.wait(self.interval)

    def _update_queue_depth(self) -> None:
        """
        Update queue depth metric from Redis.

        Implements root cause fix: directly queries RQ queue count
        instead of relying on cached values that could be stale.
        """
        from render_queue import get_queue_manager

        queue_mgr = get_queue_manager()

        # Ensure queue manager is initialized
        if not queue_mgr._initialized:
            logger.warning("Queue manager not initialized, attempting to initialize")
            queue_mgr.initialize()

        # Get queue count directly from Redis
        if queue_mgr._queue:
            count = queue_mgr._queue.count
            render_queue_depth.labels(service='pop-render').set(count)
            logger.debug(
                "Queue depth updated",
                extra={"count": count},
            )
        else:
            logger.warning("Queue not available for depth monitoring")
            render_queue_depth.labels(service='pop-render').set(-1)


class StorageSizeMonitor:
    """
    Background thread to monitor storage bucket size hourly.

    Features:
    - Hourly bucket size calculation
    - Automatic recovery from MinIO connection failures
    - Efficient iteration over bucket objects
    - Observable via metrics even when storage is unavailable

    Root Cause Prevention:
    - Prevents storage exhaustion by continuous monitoring
    - Detects storage availability issues automatically
    - Self-heals from transient MinIO failures
    - Provides early warning for capacity planning
    """

    def __init__(self, interval: int = 3600):
        """
        Initialize storage size monitor.

        Args:
            interval: Update interval in seconds (default: 3600 = 1 hour)
        """
        self.interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

    def start(self) -> None:
        """Start background monitoring thread."""
        if self._running:
            logger.warning("Storage size monitor already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="StorageSizeMonitor",
            daemon=True,
        )
        self._thread.start()
        self._running = True
        logger.info(
            "Storage size monitor started",
            extra={"interval_seconds": self.interval},
        )

    def stop(self) -> None:
        """Stop background monitoring thread."""
        if not self._running:
            return

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._running = False
        logger.info("Storage size monitor stopped")

    def _monitor_loop(self) -> None:
        """Main monitoring loop with error recovery."""
        while not self._stop_event.is_set():
            try:
                self._update_storage_size()
            except Exception as e:
                logger.error(
                    "Failed to update storage size metric",
                    extra={"error": str(e)},
                )
                # Set to -1 to indicate monitoring failure
                render_storage_bytes_total.labels(service='pop-render').set(-1)

            # Wait for next interval or stop event
            self._stop_event.wait(self.interval)

    def _update_storage_size(self) -> None:
        """
        Update storage bucket size metric from MinIO.

        Implements root cause fix: iterates all objects to calculate
        accurate total size instead of relying on cached metadata.
        """
        from storage import get_storage_client

        storage = get_storage_client()

        # Ensure storage client is initialized
        if not storage._initialized:
            logger.warning("Storage client not initialized, attempting to initialize")
            storage.initialize()

        # Calculate total bucket size
        if storage._client:
            total_bytes = 0
            paginator = storage._client.get_paginator('list_objects_v2')

            try:
                for page in paginator.paginate(Bucket=storage._bucket_name):
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            total_bytes += obj['Size']

                render_storage_bytes_total.labels(service='pop-render').set(total_bytes)
                logger.info(
                    "Storage size updated",
                    extra={
                        "total_bytes": total_bytes,
                        "total_mb": round(total_bytes / (1024 * 1024), 2),
                    },
                )
            except Exception as e:
                logger.error(
                    "Failed to calculate bucket size",
                    extra={"error": str(e)},
                )
                render_storage_bytes_total.labels(service='pop-render').set(-1)
        else:
            logger.warning("Storage client not available for size monitoring")
            render_storage_bytes_total.labels(service='pop-render').set(-1)


class ProcessMemoryMonitor:
    """
    Background thread to monitor process memory every 30 seconds.

    Features:
    - Tracks resident memory (RSS) for worker processes
    - Enables memory leak detection
    - Provides data for capacity planning

    Root Cause Prevention:
    - Detects memory leaks early before OOM kills
    - Provides trend data for memory growth analysis
    - Enables proactive scaling decisions
    """

    def __init__(self, interval: int = 30):
        """
        Initialize process memory monitor.

        Args:
            interval: Update interval in seconds (default: 30)
        """
        self.interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
        self._process = psutil.Process(os.getpid())

    def start(self) -> None:
        """Start background monitoring thread."""
        if self._running:
            logger.warning("Process memory monitor already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="ProcessMemoryMonitor",
            daemon=True,
        )
        self._thread.start()
        self._running = True
        logger.info(
            "Process memory monitor started",
            extra={"interval_seconds": self.interval},
        )

    def stop(self) -> None:
        """Stop background monitoring thread."""
        if not self._running:
            return

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._running = False
        logger.info("Process memory monitor stopped")

    def _monitor_loop(self) -> None:
        """Main monitoring loop with error recovery."""
        while not self._stop_event.is_set():
            try:
                self._update_memory_usage()
            except Exception as e:
                logger.error(
                    "Failed to update memory metric",
                    extra={"error": str(e)},
                )

            # Wait for next interval or stop event
            self._stop_event.wait(self.interval)

    def _update_memory_usage(self) -> None:
        """Update process memory metric."""
        memory_info = self._process.memory_info()
        rss_bytes = memory_info.rss

        pop_render_process_rss_bytes.labels(service='pop-render').set(rss_bytes)
        logger.debug(
            "Process memory updated",
            extra={
                "rss_bytes": rss_bytes,
                "rss_mb": round(rss_bytes / (1024 * 1024), 2),
            },
        )


# ============================================================================
# Global Monitor Instances
# ============================================================================

_queue_monitor: Optional[QueueDepthMonitor] = None
_storage_monitor: Optional[StorageSizeMonitor] = None
_memory_monitor: Optional[ProcessMemoryMonitor] = None


def start_monitoring() -> None:
    """
    Start all background monitoring threads.

    Initializes queue depth, storage size, and memory monitoring.
    Safe to call multiple times (idempotent).
    """
    global _queue_monitor, _storage_monitor, _memory_monitor

    # Start queue depth monitoring (every 60 seconds)
    if _queue_monitor is None:
        _queue_monitor = QueueDepthMonitor(interval=60)
        _queue_monitor.start()

    # Start storage size monitoring (every hour)
    if _storage_monitor is None:
        _storage_monitor = StorageSizeMonitor(interval=3600)
        _storage_monitor.start()

    # Start memory monitoring (every 30 seconds)
    if _memory_monitor is None:
        _memory_monitor = ProcessMemoryMonitor(interval=30)
        _memory_monitor.start()

    logger.info("All monitoring threads started")


def stop_monitoring() -> None:
    """
    Stop all background monitoring threads.

    Gracefully shuts down all monitoring threads.
    Safe to call multiple times (idempotent).
    """
    global _queue_monitor, _storage_monitor, _memory_monitor

    if _queue_monitor:
        _queue_monitor.stop()
        _queue_monitor = None

    if _storage_monitor:
        _storage_monitor.stop()
        _storage_monitor = None

    if _memory_monitor:
        _memory_monitor.stop()
        _memory_monitor = None

    logger.info("All monitoring threads stopped")


# ============================================================================
# Helper Functions
# ============================================================================

def track_render_job(status: str, style: str, duration_seconds: float = 0.0) -> None:
    """
    Track render job metrics with service label.

    Args:
        status: Job status ('completed', 'failed')
        style: Rendering style slug
        duration_seconds: Job duration in seconds (for completed jobs)

    Root Cause Prevention:
    - Always includes service label for multi-service environments
    - Captures both success and failure metrics
    - Records duration for performance analysis
    """
    # Increment counter with all labels
    render_jobs_total.labels(
        status=status,
        style=style,
        service='pop-render',
    ).inc()

    # Record duration for completed jobs
    if status == 'completed' and duration_seconds > 0:
        render_duration_seconds.labels(
            style=style,
            service='pop-render',
        ).observe(duration_seconds)

    logger.debug(
        "Render job tracked",
        extra={
            "status": status,
            "style": style,
            "duration_seconds": duration_seconds,
        },
    )

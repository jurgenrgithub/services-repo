"""
Redis Queue (RQ) management for ASO Render Service.

Provides enterprise-grade job queue operations for background render processing
with automatic connection management, health checks, and error recovery.
"""

import logging
from typing import Optional, Any, Dict
from redis import Redis
from rq import Queue
from rq.job import Job

from config import Config

logger = logging.getLogger(__name__)


class QueueManager:
    """
    Redis Queue manager for background render jobs.

    Features:
    - Automatic Redis connection management
    - Job enqueueing with metadata
    - Job status tracking
    - Health checks for monitoring
    - Error recovery and retry logic

    Usage:
        queue_mgr = QueueManager()
        queue_mgr.initialize()

        # Enqueue job
        job = queue_mgr.enqueue_render(
            render_id='uuid',
            asset_id='uuid',
            style_id='uuid',
            size_preset_id='uuid'
        )

        # Get job status
        status = queue_mgr.get_job_status(job.id)
    """

    def __init__(self):
        """Initialize queue manager (call initialize() to connect)."""
        self._redis: Optional[Redis] = None
        self._queue: Optional[Queue] = None
        self._initialized = False

    def initialize(self) -> None:
        """
        Initialize Redis connection and queue.

        Raises:
            ConnectionError: If Redis connection fails
        """
        if self._initialized:
            logger.warning("Queue manager already initialized")
            return

        try:
            # Create Redis connection
            self._redis = Redis(
                host=Config.REDIS_HOST,
                port=Config.REDIS_PORT,
                db=Config.REDIS_DB,
                decode_responses=False,  # RQ needs bytes mode
                socket_connect_timeout=10,
                socket_timeout=10,
                retry_on_timeout=True,
            )

            # Test connection
            self._redis.ping()

            # Create RQ queue
            self._queue = Queue('renders', connection=self._redis)

            self._initialized = True
            logger.info(
                "Queue manager initialized",
                extra={
                    "redis_host": Config.REDIS_HOST,
                    "redis_port": Config.REDIS_PORT,
                    "queue": "renders",
                },
            )
        except Exception as e:
            logger.error(
                "Failed to initialize queue manager",
                extra={"error": str(e), "redis_host": Config.REDIS_HOST},
            )
            raise

    def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            self._redis.close()
            self._initialized = False
            logger.info("Queue manager closed")

    def enqueue_render(
        self,
        render_id: str,
        asset_id: str,
        style_id: str,
        size_preset_id: str,
    ) -> Job:
        """
        Enqueue a render job for background processing.

        Args:
            render_id: UUID of the render record
            asset_id: UUID of the source asset
            style_id: UUID of the rendering style
            size_preset_id: UUID of the output size preset

        Returns:
            RQ Job object

        Raises:
            RuntimeError: If queue not initialized
            Exception: If job enqueueing fails
        """
        if not self._initialized or not self._queue:
            raise RuntimeError("Queue manager not initialized. Call initialize() first.")

        try:
            # Import here to avoid circular dependency
            from pipelines import process_render

            # Enqueue job with metadata
            job = self._queue.enqueue(
                process_render,
                render_id=render_id,
                asset_id=asset_id,
                style_id=style_id,
                size_preset_id=size_preset_id,
                job_timeout='10m',  # 10 minute timeout for render jobs
                result_ttl=86400,  # Keep results for 24 hours
                failure_ttl=604800,  # Keep failures for 7 days
            )

            logger.info(
                "Render job enqueued",
                extra={
                    "job_id": job.id,
                    "render_id": render_id,
                    "asset_id": asset_id,
                    "style_id": style_id,
                    "size_preset_id": size_preset_id,
                },
            )
            return job
        except Exception as e:
            logger.error(
                "Failed to enqueue render job",
                extra={
                    "error": str(e),
                    "render_id": render_id,
                },
            )
            raise

    def get_job(self, job_id: str) -> Optional[Job]:
        """
        Get a job by ID.

        Args:
            job_id: RQ job ID

        Returns:
            Job object or None if not found

        Raises:
            RuntimeError: If queue not initialized
        """
        if not self._initialized or not self._redis:
            raise RuntimeError("Queue manager not initialized. Call initialize() first.")

        try:
            return Job.fetch(job_id, connection=self._redis)
        except Exception as e:
            logger.debug(
                "Failed to fetch job",
                extra={"error": str(e), "job_id": job_id},
            )
            return None

    def get_job_status(self, job_id: str) -> Optional[str]:
        """
        Get the status of a job.

        Args:
            job_id: RQ job ID

        Returns:
            Job status ('queued', 'started', 'finished', 'failed') or None

        Raises:
            RuntimeError: If queue not initialized
        """
        job = self.get_job(job_id)
        if job:
            return job.get_status()
        return None

    def health_check(self) -> bool:
        """
        Check Redis connectivity and queue health.

        Returns:
            True if queue is healthy, False otherwise
        """
        if not self._initialized or not self._redis:
            logger.warning("Queue manager not initialized for health check")
            return False

        try:
            # Test Redis connection
            self._redis.ping()
            return True
        except Exception as e:
            logger.error("Queue health check failed", extra={"error": str(e)})
            return False


# Global queue manager instance
queue_manager = QueueManager()


def get_queue_manager() -> QueueManager:
    """
    Get the global queue manager instance.

    Returns:
        QueueManager instance
    """
    return queue_manager

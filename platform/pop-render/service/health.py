"""
Health check endpoint for ASO Render Service.

Provides comprehensive health monitoring with dependency checks for PostgreSQL,
Redis, and MinIO storage. Returns detailed status information for observability.
"""

import logging
from datetime import datetime
from typing import Dict, Any
import time
import redis
from flask import jsonify, Response

from database import get_db_pool
from storage import get_storage_client
from config import Config
from metrics import update_health_status

logger = logging.getLogger(__name__)

# Track service start time for uptime calculation
_service_start_time = time.time()


def check_database() -> Dict[str, Any]:
    """
    Check PostgreSQL database connectivity and health.

    Returns:
        Health check result with status and latency
    """
    db_pool = get_db_pool()
    start_time = time.time()

    try:
        is_healthy = db_pool.health_check()
        latency_ms = int((time.time() - start_time) * 1000)

        result = {
            "status": "healthy" if is_healthy else "unhealthy",
            "latency_ms": latency_ms,
        }

        if not is_healthy:
            result["error"] = "Database connection test failed"

        update_health_status("database", is_healthy)
        return result

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        logger.error("Database health check failed", extra={"error": str(e)})
        update_health_status("database", False)
        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "error": str(e),
        }


def check_redis() -> Dict[str, Any]:
    """
    Check Redis connectivity and health.

    Returns:
        Health check result with status and latency
    """
    start_time = time.time()

    try:
        # Create Redis client
        redis_client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            db=Config.REDIS_DB,
            socket_connect_timeout=5,
            socket_timeout=5,
        )

        # Test connection with PING
        response = redis_client.ping()
        latency_ms = int((time.time() - start_time) * 1000)

        is_healthy = response is True

        result = {
            "status": "healthy" if is_healthy else "unhealthy",
            "latency_ms": latency_ms,
        }

        update_health_status("redis", is_healthy)
        return result

    except redis.RedisError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        logger.error("Redis health check failed", extra={"error": str(e)})
        update_health_status("redis", False)
        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "error": str(e),
        }
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        logger.error("Redis health check failed", extra={"error": str(e)})
        update_health_status("redis", False)
        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "error": str(e),
        }


def check_storage() -> Dict[str, Any]:
    """
    Check MinIO/S3 storage connectivity and health.

    Returns:
        Health check result with status and latency
    """
    storage_client = get_storage_client()
    start_time = time.time()

    try:
        is_healthy = storage_client.health_check()
        latency_ms = int((time.time() - start_time) * 1000)

        result = {
            "status": "healthy" if is_healthy else "unhealthy",
            "latency_ms": latency_ms,
        }

        if not is_healthy:
            result["error"] = "Storage connection test failed"

        update_health_status("storage", is_healthy)
        return result

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        logger.error("Storage health check failed", extra={"error": str(e)})
        update_health_status("storage", False)
        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "error": str(e),
        }


def health_check() -> Dict[str, Any]:
    """
    Perform comprehensive health check of all dependencies.

    Returns:
        Health check results for all components
    """
    # Run all health checks
    checks = {
        "database": check_database(),
        "redis": check_redis(),
        "storage": check_storage(),
    }

    # Determine overall health
    all_healthy = all(
        check["status"] == "healthy"
        for check in checks.values()
    )

    # Calculate uptime
    uptime_seconds = int(time.time() - _service_start_time)

    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "service": "pop-render",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "uptime_seconds": uptime_seconds,
        "checks": checks,
    }


def health_endpoint() -> Response:
    """
    Flask health check endpoint handler.

    Returns 200 OK if all dependencies are healthy, 503 Service Unavailable otherwise.

    Returns:
        Flask Response with health check JSON
    """
    result = health_check()
    status_code = 200 if result["status"] == "healthy" else 503

    logger.debug(
        "Health check performed",
        extra={
            "status": result["status"],
            "checks": {
                name: check["status"]
                for name, check in result["checks"].items()
            },
        },
    )

    return jsonify(result), status_code


def readiness_check() -> Dict[str, Any]:
    """
    Perform readiness check (can service handle requests?).

    This is a lighter check than full health - just verifies critical dependencies.

    Returns:
        Readiness check result
    """
    # Only check database for readiness (most critical)
    db_check = check_database()
    is_ready = db_check["status"] == "healthy"

    return {
        "status": "ready" if is_ready else "not_ready",
        "service": "pop-render",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "checks": {
            "database": db_check,
        },
    }


def readiness_endpoint() -> Response:
    """
    Flask readiness check endpoint handler.

    Returns:
        Flask Response with readiness check JSON
    """
    result = readiness_check()
    status_code = 200 if result["status"] == "ready" else 503
    return jsonify(result), status_code


def liveness_check() -> Dict[str, Any]:
    """
    Perform liveness check (is service alive?).

    This is the lightest check - just confirms the service is running.

    Returns:
        Liveness check result
    """
    uptime_seconds = int(time.time() - _service_start_time)

    return {
        "status": "alive",
        "service": "pop-render",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "uptime_seconds": uptime_seconds,
    }


def liveness_endpoint() -> Response:
    """
    Flask liveness check endpoint handler.

    Returns:
        Flask Response with liveness check JSON
    """
    result = liveness_check()
    return jsonify(result), 200

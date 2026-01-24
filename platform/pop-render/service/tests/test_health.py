"""
Tests for health check endpoints.

Tests the health, readiness, and liveness endpoints with mocked dependencies.
"""

import pytest
import sys
from unittest.mock import Mock, patch, MagicMock

# Add service directory to path
sys.path.insert(0, '/home/agent/workspaces/3cc47d96-a71e-42bc-918f-a1566ebef2df/platform/pop-render/service')


@pytest.fixture
def mock_db_pool():
    """Mock database pool."""
    with patch('health.get_db_pool') as mock:
        pool = Mock()
        pool.health_check.return_value = True
        mock.return_value = pool
        yield pool


@pytest.fixture
def mock_storage_client():
    """Mock storage client."""
    with patch('health.get_storage_client') as mock:
        client = Mock()
        client.health_check.return_value = True
        mock.return_value = client
        yield client


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    with patch('health.redis.Redis') as mock:
        redis_client = Mock()
        redis_client.ping.return_value = True
        mock.return_value = redis_client
        yield redis_client


@pytest.fixture
def mock_metrics():
    """Mock metrics updates."""
    with patch('health.update_health_status') as mock:
        yield mock


def test_check_database_healthy(mock_db_pool, mock_metrics):
    """Test database health check when healthy."""
    from health import check_database

    result = check_database()

    assert result["status"] == "healthy"
    assert "latency_ms" in result
    assert result["latency_ms"] >= 0
    mock_db_pool.health_check.assert_called_once()
    mock_metrics.assert_called_with("database", True)


def test_check_database_unhealthy(mock_db_pool, mock_metrics):
    """Test database health check when unhealthy."""
    from health import check_database

    mock_db_pool.health_check.return_value = False

    result = check_database()

    assert result["status"] == "unhealthy"
    assert "error" in result
    mock_metrics.assert_called_with("database", False)


def test_check_database_exception(mock_db_pool, mock_metrics):
    """Test database health check when exception occurs."""
    from health import check_database

    mock_db_pool.health_check.side_effect = Exception("Connection failed")

    result = check_database()

    assert result["status"] == "unhealthy"
    assert "error" in result
    assert "Connection failed" in result["error"]
    mock_metrics.assert_called_with("database", False)


def test_check_redis_healthy(mock_redis, mock_metrics):
    """Test Redis health check when healthy."""
    from health import check_redis

    result = check_redis()

    assert result["status"] == "healthy"
    assert "latency_ms" in result
    assert result["latency_ms"] >= 0
    mock_redis.ping.assert_called_once()
    mock_metrics.assert_called_with("redis", True)


def test_check_redis_unhealthy(mock_redis, mock_metrics):
    """Test Redis health check when connection fails."""
    from health import check_redis
    import redis as redis_module

    mock_redis.ping.side_effect = redis_module.RedisError("Connection refused")

    result = check_redis()

    assert result["status"] == "unhealthy"
    assert "error" in result
    mock_metrics.assert_called_with("redis", False)


def test_check_storage_healthy(mock_storage_client, mock_metrics):
    """Test storage health check when healthy."""
    from health import check_storage

    result = check_storage()

    assert result["status"] == "healthy"
    assert "latency_ms" in result
    mock_storage_client.health_check.assert_called_once()
    mock_metrics.assert_called_with("storage", True)


def test_check_storage_unhealthy(mock_storage_client, mock_metrics):
    """Test storage health check when unhealthy."""
    from health import check_storage

    mock_storage_client.health_check.return_value = False

    result = check_storage()

    assert result["status"] == "unhealthy"
    assert "error" in result
    mock_metrics.assert_called_with("storage", False)


def test_health_check_all_healthy(mock_db_pool, mock_redis, mock_storage_client, mock_metrics):
    """Test comprehensive health check when all dependencies healthy."""
    from health import health_check

    result = health_check()

    assert result["status"] == "healthy"
    assert result["service"] == "pop-render"
    assert "timestamp" in result
    assert "uptime_seconds" in result
    assert result["uptime_seconds"] >= 0
    assert "checks" in result
    assert result["checks"]["database"]["status"] == "healthy"
    assert result["checks"]["redis"]["status"] == "healthy"
    assert result["checks"]["storage"]["status"] == "healthy"


def test_health_check_database_unhealthy(mock_db_pool, mock_redis, mock_storage_client, mock_metrics):
    """Test comprehensive health check when database unhealthy."""
    from health import health_check

    mock_db_pool.health_check.return_value = False

    result = health_check()

    assert result["status"] == "unhealthy"
    assert result["checks"]["database"]["status"] == "unhealthy"


def test_health_check_partial_failure(mock_db_pool, mock_redis, mock_storage_client, mock_metrics):
    """Test comprehensive health check with partial dependency failure."""
    from health import health_check
    import redis as redis_module

    mock_redis.ping.side_effect = redis_module.RedisError("Connection failed")

    result = health_check()

    assert result["status"] == "unhealthy"
    assert result["checks"]["database"]["status"] == "healthy"
    assert result["checks"]["redis"]["status"] == "unhealthy"
    assert result["checks"]["storage"]["status"] == "healthy"


def test_liveness_check():
    """Test liveness check always returns alive."""
    from health import liveness_check

    result = liveness_check()

    assert result["status"] == "alive"
    assert result["service"] == "pop-render"
    assert "timestamp" in result
    assert "uptime_seconds" in result


def test_readiness_check_ready(mock_db_pool, mock_metrics):
    """Test readiness check when database is ready."""
    from health import readiness_check

    result = readiness_check()

    assert result["status"] == "ready"
    assert result["checks"]["database"]["status"] == "healthy"


def test_readiness_check_not_ready(mock_db_pool, mock_metrics):
    """Test readiness check when database is not ready."""
    from health import readiness_check

    mock_db_pool.health_check.return_value = False

    result = readiness_check()

    assert result["status"] == "not_ready"
    assert result["checks"]["database"]["status"] == "unhealthy"

"""
Tests for configuration management.

Tests environment variable loading, validation, and configuration utilities.
"""

import pytest
import sys
import os
from unittest.mock import patch

# Add service directory to path
sys.path.insert(0, '/home/agent/workspaces/3cc47d96-a71e-42bc-918f-a1566ebef2df/platform/pop-render/service')


@pytest.fixture
def clean_env():
    """Clean environment for testing."""
    # Store original env
    original_env = os.environ.copy()

    # Clear relevant env vars
    keys_to_remove = [
        'DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD',
        'REDIS_HOST', 'REDIS_PORT', 'REDIS_DB',
        'MINIO_ENDPOINT', 'MINIO_ACCESS_KEY', 'MINIO_SECRET_KEY', 'MINIO_BUCKET',
        'API_PORT', 'WORKER_COUNT', 'LOG_LEVEL',
    ]
    for key in keys_to_remove:
        os.environ.pop(key, None)

    yield

    # Restore original env
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def valid_env():
    """Set up valid environment variables."""
    os.environ['DB_HOST'] = 'localhost'
    os.environ['DB_PORT'] = '5432'
    os.environ['DB_NAME'] = 'test_db'
    os.environ['DB_USER'] = 'test_user'
    os.environ['DB_PASSWORD'] = 'test_pass'
    os.environ['REDIS_HOST'] = 'localhost'
    os.environ['REDIS_PORT'] = '6379'
    os.environ['REDIS_DB'] = '0'
    os.environ['MINIO_ENDPOINT'] = 'http://localhost:9000'
    os.environ['MINIO_ACCESS_KEY'] = 'test_access'
    os.environ['MINIO_SECRET_KEY'] = 'test_secret'
    os.environ['MINIO_BUCKET'] = 'test-bucket'
    os.environ['API_PORT'] = '8089'
    os.environ['WORKER_COUNT'] = '2'
    os.environ['LOG_LEVEL'] = 'INFO'


def test_config_defaults(clean_env):
    """Test default configuration values."""
    # Need to reload config module to pick up env changes
    import importlib
    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])

    from config import Config

    assert Config.DB_HOST == 'localhost'
    assert Config.DB_PORT == 5432
    assert Config.DB_NAME == 'aso_render'
    assert Config.DB_USER == 'postgres'
    assert Config.REDIS_HOST == 'localhost'
    assert Config.REDIS_PORT == 6379
    assert Config.REDIS_DB == 0
    assert Config.MINIO_BUCKET == 'render-assets'
    assert Config.API_PORT == 8089
    assert Config.WORKER_COUNT == 2
    assert Config.LOG_LEVEL == 'INFO'


def test_config_from_env(clean_env, valid_env):
    """Test loading configuration from environment variables."""
    import importlib
    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])

    from config import Config

    assert Config.DB_HOST == 'localhost'
    assert Config.DB_PORT == 5432
    assert Config.DB_NAME == 'test_db'
    assert Config.DB_USER == 'test_user'
    assert Config.DB_PASSWORD == 'test_pass'
    assert Config.REDIS_HOST == 'localhost'
    assert Config.REDIS_PORT == 6379
    assert Config.REDIS_DB == 0
    assert Config.MINIO_ENDPOINT == 'http://localhost:9000'
    assert Config.MINIO_ACCESS_KEY == 'test_access'
    assert Config.MINIO_SECRET_KEY == 'test_secret'
    assert Config.MINIO_BUCKET == 'test-bucket'
    assert Config.API_PORT == 8089
    assert Config.WORKER_COUNT == 2
    assert Config.LOG_LEVEL == 'INFO'


def test_config_validation_success(clean_env, valid_env):
    """Test configuration validation with valid values."""
    import importlib
    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])

    from config import Config

    # Should not raise
    Config.validate()


def test_config_validation_missing_db_password(clean_env, valid_env):
    """Test validation fails when DB_PASSWORD is missing."""
    os.environ.pop('DB_PASSWORD')

    import importlib
    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])

    from config import Config

    with pytest.raises(ValueError) as exc_info:
        Config.validate()

    assert 'DB_PASSWORD is required' in str(exc_info.value)


def test_config_validation_missing_minio_endpoint(clean_env, valid_env):
    """Test validation fails when MINIO_ENDPOINT is missing."""
    os.environ.pop('MINIO_ENDPOINT')

    import importlib
    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])

    from config import Config

    with pytest.raises(ValueError) as exc_info:
        Config.validate()

    assert 'MINIO_ENDPOINT is required' in str(exc_info.value)


def test_config_validation_missing_minio_credentials(clean_env, valid_env):
    """Test validation fails when MinIO credentials are missing."""
    os.environ.pop('MINIO_ACCESS_KEY')
    os.environ.pop('MINIO_SECRET_KEY')

    import importlib
    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])

    from config import Config

    with pytest.raises(ValueError) as exc_info:
        Config.validate()

    assert 'MINIO_ACCESS_KEY is required' in str(exc_info.value)
    assert 'MINIO_SECRET_KEY is required' in str(exc_info.value)


def test_config_validation_invalid_port(clean_env, valid_env):
    """Test validation fails with invalid port number."""
    os.environ['DB_PORT'] = '99999'

    import importlib
    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])

    from config import Config

    with pytest.raises(ValueError) as exc_info:
        Config.validate()

    assert 'DB_PORT must be between 1-65535' in str(exc_info.value)


def test_config_validation_invalid_log_level(clean_env, valid_env):
    """Test validation fails with invalid log level."""
    os.environ['LOG_LEVEL'] = 'INVALID'

    import importlib
    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])

    from config import Config

    with pytest.raises(ValueError) as exc_info:
        Config.validate()

    assert 'LOG_LEVEL must be one of' in str(exc_info.value)


def test_config_get_db_uri(clean_env, valid_env):
    """Test database URI generation."""
    import importlib
    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])

    from config import Config

    uri = Config.get_db_uri()

    assert uri == 'postgresql://test_user:test_pass@localhost:5432/test_db'


def test_config_get_redis_url(clean_env, valid_env):
    """Test Redis URL generation."""
    import importlib
    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])

    from config import Config

    url = Config.get_redis_url()

    assert url == 'redis://localhost:6379/0'


def test_config_to_dict_masks_secrets(clean_env, valid_env):
    """Test that to_dict masks sensitive values."""
    import importlib
    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])

    from config import Config

    config_dict = Config.to_dict()

    assert config_dict['db_password'] == '***'
    assert config_dict['minio_access_key'] == '***'
    assert config_dict['minio_secret_key'] == '***'
    assert config_dict['db_user'] == 'test_user'
    assert config_dict['db_host'] == 'localhost'
    assert config_dict['minio_endpoint'] == 'http://localhost:9000'


def test_config_numeric_parsing(clean_env):
    """Test numeric environment variable parsing."""
    os.environ['DB_PORT'] = '5433'
    os.environ['REDIS_PORT'] = '6380'
    os.environ['REDIS_DB'] = '5'
    os.environ['API_PORT'] = '8090'
    os.environ['WORKER_COUNT'] = '4'
    os.environ['DB_PASSWORD'] = 'pass'
    os.environ['MINIO_ENDPOINT'] = 'http://minio:9000'
    os.environ['MINIO_ACCESS_KEY'] = 'key'
    os.environ['MINIO_SECRET_KEY'] = 'secret'

    import importlib
    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])

    from config import Config

    assert Config.DB_PORT == 5433
    assert Config.REDIS_PORT == 6380
    assert Config.REDIS_DB == 5
    assert Config.API_PORT == 8090
    assert Config.WORKER_COUNT == 4


def test_config_log_level_case_insensitive(clean_env, valid_env):
    """Test that log level is converted to uppercase."""
    os.environ['LOG_LEVEL'] = 'debug'

    import importlib
    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])

    from config import Config

    assert Config.LOG_LEVEL == 'DEBUG'

"""
Configuration management for ASO Render Service.

Loads and validates environment variables for database, storage, and service configuration.
Follows ASO pattern with enterprise-grade validation and defaults.
"""

import os
from typing import Optional


class Config:
    """
    Central configuration for ASO Render Service.

    Environment Variables:
        Database:
            DB_HOST: PostgreSQL host (default: localhost)
            DB_PORT: PostgreSQL port (default: 5432)
            DB_NAME: Database name (default: aso_render)
            DB_USER: Database user (default: postgres)
            DB_PASSWORD: Database password (required)

        Redis:
            REDIS_HOST: Redis host (default: localhost)
            REDIS_PORT: Redis port (default: 6379)
            REDIS_DB: Redis database number (default: 0)

        MinIO/S3:
            MINIO_ENDPOINT: MinIO endpoint URL (required)
            MINIO_ACCESS_KEY: MinIO access key (required)
            MINIO_SECRET_KEY: MinIO secret key (required)
            MINIO_BUCKET: Bucket name (default: render-assets)

        Service:
            API_PORT: Flask API port (default: 8089)
            WORKER_COUNT: Gunicorn worker count (default: 2)
            LOG_LEVEL: Logging level (default: INFO)
    """

    # Database Configuration
    DB_HOST: str = os.environ.get("DB_HOST", "localhost")
    DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
    DB_NAME: str = os.environ.get("DB_NAME", "aso_render")
    DB_USER: str = os.environ.get("DB_USER", "postgres")
    DB_PASSWORD: str = os.environ.get("DB_PASSWORD", "")

    # Redis Configuration
    REDIS_HOST: str = os.environ.get("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.environ.get("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.environ.get("REDIS_DB", "0"))

    # MinIO/S3 Configuration
    MINIO_ENDPOINT: str = os.environ.get("MINIO_ENDPOINT", "")
    MINIO_ACCESS_KEY: str = os.environ.get("MINIO_ACCESS_KEY", "")
    MINIO_SECRET_KEY: str = os.environ.get("MINIO_SECRET_KEY", "")
    MINIO_BUCKET: str = os.environ.get("MINIO_BUCKET", "render-assets")

    # Service Configuration
    API_PORT: int = int(os.environ.get("API_PORT", "8089"))
    WORKER_COUNT: int = int(os.environ.get("WORKER_COUNT", "2"))
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls) -> None:
        """
        Validate required configuration values.

        Raises:
            ValueError: If required configuration is missing
        """
        errors = []

        # Check required database config
        if not cls.DB_PASSWORD:
            errors.append("DB_PASSWORD is required")

        # Check required MinIO config
        if not cls.MINIO_ENDPOINT:
            errors.append("MINIO_ENDPOINT is required")
        if not cls.MINIO_ACCESS_KEY:
            errors.append("MINIO_ACCESS_KEY is required")
        if not cls.MINIO_SECRET_KEY:
            errors.append("MINIO_SECRET_KEY is required")

        # Validate numeric ranges
        if cls.DB_PORT <= 0 or cls.DB_PORT > 65535:
            errors.append(f"DB_PORT must be between 1-65535, got {cls.DB_PORT}")
        if cls.REDIS_PORT <= 0 or cls.REDIS_PORT > 65535:
            errors.append(f"REDIS_PORT must be between 1-65535, got {cls.REDIS_PORT}")
        if cls.API_PORT <= 0 or cls.API_PORT > 65535:
            errors.append(f"API_PORT must be between 1-65535, got {cls.API_PORT}")
        if cls.WORKER_COUNT <= 0:
            errors.append(f"WORKER_COUNT must be positive, got {cls.WORKER_COUNT}")

        # Validate log level
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if cls.LOG_LEVEL not in valid_levels:
            errors.append(f"LOG_LEVEL must be one of {valid_levels}, got {cls.LOG_LEVEL}")

        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")

    @classmethod
    def get_db_uri(cls) -> str:
        """
        Get PostgreSQL connection URI.

        Returns:
            Database connection string
        """
        return f"postgresql://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"

    @classmethod
    def get_redis_url(cls) -> str:
        """
        Get Redis connection URL.

        Returns:
            Redis connection string
        """
        return f"redis://{cls.REDIS_HOST}:{cls.REDIS_PORT}/{cls.REDIS_DB}"

    @classmethod
    def to_dict(cls) -> dict:
        """
        Export configuration as dictionary (safe for logging).

        Returns:
            Configuration dictionary with secrets masked
        """
        return {
            "db_host": cls.DB_HOST,
            "db_port": cls.DB_PORT,
            "db_name": cls.DB_NAME,
            "db_user": cls.DB_USER,
            "db_password": "***" if cls.DB_PASSWORD else "",
            "redis_host": cls.REDIS_HOST,
            "redis_port": cls.REDIS_PORT,
            "redis_db": cls.REDIS_DB,
            "minio_endpoint": cls.MINIO_ENDPOINT,
            "minio_access_key": "***" if cls.MINIO_ACCESS_KEY else "",
            "minio_secret_key": "***" if cls.MINIO_SECRET_KEY else "",
            "minio_bucket": cls.MINIO_BUCKET,
            "api_port": cls.API_PORT,
            "worker_count": cls.WORKER_COUNT,
            "log_level": cls.LOG_LEVEL,
        }

"""
Configuration utilities for ASO services.
"""

import os
from typing import Optional, Any, Dict
from pathlib import Path


def get_env(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """
    Get environment variable with optional default.

    Args:
        key: Environment variable name
        default: Default value if not set
        required: Raise error if not set and no default

    Returns:
        Environment variable value

    Raises:
        ValueError: If required and not set
    """
    value = os.environ.get(key, default)
    if required and value is None:
        raise ValueError(f"Required environment variable {key} is not set")
    return value


def load_config(env_file: Optional[str] = None) -> Dict[str, str]:
    """
    Load configuration from environment file.

    Args:
        env_file: Path to .env file (optional)

    Returns:
        Dictionary of configuration values
    """
    config = {}

    # Load from file if specified
    if env_file:
        env_path = Path(env_file)
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        config[key.strip()] = value.strip().strip('"').strip("'")

    # Environment variables override file
    for key in config:
        if key in os.environ:
            config[key] = os.environ[key]

    return config


class Config:
    """Configuration class with typed access."""

    def __init__(self, prefix: str = ""):
        self.prefix = prefix
        self._cache: Dict[str, Any] = {}

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get string config value."""
        full_key = f"{self.prefix}{key}" if self.prefix else key
        return os.environ.get(full_key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        """Get integer config value."""
        value = self.get(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get boolean config value."""
        value = self.get(key)
        if value is None:
            return default
        return value.lower() in ("true", "1", "yes", "on")

    def get_list(self, key: str, default: Optional[list] = None, sep: str = ",") -> list:
        """Get list config value."""
        value = self.get(key)
        if value is None:
            return default or []
        return [item.strip() for item in value.split(sep)]

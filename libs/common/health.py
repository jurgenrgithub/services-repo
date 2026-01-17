"""
Health check utilities for ASO services.
"""

import time
from datetime import datetime
from typing import Callable, Dict, Optional, Any
from dataclasses import dataclass, field


@dataclass
class HealthCheck:
    """
    Health check manager for a service.

    Usage:
        health = HealthCheck("my-service")

        # Add dependency checks
        health.add_check("database", check_database)
        health.add_check("redis", check_redis)

        # Get health status
        status = health.check()
    """

    service_name: str
    checks: Dict[str, Callable[[], bool]] = field(default_factory=dict)
    _start_time: float = field(default_factory=time.time)

    def add_check(self, name: str, check_fn: Callable[[], bool]) -> None:
        """Add a health check function."""
        self.checks[name] = check_fn

    def check(self) -> Dict[str, Any]:
        """
        Run all health checks and return status.

        Returns:
            Health status dictionary
        """
        results = {}
        all_healthy = True

        for name, check_fn in self.checks.items():
            try:
                start = time.time()
                healthy = check_fn()
                latency_ms = int((time.time() - start) * 1000)
                results[name] = {
                    "status": "healthy" if healthy else "unhealthy",
                    "latency_ms": latency_ms,
                }
                if not healthy:
                    all_healthy = False
            except Exception as e:
                results[name] = {
                    "status": "unhealthy",
                    "error": str(e),
                }
                all_healthy = False

        uptime_seconds = int(time.time() - self._start_time)

        return {
            "status": "healthy" if all_healthy else "unhealthy",
            "service": self.service_name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "uptime_seconds": uptime_seconds,
            "checks": results,
        }

    def is_healthy(self) -> bool:
        """Quick check if service is healthy."""
        return self.check()["status"] == "healthy"


def create_health_endpoint(health: HealthCheck):
    """
    Create a Flask health endpoint.

    Usage:
        from flask import Flask
        app = Flask(__name__)

        health = HealthCheck("my-service")
        app.route("/health")(create_health_endpoint(health))
    """
    def health_endpoint():
        from flask import jsonify
        result = health.check()
        status_code = 200 if result["status"] == "healthy" else 503
        return jsonify(result), status_code

    return health_endpoint

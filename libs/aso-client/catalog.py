"""
Catalog Client - Service discovery and registration.
"""

import requests
from typing import Optional, List, Dict, Any


class CatalogClient:
    """Client for ASO Catalog API."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def health(self) -> dict:
        """Check catalog health."""
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=5)
            return resp.json()
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def list_services(
        self,
        service_type: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[dict]:
        """
        List services from the catalog.

        Args:
            service_type: Filter by type (platform, infrastructure, application)
            status: Filter by status (active, provisioning, deprecated, inactive)
            search: Search in name and description

        Returns:
            List of service records
        """
        params = {}
        if service_type:
            params["type"] = service_type
        if status:
            params["status"] = status
        if search:
            params["search"] = search

        resp = requests.get(f"{self.base_url}/services", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_service(self, name: str) -> dict:
        """Get a specific service by name."""
        resp = requests.get(f"{self.base_url}/services/{name}", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def register_service(self, service: Dict[str, Any]) -> dict:
        """
        Register a new service in the catalog.

        Args:
            service: Service definition with name, type, description, etc.

        Returns:
            Created service record
        """
        resp = requests.post(f"{self.base_url}/services", json=service, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def update_service(self, name: str, updates: Dict[str, Any]) -> dict:
        """Update an existing service."""
        resp = requests.put(f"{self.base_url}/services/{name}", json=updates, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_dependencies(self, name: str) -> List[dict]:
        """Get all dependencies for a service (recursive)."""
        resp = requests.get(f"{self.base_url}/services/{name}/dependencies", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_dependency_graph(self) -> List[dict]:
        """Get the full dependency graph."""
        resp = requests.get(f"{self.base_url}/graph/dependencies", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def record_health(self, name: str, status: str, latency_ms: Optional[int] = None) -> dict:
        """Record a health check result for a service."""
        data = {"status": status}
        if latency_ms is not None:
            data["latency_ms"] = latency_ms

        resp = requests.post(f"{self.base_url}/services/{name}/health", json=data, timeout=10)
        resp.raise_for_status()
        return resp.json()

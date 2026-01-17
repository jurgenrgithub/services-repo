"""
Dispatcher Client - Submit and manage jobs.
"""

import requests
from typing import Optional, Dict, Any, List


class DispatcherClient:
    """Client for ASO Dispatcher service."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def health(self) -> dict:
        """Check dispatcher health."""
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=5)
            return resp.json()
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def submit_job(
        self,
        job_type: str,
        payload: Dict[str, Any],
        priority: int = 5,
        correlation_id: Optional[str] = None,
    ) -> str:
        """
        Submit a new job to the dispatcher.

        Args:
            job_type: Type of job (e.g., "transcribe", "merge")
            payload: Job-specific data
            priority: Job priority (1-10, lower is higher priority)
            correlation_id: Optional correlation ID for tracing

        Returns:
            Job ID
        """
        data = {
            "type": job_type,
            "payload": payload,
            "priority": priority,
        }
        if correlation_id:
            data["correlation_id"] = correlation_id

        resp = requests.post(f"{self.base_url}/jobs", json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()["job_id"]

    def get_job(self, job_id: str) -> dict:
        """Get job status and details."""
        resp = requests.get(f"{self.base_url}/jobs/{job_id}", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def list_jobs(
        self,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        """List jobs with optional filters."""
        params = {"limit": limit}
        if status:
            params["status"] = status
        if job_type:
            params["type"] = job_type

        resp = requests.get(f"{self.base_url}/jobs", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def cancel_job(self, job_id: str) -> dict:
        """Cancel a pending or running job."""
        resp = requests.delete(f"{self.base_url}/jobs/{job_id}", timeout=10)
        resp.raise_for_status()
        return resp.json()

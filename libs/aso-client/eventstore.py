"""
EventStore Client - Event sourcing and audit trail.
"""

import json
import uuid
import requests
from datetime import datetime
from typing import Optional, Dict, Any, List


class EventStoreClient:
    """Client for EventStoreDB."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def health(self) -> dict:
        """Check eventstore health."""
        try:
            resp = requests.get(f"{self.base_url}/health/live", timeout=5)
            if resp.status_code == 204:
                return {"status": "healthy"}
            return {"status": "unhealthy", "code": resp.status_code}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def emit(
        self,
        event_type: str,
        data: Dict[str, Any],
        stream: Optional[str] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> str:
        """
        Emit an event to EventStore.

        Args:
            event_type: Type of event (e.g., "job.submitted", "transcription.completed")
            data: Event payload
            stream: Stream name (defaults to event type prefix)
            correlation_id: Correlation ID for distributed tracing
            causation_id: ID of the event that caused this one

        Returns:
            Event ID
        """
        if stream is None:
            # Default stream from event type prefix
            stream = event_type.split(".")[0]

        event_id = str(uuid.uuid4())
        metadata = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_id": event_id,
        }
        if correlation_id:
            metadata["$correlationId"] = correlation_id
        if causation_id:
            metadata["$causationId"] = causation_id

        event = {
            "eventId": event_id,
            "eventType": event_type,
            "data": data,
            "metadata": metadata,
        }

        headers = {
            "Content-Type": "application/json",
            "ES-EventType": event_type,
            "ES-EventId": event_id,
        }

        resp = requests.post(
            f"{self.base_url}/streams/{stream}",
            json=[event],
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        return event_id

    def read_stream(
        self,
        stream: str,
        start: int = 0,
        count: int = 100,
        direction: str = "forward",
    ) -> List[dict]:
        """
        Read events from a stream.

        Args:
            stream: Stream name
            start: Starting position
            count: Number of events to read
            direction: "forward" or "backward"

        Returns:
            List of events
        """
        headers = {"Accept": "application/json"}
        url = f"{self.base_url}/streams/{stream}/{start}/{direction}/{count}"

        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()

        result = resp.json()
        return result.get("entries", [])

    def read_all(self, count: int = 100, position: Optional[str] = None) -> List[dict]:
        """Read from the $all stream."""
        headers = {"Accept": "application/json"}
        url = f"{self.base_url}/streams/$all"
        params = {"count": count}
        if position:
            params["position"] = position

        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()

        result = resp.json()
        return result.get("entries", [])

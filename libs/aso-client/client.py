"""
ASO Platform Client - Main entry point for ASO services.
"""

import os
from typing import Optional
from .dispatcher import DispatcherClient
from .catalog import CatalogClient
from .eventstore import EventStoreClient


class ASOClient:
    """
    Main client for interacting with ASO platform services.

    Usage:
        client = ASOClient()

        # Submit a job
        job_id = client.dispatcher.submit_job("transcribe", {"file": "audio.mp3"})

        # Query the catalog
        services = client.catalog.list_services(type="application")

        # Emit an event
        client.eventstore.emit("job.completed", {"job_id": job_id})
    """

    def __init__(
        self,
        dispatcher_url: Optional[str] = None,
        catalog_url: Optional[str] = None,
        eventstore_url: Optional[str] = None,
    ):
        """
        Initialize ASO client with service URLs.

        URLs default to environment variables or standard local addresses.
        """
        self._dispatcher_url = dispatcher_url or os.environ.get(
            "ASO_DISPATCHER_URL", "http://aso-local-dispatcher:8080"
        )
        self._catalog_url = catalog_url or os.environ.get(
            "ASO_CATALOG_URL", "http://aso-local-catalog:8085"
        )
        self._eventstore_url = eventstore_url or os.environ.get(
            "ASO_EVENTSTORE_URL", "http://aso-local-eventstore:2113"
        )

        self._dispatcher: Optional[DispatcherClient] = None
        self._catalog: Optional[CatalogClient] = None
        self._eventstore: Optional[EventStoreClient] = None

    @property
    def dispatcher(self) -> DispatcherClient:
        """Get dispatcher client (lazy initialization)."""
        if self._dispatcher is None:
            self._dispatcher = DispatcherClient(self._dispatcher_url)
        return self._dispatcher

    @property
    def catalog(self) -> CatalogClient:
        """Get catalog client (lazy initialization)."""
        if self._catalog is None:
            self._catalog = CatalogClient(self._catalog_url)
        return self._catalog

    @property
    def eventstore(self) -> EventStoreClient:
        """Get eventstore client (lazy initialization)."""
        if self._eventstore is None:
            self._eventstore = EventStoreClient(self._eventstore_url)
        return self._eventstore

    def health_check(self) -> dict:
        """Check health of all ASO services."""
        return {
            "dispatcher": self.dispatcher.health(),
            "catalog": self.catalog.health(),
            "eventstore": self.eventstore.health(),
        }

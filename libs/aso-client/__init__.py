"""
ASO Platform Client SDK

Provides easy integration with ASO platform services.
"""

from .client import ASOClient
from .dispatcher import DispatcherClient
from .catalog import CatalogClient
from .eventstore import EventStoreClient

__version__ = "0.1.0"
__all__ = ["ASOClient", "DispatcherClient", "CatalogClient", "EventStoreClient"]

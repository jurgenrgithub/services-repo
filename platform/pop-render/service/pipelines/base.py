"""
Base abstract class for rendering pipelines.

Defines the interface that all rendering pipelines must implement,
ensuring consistency and enabling enterprise observability.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from PIL import Image
import logging

logger = logging.getLogger(__name__)


class RenderPipeline(ABC):
    """
    Abstract base class for all rendering pipelines.

    All pipelines must:
    - Be deterministic (same input -> same output)
    - Support parameter overrides via algorithm_config
    - Provide observability through logging
    - Handle errors gracefully with context

    Enterprise Requirements:
    - ROOT CAUSE: Standardized interface prevents inconsistent pipeline behavior
    - RECURRENCE PREVENTION: Type contracts enforced at compile time
    - OBSERVABILITY: Logging built into base class
    - SELF-HEALING: Parameter validation with safe defaults
    """

    def __init__(self, algorithm_config: Optional[Dict[str, Any]] = None):
        """
        Initialize the pipeline with optional configuration overrides.

        Args:
            algorithm_config: JSONB-compatible dict for parameter overrides
                            Each pipeline defines its own supported parameters
        """
        self.config = algorithm_config or {}
        self._validate_config()
        logger.info(
            f"Initialized {self.__class__.__name__} with config: {self.config}"
        )

    def _validate_config(self) -> None:
        """
        Validate algorithm_config contains only supported parameters.

        Override in subclasses to implement specific validation.
        Raises ValueError if config is invalid.
        """
        pass

    @abstractmethod
    def render(self, image: Image.Image) -> Image.Image:
        """
        Process the input image through the rendering pipeline.

        Args:
            image: PIL Image object to process

        Returns:
            Processed PIL Image object

        Raises:
            ValueError: If image is invalid or processing fails

        Implementation Requirements:
        - Must be deterministic (same input -> same output)
        - Should use self.config for parameter overrides
        - Must preserve image mode compatibility (convert if needed)
        - Should log processing steps for observability
        """
        pass

    def get_default_config(self) -> Dict[str, Any]:
        """
        Get the default configuration parameters for this pipeline.

        Returns:
            Dict of default parameter names and values
        """
        return {}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(config={self.config})"

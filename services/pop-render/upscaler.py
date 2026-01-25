"""
Enterprise Image Upscaler for ASO Pop-Render Service.

Provides tiered upscaling using OpenCV DNN Super-Resolution models.
Automatically selects the best approach based on scale factor.

Models used:
- ESPCN: Fast, good quality for 2-4x upscaling
- FSRCNN: Faster alternative, slightly lower quality
- LANCZOS: Fallback for small scales or when models unavailable
"""

import os
import logging
import math
from typing import Tuple, Optional
from PIL import Image
import numpy as np
import cv2

logger = logging.getLogger(__name__)

# Model paths - downloaded to /opt/pop-render/models/
MODEL_DIR = "/opt/pop-render/models"
MODELS = {
    "espcn": {
        2: "ESPCN_x2.pb",
        3: "ESPCN_x3.pb",
        4: "ESPCN_x4.pb",
    },
    "fsrcnn": {
        2: "FSRCNN_x2.pb",
        3: "FSRCNN_x3.pb",
        4: "FSRCNN_x4.pb",
    },
}


class Upscaler:
    """
    Enterprise-grade image upscaler with tiered quality levels.

    Automatically selects upscaling method based on:
    - Required scale factor
    - Available models
    - Performance requirements
    """

    def __init__(self, model_type: str = "espcn"):
        """
        Initialize upscaler with specified model type.

        Args:
            model_type: "espcn" (better quality) or "fsrcnn" (faster)
        """
        self.model_type = model_type
        self._sr_cache = {}  # Cache loaded models
        self._check_models()

    def _check_models(self) -> None:
        """Check which models are available."""
        self.available_scales = []
        if self.model_type in MODELS:
            for scale, filename in MODELS[self.model_type].items():
                path = os.path.join(MODEL_DIR, filename)
                if os.path.exists(path):
                    self.available_scales.append(scale)

        if self.available_scales:
            logger.info(f"Upscaler initialized with {self.model_type}, scales: {self.available_scales}")
        else:
            logger.warning(f"No upscale models found in {MODEL_DIR}, using LANCZOS fallback")

    def _get_sr_model(self, scale: int) -> Optional[cv2.dnn_superres.DnnSuperResImpl]:
        """Get or create super-resolution model for given scale."""
        if scale not in self.available_scales:
            return None

        cache_key = f"{self.model_type}_{scale}"
        if cache_key not in self._sr_cache:
            model_path = os.path.join(MODEL_DIR, MODELS[self.model_type][scale])
            sr = cv2.dnn_superres.DnnSuperResImpl_create()
            sr.readModel(model_path)
            sr.setModel(self.model_type, scale)
            self._sr_cache[cache_key] = sr
            logger.info(f"Loaded SR model: {model_path}")

        return self._sr_cache[cache_key]

    def calculate_scale_factor(
        self,
        input_size: Tuple[int, int],
        target_size: Tuple[int, int]
    ) -> float:
        """
        Calculate required scale factor.

        Args:
            input_size: (width, height) of input image
            target_size: (width, height) of desired output

        Returns:
            Scale factor (e.g., 2.5 means 2.5x upscale needed)
        """
        width_scale = target_size[0] / input_size[0]
        height_scale = target_size[1] / input_size[1]
        return max(width_scale, height_scale)

    def upscale(
        self,
        image: Image.Image,
        target_size: Tuple[int, int],
        min_scale_for_ai: float = 1.5
    ) -> Image.Image:
        """
        Upscale image to target size using best available method.

        Args:
            image: PIL Image to upscale
            target_size: (width, height) tuple for output
            min_scale_for_ai: Minimum scale factor to trigger AI upscaling

        Returns:
            Upscaled PIL Image
        """
        input_size = image.size
        scale_factor = self.calculate_scale_factor(input_size, target_size)

        logger.info(
            f"Upscaling from {input_size} to {target_size}, "
            f"scale factor: {scale_factor:.2f}"
        )

        # No upscaling needed
        if scale_factor <= 1.0:
            logger.info("No upscaling needed, returning original")
            return image

        # Small upscale - use LANCZOS
        if scale_factor < min_scale_for_ai or not self.available_scales:
            logger.info(f"Using LANCZOS for {scale_factor:.2f}x upscale")
            return image.resize(target_size, Image.Resampling.LANCZOS)

        # AI upscaling needed - may need multiple passes
        result = self._ai_upscale(image, scale_factor)

        # Final resize to exact target dimensions
        if result.size != target_size:
            result = result.resize(target_size, Image.Resampling.LANCZOS)

        return result

    def _ai_upscale(self, image: Image.Image, target_scale: float) -> Image.Image:
        """
        Apply AI upscaling, potentially in multiple passes.

        Args:
            image: PIL Image to upscale
            target_scale: Total scale factor needed

        Returns:
            Upscaled PIL Image
        """
        # Convert PIL to OpenCV format
        img_array = np.array(image)
        if len(img_array.shape) == 2:
            img_cv = cv2.cvtColor(img_array, cv2.COLOR_GRAY2BGR)
        elif img_array.shape[2] == 4:
            img_cv = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
        else:
            img_cv = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        current_scale = 1.0

        # Apply upscaling in passes until we reach target
        while current_scale < target_scale:
            # Find best available scale for this pass
            remaining = target_scale / current_scale

            # Choose largest available scale that doesn't overshoot too much
            best_scale = None
            for s in sorted(self.available_scales, reverse=True):
                if s <= remaining * 1.2:  # Allow 20% overshoot
                    best_scale = s
                    break

            if best_scale is None:
                best_scale = min(self.available_scales) if self.available_scales else None

            if best_scale is None:
                # No models available, finish with LANCZOS
                break

            sr = self._get_sr_model(best_scale)
            if sr is None:
                break

            logger.info(f"Applying {self.model_type} {best_scale}x upscale (current: {current_scale:.2f}x)")
            img_cv = sr.upsample(img_cv)
            current_scale *= best_scale

            # Safety check - don't go too far over target
            if current_scale >= target_scale:
                break

        # Convert back to PIL
        img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
        return Image.fromarray(img_rgb)


# Singleton instance
_upscaler: Optional[Upscaler] = None


def get_upscaler() -> Upscaler:
    """Get or create the global upscaler instance."""
    global _upscaler
    if _upscaler is None:
        _upscaler = Upscaler(model_type="espcn")
    return _upscaler


def upscale_image(
    image: Image.Image,
    target_size: Tuple[int, int]
) -> Image.Image:
    """
    Convenience function to upscale an image.

    Args:
        image: PIL Image to upscale
        target_size: (width, height) tuple

    Returns:
        Upscaled PIL Image
    """
    return get_upscaler().upscale(image, target_size)

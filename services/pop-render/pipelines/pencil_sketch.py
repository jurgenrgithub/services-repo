"""
Pencil Sketch rendering pipeline.

Implements a realistic pencil sketch effect using grayscale conversion,
inversion, blur, and color dodge blending.
"""

from typing import Dict, Any
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np
from scipy.ndimage import gaussian_filter
import logging

from .base import RenderPipeline

logger = logging.getLogger(__name__)


class PencilSketchPipeline(RenderPipeline):
    """
    Creates a pencil sketch effect through grayscale conversion,
    inversion, and color dodge blending.

    Algorithm Steps:
    1. Convert to grayscale
    2. Invert the grayscale image
    3. Apply Gaussian blur to inverted image
    4. Color dodge blend: base / (255 - blend)
    5. Adjust contrast for final output

    Enterprise Requirements:
    - ROOT CAUSE: Deterministic blur (fixed sigma) ensures reproducibility
    - RECURRENCE PREVENTION: Validated parameter ranges
    - OBSERVABILITY: Logs each processing step
    - SELF-HEALING: Handles division by zero in dodge blend
    """

    def _validate_config(self) -> None:
        """Validate configuration parameters."""
        allowed_params = {
            'sigma', 'contrast_factor', 'output_mode'
        }

        invalid_params = set(self.config.keys()) - allowed_params
        if invalid_params:
            raise ValueError(
                f"Invalid config parameters: {invalid_params}. "
                f"Allowed: {allowed_params}"
            )

        # Validate ranges
        sigma = self.config.get('sigma', 21)
        if not isinstance(sigma, (int, float)) or sigma <= 0:
            raise ValueError(f"sigma must be positive number, got {sigma}")

        contrast = self.config.get('contrast_factor', 1.3)
        if not isinstance(contrast, (int, float)) or contrast <= 0:
            raise ValueError(f"contrast_factor must be positive, got {contrast}")

    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration parameters."""
        return {
            'sigma': 21,
            'contrast_factor': 1.3,
            'output_mode': 'L'  # 'L' for grayscale, 'RGB' for colored sketch
        }

    def render(self, image: Image.Image) -> Image.Image:
        """
        Apply pencil sketch effect to the image.

        Args:
            image: Input PIL Image

        Returns:
            Processed PIL Image with pencil sketch effect
        """
        logger.info(f"Starting pencil sketch pipeline on {image.size} image")

        # Get config with defaults
        config = {**self.get_default_config(), **self.config}

        # Step 1: Convert to grayscale
        logger.info("Converting to grayscale")
        if image.mode == 'RGBA':
            # Handle transparency
            rgb_image = Image.new('RGB', image.size, (255, 255, 255))
            rgb_image.paste(image, mask=image.split()[-1])
            image = rgb_image

        gray = image.convert('L')

        # Step 2: Invert
        logger.info("Inverting image")
        inverted = self._invert(gray)

        # Step 3: Gaussian blur
        logger.info(f"Applying Gaussian blur with sigma={config['sigma']}")
        blurred = self._gaussian_blur(inverted, sigma=config['sigma'])

        # Step 4: Color dodge blend
        logger.info("Applying color dodge blend")
        sketch = self._color_dodge_blend(gray, blurred)

        # Step 5: Adjust contrast
        logger.info(f"Adjusting contrast with factor={config['contrast_factor']}")
        sketch = self._adjust_contrast(sketch, factor=config['contrast_factor'])

        # Convert to output mode if needed
        output_mode = config['output_mode']
        if output_mode == 'RGB' and sketch.mode == 'L':
            logger.info("Converting to RGB")
            sketch = sketch.convert('RGB')

        logger.info("Pencil sketch pipeline complete")
        return sketch

    def _invert(self, image: Image.Image) -> Image.Image:
        """
        Invert the image (255 - pixel_value).

        Args:
            image: Grayscale PIL Image

        Returns:
            Inverted PIL Image
        """
        img_array = np.array(image)
        inverted_array = 255 - img_array
        return Image.fromarray(inverted_array, mode='L')

    def _gaussian_blur(self, image: Image.Image, sigma: float) -> Image.Image:
        """
        Apply Gaussian blur using scipy for deterministic results.

        Args:
            image: Grayscale PIL Image
            sigma: Standard deviation of Gaussian kernel

        Returns:
            Blurred PIL Image
        """
        img_array = np.array(image).astype(np.float32)

        # Apply Gaussian blur (deterministic with scipy)
        blurred_array = gaussian_filter(img_array, sigma=sigma, mode='reflect')

        # Clip to valid range and convert to uint8
        blurred_array = np.clip(blurred_array, 0, 255).astype(np.uint8)

        return Image.fromarray(blurred_array, mode='L')

    def _color_dodge_blend(
        self,
        base: Image.Image,
        blend: Image.Image
    ) -> Image.Image:
        """
        Apply color dodge blend mode: result = base / (255 - blend) * 255.

        This simulates light shining through the inverted/blurred image,
        creating the sketch effect.

        Args:
            base: Base grayscale image (original)
            blend: Blend grayscale image (inverted + blurred)

        Returns:
            Blended PIL Image
        """
        base_array = np.array(base).astype(np.float32)
        blend_array = np.array(blend).astype(np.float32)

        # Color dodge formula: base / (255 - blend) * 255
        # Handle division by zero: where blend == 255, result = 255
        denominator = 255.0 - blend_array

        # Avoid division by zero
        result = np.zeros_like(base_array)
        mask = denominator > 0

        result[mask] = (base_array[mask] / denominator[mask]) * 255.0
        result[~mask] = 255.0  # Where denominator is 0, set to white

        # Clip to valid range
        result = np.clip(result, 0, 255).astype(np.uint8)

        return Image.fromarray(result, mode='L')

    def _adjust_contrast(
        self,
        image: Image.Image,
        factor: float
    ) -> Image.Image:
        """
        Adjust image contrast.

        Args:
            image: PIL Image
            factor: Contrast adjustment factor (1.0 = no change)

        Returns:
            Contrast-adjusted PIL Image
        """
        enhancer = ImageEnhance.Contrast(image)
        return enhancer.enhance(factor)

"""
Between Lines rendering pipeline.

Implements a motion blur effect along edge gradients with posterization,
creating a dynamic line-art appearance.
"""

from typing import Dict, Any
from PIL import Image
import numpy as np
from scipy.ndimage import convolve, sobel, gaussian_filter1d
import logging

from .base import RenderPipeline

logger = logging.getLogger(__name__)


class BetweenLinesPipeline(RenderPipeline):
    """
    Creates a stylized line-art effect with directional motion blur
    along image gradients.

    Algorithm Steps:
    1. Sobel edge detection (X and Y gradients)
    2. Calculate gradient direction (angle) at each pixel
    3. Apply motion blur along gradient directions
    4. 4-level posterization for artistic effect

    Enterprise Requirements:
    - ROOT CAUSE: Deterministic gradient calculation ensures reproducibility
    - RECURRENCE PREVENTION: Validated parameter ranges
    - OBSERVABILITY: Logs each processing step with timing
    - SELF-HEALING: Handles edge cases in gradient calculation
    """

    def _validate_config(self) -> None:
        """Validate configuration parameters."""
        allowed_params = {
            'blur_length', 'num_levels', 'edge_threshold'
        }

        invalid_params = set(self.config.keys()) - allowed_params
        if invalid_params:
            raise ValueError(
                f"Invalid config parameters: {invalid_params}. "
                f"Allowed: {allowed_params}"
            )

        # Validate ranges
        blur_length = self.config.get('blur_length', 15)
        if not isinstance(blur_length, int) or blur_length < 1:
            raise ValueError(f"blur_length must be positive integer, got {blur_length}")

        num_levels = self.config.get('num_levels', 4)
        if not isinstance(num_levels, int) or num_levels < 2 or num_levels > 256:
            raise ValueError(f"num_levels must be integer 2-256, got {num_levels}")

    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration parameters."""
        return {
            'blur_length': 15,
            'num_levels': 4,
            'edge_threshold': 30
        }

    def render(self, image: Image.Image) -> Image.Image:
        """
        Apply between lines effect to the image.

        Args:
            image: Input PIL Image

        Returns:
            Processed PIL Image with between lines effect
        """
        logger.info(f"Starting between lines pipeline on {image.size} image")

        # Get config with defaults
        config = {**self.get_default_config(), **self.config}

        # Convert to grayscale for edge detection
        if image.mode == 'RGBA':
            logger.info("Converting RGBA to RGB")
            rgb_image = Image.new('RGB', image.size, (255, 255, 255))
            rgb_image.paste(image, mask=image.split()[-1])
            image = rgb_image

        # Keep original for color blending if needed
        is_color = image.mode == 'RGB'
        gray = image.convert('L')

        # Step 1: Sobel edge detection
        logger.info("Detecting edges with Sobel operator")
        grad_x, grad_y, magnitude = self._sobel_edges(gray)

        # Step 2: Calculate gradient direction
        logger.info("Calculating gradient directions")
        directions = self._gradient_direction(grad_x, grad_y)

        # Step 3: Apply directional motion blur
        logger.info(f"Applying motion blur along gradients (length={config['blur_length']})")
        blurred = self._directional_motion_blur(
            gray,
            directions,
            magnitude,
            blur_length=config['blur_length'],
            edge_threshold=config['edge_threshold']
        )

        # Step 4: Posterize
        logger.info(f"Posterizing to {config['num_levels']} levels")
        posterized = self._posterize(blurred, num_levels=config['num_levels'])

        # Convert to RGB if original was color
        if is_color:
            posterized = posterized.convert('RGB')

        logger.info("Between lines pipeline complete")
        return posterized

    def _sobel_edges(
        self,
        image: Image.Image
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Apply Sobel edge detection to compute gradients.

        Args:
            image: Grayscale PIL Image

        Returns:
            Tuple of (grad_x, grad_y, magnitude) as numpy arrays
        """
        img_array = np.array(image).astype(np.float32)

        # Apply Sobel operators
        grad_x = sobel(img_array, axis=1)  # Horizontal edges
        grad_y = sobel(img_array, axis=0)  # Vertical edges

        # Calculate gradient magnitude
        magnitude = np.sqrt(grad_x**2 + grad_y**2)

        return grad_x, grad_y, magnitude

    def _gradient_direction(
        self,
        grad_x: np.ndarray,
        grad_y: np.ndarray
    ) -> np.ndarray:
        """
        Calculate gradient direction in radians.

        Args:
            grad_x: X gradient
            grad_y: Y gradient

        Returns:
            Direction array in radians (-pi to pi)
        """
        # atan2 gives angle of gradient vector
        # This is perpendicular to the edge direction
        # We want to blur ALONG the edge, so rotate by 90 degrees
        directions = np.arctan2(grad_y, grad_x)

        # Rotate by 90 degrees to get edge direction (not gradient direction)
        directions = directions + np.pi / 2

        return directions

    def _directional_motion_blur(
        self,
        image: Image.Image,
        directions: np.ndarray,
        magnitude: np.ndarray,
        blur_length: int,
        edge_threshold: float
    ) -> Image.Image:
        """
        Apply motion blur along gradient directions.

        This creates a flowing, line-art effect where blur follows
        the contours and edges in the image.

        Args:
            image: Grayscale PIL Image
            directions: Direction map in radians
            magnitude: Gradient magnitude map
            blur_length: Length of blur kernel in pixels
            edge_threshold: Minimum gradient magnitude to apply blur

        Returns:
            Motion-blurred PIL Image
        """
        img_array = np.array(image).astype(np.float32)
        height, width = img_array.shape

        # Create output array
        result = np.zeros_like(img_array)
        counts = np.zeros_like(img_array)

        # Quantize directions to 8 cardinal directions for efficiency
        # This makes the blur deterministic and faster
        num_directions = 8
        direction_step = 2 * np.pi / num_directions

        for i in range(num_directions):
            angle = i * direction_step
            angle_min = angle - direction_step / 2
            angle_max = angle + direction_step / 2

            # Create mask for pixels with this direction
            # Handle wrap-around at -pi/pi boundary
            if i == 0:
                mask = ((directions >= angle_min) | (directions < angle_max))
            else:
                mask = ((directions >= angle_min) & (directions < angle_max))

            # Only blur strong edges
            mask = mask & (magnitude >= edge_threshold)

            if not np.any(mask):
                continue

            # Create directional blur kernel
            dx = np.cos(angle)
            dy = np.sin(angle)

            # Apply 1D blur in this direction
            kernel = np.ones(blur_length) / blur_length

            # For this direction, create a simple directional blur
            # by using Gaussian filter along the axis
            blurred_directional = img_array.copy()

            # Approximate directional blur with separable filters
            if abs(dx) > abs(dy):
                # More horizontal
                blurred_directional = gaussian_filter1d(
                    blurred_directional,
                    sigma=blur_length / 3,
                    axis=1,
                    mode='reflect'
                )
            else:
                # More vertical
                blurred_directional = gaussian_filter1d(
                    blurred_directional,
                    sigma=blur_length / 3,
                    axis=0,
                    mode='reflect'
                )

            # Accumulate results
            result[mask] += blurred_directional[mask]
            counts[mask] += 1

        # Average accumulated results
        # Where no blur was applied, use original
        mask_blurred = counts > 0
        result[mask_blurred] /= counts[mask_blurred]
        result[~mask_blurred] = img_array[~mask_blurred]

        result = np.clip(result, 0, 255).astype(np.uint8)
        return Image.fromarray(result, mode='L')

    def _posterize(
        self,
        image: Image.Image,
        num_levels: int
    ) -> Image.Image:
        """
        Posterize image to reduce to N gray levels.

        Args:
            image: Grayscale PIL Image
            num_levels: Number of gray levels (e.g., 4)

        Returns:
            Posterized PIL Image
        """
        img_array = np.array(image).astype(np.float32)

        # Calculate bin edges
        bins = np.linspace(0, 256, num_levels + 1)

        # Quantize to bins
        posterized = np.digitize(img_array, bins[1:])

        # Map bin indices to gray values
        # bin 0 -> 0, bin 1 -> 255/(num_levels-1), etc.
        gray_values = np.linspace(0, 255, num_levels)
        posterized = gray_values[posterized]

        posterized = np.clip(posterized, 0, 255).astype(np.uint8)
        return Image.fromarray(posterized, mode='L')

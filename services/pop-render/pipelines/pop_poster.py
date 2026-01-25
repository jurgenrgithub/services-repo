"""
Pop Poster rendering pipeline.

Implements a vibrant posterization effect using K-means clustering
combined with edge detection for bold, graphic output.
"""

from typing import Dict, Any
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np
from sklearn.cluster import KMeans
import cv2
import logging

from .base import RenderPipeline

logger = logging.getLogger(__name__)


class PopPosterPipeline(RenderPipeline):
    """
    Creates a pop-art poster effect through K-means color quantization
    with edge enhancement.

    Algorithm Steps:
    1. K-means posterization (reduce to k dominant colors)
    2. Canny edge detection to find contours
    3. Composite edges over posterized image
    4. Apply unsharp mask for sharpening

    Enterprise Requirements:
    - ROOT CAUSE: Deterministic seed ensures reproducible output
    - RECURRENCE PREVENTION: Validated parameter ranges
    - OBSERVABILITY: Logs each processing step
    - SELF-HEALING: Handles grayscale and RGBA inputs
    """

    def _validate_config(self) -> None:
        """Validate configuration parameters."""
        allowed_params = {
            'k', 'seed', 'canny_low', 'canny_high',
            'sharpen_radius', 'sharpen_percent', 'sharpen_threshold'
        }

        invalid_params = set(self.config.keys()) - allowed_params
        if invalid_params:
            raise ValueError(
                f"Invalid config parameters: {invalid_params}. "
                f"Allowed: {allowed_params}"
            )

        # Validate ranges
        k = self.config.get('k', 8)
        if not isinstance(k, int) or k < 2 or k > 256:
            raise ValueError(f"k must be integer between 2 and 256, got {k}")

    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration parameters."""
        return {
            'k': 8,
            'seed': 42,
            'canny_low': 50,
            'canny_high': 150,
            'sharpen_radius': 2,
            'sharpen_percent': 150,
            'sharpen_threshold': 3
        }

    def render(self, image: Image.Image) -> Image.Image:
        """
        Apply pop poster effect to the image.

        Args:
            image: Input PIL Image

        Returns:
            Processed PIL Image with pop poster effect
        """
        logger.info(f"Starting pop poster pipeline on {image.size} image")

        # Get config with defaults
        config = {**self.get_default_config(), **self.config}

        # Convert to RGB if needed
        if image.mode == 'RGBA':
            logger.info("Converting RGBA to RGB")
            rgb_image = Image.new('RGB', image.size, (255, 255, 255))
            rgb_image.paste(image, mask=image.split()[-1])
            image = rgb_image
        elif image.mode != 'RGB':
            logger.info(f"Converting {image.mode} to RGB")
            image = image.convert('RGB')

        # Step 1: K-means posterization
        logger.info(f"Applying K-means with k={config['k']}, seed={config['seed']}")
        posterized = self._kmeans_posterize(
            image,
            k=config['k'],
            seed=config['seed']
        )

        # Step 2: Canny edge detection
        logger.info(
            f"Detecting edges with Canny "
            f"(low={config['canny_low']}, high={config['canny_high']})"
        )
        edges = self._canny_edges(
            image,
            low_threshold=config['canny_low'],
            high_threshold=config['canny_high']
        )

        # Step 3: Composite edges over posterized image
        logger.info("Compositing edges over posterized image")
        composited = self._composite_edges(posterized, edges)

        # Step 4: Sharpen
        logger.info(
            f"Sharpening with radius={config['sharpen_radius']}, "
            f"percent={config['sharpen_percent']}"
        )
        sharpened = self._sharpen(
            composited,
            radius=config['sharpen_radius'],
            percent=config['sharpen_percent'],
            threshold=config['sharpen_threshold']
        )

        logger.info("Pop poster pipeline complete")
        return sharpened

    def _kmeans_posterize(
        self,
        image: Image.Image,
        k: int,
        seed: int
    ) -> Image.Image:
        """
        Apply K-means clustering for color quantization.

        Args:
            image: RGB PIL Image
            k: Number of color clusters
            seed: Random seed for reproducibility

        Returns:
            Posterized PIL Image
        """
        # Convert to numpy array
        img_array = np.array(image)
        original_shape = img_array.shape

        # Reshape to (pixels, channels)
        pixels = img_array.reshape(-1, 3).astype(np.float32)

        # Apply K-means
        kmeans = KMeans(
            n_clusters=k,
            random_state=seed,
            n_init=10,
            max_iter=300
        )
        kmeans.fit(pixels)

        # Replace each pixel with its cluster center
        quantized = kmeans.cluster_centers_[kmeans.labels_]
        quantized = quantized.reshape(original_shape).astype(np.uint8)

        return Image.fromarray(quantized, mode='RGB')

    def _canny_edges(
        self,
        image: Image.Image,
        low_threshold: int,
        high_threshold: int
    ) -> np.ndarray:
        """
        Detect edges using Canny algorithm.

        Args:
            image: RGB PIL Image
            low_threshold: Lower threshold for edge detection
            high_threshold: Upper threshold for edge detection

        Returns:
            Binary edge map as numpy array
        """
        # Convert to grayscale
        gray = np.array(image.convert('L'))

        # Apply Canny edge detection
        edges = cv2.Canny(gray, low_threshold, high_threshold)

        return edges

    def _composite_edges(
        self,
        image: Image.Image,
        edges: np.ndarray
    ) -> Image.Image:
        """
        Overlay black edges on the posterized image.

        Args:
            image: Posterized RGB PIL Image
            edges: Binary edge map

        Returns:
            Composited PIL Image
        """
        img_array = np.array(image)

        # Create black color for edges
        # Where edges are detected (255), set pixel to black (0)
        edge_mask = edges > 0
        img_array[edge_mask] = [0, 0, 0]

        return Image.fromarray(img_array, mode='RGB')

    def _sharpen(
        self,
        image: Image.Image,
        radius: int,
        percent: int,
        threshold: int
    ) -> Image.Image:
        """
        Apply unsharp mask for sharpening.

        Args:
            image: PIL Image to sharpen
            radius: Blur radius for unsharp mask
            percent: Sharpening strength percentage
            threshold: Minimum brightness change to sharpen

        Returns:
            Sharpened PIL Image
        """
        return image.filter(
            ImageFilter.UnsharpMask(
                radius=radius,
                percent=percent,
                threshold=threshold
            )
        )

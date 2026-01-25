"""
Pop Screenprint rendering pipelines.

Implements authentic screen-print style effects with:
- Fixed curated color palettes (not auto k-means)
- LAB colorspace for natural skin tones
- Bilateral smoothing for ink-block look
- Morphological edge processing
- Paper grain and ink distress textures

Two presets:
- Coastal: Calm teal/cream, Manly beach vibe (default)
- Rebel: Bold purple, high contrast drama
"""

from typing import Dict, Any, List, Tuple
from PIL import Image, ImageFilter
import numpy as np
import cv2
import logging

from .base import RenderPipeline

logger = logging.getLogger(__name__)


class PopScreenprintPipeline(RenderPipeline):
    """
    Base class for screen-print style pop art.

    Key differences from basic posterization:
    - Uses fixed curated palettes, not auto k-means
    - LAB colorspace preserves skin tones
    - Bilateral filter creates ink-block smoothness
    - Morphological ops on edges for print feel
    - Paper grain and ink distress textures
    """

    # Subclasses override these
    PRESET_ID = "pop_screenprint"
    PRESET_LABEL = "Pop – Screenprint"

    DEFAULT_PALETTE = [
        [233, 226, 198],  # cream paper
        [31, 42, 46],     # charcoal ink
        [126, 146, 142],  # muted teal
        [201, 193, 167]   # warm midtone
    ]

    DEFAULT_EDGE_COLOR = [31, 42, 46]

    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "posterization": {
                "k": 4,
                "colorspace": "LAB",
                "seed": 42,
                "palette": self.DEFAULT_PALETTE
            },
            "pre_smooth": {
                "type": "bilateral",
                "d": 9,
                "sigmaColor": 75,
                "sigmaSpace": 75
            },
            "edges": {
                "method": "canny",
                "low": 80,
                "high": 200,
                "dilate": {"kernel": [3, 3], "iterations": 2},
                "close": {"kernel": [3, 3], "iterations": 1},
                "color": self.DEFAULT_EDGE_COLOR
            },
            "sharpen": {
                "radius": 1.2,
                "percent": 120,
                "threshold": 2
            },
            "texture": {
                "paper_grain": 0.08,
                "speckle": 0.004,
                "ink_distress": 0.15
            }
        }

    def render(self, image: Image.Image) -> Image.Image:
        """Apply screen-print pop art effect."""
        logger.info(f"Starting {self.PRESET_LABEL} pipeline on {image.size} image")

        config = {**self.get_default_config(), **self.config}

        # Convert to RGB if needed
        if image.mode != 'RGB':
            image = self._ensure_rgb(image)

        img_array = np.array(image)

        # Step 1: Bilateral smoothing (creates ink-block look)
        logger.info("Applying bilateral smoothing")
        smoothed = self._bilateral_smooth(img_array, config["pre_smooth"])

        # Step 2: Map to fixed palette in LAB space
        logger.info(f"Mapping to {len(config['posterization']['palette'])}-color palette")
        posterized = self._palette_map(smoothed, config["posterization"])

        # Step 3: Edge detection with morphological processing
        logger.info("Detecting and processing edges")
        edges = self._process_edges(img_array, config["edges"])

        # Step 4: Composite edges over posterized image
        logger.info("Compositing edges")
        composited = self._composite_edges(posterized, edges, config["edges"]["color"])

        # Step 5: Apply textures (paper grain, speckle, ink distress)
        logger.info("Applying screen-print textures")
        textured = self._apply_textures(composited, config["texture"])

        # Step 6: Sharpen for print
        logger.info("Sharpening")
        result = Image.fromarray(textured)
        result = self._sharpen(result, config["sharpen"])

        logger.info(f"{self.PRESET_LABEL} pipeline complete")
        return result

    def _ensure_rgb(self, image: Image.Image) -> Image.Image:
        """Convert image to RGB."""
        if image.mode == 'RGBA':
            rgb = Image.new('RGB', image.size, (255, 255, 255))
            rgb.paste(image, mask=image.split()[-1])
            return rgb
        return image.convert('RGB')

    def _bilateral_smooth(self, img: np.ndarray, config: Dict) -> np.ndarray:
        """Apply bilateral filter for ink-block smoothness."""
        return cv2.bilateralFilter(
            img,
            d=config["d"],
            sigmaColor=config["sigmaColor"],
            sigmaSpace=config["sigmaSpace"]
        )

    def _palette_map(self, img: np.ndarray, config: Dict) -> np.ndarray:
        """Map image to fixed palette using LAB colorspace."""
        palette = np.array(config["palette"], dtype=np.uint8)

        if config["colorspace"] == "LAB":
            # Convert image and palette to LAB
            img_lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB).astype(np.float32)

            # Convert palette to LAB
            palette_rgb = palette.reshape(1, -1, 3)
            palette_lab = cv2.cvtColor(palette_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
            palette_lab = palette_lab.reshape(-1, 3)

            # Find nearest palette color for each pixel
            h, w = img_lab.shape[:2]
            pixels = img_lab.reshape(-1, 3)

            # Calculate distances to each palette color
            distances = np.zeros((pixels.shape[0], len(palette_lab)))
            for i, color in enumerate(palette_lab):
                distances[:, i] = np.sqrt(np.sum((pixels - color) ** 2, axis=1))

            # Assign nearest color
            nearest = np.argmin(distances, axis=1)
            result_lab = palette_lab[nearest].reshape(h, w, 3).astype(np.uint8)

            # Convert back to RGB
            result = cv2.cvtColor(result_lab, cv2.COLOR_LAB2RGB)
        else:
            # RGB space fallback
            h, w = img.shape[:2]
            pixels = img.reshape(-1, 3).astype(np.float32)
            palette_f = palette.astype(np.float32)

            distances = np.zeros((pixels.shape[0], len(palette_f)))
            for i, color in enumerate(palette_f):
                distances[:, i] = np.sqrt(np.sum((pixels - color) ** 2, axis=1))

            nearest = np.argmin(distances, axis=1)
            result = palette[nearest].reshape(h, w, 3)

        return result

    def _process_edges(self, img: np.ndarray, config: Dict) -> np.ndarray:
        """Detect edges with morphological processing."""
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        # Canny edge detection
        edges = cv2.Canny(gray, config["low"], config["high"])

        # Dilate edges (thicken ink lines)
        if config.get("dilate"):
            kernel = np.ones(tuple(config["dilate"]["kernel"]), np.uint8)
            edges = cv2.dilate(edges, kernel, iterations=config["dilate"]["iterations"])

        # Close gaps (morphological closing)
        if config.get("close"):
            kernel = np.ones(tuple(config["close"]["kernel"]), np.uint8)
            edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel,
                                     iterations=config["close"]["iterations"])

        return edges

    def _composite_edges(self, img: np.ndarray, edges: np.ndarray,
                         edge_color: List[int]) -> np.ndarray:
        """Overlay colored edges on image."""
        result = img.copy()
        edge_mask = edges > 0
        result[edge_mask] = edge_color
        return result

    def _apply_textures(self, img: np.ndarray, config: Dict) -> np.ndarray:
        """Apply paper grain, speckle, and ink distress textures."""
        result = img.astype(np.float32)
        h, w = img.shape[:2]

        np.random.seed(42)  # Deterministic

        # Paper grain (subtle noise across whole image)
        if config.get("paper_grain", 0) > 0:
            grain = np.random.normal(0, config["paper_grain"] * 255, (h, w, 1))
            grain = np.repeat(grain, 3, axis=2)
            result = result + grain

        # Speckle (random dark spots like screen-print imperfections)
        if config.get("speckle", 0) > 0:
            speckle_mask = np.random.random((h, w)) < config["speckle"]
            result[speckle_mask] = result[speckle_mask] * 0.7

        # Ink distress (slight variation in ink density)
        if config.get("ink_distress", 0) > 0:
            distress = np.random.normal(1.0, config["ink_distress"], (h, w, 1))
            distress = np.clip(distress, 0.8, 1.2)
            distress = np.repeat(distress, 3, axis=2)
            result = result * distress

        return np.clip(result, 0, 255).astype(np.uint8)

    def _sharpen(self, image: Image.Image, config: Dict) -> Image.Image:
        """Apply unsharp mask sharpening."""
        return image.filter(
            ImageFilter.UnsharpMask(
                radius=config["radius"],
                percent=int(config["percent"]),
                threshold=config["threshold"]
            )
        )


class PopCoastalPipeline(PopScreenprintPipeline):
    """
    Pop – Coastal Screenprint

    Calm, beachy, Manly-coastal vibe.
    Cream paper background with muted teal + charcoal ink.
    Romantic, warm, not aggressive.

    This is the default Jules & Zest Pop style.
    """

    PRESET_ID = "pop_coastal"
    PRESET_LABEL = "Pop – Coastal"

    DEFAULT_PALETTE = [
        [233, 226, 198],  # cream paper
        [31, 42, 46],     # charcoal ink
        [126, 146, 142],  # muted teal
        [201, 193, 167]   # warm midtone
    ]

    DEFAULT_EDGE_COLOR = [31, 42, 46]

    def get_default_config(self) -> Dict[str, Any]:
        config = super().get_default_config()
        config["posterization"]["palette"] = self.DEFAULT_PALETTE
        config["edges"]["color"] = self.DEFAULT_EDGE_COLOR
        config["edges"]["low"] = 80
        config["edges"]["high"] = 200
        config["pre_smooth"]["sigmaColor"] = 75
        config["pre_smooth"]["sigmaSpace"] = 75
        config["sharpen"]["radius"] = 1.2
        config["sharpen"]["percent"] = 120
        config["texture"]["paper_grain"] = 0.08
        config["texture"]["speckle"] = 0.004
        config["texture"]["ink_distress"] = 0.15
        return config


class PopRebelPipeline(PopScreenprintPipeline):
    """
    Pop – Rebel Romance

    Bold, emotional, high contrast.
    Statement wall art with deep purple palette.
    Perfect for text overlays.
    """

    PRESET_ID = "pop_rebel"
    PRESET_LABEL = "Pop – Rebel"

    DEFAULT_PALETTE = [
        [220, 212, 182],  # cream
        [42, 31, 59],     # deep purple ink
        [108, 90, 134],   # mid purple
        [157, 141, 180]   # light purple
    ]

    DEFAULT_EDGE_COLOR = [42, 31, 59]

    def get_default_config(self) -> Dict[str, Any]:
        config = super().get_default_config()
        config["posterization"]["palette"] = self.DEFAULT_PALETTE
        config["edges"]["color"] = self.DEFAULT_EDGE_COLOR
        config["edges"]["low"] = 70
        config["edges"]["high"] = 180
        config["pre_smooth"]["sigmaColor"] = 80
        config["pre_smooth"]["sigmaSpace"] = 80
        config["sharpen"]["radius"] = 1.3
        config["sharpen"]["percent"] = 135
        config["texture"]["paper_grain"] = 0.1
        config["texture"]["speckle"] = 0.005
        config["texture"]["ink_distress"] = 0.2
        return config

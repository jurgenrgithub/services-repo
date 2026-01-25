"""
Pop Coastal Poster - Aggressive graphic screen-print style.

Key differences from standard Coastal:
- k=3 palette (cream, ink, one midtone)
- Highlight clipping to cream
- Directional ink texture (not random grain)
- Edge suppression in low-contrast areas
"""

from typing import Dict, Any, List
from PIL import Image, ImageFilter
import numpy as np
import cv2
import logging

from .base import RenderPipeline

logger = logging.getLogger(__name__)


class PopCoastalPosterPipeline(RenderPipeline):
    """
    Pop – Coastal Poster

    Aggressive graphic look for statement wall art.
    Hard ink silhouettes, cream dominance, directional texture.
    Perfect for text overlays ("That kiss though...").
    """

    PRESET_ID = "pop_coastal_poster"
    PRESET_LABEL = "Pop – Coastal Poster"

    # 3-color palette: cream paper, dark ink, one midtone
    PALETTE = [
        [233, 226, 198],  # cream paper (dominant)
        [31, 42, 46],     # dark ink
        [140, 160, 158]   # muted teal midtone
    ]

    EDGE_COLOR = [31, 42, 46]
    CREAM = [233, 226, 198]

    def get_default_config(self) -> Dict[str, Any]:
        return {
            "posterization": {
                "k": 3,
                "colorspace": "LAB",
                "seed": 42,
                "palette": self.PALETTE
            },
            "highlight_clip": {
                "enabled": True,
                "threshold": 190
            },
            "pre_smooth": {
                "type": "bilateral",
                "d": 9,
                "sigmaColor": 85,
                "sigmaSpace": 85
            },
            "edges": {
                "method": "canny",
                "low": 90,
                "high": 220,
                "dilate": {"kernel": [3, 3], "iterations": 2},
                "close": {"kernel": [3, 3], "iterations": 1},
                "suppress_low_contrast": True,
                "contrast_threshold": 12,
                "color": self.EDGE_COLOR
            },
            "sharpen": {
                "radius": 1.0,
                "percent": 100,
                "threshold": 2
            },
            "texture": {
                "directional_ink": True,
                "ink_intensity": 0.1,
                "stretch_factor": 2.0,
                "blur_sigma": 6
            }
        }

    def render(self, image: Image.Image) -> Image.Image:
        """Apply aggressive poster screen-print effect."""
        logger.info(f"Starting {self.PRESET_LABEL} pipeline on {image.size} image")

        config = {**self.get_default_config(), **self.config}

        # Convert to RGB
        if image.mode != 'RGB':
            image = self._ensure_rgb(image)

        img_array = np.array(image)
        h, w = img_array.shape[:2]

        # Step 1: Bilateral smoothing
        logger.info("Applying bilateral smoothing")
        smoothed = self._bilateral_smooth(img_array, config["pre_smooth"])

        # Step 2: Map to 3-color palette
        logger.info("Mapping to 3-color palette")
        posterized = self._palette_map(smoothed, config["posterization"])

        # Step 3: Clip highlights to cream (key for poster look)
        if config["highlight_clip"]["enabled"]:
            logger.info("Clipping highlights to cream")
            posterized = self._clip_highlights(posterized, config["highlight_clip"])

        # Step 4: Edge detection with suppression
        logger.info("Detecting edges with suppression")
        edges = self._process_edges(img_array, config["edges"])

        # Step 5: Composite edges
        logger.info("Compositing edges")
        composited = self._composite_edges(posterized, edges, config["edges"]["color"])

        # Step 6: Apply directional ink texture
        logger.info("Applying directional ink texture")
        textured = self._apply_directional_texture(composited, config["texture"])

        # Step 7: Light sharpen
        logger.info("Sharpening")
        result = Image.fromarray(textured)
        result = self._sharpen(result, config["sharpen"])

        logger.info(f"{self.PRESET_LABEL} pipeline complete")
        return result

    def _ensure_rgb(self, image: Image.Image) -> Image.Image:
        if image.mode == 'RGBA':
            rgb = Image.new('RGB', image.size, (255, 255, 255))
            rgb.paste(image, mask=image.split()[-1])
            return rgb
        return image.convert('RGB')

    def _bilateral_smooth(self, img: np.ndarray, config: Dict) -> np.ndarray:
        return cv2.bilateralFilter(
            img,
            d=config["d"],
            sigmaColor=config["sigmaColor"],
            sigmaSpace=config["sigmaSpace"]
        )

    def _palette_map(self, img: np.ndarray, config: Dict) -> np.ndarray:
        """Map to fixed 3-color palette in LAB space."""
        palette = np.array(config["palette"], dtype=np.uint8)

        # Convert to LAB
        img_lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB).astype(np.float32)

        palette_rgb = palette.reshape(1, -1, 3)
        palette_lab = cv2.cvtColor(palette_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        palette_lab = palette_lab.reshape(-1, 3)

        h, w = img_lab.shape[:2]
        pixels = img_lab.reshape(-1, 3)

        # Find nearest palette color
        distances = np.zeros((pixels.shape[0], len(palette_lab)))
        for i, color in enumerate(palette_lab):
            distances[:, i] = np.sqrt(np.sum((pixels - color) ** 2, axis=1))

        nearest = np.argmin(distances, axis=1)
        result_lab = palette_lab[nearest].reshape(h, w, 3).astype(np.uint8)

        return cv2.cvtColor(result_lab, cv2.COLOR_LAB2RGB)

    def _clip_highlights(self, img: np.ndarray, config: Dict) -> np.ndarray:
        """Force bright areas to cream - makes faces glow."""
        result = img.copy()
        threshold = config["threshold"]

        # Pixels brighter than threshold → cream
        brightness = np.mean(img, axis=2)
        mask = brightness > threshold
        result[mask] = self.CREAM

        return result

    def _process_edges(self, img: np.ndarray, config: Dict) -> np.ndarray:
        """Edge detection with low-contrast suppression."""
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        # Canny
        edges = cv2.Canny(gray, config["low"], config["high"])

        # Dilate
        if config.get("dilate"):
            kernel = np.ones(tuple(config["dilate"]["kernel"]), np.uint8)
            edges = cv2.dilate(edges, kernel, iterations=config["dilate"]["iterations"])

        # Close gaps
        if config.get("close"):
            kernel = np.ones(tuple(config["close"]["kernel"]), np.uint8)
            edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel,
                                     iterations=config["close"]["iterations"])

        # Remove weak edges
        edges[edges < 255] = 0

        # Suppress edges in low-contrast regions (key for poster look)
        if config.get("suppress_low_contrast"):
            contrast = cv2.Laplacian(gray, cv2.CV_64F)
            threshold = config.get("contrast_threshold", 12)
            edges[np.abs(contrast) < threshold] = 0

        return edges

    def _composite_edges(self, img: np.ndarray, edges: np.ndarray,
                         edge_color: List[int]) -> np.ndarray:
        result = img.copy()
        edge_mask = edges > 0
        result[edge_mask] = edge_color
        return result

    def _apply_directional_texture(self, img: np.ndarray, config: Dict) -> np.ndarray:
        """Apply directional ink texture (scraped/brushed feel)."""
        if not config.get("directional_ink", False):
            return img

        result = img.astype(np.float32)
        h, w = img.shape[:2]

        np.random.seed(42)  # Deterministic

        # Create low-frequency directional noise
        # Generate at smaller size, blur, then stretch vertically
        small_h = h // 4
        small_w = w // 4

        grain = np.random.normal(0, 1, (small_h, small_w))

        # Blur for low-frequency
        blur_sigma = config.get("blur_sigma", 6)
        grain = cv2.GaussianBlur(grain.astype(np.float32), (0, 0), blur_sigma)

        # Stretch vertically (creates directional feel)
        stretch = config.get("stretch_factor", 2.0)
        grain = cv2.resize(grain, (w, int(small_h * stretch)))

        # Crop/tile to match image size
        if grain.shape[0] < h:
            repeats = (h // grain.shape[0]) + 1
            grain = np.tile(grain, (repeats, 1))
        grain = grain[:h, :w]

        # Apply as multiplicative texture
        intensity = config.get("ink_intensity", 0.1)
        grain_3d = grain[..., np.newaxis]
        grain_3d = np.repeat(grain_3d, 3, axis=2)

        result = result * (1.0 - intensity + intensity * (grain_3d + 1) / 2)

        return np.clip(result, 0, 255).astype(np.uint8)

    def _sharpen(self, image: Image.Image, config: Dict) -> Image.Image:
        return image.filter(
            ImageFilter.UnsharpMask(
                radius=config["radius"],
                percent=int(config["percent"]),
                threshold=config["threshold"]
            )
        )

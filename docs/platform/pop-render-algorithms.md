# Pop-Render Rendering Algorithms

## Overview

The pop-render service implements three distinct rendering pipelines that transform source images into artistic outputs optimized for print production. All pipelines inherit from a common abstract base class ensuring deterministic output, configurable parameters, and consistent error handling.

**Key Principles:**
- **Determinism:** Same input + same configuration = same output (critical for reprints)
- **Configurability:** Algorithm parameters can be overridden via `algorithm_config` JSONB field
- **Observability:** All pipelines emit metrics and structured logs
- **Quality:** High-resolution output (300 DPI) with professional print quality

**Pipeline Files:**
- Base class: `platform/pop-render/service/pipelines/base.py`
- Pop Poster: `platform/pop-render/service/pipelines/pop_poster.py`
- Pencil Sketch: `platform/pop-render/service/pipelines/pencil_sketch.py`
- Between The Lines: `platform/pop-render/service/pipelines/between_lines.py`
- Registry: `platform/pop-render/service/pipelines/__init__.py`

## Pipeline Architecture

### Abstract Base Class: RenderPipeline

**File:** `platform/pop-render/service/pipelines/base.py`

All rendering pipelines inherit from the `RenderPipeline` abstract base class.

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from PIL import Image

class RenderPipeline(ABC):
    """
    Abstract base class for all rendering pipelines.

    Ensures:
    - Deterministic output (reproducible results)
    - Parameter overrides via algorithm_config
    - Built-in observability and logging
    - Graceful error handling
    - Consistent interface
    """

    def __init__(self, algorithm_config: Optional[Dict[str, Any]] = None):
        """
        Initialize pipeline with optional configuration overrides.

        Args:
            algorithm_config: Dictionary of parameters to override defaults
        """
        self.config = algorithm_config or {}
        self._validate_config()

    @abstractmethod
    def render(self, image: Image.Image) -> Image.Image:
        """
        Process image through the rendering pipeline.

        Args:
            image: Source PIL Image

        Returns:
            Rendered PIL Image

        Raises:
            ValueError: Invalid image or configuration
            RuntimeError: Processing error
        """
        pass

    def _validate_config(self) -> None:
        """
        Validate configuration parameters.
        Override in subclasses for parameter-specific validation.
        """
        pass

    def get_default_config(self) -> Dict[str, Any]:
        """
        Get default configuration parameters.
        Override in subclasses to define defaults.
        """
        return {}
```

**Design Benefits:**
- **Type Safety:** Abstract methods enforce implementation requirements
- **Configuration Merging:** Override defaults while preserving unspecified parameters
- **Validation:** Early parameter validation before processing
- **Extensibility:** New pipelines follow established pattern

### Pipeline Registry

**File:** `platform/pop-render/service/pipelines/__init__.py`

The pipeline registry maps style slugs to pipeline classes.

```python
from .pop_poster import PopPosterPipeline
from .pencil_sketch import PencilSketchPipeline
from .between_lines import BetweenLinesPipeline

PIPELINE_MAP = {
    'pop-poster': PopPosterPipeline,
    'pencil-sketch': PencilSketchPipeline,
    'between-the-lines': BetweenLinesPipeline,
}

def get_pipeline(style_slug: str, algorithm_config: dict) -> RenderPipeline:
    """
    Get pipeline instance for a given style.

    Args:
        style_slug: Style identifier (e.g., 'pop-poster')
        algorithm_config: Configuration parameters

    Returns:
        Instantiated pipeline ready for rendering

    Raises:
        ValueError: Unknown style slug
    """
    if style_slug not in PIPELINE_MAP:
        raise ValueError(f"Unknown style: {style_slug}")

    pipeline_class = PIPELINE_MAP[style_slug]
    return pipeline_class(algorithm_config)
```

## Pipeline 1: Pop Poster

**File:** `platform/pop-render/service/pipelines/pop_poster.py`

### Algorithm Overview

The Pop Poster pipeline creates vibrant pop-art style images with bold outlines and reduced color palettes. It combines K-means color clustering (posterization) with Canny edge detection to produce high-contrast artistic outputs reminiscent of Andy Warhol's silkscreen prints.

**Visual Characteristics:**
- Reduced color palette (typically 4-12 colors)
- Bold black outlines emphasizing edges and contours
- Flat color regions (posterized)
- Enhanced sharpness for crisp details
- Vibrant, saturated colors

### Algorithm Steps

#### Step 1: K-Means Posterization

**Purpose:** Reduce image to k dominant colors

**Process:**
1. Convert image to RGB array (height × width × 3)
2. Reshape to 2D array of pixels: (num_pixels, 3)
3. Apply K-means clustering with `n_clusters=k`
4. Replace each pixel with its cluster center color
5. Reshape back to original image dimensions

**Parameters:**
- `k`: Number of color clusters (default: 8)
- `seed`: Random seed for reproducibility (default: 42)

**Code:**
```python
import numpy as np
from sklearn.cluster import KMeans

pixels = np.array(image).reshape(-1, 3)
kmeans = KMeans(n_clusters=k, random_state=seed, n_init=10)
kmeans.fit(pixels)
labels = kmeans.labels_
centers = kmeans.cluster_centers_.astype('uint8')
posterized = centers[labels].reshape(image.size[1], image.size[0], 3)
posterized_image = Image.fromarray(posterized)
```

**Determinism:** Fixed seed ensures identical cluster assignments across runs

#### Step 2: Canny Edge Detection

**Purpose:** Extract bold outlines

**Process:**
1. Convert posterized image to grayscale
2. Apply Gaussian blur (sigma=1.0) to reduce noise
3. Compute intensity gradients (Sobel operator)
4. Apply non-maximum suppression
5. Double threshold to identify strong and weak edges
6. Edge tracking by hysteresis

**Parameters:**
- `canny_low`: Lower threshold for edge detection (default: 50)
- `canny_high`: Upper threshold for edge detection (default: 150)

**Code:**
```python
import cv2

gray = cv2.cvtColor(posterized, cv2.COLOR_RGB2GRAY)
edges = cv2.Canny(gray, canny_low, canny_high)
edges_rgb = cv2.cvtColor(edges, cv2.COLOR_GRAY2RGB)
```

**Thresholds:**
- Low threshold (50): Pixels with gradient ≥50 are weak edges
- High threshold (150): Pixels with gradient ≥150 are strong edges
- Weak edges connected to strong edges are kept

#### Step 3: Composite Edges Over Posterized Image

**Purpose:** Overlay black outlines on posterized colors

**Process:**
1. Convert edge map to binary mask (edges=black, non-edges=white)
2. Blend using mask: `result = posterized where mask=white, black where mask=black`

**Code:**
```python
edges_mask = edges > 0
output = posterized_image.copy()
output_array = np.array(output)
output_array[edges_mask] = [0, 0, 0]  # Black edges
output = Image.fromarray(output_array)
```

#### Step 4: Unsharp Mask Sharpening

**Purpose:** Enhance crisp details and edge clarity

**Process:**
1. Create Gaussian-blurred version of image
2. Compute difference: `unsharp_mask = original - blurred`
3. Add scaled mask back: `sharpened = original + (unsharp_mask × percent / 100)`
4. Apply only where mask > threshold

**Parameters:**
- `sharpen_radius`: Gaussian blur radius (default: 2)
- `sharpen_percent`: Sharpening intensity percentage (default: 150)
- `sharpen_threshold`: Minimum difference to sharpen (default: 3)

**Code:**
```python
from PIL import ImageFilter

output = output.filter(ImageFilter.UnsharpMask(
    radius=sharpen_radius,
    percent=sharpen_percent,
    threshold=sharpen_threshold
))
```

### Default Configuration

```python
{
    'k': 8,                    # Number of color clusters
    'seed': 42,               # Random seed for K-means
    'canny_low': 50,          # Lower Canny threshold
    'canny_high': 150,        # Upper Canny threshold
    'sharpen_radius': 2,      # Unsharp mask radius
    'sharpen_percent': 150,   # Sharpening intensity
    'sharpen_threshold': 3    # Sharpening threshold
}
```

### Parameter Tuning Guide

**Color Reduction (`k`):**
- `k=4`: Very bold, simplified look (4 colors)
- `k=8`: Balanced detail and simplicity (default)
- `k=12`: More nuanced color transitions
- `k=16`: Maximum detail retention

**Edge Detection (`canny_low`, `canny_high`):**
- Lower thresholds (30/100): More edges, busier look
- Default (50/150): Balanced edge detection
- Higher thresholds (70/200): Only strongest edges, cleaner look

**Sharpening (`sharpen_percent`):**
- 100: Subtle sharpening
- 150: Balanced sharpness (default)
- 200: Aggressive sharpening (may introduce artifacts)

### Example Input/Output

**Input Image:**
- Format: JPEG, 3000x4000px
- Subject: Portrait photograph
- Color profile: sRGB

**Processing:**
- K-means reduces to 8 dominant colors
- Canny detects facial features, hair edges
- Edges composited as black outlines
- Unsharp mask enhances detail

**Output Image:**
- Format: TIFF, 300 DPI, LZW compression
- Style: Pop-art with vibrant color blocks
- Edges: Bold black outlines
- File size: ~40-60MB (TIFF), ~200-400KB (JPEG preview)

### Determinism Guarantees

**Sources of Non-Determinism (Eliminated):**
1. **K-means random initialization:** Fixed with `random_state=42`
2. **Floating-point operations:** Use 32-bit float consistently
3. **Library versions:** Pin scikit-learn==1.4.0 in requirements.txt

**Verification:**
```python
# Same input + same config = same output
output1 = pipeline.render(image)
output2 = pipeline.render(image)
assert np.array_equal(np.array(output1), np.array(output2))
```

## Pipeline 2: Pencil Sketch

**File:** `platform/pop-render/service/pipelines/pencil_sketch.py`

### Algorithm Overview

The Pencil Sketch pipeline creates realistic pencil drawing effects using grayscale inversion and Gaussian blur with color dodge blending. The technique simulates graphite on paper by leveraging the mathematical relationship between an image and its inverted, blurred counterpart.

**Visual Characteristics:**
- Realistic pencil strokes and hatching
- Paper grain texture effect
- Preserved detail in high-contrast areas
- Natural grayscale gradients
- Authentic hand-drawn appearance

### Algorithm Steps

#### Step 1: Grayscale Conversion

**Purpose:** Reduce image to intensity values

**Process:**
1. Convert RGB to grayscale using luminosity method
2. Formula: `Gray = 0.299R + 0.587G + 0.114B`
3. Result: Single-channel 8-bit image (0-255)

**Code:**
```python
from PIL import Image

gray = image.convert('L')
```

**Output Mode Options:**
- `'L'`: Grayscale sketch (default)
- `'RGB'`: Colored sketch (grayscale applied to each channel equally)

#### Step 2: Inversion

**Purpose:** Create negative image for dodge blending

**Process:**
1. Invert each pixel: `inverted = 255 - pixel`
2. Dark areas become light, light areas become dark

**Code:**
```python
from PIL import ImageOps

inverted = ImageOps.invert(gray)
```

**Mathematical Effect:**
- Black (0) → White (255)
- White (255) → Black (0)
- Mid-gray (128) → Mid-gray (127)

#### Step 3: Gaussian Blur

**Purpose:** Create soft, diffused negative for blending

**Process:**
1. Apply Gaussian blur with sigma parameter
2. Convolution with Gaussian kernel: `G(x,y) = (1/2πσ²) * e^(-(x²+y²)/2σ²)`
3. Larger sigma = more blur = softer sketch strokes

**Parameters:**
- `sigma`: Blur intensity (default: 21)

**Code:**
```python
from scipy.ndimage import gaussian_filter

blurred = gaussian_filter(inverted, sigma=sigma)
```

**Determinism:** SciPy's Gaussian filter is deterministic (no random sampling)

#### Step 4: Color Dodge Blend

**Purpose:** Blend base and inverted-blurred images to create sketch effect

**Process:**
1. For each pixel: `result = (base / (255 - blend)) × 255`
2. Clip values to [0, 255] range
3. Handle divide-by-zero: If `blend=255`, set `result=255`

**Code:**
```python
def color_dodge_blend(base, blend):
    # Avoid divide by zero
    blend = 255 - blend
    blend[blend == 0] = 1

    # Color dodge formula
    result = (base.astype(float) / blend.astype(float)) * 255.0
    result = np.clip(result, 0, 255).astype('uint8')
    return result

sketch = color_dodge_blend(gray_array, blurred_array)
```

**Blending Effect:**
- Where base is dark and blend is light: Dark pencil strokes
- Where base is light and blend is dark: Light paper texture
- Gradient transitions create shading effect

#### Step 5: Contrast Adjustment

**Purpose:** Enhance sketch definition

**Process:**
1. Apply contrast enhancement
2. Formula: `output = (input - 128) × factor + 128`
3. Clip to [0, 255] range

**Parameters:**
- `contrast_factor`: Contrast multiplier (default: 1.3)

**Code:**
```python
from PIL import ImageEnhance

enhancer = ImageEnhance.Contrast(sketch)
sketch = enhancer.enhance(contrast_factor)
```

**Effect:**
- `factor=1.0`: No change
- `factor=1.3`: 30% more contrast (default)
- `factor=1.5`: Very high contrast (may lose mid-tones)

### Default Configuration

```python
{
    'sigma': 21,              # Gaussian blur intensity
    'contrast_factor': 1.3,   # Contrast adjustment
    'output_mode': 'L'        # 'L' for grayscale, 'RGB' for color
}
```

### Parameter Tuning Guide

**Blur Intensity (`sigma`):**
- `sigma=10`: Fine detail, thin pencil lines
- `sigma=21`: Balanced detail and softness (default)
- `sigma=30`: Soft, charcoal-like strokes
- `sigma=50`: Very soft, minimal detail

**Contrast (`contrast_factor`):**
- `1.0`: Natural, subtle sketch
- `1.3`: Enhanced definition (default)
- `1.5`: High contrast, dramatic sketch
- `1.8`: Very high contrast (may lose mid-tones)

**Output Mode (`output_mode`):**
- `'L'`: True grayscale sketch
- `'RGB'`: Colored sketch preserving original hues

### Example Input/Output

**Input Image:**
- Format: JPEG, 4000x3000px
- Subject: Landscape photograph
- Colors: Vibrant blues and greens

**Processing:**
- Converted to grayscale (if output_mode='L')
- Inverted and blurred with sigma=21
- Color dodge blend creates pencil strokes
- Contrast enhanced by 30%

**Output Image:**
- Format: TIFF, 300 DPI, LZW compression
- Style: Realistic pencil sketch on white paper
- Detail: Fine lines in high-contrast areas, soft shading in gradients
- File size: ~25-40MB (TIFF), ~150-300KB (JPEG preview)

### Determinism Guarantees

**Sources of Non-Determinism (Eliminated):**
1. **Gaussian blur:** Deterministic convolution (scipy)
2. **Color dodge:** Pure arithmetic operations
3. **Contrast adjustment:** Deterministic linear transformation

**Verification:**
```python
# Identical results across runs
output1 = pipeline.render(image)
output2 = pipeline.render(image)
assert np.array_equal(np.array(output1), np.array(output2))
```

## Pipeline 3: Between The Lines

**File:** `platform/pop-render/service/pipelines/between_lines.py`

### Algorithm Overview

The Between The Lines pipeline creates stylized line art with directional motion blur following image contours. It uses Sobel edge detection to identify gradients, then applies motion blur along gradient directions to create parallel hatching effects reminiscent of technical drawings and engravings.

**Visual Characteristics:**
- Directional line work following contours
- Parallel hatching creates shading
- Clean, technical drawing aesthetic
- Posterized gray levels for simplified tones
- Architectural/engineering drawing style

### Algorithm Steps

#### Step 1: Sobel Edge Detection

**Purpose:** Compute intensity gradients in X and Y directions

**Process:**
1. Convert image to grayscale
2. Apply Sobel operator in X direction (horizontal edges)
3. Apply Sobel operator in Y direction (vertical edges)
4. Compute gradient magnitude: `magnitude = sqrt(Gx² + Gy²)`
5. Compute gradient direction: `angle = atan2(Gy, Gx)`

**Code:**
```python
import cv2
import numpy as np

gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)

# Sobel gradients
sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)

# Gradient magnitude and direction
magnitude = np.sqrt(sobelx**2 + sobely**2)
angle = np.arctan2(sobely, sobelx)
```

**Sobel Kernels:**
- X-direction: `[[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]]`
- Y-direction: `[[-1, -2, -1], [0, 0, 0], [1, 2, 1]]`

#### Step 2: Gradient Direction Calculation

**Purpose:** Determine blur direction perpendicular to edges

**Process:**
1. For each pixel, compute gradient angle in radians
2. Rotate angle by 90° to get perpendicular direction
3. Perpendicular direction creates hatching along contours

**Code:**
```python
# Rotate by 90 degrees for perpendicular hatching
blur_angle = angle + np.pi / 2
```

**Direction Mapping:**
- Edge pointing right (0°) → Blur vertically (90°)
- Edge pointing up (90°) → Blur horizontally (0°)
- Edge pointing left (180°) → Blur vertically (270°)
- Edge pointing down (270°) → Blur horizontally (180°)

#### Step 3: Directional Motion Blur

**Purpose:** Apply motion blur along gradient directions

**Process:**
1. For each pixel with significant gradient (magnitude > threshold):
   - Create motion blur kernel along gradient direction
   - Kernel length = `blur_length` pixels
   - Apply kernel as convolution
2. Skip pixels with low gradient (flat regions)

**Parameters:**
- `blur_length`: Motion blur kernel length (default: 15)
- `edge_threshold`: Minimum gradient magnitude to blur (default: 30)

**Code:**
```python
def create_motion_kernel(length, angle):
    """Create directional motion blur kernel"""
    kernel = np.zeros((length, length))
    center = length // 2

    # Draw line along angle
    for i in range(length):
        offset = i - center
        x = int(center + offset * np.cos(angle))
        y = int(center + offset * np.sin(angle))
        if 0 <= x < length and 0 <= y < length:
            kernel[y, x] = 1

    # Normalize
    kernel = kernel / np.sum(kernel)
    return kernel

# Apply per-pixel directional blur
for y in range(height):
    for x in range(width):
        if magnitude[y, x] > edge_threshold:
            kernel = create_motion_kernel(blur_length, blur_angle[y, x])
            # Apply kernel to neighborhood
            output[y, x] = apply_kernel(image, x, y, kernel)
```

**Performance Note:** Per-pixel kernel creation is computationally expensive. Implementation may use binned angles (e.g., 8 directions) with pre-computed kernels for efficiency.

#### Step 4: Posterization

**Purpose:** Reduce to discrete gray levels for artistic effect

**Process:**
1. Map continuous gray values [0-255] to discrete levels
2. Formula: `level = floor(gray / (256 / num_levels)) × (256 / num_levels)`
3. Creates flat tonal regions

**Parameters:**
- `num_levels`: Number of gray levels (default: 4)

**Code:**
```python
def posterize(image, num_levels):
    # Compute level step
    step = 256 // num_levels

    # Quantize to levels
    posterized = (image // step) * step

    return posterized.astype('uint8')

output = posterize(blurred, num_levels)
```

**Level Examples:**
- `num_levels=2`: Black and white only
- `num_levels=4`: Black, dark gray, light gray, white (default)
- `num_levels=8`: More nuanced shading

### Default Configuration

```python
{
    'blur_length': 15,        # Motion blur kernel length (pixels)
    'num_levels': 4,          # Posterization gray levels
    'edge_threshold': 30      # Min gradient magnitude to apply blur
}
```

### Parameter Tuning Guide

**Blur Length (`blur_length`):**
- `10`: Short, subtle hatching lines
- `15`: Balanced line length (default)
- `25`: Long, dramatic hatching strokes
- `40`: Very long strokes (architectural style)

**Posterization (`num_levels`):**
- `2`: Pure black and white, high contrast
- `4`: Classic line art with shading (default)
- `6`: More gradual tonal transitions
- `8`: Near-continuous shading

**Edge Threshold (`edge_threshold`):**
- `10`: Blur applied everywhere, busy appearance
- `30`: Only significant edges blurred (default)
- `50`: Only strongest edges, minimal hatching
- `70`: Very selective, clean look

### Example Input/Output

**Input Image:**
- Format: PNG, 3600x4800px
- Subject: Architectural photograph
- Features: Strong vertical and horizontal lines

**Processing:**
- Sobel detects edges and gradients
- Gradient directions computed (angles)
- Motion blur applied along contour directions
- Posterized to 4 gray levels

**Output Image:**
- Format: TIFF, 300 DPI, LZW compression
- Style: Technical drawing with parallel hatching
- Lines: Follow building contours and architectural features
- File size: ~20-35MB (TIFF), ~120-250KB (JPEG preview)

### Determinism Guarantees

**Sources of Non-Determinism (Eliminated):**
1. **Sobel operator:** Deterministic convolution (OpenCV)
2. **Gradient calculation:** Pure arithmetic
3. **Motion blur:** Deterministic kernel convolution
4. **Posterization:** Deterministic quantization

**Verification:**
```python
# Consistent results
output1 = pipeline.render(image)
output2 = pipeline.render(image)
assert np.array_equal(np.array(output1), np.array(output2))
```

## Algorithm Versioning Strategy

### Version Tracking

Each algorithm implementation is versioned to ensure reproducibility and allow algorithm evolution without breaking existing renders.

**Versioning Scheme:** Semantic versioning (MAJOR.MINOR.PATCH)

- **MAJOR:** Breaking changes to algorithm output (different visual result)
- **MINOR:** New features/parameters (backward compatible)
- **PATCH:** Bug fixes, performance improvements (output unchanged)

**Database Schema:**
```sql
ALTER TABLE styles ADD COLUMN algorithm_version VARCHAR(20) DEFAULT '1.0.0';
ALTER TABLE renders ADD COLUMN algorithm_version VARCHAR(20);
```

**Version Recording:**
```python
class PopPosterPipeline(RenderPipeline):
    VERSION = "1.0.0"

    def render(self, image: Image.Image) -> Image.Image:
        # Record version in render metadata
        self._version = self.VERSION
        # ... processing ...
```

**Usage in Worker:**
```python
def process_render(render_id, asset_id, style_id, size_preset_id):
    pipeline = get_pipeline(style_slug, algorithm_config)
    output = pipeline.render(input_image)

    # Store algorithm version in DB
    update_render(
        render_id,
        algorithm_version=pipeline.VERSION,
        status='completed'
    )
```

### Version Migration Strategy

**Scenario 1: Bug Fix (Patch Version)**
- Example: Fix edge case in color dodge divide-by-zero
- Version: 1.0.0 → 1.0.1
- Action: Deploy immediately, no user impact
- Database: New renders use 1.0.1, old renders remain 1.0.0

**Scenario 2: New Feature (Minor Version)**
- Example: Add `edge_enhance` parameter to Pop Poster
- Version: 1.0.1 → 1.1.0
- Action: Update default config, add parameter validation
- Database: New renders use 1.1.0 with new parameter
- Backward Compatibility: Old configs without parameter still work

**Scenario 3: Algorithm Change (Major Version)**
- Example: Replace K-means with median cut in Pop Poster
- Version: 1.1.0 → 2.0.0
- Action: Create new pipeline class `PopPosterV2Pipeline`
- Database: Add new style entry `pop-poster-v2`
- Migration: Existing renders continue using v1, new renders offer v2
- User Communication: "New improved Pop Poster style available"

### Rollback Strategy

**Scenario:** Algorithm version causes issues in production

**Rollback Steps:**
1. Identify problematic version (e.g., 2.0.0)
2. Update style record to pin previous version:
   ```sql
   UPDATE styles
   SET algorithm_version='1.1.0'
   WHERE slug='pop-poster';
   ```
3. Restart workers to reload configuration
4. New renders use previous version
5. Investigate and fix issue
6. Deploy corrected version 2.0.1

### Reproducibility Guarantees

**Reprint Scenario:**
User requests reprint of render created 6 months ago.

**Guarantee:**
1. Original render record stores algorithm_version='1.2.0'
2. System loads pipeline version 1.2.0 from code
3. Applies same algorithm_config parameters
4. Produces pixel-perfect identical output

**Implementation:**
```python
def reprint_render(original_render_id):
    # Fetch original render details
    original = get_render(original_render_id)

    # Use same style, config, and version
    pipeline = get_pipeline_version(
        style_slug=original.style.slug,
        version=original.algorithm_version,
        algorithm_config=original.style.algorithm_config
    )

    # Render with identical parameters
    output = pipeline.render(source_image)

    # Output matches original exactly
    return output
```

## Comparative Algorithm Analysis

### Performance Comparison

| Pipeline | Avg Duration | Memory Usage | CPU Intensity | Complexity |
|----------|--------------|--------------|---------------|------------|
| Pop Poster | 45-60s | 800MB-1.2GB | High (K-means) | High |
| Pencil Sketch | 15-25s | 400MB-600MB | Low (blur) | Low |
| Between The Lines | 60-90s | 1GB-1.5GB | Very High (per-pixel) | Very High |

**Test Conditions:** 3000x4000px input, 4-core CPU, default configurations

### Quality Comparison

| Pipeline | Print Quality | Detail Retention | Color Accuracy | Artistic Appeal |
|----------|---------------|------------------|----------------|-----------------|
| Pop Poster | Excellent | Medium | Modified (posterized) | High (bold, vibrant) |
| Pencil Sketch | Excellent | High | N/A (grayscale) | High (realistic) |
| Between The Lines | Excellent | Medium | N/A (grayscale) | Medium (technical) |

### Use Case Recommendations

**Pop Poster:**
- **Best For:** Portraits, vibrant subjects, pop culture imagery
- **Print Sizes:** All sizes, especially large (16x20"+)
- **Target Audience:** Modern, bold aesthetic preferences
- **Examples:** Celebrity portraits, pet photos, colorful landscapes

**Pencil Sketch:**
- **Best For:** Portraits, detailed subjects, nostalgic imagery
- **Print Sizes:** Small to medium (9x12" to 16x20")
- **Target Audience:** Classic, elegant aesthetic preferences
- **Examples:** Family portraits, architectural details, still life

**Between The Lines:**
- **Best For:** Architecture, geometric subjects, technical illustrations
- **Print Sizes:** Medium to large (12x16" to 30x40")
- **Target Audience:** Modern, minimalist aesthetic preferences
- **Examples:** Building facades, mechanical objects, abstract patterns

## Configuration Best Practices

### Environment-Specific Configurations

**Development Environment:**
```python
{
    'k': 4,                # Faster K-means
    'sigma': 15,          # Less blur, faster processing
    'blur_length': 10,    # Shorter kernels
}
```

**Production Environment:**
```python
{
    'k': 8,                # Balanced quality
    'sigma': 21,          # Full quality blur
    'blur_length': 15,    # Standard kernel length
}
```

**High-Quality Production:**
```python
{
    'k': 12,               # Maximum color detail
    'sigma': 25,          # Very smooth gradients
    'blur_length': 20,    # Longer hatching strokes
}
```

### Performance Optimization

**CPU Optimization:**
- Use NumPy vectorized operations
- Avoid Python loops where possible
- Pre-compute constant values
- Enable OpenCV threading: `cv2.setNumThreads(4)`

**Memory Optimization:**
- Process in tiles for very large images
- Delete intermediate arrays: `del posterized_array`
- Use in-place operations where possible
- Convert to uint8 early to reduce memory

**Caching Strategy:**
```python
# Cache K-means models for common cluster counts
kmeans_cache = {
    4: KMeans(n_clusters=4, random_state=42),
    8: KMeans(n_clusters=8, random_state=42),
    12: KMeans(n_clusters=12, random_state=42),
}

# Reuse trained models where possible
kmeans = kmeans_cache.get(k) or KMeans(n_clusters=k, random_state=42)
```

## Testing & Validation

### Unit Testing

**Test Determinism:**
```python
def test_pop_poster_determinism():
    image = load_test_image()
    pipeline = PopPosterPipeline()

    output1 = pipeline.render(image)
    output2 = pipeline.render(image)

    assert np.array_equal(np.array(output1), np.array(output2))
```

**Test Parameter Validation:**
```python
def test_invalid_parameters():
    with pytest.raises(ValueError):
        PopPosterPipeline({'k': 0})  # Invalid cluster count

    with pytest.raises(ValueError):
        PencilSketchPipeline({'sigma': -5})  # Negative sigma
```

**Test Configuration Override:**
```python
def test_config_override():
    config = {'k': 12}
    pipeline = PopPosterPipeline(config)

    assert pipeline.config['k'] == 12
    assert pipeline.config['seed'] == 42  # Default preserved
```

### Visual Regression Testing

**Approach:**
1. Generate reference outputs with known-good algorithm versions
2. Store reference images and configurations
3. On code changes, regenerate outputs
4. Compare pixel-by-pixel or use perceptual metrics (SSIM, PSNR)

**Example:**
```python
def test_visual_regression_pop_poster():
    image = load_test_image()
    pipeline = PopPosterPipeline()
    output = pipeline.render(image)

    reference = load_reference_image('pop_poster_reference.tiff')

    # Exact pixel match
    assert np.array_equal(np.array(output), np.array(reference))

    # Or perceptual similarity
    ssim_score = compute_ssim(output, reference)
    assert ssim_score > 0.99
```

### Integration Testing

**Full Pipeline Test:**
```python
def test_full_render_pipeline():
    # Upload image
    response = client.post('/v1/renders', data={
        'file': open('test.jpg', 'rb'),
        'style_id': POP_POSTER_STYLE_ID,
        'size_preset_id': SIZE_9X12_ID,
    })
    assert response.status_code == 201
    render_id = response.json['render_id']

    # Wait for completion
    for _ in range(60):
        status = client.get(f'/v1/renders/{render_id}').json
        if status['status'] == 'completed':
            break
        time.sleep(5)

    assert status['status'] == 'completed'
    assert status['duration_ms'] > 0

    # Download output
    download = client.get(f'/v1/renders/{render_id}/download').json
    assert 'url' in download
```

## Troubleshooting

### Common Issues

**Issue: K-means produces different results across runs**
- **Cause:** Non-deterministic random initialization
- **Solution:** Ensure `random_state=42` is set in KMeans
- **Verification:** Run same input twice, compare pixel arrays

**Issue: Out of memory during processing**
- **Cause:** Large image dimensions (>8000px)
- **Solution:**
  - Scale down before processing
  - Process in tiles
  - Increase worker memory limits

**Issue: Motion blur too slow**
- **Cause:** Per-pixel kernel creation is expensive
- **Solution:**
  - Bin angles to 8 directions with pre-computed kernels
  - Skip low-gradient pixels (increase edge_threshold)
  - Downsample, process, upsample

**Issue: Output too dark/light**
- **Cause:** Color space or gamma mismatch
- **Solution:**
  - Ensure sRGB color space throughout pipeline
  - Apply gamma correction if needed
  - Adjust contrast_factor parameter

**Issue: Edges not detected in Canny**
- **Cause:** Thresholds too high for low-contrast images
- **Solution:**
  - Lower canny_low and canny_high
  - Apply histogram equalization before edge detection
  - Increase image contrast preprocessing

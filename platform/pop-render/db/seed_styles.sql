-- ASO Render Styles Seed Data
-- Populates the styles table with initial artistic rendering algorithms
-- Created for WP-129

SET search_path TO aso_render, public;

-- Clear existing styles (optional - uncomment if you want to reset)
-- TRUNCATE TABLE styles CASCADE;

-- Insert styles
INSERT INTO styles (name, slug, algorithm_config, description) VALUES
(
    'Pop Poster',
    'pop-poster',
    '{
        "algorithm": "posterize",
        "params": {
            "color_levels": 8,
            "edge_detection": true,
            "edge_threshold": 128,
            "edge_thickness": 2,
            "saturation_boost": 1.3,
            "contrast_enhance": 1.2,
            "style_preset": "pop_art"
        },
        "processing": {
            "bilateral_filter": {
                "enabled": true,
                "d": 9,
                "sigma_color": 75,
                "sigma_space": 75
            },
            "color_quantization": {
                "method": "kmeans",
                "clusters": 8
            }
        },
        "output": {
            "format": "PNG",
            "quality": 95,
            "color_space": "sRGB"
        }
    }'::jsonb,
    'Bold, vibrant pop art style with reduced color palette and strong outlines. Creates poster-like effect with enhanced colors and simplified shapes reminiscent of 1960s pop art movement.'
),
(
    'Pencil Sketch',
    'pencil-sketch',
    '{
        "algorithm": "sketch",
        "params": {
            "edge_method": "dog",
            "sigma1": 0.5,
            "sigma2": 1.0,
            "threshold": 0.05,
            "invert": true,
            "line_darkness": 0.8,
            "texture_overlay": "paper_grain"
        },
        "processing": {
            "grayscale": true,
            "gaussian_blur": {
                "enabled": true,
                "kernel_size": 3,
                "sigma": 0.8
            },
            "adaptive_threshold": {
                "enabled": false
            }
        },
        "output": {
            "format": "PNG",
            "quality": 95,
            "color_space": "Grayscale"
        }
    }'::jsonb,
    'Realistic pencil sketch effect using edge detection and texture overlay. Converts images to grayscale with natural pencil-like strokes and subtle paper grain texture.'
),
(
    'Between The Lines',
    'between-the-lines',
    '{
        "algorithm": "line_art",
        "params": {
            "line_density": "medium",
            "line_direction": "contour_following",
            "line_thickness": 1.5,
            "spacing": 3,
            "angle_variation": 15,
            "edge_emphasis": 0.7,
            "background_color": "#FFFFFF"
        },
        "processing": {
            "edge_detection": {
                "method": "canny",
                "low_threshold": 50,
                "high_threshold": 150
            },
            "contour_analysis": {
                "enabled": true,
                "min_area": 100
            },
            "hatch_pattern": {
                "style": "cross_hatch",
                "density_map": true
            }
        },
        "output": {
            "format": "PNG",
            "quality": 95,
            "color_space": "Grayscale"
        }
    }'::jsonb,
    'Artistic line work with parallel hatching and cross-hatching. Creates depth and form through varying line density following the contours of the subject, similar to traditional pen and ink illustration techniques.'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    algorithm_config = EXCLUDED.algorithm_config,
    description = EXCLUDED.description;

-- Verify insertion
DO $$
DECLARE
    style_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO style_count FROM styles;
    RAISE NOTICE 'Seeded % styles', style_count;
END $$;

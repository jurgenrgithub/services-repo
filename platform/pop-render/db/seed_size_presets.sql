-- ASO Render Size Presets Seed Data
-- Populates the size_presets table with standard print sizes
-- Created for WP-129
-- All presets are at 300 DPI for high-quality print output

SET search_path TO aso_render, public;

-- Clear existing size presets (optional - uncomment if you want to reset)
-- TRUNCATE TABLE size_presets CASCADE;

-- Insert standard print size presets at 300 DPI
INSERT INTO size_presets (name, width_inches, height_inches, dpi) VALUES
    ('9x12', 9.00, 12.00, 300),
    ('12x16', 12.00, 16.00, 300),
    ('16x20', 16.00, 20.00, 300),
    ('20x24', 20.00, 24.00, 300),
    ('30x40', 30.00, 40.00, 300)
ON CONFLICT DO NOTHING;

-- Verify insertion
DO $$
DECLARE
    preset_count INTEGER;
    preset_rec RECORD;
BEGIN
    SELECT COUNT(*) INTO preset_count FROM size_presets;
    RAISE NOTICE 'Seeded % size presets at 300 DPI:', preset_count;

    FOR preset_rec IN
        SELECT name, width_inches, height_inches, dpi,
               (width_inches * dpi)::INTEGER as width_px,
               (height_inches * dpi)::INTEGER as height_px
        FROM size_presets
        ORDER BY width_inches * height_inches
    LOOP
        RAISE NOTICE '  % (%"x%") = %x% pixels',
            preset_rec.name,
            preset_rec.width_inches,
            preset_rec.height_inches,
            preset_rec.width_px,
            preset_rec.height_px;
    END LOOP;
END $$;

-- ASO Render Database Schema
-- This schema manages image rendering pipeline for artistic style transformations
-- Created for WP-129

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create schema
CREATE SCHEMA IF NOT EXISTS aso_render;

SET search_path TO aso_render, public;

-- ============================================================================
-- TABLES
-- ============================================================================

-- assets: Source images uploaded for rendering
CREATE TABLE IF NOT EXISTS assets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR(255) NOT NULL,
    minio_key VARCHAR(512) NOT NULL UNIQUE,
    format VARCHAR(50) NOT NULL,
    width_px INTEGER NOT NULL CHECK (width_px > 0),
    height_px INTEGER NOT NULL CHECK (height_px > 0),
    file_size_bytes BIGINT NOT NULL CHECK (file_size_bytes > 0),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE assets IS 'Source images uploaded for artistic rendering';
COMMENT ON COLUMN assets.id IS 'Unique identifier for the asset';
COMMENT ON COLUMN assets.filename IS 'Original filename from upload';
COMMENT ON COLUMN assets.minio_key IS 'Object storage key in MinIO';
COMMENT ON COLUMN assets.format IS 'Image format (e.g., JPEG, PNG, TIFF)';
COMMENT ON COLUMN assets.width_px IS 'Image width in pixels';
COMMENT ON COLUMN assets.height_px IS 'Image height in pixels';
COMMENT ON COLUMN assets.file_size_bytes IS 'File size in bytes';

-- styles: Artistic rendering algorithms and configurations
CREATE TABLE IF NOT EXISTS styles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    algorithm_config JSONB NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE styles IS 'Artistic rendering styles with algorithm configurations';
COMMENT ON COLUMN styles.id IS 'Unique identifier for the style';
COMMENT ON COLUMN styles.name IS 'Human-readable style name';
COMMENT ON COLUMN styles.slug IS 'URL-safe identifier for the style';
COMMENT ON COLUMN styles.algorithm_config IS 'JSON configuration for rendering algorithm';
COMMENT ON COLUMN styles.description IS 'Detailed description of the style effect';

-- size_presets: Predefined output dimensions for print sizes
CREATE TABLE IF NOT EXISTS size_presets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    width_inches DECIMAL(6,2) NOT NULL CHECK (width_inches > 0),
    height_inches DECIMAL(6,2) NOT NULL CHECK (height_inches > 0),
    dpi INTEGER NOT NULL CHECK (dpi > 0),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE size_presets IS 'Predefined print sizes with DPI settings';
COMMENT ON COLUMN size_presets.id IS 'Unique identifier for the size preset';
COMMENT ON COLUMN size_presets.name IS 'Display name for the size (e.g., "9x12")';
COMMENT ON COLUMN size_presets.width_inches IS 'Output width in inches';
COMMENT ON COLUMN size_presets.height_inches IS 'Output height in inches';
COMMENT ON COLUMN size_presets.dpi IS 'Dots per inch for print quality';

-- renders: Tracking table for render jobs and outputs
CREATE TABLE IF NOT EXISTS renders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    style_id UUID NOT NULL REFERENCES styles(id) ON DELETE RESTRICT,
    size_preset_id UUID NOT NULL REFERENCES size_presets(id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL CHECK (status IN ('queued', 'started', 'completed', 'failed')),
    rq_job_id VARCHAR(100),
    output_minio_key VARCHAR(512),
    preview_minio_key VARCHAR(512),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER CHECK (duration_ms >= 0),
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE renders IS 'Render job tracking with status and outputs';
COMMENT ON COLUMN renders.id IS 'Unique identifier for the render job';
COMMENT ON COLUMN renders.asset_id IS 'Reference to source asset';
COMMENT ON COLUMN renders.style_id IS 'Reference to rendering style';
COMMENT ON COLUMN renders.size_preset_id IS 'Reference to output size preset';
COMMENT ON COLUMN renders.status IS 'Current job status: queued, started, completed, failed';
COMMENT ON COLUMN renders.rq_job_id IS 'Redis Queue job identifier for background processing';
COMMENT ON COLUMN renders.output_minio_key IS 'MinIO key for final rendered output';
COMMENT ON COLUMN renders.preview_minio_key IS 'MinIO key for preview/thumbnail';
COMMENT ON COLUMN renders.started_at IS 'Timestamp when rendering started';
COMMENT ON COLUMN renders.completed_at IS 'Timestamp when rendering completed or failed';
COMMENT ON COLUMN renders.duration_ms IS 'Total processing time in milliseconds';
COMMENT ON COLUMN renders.error_message IS 'Error details if status is failed';
COMMENT ON COLUMN renders.metadata IS 'Additional metadata about the render (parameters, settings, etc.)';

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Assets indexes
CREATE INDEX IF NOT EXISTS idx_assets_created_at ON assets(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_assets_format ON assets(format);

-- Styles indexes
CREATE INDEX IF NOT EXISTS idx_styles_slug ON styles(slug);

-- Renders indexes
CREATE INDEX IF NOT EXISTS idx_renders_asset_id ON renders(asset_id);
CREATE INDEX IF NOT EXISTS idx_renders_style_id ON renders(style_id);
CREATE INDEX IF NOT EXISTS idx_renders_size_preset_id ON renders(size_preset_id);
CREATE INDEX IF NOT EXISTS idx_renders_status ON renders(status);
CREATE INDEX IF NOT EXISTS idx_renders_created_at ON renders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_renders_rq_job_id ON renders(rq_job_id) WHERE rq_job_id IS NOT NULL;

-- Composite index for common queries
CREATE INDEX IF NOT EXISTS idx_renders_status_created ON renders(status, created_at DESC);

-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update updated_at on renders table
DROP TRIGGER IF EXISTS update_renders_updated_at ON renders;
CREATE TRIGGER update_renders_updated_at
    BEFORE UPDATE ON renders
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- GRANTS (adjust based on your application user)
-- ============================================================================

-- Grant usage on schema
-- GRANT USAGE ON SCHEMA aso_render TO your_app_user;

-- Grant table permissions
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA aso_render TO your_app_user;

-- Grant sequence permissions for UUID generation
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA aso_render TO your_app_user;

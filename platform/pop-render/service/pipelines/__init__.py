"""
Rendering pipeline system for ASO pop-render service.

This module provides a pluggable architecture for image rendering pipelines
with deterministic output, parameter overrides, and enterprise-grade observability.
"""

import logging
import time
import tempfile
import os
from typing import Optional
from PIL import Image

from .base import RenderPipeline
from .pop_poster import PopPosterPipeline
from .pencil_sketch import PencilSketchPipeline
from .between_lines import BetweenLinesPipeline
from monitoring import track_render_job

logger = logging.getLogger(__name__)

__all__ = [
    'RenderPipeline',
    'PopPosterPipeline',
    'PencilSketchPipeline',
    'BetweenLinesPipeline',
    'process_render',
]


# Mapping of style slugs to pipeline classes
PIPELINE_MAP = {
    'pop-poster': PopPosterPipeline,
    'pencil-sketch': PencilSketchPipeline,
    'between-the-lines': BetweenLinesPipeline,
}


def process_render(
    render_id: str,
    asset_id: str,
    style_id: str,
    size_preset_id: str,
) -> dict:
    """
    Background job function to process a render.

    This function is enqueued in RQ and processes the render asynchronously.
    It updates the database with progress and results.

    Args:
        render_id: UUID of the render record
        asset_id: UUID of the source asset
        style_id: UUID of the rendering style
        size_preset_id: UUID of the output size preset

    Returns:
        Result dictionary with status and output keys

    Raises:
        Exception: If rendering fails
    """
    from database import get_db_pool
    from database import db_pool as db_pool_global
    from storage import get_storage_client
    from storage import storage_client as storage_global

    start_time = time.time()
    
    # Auto-initialize for worker context (RQ workers dont go through app init)
    if not db_pool_global._initialized:
        logger.info("Initializing database pool for worker")
        db_pool_global.initialize()
    if not storage_global._initialized:
        logger.info("Initializing storage client for worker")
        storage_global.initialize()
    
    db_pool = get_db_pool()
    storage = get_storage_client()

    logger.info(
        "Starting render processing",
        extra={
            "render_id": render_id,
            "asset_id": asset_id,
            "style_id": style_id,
            "size_preset_id": size_preset_id,
        },
    )

    try:
        # Update status to 'started'
        with db_pool.get_connection() as conn:
            with db_pool.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    UPDATE aso_render.renders
                    SET status = 'started', started_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (render_id,)
                )

        # Fetch render details
        with db_pool.get_connection() as conn:
            with db_pool.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        a.minio_key as asset_key,
                        s.slug as style_slug,
                        s.algorithm_config,
                        sp.width_inches,
                        sp.height_inches,
                        sp.dpi
                    FROM aso_render.renders r
                    JOIN aso_render.assets a ON r.asset_id = a.id
                    JOIN aso_render.styles s ON r.style_id = s.id
                    JOIN aso_render.size_presets sp ON r.size_preset_id = sp.id
                    WHERE r.id = %s
                    """,
                    (render_id,)
                )
                render_data = cursor.fetchone()

                if not render_data:
                    raise ValueError(f"Render not found: {render_id}")

        # Get pipeline class
        pipeline_class = PIPELINE_MAP.get(render_data['style_slug'])
        if not pipeline_class:
            raise ValueError(f"Unknown style: {render_data['style_slug']}")

        # Download source asset
        with tempfile.NamedTemporaryFile(suffix='.tmp', delete=False) as tmp_input:
            input_path = tmp_input.name
            storage.download_file(render_data['asset_key'], input_path)

        try:
            # Calculate target dimensions
            target_width = int(render_data['width_inches'] * render_data['dpi'])
            target_height = int(render_data['height_inches'] * render_data['dpi'])

            # Create pipeline and process
            # Load the source image and upscale if needed
            from upscaler import upscale_image
            target_size = (target_width, target_height)
            source_image = Image.open(input_path)
            # Upscale source image if needed for target print size
            source_image = upscale_image(source_image, target_size)
            pipeline = pipeline_class()
            output_image = pipeline.render(source_image)

            # Resize to target dimensions
            if output_image.size != (target_width, target_height):
                output_image = output_image.resize(
                    (target_width, target_height),
                    Image.Resampling.LANCZOS
                )

            # Save output as TIFF
            with tempfile.NamedTemporaryFile(suffix='.tiff', delete=False) as tmp_output:
                output_path = tmp_output.name
                output_image.save(
                    output_path,
                    format='TIFF',
                    compression='lzw',
                    dpi=(render_data['dpi'], render_data['dpi'])
                )

            # Save preview as JPEG
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_preview:
                preview_path = tmp_preview.name
                # Create smaller preview (max 1200px wide)
                preview_width = min(1200, output_image.width)
                preview_height = int(output_image.height * (preview_width / output_image.width))
                preview_image = output_image.resize(
                    (preview_width, preview_height),
                    Image.Resampling.LANCZOS
                )
                preview_image.convert('RGB').save(
                    preview_path,
                    format='JPEG',
                    quality=85,
                    optimize=True
                )

            try:
                # Upload output to MinIO
                output_key = f"renders/{render_id}/output.tiff"
                storage.upload_file(output_path, output_key)

                preview_key = f"renders/{render_id}/preview.jpg"
                storage.upload_file(preview_path, preview_key)

                # Calculate duration
                duration_ms = int((time.time() - start_time) * 1000)

                # Update database with completion
                with db_pool.get_connection() as conn:
                    with db_pool.get_cursor(conn) as cursor:
                        cursor.execute(
                            """
                            UPDATE aso_render.renders
                            SET status = 'completed',
                                output_minio_key = %s,
                                preview_minio_key = %s,
                                completed_at = CURRENT_TIMESTAMP,
                                duration_ms = %s
                            WHERE id = %s
                            """,
                            (output_key, preview_key, duration_ms, render_id)
                        )

                # Track successful completion metrics
                duration_seconds = duration_ms / 1000.0
                track_render_job(
                    status='completed',
                    style=render_data['style_slug'],
                    duration_seconds=duration_seconds,
                )

                logger.info(
                    "Render completed successfully",
                    extra={
                        "render_id": render_id,
                        "duration_ms": duration_ms,
                        "output_key": output_key,
                    },
                )

                return {
                    "status": "completed",
                    "output_key": output_key,
                    "preview_key": preview_key,
                    "duration_ms": duration_ms,
                }

            finally:
                # Clean up temp files
                for path in [output_path, preview_path]:
                    try:
                        os.unlink(path)
                    except:
                        pass

        finally:
            # Clean up input temp file
            try:
                os.unlink(input_path)
            except:
                pass

    except Exception as e:
        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Track failure metrics (need to fetch style_slug if not already available)
        style_slug = 'unknown'
        try:
            # Try to get style_slug from render_data if it exists
            if 'render_data' in locals() and render_data:
                style_slug = render_data.get('style_slug', 'unknown')
        except:
            pass

        track_render_job(
            status='failed',
            style=style_slug,
            duration_seconds=0.0,
        )

        logger.error(
            "Render failed",
            extra={
                "render_id": render_id,
                "error": str(e),
                "duration_ms": duration_ms,
            },
        )

        # Update database with failure
        try:
            with db_pool.get_connection() as conn:
                with db_pool.get_cursor(conn) as cursor:
                    cursor.execute(
                        """
                        UPDATE aso_render.renders
                        SET status = 'failed',
                            error_message = %s,
                            completed_at = CURRENT_TIMESTAMP,
                            duration_ms = %s
                        WHERE id = %s
                        """,
                        (str(e), duration_ms, render_id)
                    )
        except Exception as db_error:
            logger.error(
                "Failed to update render status",
                extra={"render_id": render_id, "error": str(db_error)},
            )

        raise

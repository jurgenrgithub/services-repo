"""
Render endpoints for ASO Render Service.

Provides REST API for creating render jobs, checking status, and downloading outputs.
"""

import logging
import time
import uuid
from flask import request, jsonify
from werkzeug.exceptions import RequestEntityTooLarge

from routes import v1_bp
from database import get_db_pool
from storage import get_storage_client
from queue import get_queue_manager
from validation import (
    validate_image_upload,
    validate_uuid,
    validate_style_exists,
    validate_size_preset_exists,
)

logger = logging.getLogger(__name__)


@v1_bp.route('/renders', methods=['POST'])
def create_render():
    """
    Create a new render job.

    Accepts multipart/form-data with:
    - file: Image file (required)
    - style_id: UUID of rendering style (required)
    - size_preset_id: UUID of output size preset (required)

    Returns:
        201: {render_id, status, created_at}
        400: Validation error
        413: File too large
        500: Server error
    """
    start_time = time.time()

    try:
        # Validate request has file
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files['file']

        # Validate form fields
        style_id = request.form.get('style_id')
        size_preset_id = request.form.get('size_preset_id')

        if not style_id:
            return jsonify({"error": "style_id is required"}), 400

        if not size_preset_id:
            return jsonify({"error": "size_preset_id is required"}), 400

        # Validate image upload
        try:
            image_format, width, height, file_size = validate_image_upload(file)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        # Validate style exists
        try:
            style = validate_style_exists(style_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        # Validate size preset exists
        try:
            size_preset = validate_size_preset_exists(size_preset_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        # Generate IDs
        asset_id = str(uuid.uuid4())
        render_id = str(uuid.uuid4())

        # Store file in MinIO with uploads/ prefix
        storage = get_storage_client()
        original_filename = file.filename
        minio_key = f"uploads/{asset_id}/{original_filename}"

        try:
            file.seek(0)  # Reset file pointer
            storage.upload_fileobj(
                file,
                minio_key,
                metadata={
                    'original_filename': original_filename,
                    'asset_id': asset_id,
                    'content_type': file.content_type or 'application/octet-stream',
                }
            )
        except Exception as e:
            logger.error(
                "Failed to upload file to MinIO",
                extra={"error": str(e), "asset_id": asset_id},
            )
            return jsonify({"error": "Failed to store uploaded file"}), 500

        # Insert asset record
        db_pool = get_db_pool()
        try:
            with db_pool.get_connection() as conn:
                with db_pool.get_cursor(conn) as cursor:
                    # Insert asset
                    cursor.execute(
                        """
                        INSERT INTO aso_render.assets
                        (id, filename, minio_key, format, width_px, height_px, file_size_bytes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING created_at
                        """,
                        (asset_id, original_filename, minio_key, image_format,
                         width, height, file_size)
                    )
                    result = cursor.fetchone()
                    created_at = result['created_at']

                    # Insert render record
                    cursor.execute(
                        """
                        INSERT INTO aso_render.renders
                        (id, asset_id, style_id, size_preset_id, status)
                        VALUES (%s, %s, %s, %s, 'queued')
                        RETURNING created_at
                        """,
                        (render_id, asset_id, style_id, size_preset_id)
                    )
                    render_created_at = cursor.fetchone()['created_at']

        except Exception as e:
            logger.error(
                "Failed to insert database records",
                extra={"error": str(e), "asset_id": asset_id, "render_id": render_id},
            )
            # Try to clean up uploaded file
            try:
                storage.delete_file(minio_key)
            except:
                pass
            return jsonify({"error": "Failed to create render record"}), 500

        # Enqueue RQ job
        queue_mgr = get_queue_manager()
        try:
            job = queue_mgr.enqueue_render(
                render_id=render_id,
                asset_id=asset_id,
                style_id=style_id,
                size_preset_id=size_preset_id,
            )

            # Update render record with RQ job ID
            with db_pool.get_connection() as conn:
                with db_pool.get_cursor(conn) as cursor:
                    cursor.execute(
                        "UPDATE aso_render.renders SET rq_job_id = %s WHERE id = %s",
                        (job.id, render_id)
                    )

        except Exception as e:
            logger.error(
                "Failed to enqueue render job",
                extra={"error": str(e), "render_id": render_id},
            )
            # Don't fail the request - job is still queued in DB and can be retried
            pass

        # Calculate response time
        duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "Render created successfully",
            extra={
                "render_id": render_id,
                "asset_id": asset_id,
                "style_id": style_id,
                "size_preset_id": size_preset_id,
                "duration_ms": duration_ms,
            },
        )

        return jsonify({
            "render_id": render_id,
            "status": "queued",
            "created_at": render_created_at.isoformat(),
        }), 201

    except RequestEntityTooLarge:
        return jsonify({"error": "File too large (maximum 50MB)"}), 413
    except Exception as e:
        logger.error(
            "Unexpected error in create_render",
            extra={"error": str(e)},
        )
        return jsonify({"error": "Internal server error"}), 500


@v1_bp.route('/renders/<render_id>', methods=['GET'])
def get_render(render_id: str):
    """
    Get render job status and details.

    Returns:
        200: Render details
        400: Invalid render_id
        404: Render not found
        500: Server error
    """
    try:
        # Validate UUID
        try:
            validated_id = validate_uuid(render_id, "render_id")
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        # Fetch render from database
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            with db_pool.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        r.id,
                        r.status,
                        r.asset_id,
                        r.style_id,
                        r.size_preset_id,
                        r.created_at,
                        r.started_at,
                        r.completed_at,
                        r.duration_ms,
                        r.error_message,
                        s.name as style_name,
                        s.slug as style_slug,
                        sp.name as size_preset_name,
                        sp.width_inches,
                        sp.height_inches,
                        sp.dpi
                    FROM aso_render.renders r
                    JOIN aso_render.styles s ON r.style_id = s.id
                    JOIN aso_render.size_presets sp ON r.size_preset_id = sp.id
                    WHERE r.id = %s
                    """,
                    (validated_id,)
                )
                render = cursor.fetchone()

                if not render:
                    return jsonify({"error": "Render not found"}), 404

                # Build response
                response = {
                    "id": str(render['id']),
                    "status": render['status'],
                    "asset_id": str(render['asset_id']),
                    "style": {
                        "id": str(render['style_id']),
                        "name": render['style_name'],
                        "slug": render['style_slug'],
                    },
                    "size_preset": {
                        "id": str(render['size_preset_id']),
                        "name": render['size_preset_name'],
                        "width_inches": float(render['width_inches']),
                        "height_inches": float(render['height_inches']),
                        "dpi": render['dpi'],
                    },
                    "created_at": render['created_at'].isoformat() if render['created_at'] else None,
                    "started_at": render['started_at'].isoformat() if render['started_at'] else None,
                    "completed_at": render['completed_at'].isoformat() if render['completed_at'] else None,
                    "duration_ms": render['duration_ms'],
                    "error_message": render['error_message'],
                }

                return jsonify(response), 200

    except Exception as e:
        logger.error(
            "Error fetching render",
            extra={"error": str(e), "render_id": render_id},
        )
        return jsonify({"error": "Internal server error"}), 500


@v1_bp.route('/renders/<render_id>/download', methods=['GET'])
def download_render(render_id: str):
    """
    Get presigned URL for downloading rendered TIFF output.

    Returns:
        200: {url, expires_in}
        400: Invalid render_id
        404: Render not found
        409: Render not completed
        500: Server error
    """
    try:
        # Validate UUID
        try:
            validated_id = validate_uuid(render_id, "render_id")
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        # Fetch render from database
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            with db_pool.get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT status, output_minio_key FROM aso_render.renders WHERE id = %s",
                    (validated_id,)
                )
                render = cursor.fetchone()

                if not render:
                    return jsonify({"error": "Render not found"}), 404

                if render['status'] != 'completed':
                    return jsonify({
                        "error": f"Render not completed (current status: {render['status']})"
                    }), 409

                if not render['output_minio_key']:
                    return jsonify({"error": "Output file not available"}), 404

                # Generate presigned URL (7-day expiry)
                storage = get_storage_client()
                expires_in = 7 * 24 * 60 * 60  # 7 days in seconds
                url = storage.get_presigned_url(
                    render['output_minio_key'],
                    expires_in=expires_in
                )

                return jsonify({
                    "url": url,
                    "expires_in": expires_in,
                }), 200

    except Exception as e:
        logger.error(
            "Error generating download URL",
            extra={"error": str(e), "render_id": render_id},
        )
        return jsonify({"error": "Internal server error"}), 500


@v1_bp.route('/renders/<render_id>/preview', methods=['GET'])
def preview_render(render_id: str):
    """
    Get presigned URL for downloading JPEG preview.

    Returns:
        200: {url, expires_in}
        400: Invalid render_id
        404: Render or preview not found
        500: Server error
    """
    try:
        # Validate UUID
        try:
            validated_id = validate_uuid(render_id, "render_id")
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        # Fetch render from database
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            with db_pool.get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT preview_minio_key FROM aso_render.renders WHERE id = %s",
                    (validated_id,)
                )
                render = cursor.fetchone()

                if not render:
                    return jsonify({"error": "Render not found"}), 404

                if not render['preview_minio_key']:
                    return jsonify({"error": "Preview not available"}), 404

                # Generate presigned URL (7-day expiry)
                storage = get_storage_client()
                expires_in = 7 * 24 * 60 * 60  # 7 days in seconds
                url = storage.get_presigned_url(
                    render['preview_minio_key'],
                    expires_in=expires_in
                )

                return jsonify({
                    "url": url,
                    "expires_in": expires_in,
                }), 200

    except Exception as e:
        logger.error(
            "Error generating preview URL",
            extra={"error": str(e), "render_id": render_id},
        )
        return jsonify({"error": "Internal server error"}), 500

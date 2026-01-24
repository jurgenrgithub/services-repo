"""
Input validation for ASO Render Service.

Provides enterprise-grade validation for uploads, UUIDs, and database references
with comprehensive error messages and security checks.
"""

import logging
import uuid
from typing import Optional, Tuple
from werkzeug.datastructures import FileStorage
from PIL import Image
from io import BytesIO

from database import get_db_pool

logger = logging.getLogger(__name__)

# Validation constants
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_IMAGE_DIMENSION = 10000  # 10000 pixels
SUPPORTED_FORMATS = {'JPEG', 'PNG', 'TIFF', 'BMP', 'WEBP'}
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.webp'}


def validate_uuid(value: str, field_name: str = "id") -> str:
    """
    Validate that a string is a valid UUID.

    Args:
        value: String to validate
        field_name: Name of the field for error messages

    Returns:
        Validated UUID string (normalized)

    Raises:
        ValueError: If value is not a valid UUID
    """
    if not value:
        raise ValueError(f"{field_name} is required")

    try:
        # Parse and normalize UUID
        parsed_uuid = uuid.UUID(value)
        return str(parsed_uuid)
    except (ValueError, AttributeError) as e:
        raise ValueError(f"{field_name} must be a valid UUID")


def validate_image_upload(file: FileStorage) -> Tuple[str, int, int, int]:
    """
    Validate an uploaded image file.

    Checks:
    - File is present
    - File size <= 50MB
    - File is a valid image format
    - Image dimensions <= 10000px
    - Image format is supported

    Args:
        file: Uploaded file from Flask request

    Returns:
        Tuple of (format, width, height, file_size)

    Raises:
        ValueError: If validation fails with specific error message
    """
    # Check file is present
    if not file:
        raise ValueError("No file provided")

    if not file.filename:
        raise ValueError("No file selected")

    # Check file extension
    filename_lower = file.filename.lower()
    if not any(filename_lower.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        raise ValueError(
            f"Unsupported file format. Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    # Read file data
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Reset to beginning

    # Check file size
    if file_size == 0:
        raise ValueError("File is empty")

    if file_size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE / (1024 * 1024)
        actual_mb = file_size / (1024 * 1024)
        raise ValueError(
            f"File size exceeds maximum of {max_mb:.0f}MB (uploaded: {actual_mb:.1f}MB)"
        )

    # Validate image using PIL
    try:
        file.seek(0)
        image = Image.open(file)
        image.verify()  # Verify it's a valid image

        # Re-open after verify (verify closes the file)
        file.seek(0)
        image = Image.open(file)

        # Check format
        if image.format not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported image format: {image.format}. "
                f"Supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}"
            )

        # Check dimensions
        width, height = image.size
        if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
            raise ValueError(
                f"Image dimensions exceed maximum of {MAX_IMAGE_DIMENSION}px "
                f"(uploaded: {width}x{height}px)"
            )

        if width == 0 or height == 0:
            raise ValueError("Invalid image dimensions")

        # Reset file pointer for later use
        file.seek(0)

        logger.debug(
            "Image validation successful",
            extra={
                "filename": file.filename,
                "format": image.format,
                "dimensions": f"{width}x{height}",
                "size_bytes": file_size,
            },
        )

        return image.format, width, height, file_size

    except ValueError:
        # Re-raise our validation errors
        raise
    except Exception as e:
        # Catch PIL errors and other issues
        raise ValueError(f"Invalid image file: {str(e)}")


def validate_style_exists(style_id: str) -> dict:
    """
    Validate that a style exists in the database.

    Args:
        style_id: UUID of the style

    Returns:
        Style record as dictionary

    Raises:
        ValueError: If style_id is invalid or style doesn't exist
    """
    # Validate UUID format
    validated_id = validate_uuid(style_id, "style_id")

    # Check database
    db_pool = get_db_pool()
    try:
        with db_pool.get_connection() as conn:
            with db_pool.get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT id, name, slug, algorithm_config FROM aso_render.styles WHERE id = %s",
                    (validated_id,)
                )
                style = cursor.fetchone()

                if not style:
                    raise ValueError(f"Style not found: {style_id}")

                return dict(style)
    except ValueError:
        # Re-raise our validation errors
        raise
    except Exception as e:
        logger.error(
            "Error validating style",
            extra={"error": str(e), "style_id": style_id},
        )
        raise ValueError(f"Error validating style: {str(e)}")


def validate_size_preset_exists(size_preset_id: str) -> dict:
    """
    Validate that a size preset exists in the database.

    Args:
        size_preset_id: UUID of the size preset

    Returns:
        Size preset record as dictionary

    Raises:
        ValueError: If size_preset_id is invalid or preset doesn't exist
    """
    # Validate UUID format
    validated_id = validate_uuid(size_preset_id, "size_preset_id")

    # Check database
    db_pool = get_db_pool()
    try:
        with db_pool.get_connection() as conn:
            with db_pool.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT id, name, width_inches, height_inches, dpi
                    FROM aso_render.size_presets
                    WHERE id = %s
                    """,
                    (validated_id,)
                )
                preset = cursor.fetchone()

                if not preset:
                    raise ValueError(f"Size preset not found: {size_preset_id}")

                return dict(preset)
    except ValueError:
        # Re-raise our validation errors
        raise
    except Exception as e:
        logger.error(
            "Error validating size preset",
            extra={"error": str(e), "size_preset_id": size_preset_id},
        )
        raise ValueError(f"Error validating size preset: {str(e)}")

"""
Tests for validation module.

Tests input validation for uploads, UUIDs, and database references.
"""

import pytest
import sys
import os
import io
from unittest.mock import Mock, patch, MagicMock
from PIL import Image

# Add service directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from validation import (
    validate_uuid,
    validate_image_upload,
    validate_style_exists,
    validate_size_preset_exists,
    MAX_FILE_SIZE,
    MAX_IMAGE_DIMENSION,
)


class TestValidateUUID:
    """Test UUID validation."""

    def test_valid_uuid(self):
        """Test that valid UUIDs are accepted."""
        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
        result = validate_uuid(valid_uuid)
        assert result == valid_uuid

    def test_valid_uuid_normalization(self):
        """Test that UUIDs are normalized."""
        uuid_upper = "550E8400-E29B-41D4-A716-446655440000"
        result = validate_uuid(uuid_upper)
        assert result == "550e8400-e29b-41d4-a716-446655440000"

    def test_invalid_uuid(self):
        """Test that invalid UUIDs are rejected."""
        with pytest.raises(ValueError, match="must be a valid UUID"):
            validate_uuid("not-a-uuid")

    def test_empty_uuid(self):
        """Test that empty UUIDs are rejected."""
        with pytest.raises(ValueError, match="is required"):
            validate_uuid("")

    def test_custom_field_name(self):
        """Test that custom field names appear in error messages."""
        with pytest.raises(ValueError, match="custom_field must be a valid UUID"):
            validate_uuid("invalid", field_name="custom_field")


class TestValidateImageUpload:
    """Test image upload validation."""

    def create_mock_file(self, filename, image_format='JPEG', width=100, height=100, file_size=1024):
        """Helper to create a mock file upload."""
        # Create test image
        img = Image.new('RGB', (width, height), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format=image_format)
        img_bytes.seek(0)

        # Create mock FileStorage
        file = Mock()
        file.filename = filename
        file.seek = img_bytes.seek
        file.tell = img_bytes.tell
        file.read = img_bytes.read

        # Store the BytesIO for later access
        file._bytes = img_bytes

        return file

    def test_valid_jpeg_upload(self):
        """Test that valid JPEG uploads are accepted."""
        file = self.create_mock_file('test.jpg', 'JPEG', 800, 600)
        format_type, width, height, size = validate_image_upload(file)

        assert format_type == 'JPEG'
        assert width == 800
        assert height == 600
        assert size > 0

    def test_valid_png_upload(self):
        """Test that valid PNG uploads are accepted."""
        file = self.create_mock_file('test.png', 'PNG', 1000, 1000)
        format_type, width, height, size = validate_image_upload(file)

        assert format_type == 'PNG'
        assert width == 1000
        assert height == 1000

    def test_no_file_provided(self):
        """Test that missing file is rejected."""
        with pytest.raises(ValueError, match="No file provided"):
            validate_image_upload(None)

    def test_no_filename(self):
        """Test that file without filename is rejected."""
        file = Mock()
        file.filename = ""
        with pytest.raises(ValueError, match="No file selected"):
            validate_image_upload(file)

    def test_unsupported_extension(self):
        """Test that unsupported file extensions are rejected."""
        file = Mock()
        file.filename = "test.txt"
        with pytest.raises(ValueError, match="Unsupported file format"):
            validate_image_upload(file)

    def test_file_too_large(self):
        """Test that files exceeding max size are rejected."""
        file = Mock()
        file.filename = "test.jpg"
        file.seek = Mock()
        file.tell = Mock(return_value=MAX_FILE_SIZE + 1)

        with pytest.raises(ValueError, match="File size exceeds maximum"):
            validate_image_upload(file)

    def test_empty_file(self):
        """Test that empty files are rejected."""
        file = Mock()
        file.filename = "test.jpg"
        file.seek = Mock()
        file.tell = Mock(return_value=0)

        with pytest.raises(ValueError, match="File is empty"):
            validate_image_upload(file)

    def test_image_dimension_too_large(self):
        """Test that images exceeding max dimensions are rejected."""
        file = self.create_mock_file('test.jpg', 'JPEG', MAX_IMAGE_DIMENSION + 1, 100)

        with pytest.raises(ValueError, match="Image dimensions exceed maximum"):
            validate_image_upload(file)

    def test_invalid_image_data(self):
        """Test that corrupted image data is rejected."""
        file = Mock()
        file.filename = "test.jpg"
        file.seek = Mock()
        file.tell = Mock(side_effect=[100, 0])
        file.read = Mock(return_value=b"not an image")

        # Mock BytesIO to return corrupted data
        img_bytes = io.BytesIO(b"not an image")
        file.seek = img_bytes.seek
        file.tell = Mock(side_effect=[100, 0, 0, 0])

        with pytest.raises(ValueError, match="Invalid image file"):
            validate_image_upload(file)


class TestValidateStyleExists:
    """Test style existence validation."""

    @patch('validation.get_db_pool')
    def test_valid_style_exists(self, mock_get_db_pool):
        """Test that existing style is validated successfully."""
        # Mock database response
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'id': '550e8400-e29b-41d4-a716-446655440000',
            'name': 'Pop Poster',
            'slug': 'pop-poster',
            'algorithm_config': {},
        }
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_pool.get_cursor.return_value = mock_cursor
        mock_get_db_pool.return_value = mock_pool

        result = validate_style_exists('550e8400-e29b-41d4-a716-446655440000')

        assert result['name'] == 'Pop Poster'
        assert result['slug'] == 'pop-poster'

    @patch('validation.get_db_pool')
    def test_style_not_found(self, mock_get_db_pool):
        """Test that non-existent style raises error."""
        # Mock database response (no results)
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_pool.get_cursor.return_value = mock_cursor
        mock_get_db_pool.return_value = mock_pool

        with pytest.raises(ValueError, match="Style not found"):
            validate_style_exists('550e8400-e29b-41d4-a716-446655440000')

    def test_invalid_style_id(self):
        """Test that invalid style ID raises error."""
        with pytest.raises(ValueError, match="must be a valid UUID"):
            validate_style_exists('invalid-id')


class TestValidateSizePresetExists:
    """Test size preset existence validation."""

    @patch('validation.get_db_pool')
    def test_valid_size_preset_exists(self, mock_get_db_pool):
        """Test that existing size preset is validated successfully."""
        # Mock database response
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'id': '550e8400-e29b-41d4-a716-446655440000',
            'name': '9x12',
            'width_inches': 9.0,
            'height_inches': 12.0,
            'dpi': 300,
        }
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_pool.get_cursor.return_value = mock_cursor
        mock_get_db_pool.return_value = mock_pool

        result = validate_size_preset_exists('550e8400-e29b-41d4-a716-446655440000')

        assert result['name'] == '9x12'
        assert result['dpi'] == 300

    @patch('validation.get_db_pool')
    def test_size_preset_not_found(self, mock_get_db_pool):
        """Test that non-existent size preset raises error."""
        # Mock database response (no results)
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_pool.get_cursor.return_value = mock_cursor
        mock_get_db_pool.return_value = mock_pool

        with pytest.raises(ValueError, match="Size preset not found"):
            validate_size_preset_exists('550e8400-e29b-41d4-a716-446655440000')

    def test_invalid_size_preset_id(self):
        """Test that invalid size preset ID raises error."""
        with pytest.raises(ValueError, match="must be a valid UUID"):
            validate_size_preset_exists('invalid-id')

"""
Tests for render routes.

Tests POST /v1/renders, GET /v1/renders/{id}, and download/preview endpoints.
"""

import pytest
import sys
import os
import io
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from PIL import Image

# Add service directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def app():
    """Create Flask test application."""
    # We need to mock the initialization to avoid database/storage connections
    with patch('app.init_app'):
        from app import app as flask_app
        flask_app.config['TESTING'] = True
        flask_app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
        return flask_app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


def create_test_image(width=800, height=600, format='JPEG'):
    """Helper to create a test image file."""
    img = Image.new('RGB', (width, height), color='red')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format=format)
    img_bytes.seek(0)
    return img_bytes


class TestCreateRenderRoute:
    """Test POST /v1/renders endpoint."""

    @patch('routes.renders.get_queue_manager')
    @patch('routes.renders.get_storage_client')
    @patch('routes.renders.get_db_pool')
    @patch('routes.renders.validate_size_preset_exists')
    @patch('routes.renders.validate_style_exists')
    @patch('routes.renders.validate_image_upload')
    def test_create_render_success(
        self,
        mock_validate_upload,
        mock_validate_style,
        mock_validate_preset,
        mock_get_db_pool,
        mock_get_storage,
        mock_get_queue,
        client
    ):
        """Test successful render creation."""
        # Mock validation
        mock_validate_upload.return_value = ('JPEG', 800, 600, 10000)
        mock_validate_style.return_value = {'id': 'style-id', 'name': 'Pop Poster'}
        mock_validate_preset.return_value = {'id': 'preset-id', 'name': '9x12'}

        # Mock storage
        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage

        # Mock database
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            {'created_at': datetime(2024, 1, 1, 12, 0, 0)},
            {'created_at': datetime(2024, 1, 1, 12, 0, 0)},
        ]
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_pool.get_cursor.return_value = mock_cursor
        mock_get_db_pool.return_value = mock_pool

        # Mock queue
        mock_job = MagicMock()
        mock_job.id = 'job-123'
        mock_queue = MagicMock()
        mock_queue.enqueue_render.return_value = mock_job
        mock_get_queue.return_value = mock_queue

        # Create request
        img_data = create_test_image()
        data = {
            'file': (img_data, 'test.jpg'),
            'style_id': '550e8400-e29b-41d4-a716-446655440000',
            'size_preset_id': '550e8400-e29b-41d4-a716-446655440001',
        }

        response = client.post(
            '/v1/renders',
            data=data,
            content_type='multipart/form-data'
        )

        # Verify response
        assert response.status_code == 201
        result = response.get_json()
        assert 'render_id' in result
        assert result['status'] == 'queued'
        assert 'created_at' in result

    def test_create_render_missing_file(self, client):
        """Test render creation without file."""
        data = {
            'style_id': '550e8400-e29b-41d4-a716-446655440000',
            'size_preset_id': '550e8400-e29b-41d4-a716-446655440001',
        }

        response = client.post(
            '/v1/renders',
            data=data,
            content_type='multipart/form-data'
        )

        assert response.status_code == 400
        result = response.get_json()
        assert 'error' in result
        assert 'No file provided' in result['error']

    def test_create_render_missing_style_id(self, client):
        """Test render creation without style_id."""
        img_data = create_test_image()
        data = {
            'file': (img_data, 'test.jpg'),
            'size_preset_id': '550e8400-e29b-41d4-a716-446655440001',
        }

        response = client.post(
            '/v1/renders',
            data=data,
            content_type='multipart/form-data'
        )

        assert response.status_code == 400
        result = response.get_json()
        assert 'error' in result
        assert 'style_id is required' in result['error']

    def test_create_render_missing_size_preset_id(self, client):
        """Test render creation without size_preset_id."""
        img_data = create_test_image()
        data = {
            'file': (img_data, 'test.jpg'),
            'style_id': '550e8400-e29b-41d4-a716-446655440000',
        }

        response = client.post(
            '/v1/renders',
            data=data,
            content_type='multipart/form-data'
        )

        assert response.status_code == 400
        result = response.get_json()
        assert 'error' in result
        assert 'size_preset_id is required' in result['error']

    @patch('routes.renders.validate_image_upload')
    def test_create_render_invalid_image(self, mock_validate_upload, client):
        """Test render creation with invalid image."""
        mock_validate_upload.side_effect = ValueError("Invalid image file")

        img_data = io.BytesIO(b"not an image")
        data = {
            'file': (img_data, 'test.jpg'),
            'style_id': '550e8400-e29b-41d4-a716-446655440000',
            'size_preset_id': '550e8400-e29b-41d4-a716-446655440001',
        }

        response = client.post(
            '/v1/renders',
            data=data,
            content_type='multipart/form-data'
        )

        assert response.status_code == 400
        result = response.get_json()
        assert 'error' in result
        assert 'Invalid image file' in result['error']

    @patch('routes.renders.validate_image_upload')
    @patch('routes.renders.validate_style_exists')
    def test_create_render_style_not_found(
        self,
        mock_validate_style,
        mock_validate_upload,
        client
    ):
        """Test render creation with non-existent style."""
        mock_validate_upload.return_value = ('JPEG', 800, 600, 10000)
        mock_validate_style.side_effect = ValueError("Style not found")

        img_data = create_test_image()
        data = {
            'file': (img_data, 'test.jpg'),
            'style_id': '550e8400-e29b-41d4-a716-446655440000',
            'size_preset_id': '550e8400-e29b-41d4-a716-446655440001',
        }

        response = client.post(
            '/v1/renders',
            data=data,
            content_type='multipart/form-data'
        )

        assert response.status_code == 400
        result = response.get_json()
        assert 'error' in result
        assert 'Style not found' in result['error']


class TestGetRenderRoute:
    """Test GET /v1/renders/{id} endpoint."""

    @patch('routes.renders.get_db_pool')
    def test_get_render_success(self, mock_get_db_pool, client):
        """Test successful render retrieval."""
        # Mock database response
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'id': '550e8400-e29b-41d4-a716-446655440000',
            'status': 'completed',
            'asset_id': '550e8400-e29b-41d4-a716-446655440001',
            'style_id': '550e8400-e29b-41d4-a716-446655440002',
            'size_preset_id': '550e8400-e29b-41d4-a716-446655440003',
            'created_at': datetime(2024, 1, 1, 12, 0, 0),
            'started_at': datetime(2024, 1, 1, 12, 0, 1),
            'completed_at': datetime(2024, 1, 1, 12, 0, 10),
            'duration_ms': 9000,
            'error_message': None,
            'style_name': 'Pop Poster',
            'style_slug': 'pop-poster',
            'size_preset_name': '9x12',
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

        # Make request
        response = client.get('/v1/renders/550e8400-e29b-41d4-a716-446655440000')

        # Verify response
        assert response.status_code == 200
        data = response.get_json()
        assert data['id'] == '550e8400-e29b-41d4-a716-446655440000'
        assert data['status'] == 'completed'
        assert data['duration_ms'] == 9000
        assert data['style']['name'] == 'Pop Poster'
        assert data['size_preset']['name'] == '9x12'

    def test_get_render_invalid_id(self, client):
        """Test render retrieval with invalid UUID."""
        response = client.get('/v1/renders/invalid-uuid')

        assert response.status_code == 400
        result = response.get_json()
        assert 'error' in result

    @patch('routes.renders.get_db_pool')
    def test_get_render_not_found(self, mock_get_db_pool, client):
        """Test render retrieval for non-existent render."""
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

        response = client.get('/v1/renders/550e8400-e29b-41d4-a716-446655440000')

        assert response.status_code == 404
        result = response.get_json()
        assert 'error' in result
        assert 'not found' in result['error'].lower()


class TestDownloadRenderRoute:
    """Test GET /v1/renders/{id}/download endpoint."""

    @patch('routes.renders.get_storage_client')
    @patch('routes.renders.get_db_pool')
    def test_download_render_success(self, mock_get_db_pool, mock_get_storage, client):
        """Test successful download URL generation."""
        # Mock database response
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'status': 'completed',
            'output_minio_key': 'renders/123/output.tiff',
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

        # Mock storage
        mock_storage = MagicMock()
        mock_storage.get_presigned_url.return_value = 'https://minio.example.com/presigned-url'
        mock_get_storage.return_value = mock_storage

        response = client.get('/v1/renders/550e8400-e29b-41d4-a716-446655440000/download')

        assert response.status_code == 200
        data = response.get_json()
        assert 'url' in data
        assert 'expires_in' in data
        assert data['url'] == 'https://minio.example.com/presigned-url'

    @patch('routes.renders.get_db_pool')
    def test_download_render_not_completed(self, mock_get_db_pool, client):
        """Test download when render is not completed."""
        # Mock database response
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'status': 'queued',
            'output_minio_key': None,
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

        response = client.get('/v1/renders/550e8400-e29b-41d4-a716-446655440000/download')

        assert response.status_code == 409
        result = response.get_json()
        assert 'error' in result
        assert 'not completed' in result['error'].lower()


class TestPreviewRenderRoute:
    """Test GET /v1/renders/{id}/preview endpoint."""

    @patch('routes.renders.get_storage_client')
    @patch('routes.renders.get_db_pool')
    def test_preview_render_success(self, mock_get_db_pool, mock_get_storage, client):
        """Test successful preview URL generation."""
        # Mock database response
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'preview_minio_key': 'renders/123/preview.jpg',
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

        # Mock storage
        mock_storage = MagicMock()
        mock_storage.get_presigned_url.return_value = 'https://minio.example.com/preview-url'
        mock_get_storage.return_value = mock_storage

        response = client.get('/v1/renders/550e8400-e29b-41d4-a716-446655440000/preview')

        assert response.status_code == 200
        data = response.get_json()
        assert 'url' in data
        assert 'expires_in' in data

    @patch('routes.renders.get_db_pool')
    def test_preview_render_not_available(self, mock_get_db_pool, client):
        """Test preview when not available."""
        # Mock database response
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'preview_minio_key': None,
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

        response = client.get('/v1/renders/550e8400-e29b-41d4-a716-446655440000/preview')

        assert response.status_code == 404
        result = response.get_json()
        assert 'error' in result
        assert 'not available' in result['error'].lower()

"""
Tests for size preset routes.

Tests the GET /v1/size-presets endpoint for listing available print sizes.
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal

# Add service directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def app():
    """Create Flask test application."""
    # We need to mock the initialization to avoid database/storage connections
    with patch('app.init_app'):
        from app import app as flask_app
        flask_app.config['TESTING'] = True
        return flask_app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestSizePresetsRoute:
    """Test size presets listing endpoint."""

    @patch('routes.size_presets.get_db_pool')
    def test_list_size_presets_success(self, mock_get_db_pool, client):
        """Test successful listing of size presets."""
        # Mock database response
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                'id': '550e8400-e29b-41d4-a716-446655440000',
                'name': '9x12',
                'width_inches': Decimal('9.00'),
                'height_inches': Decimal('12.00'),
                'dpi': 300,
            },
            {
                'id': '550e8400-e29b-41d4-a716-446655440001',
                'name': '16x20',
                'width_inches': Decimal('16.00'),
                'height_inches': Decimal('20.00'),
                'dpi': 300,
            },
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

        # Make request
        response = client.get('/v1/size-presets')

        # Verify response
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 2

        # Check first preset
        assert data[0]['id'] == '550e8400-e29b-41d4-a716-446655440000'
        assert data[0]['name'] == '9x12'
        assert data[0]['width_inches'] == 9.0
        assert data[0]['height_inches'] == 12.0
        assert data[0]['dpi'] == 300
        assert data[0]['width_px'] == 2700  # 9 * 300
        assert data[0]['height_px'] == 3600  # 12 * 300

        # Check second preset
        assert data[1]['name'] == '16x20'
        assert data[1]['width_px'] == 4800  # 16 * 300
        assert data[1]['height_px'] == 6000  # 20 * 300

    @patch('routes.size_presets.get_db_pool')
    def test_list_size_presets_empty(self, mock_get_db_pool, client):
        """Test listing when no size presets exist."""
        # Mock database response (empty)
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
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
        response = client.get('/v1/size-presets')

        # Verify response
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 0

    @patch('routes.size_presets.get_db_pool')
    def test_list_size_presets_database_error(self, mock_get_db_pool, client):
        """Test error handling when database query fails."""
        # Mock database error
        mock_pool = MagicMock()
        mock_pool.get_connection.side_effect = Exception("Database connection failed")
        mock_get_db_pool.return_value = mock_pool

        # Make request
        response = client.get('/v1/size-presets')

        # Verify error response
        assert response.status_code == 500
        data = response.get_json()
        assert 'error' in data
        assert data['error'] == 'Internal server error'

    def test_size_presets_only_get_method(self, client):
        """Test that only GET method is allowed."""
        # Try POST
        response = client.post('/v1/size-presets')
        assert response.status_code == 405  # Method Not Allowed

        # Try PUT
        response = client.put('/v1/size-presets')
        assert response.status_code == 405

        # Try DELETE
        response = client.delete('/v1/size-presets')
        assert response.status_code == 405

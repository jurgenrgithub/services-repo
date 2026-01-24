"""
Route registration for ASO Render Service API endpoints.

Provides centralized route registration with /v1 prefix for API versioning.
"""

from flask import Blueprint

# Create v1 API blueprint
v1_bp = Blueprint('v1', __name__, url_prefix='/v1')


def register_routes(app):
    """
    Register all API routes with the Flask application.

    Args:
        app: Flask application instance
    """
    from routes import renders, size_presets, openapi

    # Import route handlers (they will register themselves with v1_bp)
    # This happens when the modules are imported

    # Register the v1 blueprint with the app
    app.register_blueprint(v1_bp)

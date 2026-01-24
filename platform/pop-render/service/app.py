"""
ASO Render Service - Flask Application

Main Flask application for the Pop Render service. Provides REST API for
artistic rendering operations with PostgreSQL, Redis, and MinIO integration.

This service follows the ASO pattern with enterprise-grade monitoring,
structured logging, and health checks.
"""

import sys
import logging
from flask import Flask, request, jsonify
import time

# Add libs to path for common utilities
sys.path.insert(0, '/opt/libs')

from common.logging import setup_logging

from config import Config
from database import get_db_pool
from storage import get_storage_client
from render_queue import get_queue_manager
from health import health_endpoint, readiness_endpoint, liveness_endpoint
from metrics import metrics_endpoint, track_request_metrics
from monitoring import start_monitoring, stop_monitoring

# Initialize logging
logger = setup_logging("pop-render", level=Config.LOG_LEVEL)

# Create Flask application
app = Flask(__name__)


# ============================================================================
# Application Lifecycle
# ============================================================================

def init_app():
    """
    Initialize application and all dependencies.

    Validates configuration and initializes database pool, storage client.
    Follows fail-fast principle - exits if critical dependencies fail.
    """
    logger.info("Initializing Pop Render Service")

    # Validate configuration
    try:
        Config.validate()
        logger.info("Configuration validated", extra=Config.to_dict())
    except ValueError as e:
        logger.error(f"Configuration validation failed: {e}")
        sys.exit(1)

    # Initialize database pool
    try:
        db_pool = get_db_pool()
        db_pool.initialize(min_connections=2, max_connections=10)
        logger.info("Database pool initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        sys.exit(1)

    # Initialize storage client
    try:
        storage_client = get_storage_client()
        storage_client.initialize()
        logger.info("Storage client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize storage client: {e}")
        sys.exit(1)

    # Initialize queue manager
    try:
        queue_mgr = get_queue_manager()
        queue_mgr.initialize()
        logger.info("Queue manager initialized")
    except Exception as e:
        logger.error(f"Failed to initialize queue manager: {e}")
        sys.exit(1)

    # Start background monitoring threads
    try:
        start_monitoring()
        logger.info("Background monitoring started")
    except Exception as e:
        logger.error(f"Failed to start monitoring: {e}")
        # Don't exit - monitoring is not critical for operation

    logger.info("Pop Render Service initialized successfully")


def shutdown_app():
    """
    Gracefully shutdown application and close all connections.
    """
    logger.info("Shutting down Pop Render Service")

    # Stop background monitoring
    try:
        stop_monitoring()
        logger.info("Background monitoring stopped")
    except Exception as e:
        logger.error(f"Error stopping monitoring: {e}")

    # Close queue manager
    try:
        queue_mgr = get_queue_manager()
        queue_mgr.close()
        logger.info("Queue manager closed")
    except Exception as e:
        logger.error(f"Error closing queue manager: {e}")

    # Close database pool
    try:
        db_pool = get_db_pool()
        db_pool.close()
        logger.info("Database pool closed")
    except Exception as e:
        logger.error(f"Error closing database pool: {e}")

    logger.info("Pop Render Service shutdown complete")


# ============================================================================
# Middleware
# ============================================================================

@app.before_request
def before_request():
    """Store request start time for metrics."""
    request._start_time = time.time()


@app.after_request
def after_request(response):
    """Log request and track metrics."""
    # Calculate request duration
    duration = time.time() - getattr(request, '_start_time', time.time())

    # Track metrics
    track_request_metrics(
        method=request.method,
        endpoint=request.endpoint or 'unknown',
        status=response.status_code,
        duration=duration,
    )

    # Log request
    logger.info(
        "Request completed",
        extra={
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "duration_ms": int(duration * 1000),
            "user_agent": request.headers.get("User-Agent", ""),
        },
    )

    return response


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        "error": "Not Found",
        "message": "The requested resource was not found",
        "status": 404,
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error("Internal server error", extra={"error": str(error)})
    return jsonify({
        "error": "Internal Server Error",
        "message": "An internal error occurred",
        "status": 500,
    }), 500


# ============================================================================
# Health & Monitoring Endpoints
# ============================================================================

@app.route('/health', methods=['GET'])
def health():
    """
    Comprehensive health check endpoint.

    Checks PostgreSQL, Redis, and MinIO connectivity.
    Returns 200 if all healthy, 503 otherwise.
    """
    return health_endpoint()


@app.route('/health/readiness', methods=['GET'])
def readiness():
    """
    Readiness check endpoint for Kubernetes.

    Checks if service is ready to handle requests.
    """
    return readiness_endpoint()


@app.route('/health/liveness', methods=['GET'])
def liveness():
    """
    Liveness check endpoint for Kubernetes.

    Checks if service is alive and running.
    """
    return liveness_endpoint()


@app.route('/metrics', methods=['GET'])
def metrics():
    """
    Prometheus metrics endpoint.

    Exposes application metrics in Prometheus format.
    """
    return metrics_endpoint()


# ============================================================================
# API Endpoints
# ============================================================================

@app.route('/', methods=['GET'])
def index():
    """
    Service information endpoint.
    """
    return jsonify({
        "service": "pop-render",
        "version": "1.0.0",
        "description": "ASO Render Service for artistic image transformations",
        "endpoints": {
            "health": "/health",
            "readiness": "/health/readiness",
            "liveness": "/health/liveness",
            "metrics": "/metrics",
            "api": "/v1",
        },
    })


# Register API routes
from routes import register_routes
register_routes(app)


# ============================================================================
# Application Entry Point
# ============================================================================

def create_app():
    """
    Application factory function.

    Returns:
        Configured Flask application
    """
    init_app()
    return app


# Initialize app on module load for WSGI servers
init_app()
if __name__ == '__main__':
    """
    Development server entry point.

    For production, use Gunicorn:
        gunicorn -w 2 -b 0.0.0.0:8089 app:app
    """
    init_app()

    # Register shutdown handler
    import atexit
    atexit.register(shutdown_app)

    # Run development server
    app.run(
        host='0.0.0.0',
        port=Config.API_PORT,
        debug=False,  # Never use debug in production
    )

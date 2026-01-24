"""
OpenAPI documentation endpoint for ASO Render Service.

Serves the OpenAPI specification in JSON format for API documentation,
client SDK generation, and API gateway integration.
"""

import logging
import os
import json
import yaml
from flask import jsonify

from routes import v1_bp

logger = logging.getLogger(__name__)

# Cache for parsed OpenAPI spec
_openapi_spec_cache = None


def load_openapi_spec():
    """
    Load and parse the OpenAPI YAML specification.

    Returns:
        dict: Parsed OpenAPI specification

    Raises:
        FileNotFoundError: If openapi.yaml not found
        yaml.YAMLError: If YAML parsing fails
    """
    global _openapi_spec_cache

    # Return cached spec if available
    if _openapi_spec_cache is not None:
        return _openapi_spec_cache

    # Locate openapi.yaml relative to this file
    service_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec_path = os.path.join(service_dir, 'openapi.yaml')

    logger.info(f"Loading OpenAPI spec from: {spec_path}")

    try:
        with open(spec_path, 'r', encoding='utf-8') as f:
            _openapi_spec_cache = yaml.safe_load(f)
            logger.info("OpenAPI spec loaded and cached successfully")
            return _openapi_spec_cache
    except FileNotFoundError:
        logger.error(f"OpenAPI spec not found at: {spec_path}")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse OpenAPI YAML: {e}")
        raise


@v1_bp.route('/openapi.json', methods=['GET'])
def get_openapi_spec():
    """
    Serve OpenAPI specification in JSON format.

    Returns:
        200: OpenAPI spec as JSON
        500: Error loading spec

    The specification is loaded from openapi.yaml and cached in memory
    for subsequent requests. Cache persists for the lifetime of the worker process.
    """
    try:
        spec = load_openapi_spec()
        return jsonify(spec), 200

    except FileNotFoundError:
        logger.error("OpenAPI specification file not found")
        return jsonify({
            "error": "OpenAPI specification not available",
            "message": "The API documentation is temporarily unavailable"
        }), 500

    except yaml.YAMLError as e:
        logger.error(f"Failed to parse OpenAPI specification: {e}")
        return jsonify({
            "error": "Invalid OpenAPI specification",
            "message": "The API documentation could not be loaded"
        }), 500

    except Exception as e:
        logger.error(f"Unexpected error loading OpenAPI spec: {e}")
        return jsonify({
            "error": "Internal server error",
            "message": "Failed to load API documentation"
        }), 500

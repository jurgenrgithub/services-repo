"""
Size preset endpoints for ASO Render Service.

Provides REST API for listing available print size presets with calculated dimensions.
"""

import logging
from flask import jsonify
from decimal import Decimal

from routes import v1_bp
from database import get_db_pool

logger = logging.getLogger(__name__)


@v1_bp.route('/size-presets', methods=['GET'])
def list_size_presets():
    """
    List all available size presets with calculated pixel dimensions.

    Returns:
        200: Array of size presets
        500: Server error

    Response format:
        [
            {
                "id": "uuid",
                "name": "9x12",
                "width_inches": 9.0,
                "height_inches": 12.0,
                "dpi": 300,
                "width_px": 2700,
                "height_px": 3600
            },
            ...
        ]
    """
    try:
        db_pool = get_db_pool()
        with db_pool.get_connection() as conn:
            with db_pool.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        id,
                        name,
                        width_inches,
                        height_inches,
                        dpi
                    FROM aso_render.size_presets
                    ORDER BY width_inches * height_inches ASC
                    """
                )
                presets = cursor.fetchall()

                # Calculate pixel dimensions and format response
                result = []
                for preset in presets:
                    width_inches = float(preset['width_inches'])
                    height_inches = float(preset['height_inches'])
                    dpi = preset['dpi']

                    result.append({
                        "id": str(preset['id']),
                        "name": preset['name'],
                        "width_inches": width_inches,
                        "height_inches": height_inches,
                        "dpi": dpi,
                        "width_px": int(width_inches * dpi),
                        "height_px": int(height_inches * dpi),
                    })

                logger.debug(f"Retrieved {len(result)} size presets")
                return jsonify(result), 200

    except Exception as e:
        logger.error(
            "Error fetching size presets",
            extra={"error": str(e)},
        )
        return jsonify({"error": "Internal server error"}), 500

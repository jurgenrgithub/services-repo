"""
PostgreSQL database connection management for ASO Render Service.

Implements connection pooling, context managers, and RealDictCursor for enterprise-grade
database access with automatic connection lifecycle management and error recovery.
"""

import logging
from contextlib import contextmanager
from typing import Generator, Optional, Any
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from psycopg2.extensions import connection as PGConnection, cursor as PGCursor

from config import Config

logger = logging.getLogger(__name__)


class DatabasePool:
    """
    PostgreSQL connection pool manager with enterprise features.

    Features:
    - Connection pooling for performance
    - Automatic connection lifecycle management
    - RealDictCursor for dict-based row access
    - Context managers for safe resource handling
    - Health checks for monitoring
    - Self-healing on connection errors

    Usage:
        db_pool = DatabasePool()
        db_pool.initialize()

        with db_pool.get_connection() as conn:
            with db_pool.get_cursor(conn) as cursor:
                cursor.execute("SELECT * FROM assets")
                rows = cursor.fetchall()
    """

    def __init__(self):
        """Initialize database pool (call initialize() to create connections)."""
        self._pool: Optional[pool.ThreadedConnectionPool] = None
        self._initialized = False

    def initialize(
        self,
        min_connections: int = 2,
        max_connections: int = 10,
    ) -> None:
        """
        Initialize the connection pool.

        Args:
            min_connections: Minimum number of connections to maintain
            max_connections: Maximum number of connections allowed

        Raises:
            psycopg2.Error: If connection pool cannot be created
        """
        if self._initialized:
            logger.warning("Database pool already initialized")
            return

        try:
            self._pool = pool.ThreadedConnectionPool(
                min_connections,
                max_connections,
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                dbname=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                # Performance and reliability settings
                connect_timeout=10,
                options="-c search_path=aso_render,public",
            )
            self._initialized = True
            logger.info(
                "Database pool initialized",
                extra={
                    "min_connections": min_connections,
                    "max_connections": max_connections,
                    "db_host": Config.DB_HOST,
                    "db_name": Config.DB_NAME,
                },
            )
        except psycopg2.Error as e:
            logger.error(
                "Failed to initialize database pool",
                extra={"error": str(e), "db_host": Config.DB_HOST},
            )
            raise

    def close(self) -> None:
        """Close all connections in the pool."""
        if self._pool:
            self._pool.closeall()
            self._initialized = False
            logger.info("Database pool closed")

    @contextmanager
    def get_connection(self) -> Generator[PGConnection, None, None]:
        """
        Get a database connection from the pool (context manager).

        Yields:
            Database connection

        Raises:
            RuntimeError: If pool not initialized
            psycopg2.Error: On connection errors
        """
        if not self._initialized or not self._pool:
            raise RuntimeError("Database pool not initialized. Call initialize() first.")

        conn = None
        try:
            conn = self._pool.getconn()
            conn.autocommit = False
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error("Database connection error", extra={"error": str(e)})
            raise
        finally:
            if conn:
                self._pool.putconn(conn)

    @contextmanager
    def get_cursor(
        self,
        conn: PGConnection,
        cursor_factory=RealDictCursor,
    ) -> Generator[PGCursor, None, None]:
        """
        Get a cursor from a connection (context manager).

        Args:
            conn: Database connection
            cursor_factory: Cursor factory class (default: RealDictCursor)

        Yields:
            Database cursor
        """
        cursor = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
        finally:
            cursor.close()

    def health_check(self) -> bool:
        """
        Check database connectivity and pool health.

        Returns:
            True if database is healthy, False otherwise
        """
        if not self._initialized or not self._pool:
            logger.warning("Database pool not initialized for health check")
            return False

        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    return result is not None
        except Exception as e:
            logger.error("Database health check failed", extra={"error": str(e)})
            return False

    def execute_query(
        self,
        query: str,
        params: Optional[tuple] = None,
        fetch_one: bool = False,
    ) -> Any:
        """
        Execute a query and return results (convenience method).

        Args:
            query: SQL query to execute
            params: Query parameters
            fetch_one: Fetch single row instead of all rows

        Returns:
            Query results (dict or list of dicts)
        """
        with self.get_connection() as conn:
            with self.get_cursor(conn) as cursor:
                cursor.execute(query, params)
                if fetch_one:
                    return cursor.fetchone()
                return cursor.fetchall()

    def execute_update(
        self,
        query: str,
        params: Optional[tuple] = None,
    ) -> int:
        """
        Execute an INSERT/UPDATE/DELETE query (convenience method).

        Args:
            query: SQL query to execute
            params: Query parameters

        Returns:
            Number of affected rows
        """
        with self.get_connection() as conn:
            with self.get_cursor(conn) as cursor:
                cursor.execute(query, params)
                return cursor.rowcount


# Global database pool instance
db_pool = DatabasePool()


def get_db_pool() -> DatabasePool:
    """
    Get the global database pool instance.

    Returns:
        DatabasePool instance
    """
    return db_pool

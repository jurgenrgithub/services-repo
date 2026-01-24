"""
MinIO/S3 object storage client for ASO Render Service.

Implements enterprise-grade object storage operations with automatic bucket creation,
health checks, and error handling for render asset management.
"""

import logging
from typing import Optional, BinaryIO, Dict, Any
from io import BytesIO
import boto3
from botocore.exceptions import ClientError, BotoCoreError
from botocore.client import Config as BotoConfig

from config import Config

logger = logging.getLogger(__name__)


class StorageClient:
    """
    MinIO/S3 storage client for render assets.

    Features:
    - Automatic bucket creation and validation
    - Upload/download with streaming support
    - Presigned URL generation
    - Health checks for monitoring
    - Error recovery and retry logic

    Usage:
        storage = StorageClient()
        storage.initialize()

        # Upload file
        storage.upload_file('path/to/file.jpg', 'renders/output.jpg')

        # Download file
        data = storage.download_file('renders/output.jpg')

        # Get presigned URL
        url = storage.get_presigned_url('renders/output.jpg', expires_in=3600)
    """

    def __init__(self):
        """Initialize storage client (call initialize() to connect)."""
        self._client: Optional[Any] = None
        self._initialized = False
        self._bucket_name = Config.MINIO_BUCKET

    def initialize(self) -> None:
        """
        Initialize the MinIO/S3 client and ensure bucket exists.

        Raises:
            ValueError: If configuration is invalid
            ClientError: If connection or bucket creation fails
        """
        if self._initialized:
            logger.warning("Storage client already initialized")
            return

        try:
            # Create S3 client with MinIO configuration
            self._client = boto3.client(
                's3',
                endpoint_url=Config.MINIO_ENDPOINT,
                aws_access_key_id=Config.MINIO_ACCESS_KEY,
                aws_secret_access_key=Config.MINIO_SECRET_KEY,
                config=BotoConfig(
                    signature_version='s3v4',
                    connect_timeout=10,
                    read_timeout=30,
                    retries={'max_attempts': 3, 'mode': 'standard'},
                ),
            )

            # Ensure bucket exists
            self._ensure_bucket_exists()
            self._initialized = True

            logger.info(
                "Storage client initialized",
                extra={
                    "endpoint": Config.MINIO_ENDPOINT,
                    "bucket": self._bucket_name,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to initialize storage client",
                extra={"error": str(e), "endpoint": Config.MINIO_ENDPOINT},
            )
            raise

    def _ensure_bucket_exists(self) -> None:
        """
        Create bucket if it doesn't exist.

        Raises:
            ClientError: If bucket creation fails
        """
        try:
            self._client.head_bucket(Bucket=self._bucket_name)
            logger.debug(f"Bucket {self._bucket_name} exists")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == '404':
                # Bucket doesn't exist, create it
                logger.info(f"Creating bucket {self._bucket_name}")
                self._client.create_bucket(Bucket=self._bucket_name)
                logger.info(f"Bucket {self._bucket_name} created successfully")
            else:
                raise

    def upload_file(
        self,
        file_path: str,
        object_key: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Upload a file to MinIO.

        Args:
            file_path: Local file path to upload
            object_key: Object key in MinIO bucket
            metadata: Optional metadata to attach to object

        Returns:
            Object key of uploaded file

        Raises:
            RuntimeError: If client not initialized
            ClientError: If upload fails
        """
        if not self._initialized or not self._client:
            raise RuntimeError("Storage client not initialized. Call initialize() first.")

        try:
            extra_args = {}
            if metadata:
                extra_args['Metadata'] = metadata

            self._client.upload_file(
                file_path,
                self._bucket_name,
                object_key,
                ExtraArgs=extra_args,
            )

            logger.debug(
                "File uploaded successfully",
                extra={"object_key": object_key, "file_path": file_path},
            )
            return object_key
        except ClientError as e:
            logger.error(
                "Failed to upload file",
                extra={"error": str(e), "object_key": object_key},
            )
            raise

    def upload_fileobj(
        self,
        file_obj: BinaryIO,
        object_key: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Upload a file-like object to MinIO.

        Args:
            file_obj: File-like object to upload
            object_key: Object key in MinIO bucket
            metadata: Optional metadata to attach to object

        Returns:
            Object key of uploaded file

        Raises:
            RuntimeError: If client not initialized
            ClientError: If upload fails
        """
        if not self._initialized or not self._client:
            raise RuntimeError("Storage client not initialized. Call initialize() first.")

        try:
            extra_args = {}
            if metadata:
                extra_args['Metadata'] = metadata

            self._client.upload_fileobj(
                file_obj,
                self._bucket_name,
                object_key,
                ExtraArgs=extra_args,
            )

            logger.debug(
                "File object uploaded successfully",
                extra={"object_key": object_key},
            )
            return object_key
        except ClientError as e:
            logger.error(
                "Failed to upload file object",
                extra={"error": str(e), "object_key": object_key},
            )
            raise

    def download_file(self, object_key: str, file_path: str) -> str:
        """
        Download a file from MinIO.

        Args:
            object_key: Object key in MinIO bucket
            file_path: Local file path to save to

        Returns:
            Local file path

        Raises:
            RuntimeError: If client not initialized
            ClientError: If download fails
        """
        if not self._initialized or not self._client:
            raise RuntimeError("Storage client not initialized. Call initialize() first.")

        try:
            self._client.download_file(
                self._bucket_name,
                object_key,
                file_path,
            )

            logger.debug(
                "File downloaded successfully",
                extra={"object_key": object_key, "file_path": file_path},
            )
            return file_path
        except ClientError as e:
            logger.error(
                "Failed to download file",
                extra={"error": str(e), "object_key": object_key},
            )
            raise

    def download_fileobj(self, object_key: str) -> bytes:
        """
        Download a file from MinIO as bytes.

        Args:
            object_key: Object key in MinIO bucket

        Returns:
            File contents as bytes

        Raises:
            RuntimeError: If client not initialized
            ClientError: If download fails
        """
        if not self._initialized or not self._client:
            raise RuntimeError("Storage client not initialized. Call initialize() first.")

        try:
            buffer = BytesIO()
            self._client.download_fileobj(
                self._bucket_name,
                object_key,
                buffer,
            )
            buffer.seek(0)

            logger.debug(
                "File object downloaded successfully",
                extra={"object_key": object_key},
            )
            return buffer.read()
        except ClientError as e:
            logger.error(
                "Failed to download file object",
                extra={"error": str(e), "object_key": object_key},
            )
            raise

    def get_presigned_url(
        self,
        object_key: str,
        expires_in: int = 3600,
    ) -> str:
        """
        Generate a presigned URL for temporary access to an object.

        Args:
            object_key: Object key in MinIO bucket
            expires_in: URL expiration time in seconds (default: 1 hour)

        Returns:
            Presigned URL

        Raises:
            RuntimeError: If client not initialized
            ClientError: If URL generation fails
        """
        if not self._initialized or not self._client:
            raise RuntimeError("Storage client not initialized. Call initialize() first.")

        try:
            url = self._client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self._bucket_name,
                    'Key': object_key,
                },
                ExpiresIn=expires_in,
            )

            logger.debug(
                "Presigned URL generated",
                extra={"object_key": object_key, "expires_in": expires_in},
            )
            return url
        except ClientError as e:
            logger.error(
                "Failed to generate presigned URL",
                extra={"error": str(e), "object_key": object_key},
            )
            raise

    def delete_file(self, object_key: str) -> None:
        """
        Delete a file from MinIO.

        Args:
            object_key: Object key in MinIO bucket

        Raises:
            RuntimeError: If client not initialized
            ClientError: If deletion fails
        """
        if not self._initialized or not self._client:
            raise RuntimeError("Storage client not initialized. Call initialize() first.")

        try:
            self._client.delete_object(
                Bucket=self._bucket_name,
                Key=object_key,
            )

            logger.debug(
                "File deleted successfully",
                extra={"object_key": object_key},
            )
        except ClientError as e:
            logger.error(
                "Failed to delete file",
                extra={"error": str(e), "object_key": object_key},
            )
            raise

    def health_check(self) -> bool:
        """
        Check MinIO connectivity and bucket access.

        Returns:
            True if storage is healthy, False otherwise
        """
        if not self._initialized or not self._client:
            logger.warning("Storage client not initialized for health check")
            return False

        try:
            # Try to list objects in bucket (limit to 1)
            self._client.list_objects_v2(
                Bucket=self._bucket_name,
                MaxKeys=1,
            )
            return True
        except Exception as e:
            logger.error("Storage health check failed", extra={"error": str(e)})
            return False


# Global storage client instance
storage_client = StorageClient()


def get_storage_client() -> StorageClient:
    """
    Get the global storage client instance.

    Returns:
        StorageClient instance
    """
    return storage_client

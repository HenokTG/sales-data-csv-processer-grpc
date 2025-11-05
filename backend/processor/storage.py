"""
Storage abstraction layer for supporting multiple backends (local filesystem, S3, etc.)
"""

import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod

import boto3
from botocore.exceptions import ClientError

log = logging.getLogger(__name__)


@dataclass
class StorageConfig:
    """Configuration for storage backends."""

    storage_type: str = "local"  # "local" or "s3"
    local_base_path: Optional[Path] = None
    s3_bucket: Optional[str] = None
    s3_region: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_endpoint: Optional[str] = None  # For S3-compatible services


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def save_file(self, file_path: str, content: str) -> str:
        """Save file content and return the accessible path/URL."""
        pass

    @abstractmethod
    def file_exists(self, file_path: str) -> bool:
        """Check if file exists."""
        pass

    @abstractmethod
    def get_file_url(self, file_path: str) -> str:
        """Get accessible URL for the file."""
        pass


class LocalStorage(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        log.info(f"Initialized LocalStorage with base path: {self.base_path}")

    def save_file(self, file_path: str, content: str) -> str:
        """Save file to local filesystem."""
        full_path = self.base_path / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        log.info(f"Saved file locally: {full_path}")
        return str(full_path)

    def file_exists(self, file_path: str) -> bool:
        """Check if file exists in local filesystem."""
        full_path = self.base_path / file_path
        return full_path.exists()

    def get_file_url(self, file_path: str) -> str:
        """Return local file path (for API compatibility)."""
        return str(self.base_path / file_path)


class S3Storage(StorageBackend):
    """AWS S3 storage backend."""

    def __init__(
        self,
        bucket: str,
        region: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        endpoint: Optional[str] = None,
    ):
        self.bucket = bucket
        self.region = region

        # Initialize S3 client
        session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

        if endpoint:
            # For S3-compatible services (DigitalOcean Spaces, MinIO, etc.)
            self.s3_client = session.client("s3", endpoint_url=endpoint)
        else:
            # For AWS S3
            self.s3_client = session.client("s3")

        log.info(f"Initialized S3Storage with bucket: {bucket}")

    def save_file(self, file_path: str, content: str) -> str:
        """Upload file to S3."""
        try:
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=file_path,
                Body=content.encode("utf-8"),
                ContentType="text/csv",
            )
            log.info(f"Uploaded file to S3: {file_path}")
            return file_path
        except ClientError as e:
            log.error(f"Failed to upload to S3: {e}")
            raise

    def file_exists(self, file_path: str) -> bool:
        """Check if file exists in S3."""
        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=file_path)
            return True
        except ClientError:
            return False

    def get_file_url(self, file_path: str) -> str:
        """Generate presigned URL for S3 object."""
        try:
            if (
                self.s3_client.meta.endpoint_url
                and "digitaloceanspaces" in self.s3_client.meta.endpoint_url
            ):
                # DigitalOcean Spaces direct URL
                return f"https://{self.bucket}.{self.region}.digitaloceanspaces.com/{file_path}"
            else:
                # AWS S3 presigned URL
                url = self.s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": file_path},
                    ExpiresIn=3600,  # 1 hour
                )
                return url
        except ClientError as e:
            log.error(f"Failed to generate S3 URL: {e}")
            return f"s3://{self.bucket}/{file_path}"


class StorageFactory:
    """Factory class to create appropriate storage backend."""

    @staticmethod
    def create_storage(config: StorageConfig) -> StorageBackend:
        """Create storage backend based on configuration."""
        if config.storage_type == "s3":
            if not config.s3_bucket:
                raise ValueError("S3 bucket must be specified for S3 storage")

            return S3Storage(
                bucket=config.s3_bucket,
                region=config.s3_region,
                access_key=config.s3_access_key,
                secret_key=config.s3_secret_key,
                endpoint=config.s3_endpoint,
            )

        elif config.storage_type == "local":
            base_path = config.local_base_path or Path("results")
            return LocalStorage(base_path)

        else:
            raise ValueError(f"Unsupported storage type: {config.storage_type}")

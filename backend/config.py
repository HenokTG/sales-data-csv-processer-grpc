import os
import logging
from typing import List
from pathlib import Path
from dotenv import load_dotenv

from fastapi.middleware.cors import CORSMiddleware

from processor.storage import StorageConfig

# LOAD ENVIRONMENT VARIABLES FIRST!
load_dotenv()

log = logging.getLogger(__name__)


def get_development_storage_config():
    """Development storage configuration with local storage."""

    return StorageConfig(storage_type="local", local_base_path=Path("results"))


def get_production_storage_config():
    """Production configuration with AWS S3."""
    return StorageConfig(
        storage_type="s3",
        s3_bucket=os.getenv("AWS_S3_BUCKET", "my-csv-processor"),
        s3_region=os.getenv("AWS_REGION", "us-east-1"),
        s3_access_key=os.getenv("AWS_ACCESS_KEY_ID"),
        s3_secret_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


class Config:
    """Application configuration with proper type handling."""

    # SCRIPT_DIR is the path to the current directory (backend/gateway)
    RESULTS_DIR_LoCAL: Path = Path(__file__).parent / "results"

    # Server configuration
    GATEWAY_HOST = os.getenv("GATEWAY_HOST", "127.0.0.1")
    GATEWAY_PORT = int(os.getenv("GATEWAY_PORT", "8000"))

    # File processing configuration
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", str(1024 * 1024)))  # 1MB default

    # Directory configuration
    @property
    def RESULTS_DIR(self) -> str:
        """Get results file key with fallback to local."""
        results_storake_key = None  # shoulde be a file path key on prod stogare service

        if results_storake_key:
            return results_storake_key
        return self.RESULTS_DIR_LoCAL

    # gRPC configuration
    GRPC_SERVER_ADDRESS = os.getenv("GRPC_SERVER_ADDRESS", "localhost:50051")
    GRPC_PORT = int(os.getenv("GRPC_PORT", "50051"))
    GRPC_MAX_WORKERS = int(os.getenv("GRPC_MAX_WORKERS", "20"))
    GRPC_UPDATE_INTERVAL = float(os.getenv("GRPC_UPDATE_INTERVAL", "1.0"))  # in seconds

    # Get API key from environment
    API_KEY = os.getenv("API_KEY")
    REQUIRE_API_KEY = os.getenv("REQUIRE_API_KEY", "true").lower() == "true"

    def __init__(self):
        """Initialize and validate configuration."""
        self._create_directories()
        self._log_config()

    def _create_directories(self) -> None:
        """Create necessary directories."""
        os.makedirs(self.RESULTS_DIR, exist_ok=True)

    def _log_config(self) -> None:
        """Log important configuration values."""
        log.info(f"Results directory: {self.RESULTS_DIR}")
        log.info(f"Gateway port: {self.GATEWAY_PORT}")
        log.info(f"Chunk size: {self.CHUNK_SIZE} bytes")
        log.info(f"gRPC server: {self.GRPC_SERVER_ADDRESS}")

    def get_storage_config(self):
        environment = os.getenv("ENVIRONMENT", "development")

        if environment == "production":
            return get_production_storage_config()
        return None  # get_development_storage_config()

    """CORS configuration settings."""

    DEV_ORIGINS = [
        "http://localhost",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    PRODUCTION_ORIGINS = []

    ALLOWED_METHODS = ["GET", "POST", "OPTIONS"]

    ALLOWED_HEADERS = [
        "Content-Type",
        "Authorization",
        "Accept",
        "Origin",
        "X-Requested-With",
        "X-API-Key",
    ]

    EXPOSED_HEADERS = ["Content-Disposition", "Content-Length"]


# Create global configuration instance
app_config = Config()


def get_cors_origins() -> List[str]:
    """Get CORS origins based on environment."""
    environment = os.getenv("ENVIRONMENT", "development")

    if environment == "production":
        production_origins = os.getenv("CORS_ALLOWED_ORIGINS")
        if production_origins:
            return [origin.strip() for origin in production_origins.split(",")]
        return app_config.PRODUCTION_ORIGINS
    else:
        dev_origins = app_config.DEV_ORIGINS.copy()
        additional_origins = os.getenv("CORS_EXTRA_ORIGINS")
        if additional_origins:
            dev_origins.extend(
                [origin.strip() for origin in additional_origins.split(",")]
            )
        return dev_origins


def setup_cors_middleware(app):
    """Configure CORS middleware based on environment."""
    environment = os.getenv("ENVIRONMENT", "development")

    if (
        environment == "development"
        and os.getenv("CORS_ALLOW_ALL", "true").lower() == "true"
    ):
        # Development mode - allow all origins
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=app_config.ALLOWED_METHODS,
            allow_headers=app_config.ALLOWED_HEADERS,
            expose_headers=app_config.EXPOSED_HEADERS,
        )
        log.info("CORS: All origins allowed (development mode)")
    else:
        # Production or restricted mode
        origins = get_cors_origins()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=app_config.ALLOWED_METHODS,
            allow_headers=app_config.ALLOWED_HEADERS,
            expose_headers=app_config.EXPOSED_HEADERS,
        )
        log.info(f"CORS: Restricted origins enabled: {origins}")

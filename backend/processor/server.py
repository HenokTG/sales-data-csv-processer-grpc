"""
gRPC Server for CSV Processing.

This is the core backend processor. It listens for gRPC connections
from the gateway and runs the StreamProcessor logic.
"""

import os
import sys
import time
import uuid
import logging
from concurrent import futures
from dataclasses import dataclass
from typing import Iterator, Optional
from pathlib import Path

import grpc

from config import app_config
from .storage import StorageConfig, StorageFactory


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

# Add the current directory to Python path for imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# Import gRPC generated modules
try:
    from . import processing_pb2
    from . import processing_pb2_grpc
    from .processor import StreamProcessor, CSVProcessingError
except ImportError as e:
    log.critical("\n--- CRITICAL IMPORT ERROR ---")
    log.critical(
        "The gRPC code (processing_pb2.py and processing_pb2_grpc.py) could not be imported."
    )
    log.critical("Ensure you have run the following command from the project root:")
    log.critical(
        "python3 -m grpc_tools.protoc -I=protos --python_out=backend/processor/ "
        "--pyi_out=backend/processor/ --grpc_python_out=backend/processor/ protos/processing.proto"
    )
    log.critical(f"Original Error: {e}")
    sys.exit(1)
finally:
    # Remove the path addition to keep the environment clean
    if SCRIPT_DIR in sys.path:
        sys.path.remove(SCRIPT_DIR)


@dataclass
class ServerConfig:
    """Configuration for the gRPC server."""

    port: int = app_config.GRPC_PORT
    max_workers: int = app_config.GRPC_MAX_WORKERS
    progress_update_interval: float = app_config.GRPC_UPDATE_INTERVAL
    results_dir: Path = app_config.RESULTS_DIR
    storage_config: Optional[StorageConfig] = app_config.get_storage_config()


class ProcessingSession:
    """Manages state for a single CSV processing session."""

    def __init__(self, config: ServerConfig, storage_backend=None):
        self.processor = StreamProcessor()
        self.config = config
        self.start_time = time.monotonic()
        self.last_progress_update = self.start_time
        self.file_size_bytes: Optional[int] = None
        self.output_filename = f"{uuid.uuid4()}.csv"
        self.storage_backend = storage_backend

        # For local storage, use the original path
        self.output_path = config.results_dir / self.output_filename
        if storage_backend:
            self.output_path = config.results_dir

    def update_progress_timing(self) -> bool:
        """Check if enough time has passed for a progress update."""
        current_time = time.monotonic()
        should_update = (
            current_time - self.last_progress_update
        ) >= self.config.progress_update_interval
        if should_update:
            self.last_progress_update = current_time
        return should_update

    def calculate_progress_percentage(self) -> float:
        """Calculate processing progress percentage."""
        if self.file_size_bytes and self.file_size_bytes > 0:
            return (self.processor.processed_bytes / self.file_size_bytes) * 100
        return 0.0

    def get_processing_time(self) -> float:
        """Get total processing time."""
        return time.monotonic() - self.start_time


class CsvProcessorServicer(processing_pb2_grpc.CsvProcessorServicer):
    """
    Implementation of the CsvProcessor gRPC service using Bi-directional streaming.
    """

    def __init__(self, config: Optional[ServerConfig] = None):
        self.config = config or ServerConfig()
        self.storage_backend = None

        # Initialize storage if configured
        if self.config.storage_config:  # can cut it here
            try:
                self.storage_backend = StorageFactory.create_storage(
                    self.config.storage_config
                )
                log.info(
                    f"Initialized storage backend: {self.config.storage_config.storage_type}"
                )
            except Exception as e:
                log.error(f"Failed to initialize storage backend: {e}")
                # Fall back to local storage
                self.storage_backend = None

        self._ensure_results_directory()

    def _ensure_results_directory(self) -> None:
        """Ensure results directory exists."""
        self.config.results_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"Results directory set to: {self.config.results_dir}")

    def ProcessCsv(self, request_iterator: Iterator, context) -> Iterator:
        """
        Handles the bi-directional ProcessCsv RPC.

        Args:
            request_iterator: An iterator of CsvChunk messages from the client.
            context: The gRPC context for the call.

        Yields:
            ProgressUpdate messages with processing status and final summary.
        """
        log.info("New CSV stream processing session started")
        session = ProcessingSession(self.config, storage_backend=self.storage_backend)

        try:
            yield from self._process_stream(session, request_iterator, context)

        except Exception as e:
            log.error(f"Error during stream processing: {e}")
            self._handle_processing_error(context, e)
            # Yield an empty response to satisfy the iterator return type
            yield processing_pb2.ProgressUpdate()

    def _process_stream(
        self, session: ProcessingSession, request_iterator: Iterator, context
    ) -> Iterator:
        """Process the stream and yield progress updates."""
        for chunk_num, chunk in enumerate(request_iterator):
            self._handle_chunk(session, chunk, chunk_num)

            if session.update_progress_timing():
                yield self._create_progress_update(session, "Aggregating sales data...")

        # Send final updates and summary
        yield from self._finalize_processing(session)

    def _handle_chunk(self, session: ProcessingSession, chunk, chunk_num: int) -> None:
        """Process a single chunk from the stream."""
        if chunk_num == 0 and chunk.file_size_bytes:
            session.file_size_bytes = chunk.file_size_bytes
            log.info(f"Received file size: {session.file_size_bytes} bytes")

        session.processor.process_chunk(chunk.data)

    def _create_progress_update(
        self, session: ProcessingSession, message: str
    ) -> processing_pb2.ProgressUpdate:
        """Create a progress update message."""
        progress_pct = session.calculate_progress_percentage()

        return processing_pb2.ProgressUpdate(
            status_update=processing_pb2.ProcessingStatus(
                rows_processed=session.processor.rows_processed,
                malformed_rows=session.processor.malformed_rows,
                processed_percentage=round(progress_pct, 2),
                message=f"{message} ({progress_pct:.2f}%)",
            )
        )

    def _finalize_processing(self, session: ProcessingSession) -> Iterator:
        """Finalize processing and yield final results."""
        # Final progress update
        yield processing_pb2.ProgressUpdate(
            status_update=processing_pb2.ProcessingStatus(
                processed_percentage=100.0,
                rows_processed=session.processor.rows_processed,
                malformed_rows=session.processor.malformed_rows,
                message="Finalizing aggregation...",
            )
        )

        # Process final results - use storage if configured
        use_storage = session.storage_backend is not None
        stats = self._process_final_results(session, use_storage)
        processing_time = session.get_processing_time()

        log.info(f"Stream processing complete in {processing_time:.4f} seconds.")
        log.info(f"Processing stats: {stats}")

        # Get file URL based on storage backend
        storage_result_file_url = None
        if session.storage_backend:
            storage_result_file_url = session.processor.get_storage_file_url(
                session.output_filename
            )
            log.info(f"Result file accessible at: {storage_result_file_url}")

        # Final summary
        yield processing_pb2.ProgressUpdate(
            summary=processing_pb2.ProcessSummary(
                result_file_name=session.output_filename,
                storage_result_file_url=storage_result_file_url,
                processed_percentage=100.0,
                rows_processed=stats.rows_processed,
                total_sales=stats.total_sales,
                unique_departments=stats.unique_departments,
                processing_time_seconds=processing_time,
            )
        )

    def _process_final_results(
        self, session: ProcessingSession, use_storage: bool = False
    ):
        """Process final results and write output file."""
        try:
            session.processor.finalize(
                str(session.output_path), use_storage=use_storage
            )
            return session.processor.stats
        except CSVProcessingError as e:
            log.error(f"Failed to finalize processing: {e}")
            raise
        except Exception as e:
            log.error(f"Unexpected error during finalization: {e}")
            raise CSVProcessingError(f"Finalization failed: {e}") from e

    def _handle_processing_error(self, context, error: Exception) -> None:
        """Handle processing errors and set gRPC context."""
        context.set_code(grpc.StatusCode.INTERNAL)

        if isinstance(error, CSVProcessingError):
            context.set_details(f"Processing error: {error}")
        else:
            context.set_details(f"Internal server error: {error}")


class GRPCServer:
    """Manages gRPC server lifecycle."""

    def __init__(self, config: Optional[ServerConfig] = None):
        self.config = config or ServerConfig()
        self.server = None

    def start(self) -> None:
        """Start the gRPC server."""
        self.server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=self.config.max_workers)
        )

        processing_pb2_grpc.add_CsvProcessorServicer_to_server(
            CsvProcessorServicer(self.config), self.server
        )

        self.server.add_insecure_port(f"[::]:{self.config.port}")
        self.server.start()

        log.info(f"gRPC Server started on port {self.config.port}")
        log.info(f"Results directory: {self.config.results_dir}")
        log.info(f"Max workers: {self.config.max_workers}")

    def wait_for_termination(self) -> None:
        """Wait for server termination."""
        if self.server:
            self.server.wait_for_termination()
        else:
            log.warning("Server not started, cannot wait for termination")

    def stop(self, grace_period: float = 5.0) -> None:
        """Stop the gRPC server gracefully."""
        if self.server:
            self.server.stop(grace_period)
            log.info("gRPC server stopped")


def serve(config: Optional[ServerConfig] = None) -> GRPCServer:
    """Start and return a configured gRPC server."""
    server = GRPCServer(config)
    server.start()
    return server


if __name__ == "__main__":
    # Custom configuration can be passed here
    config = ServerConfig()

    server = serve(config)

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        log.info("Received interrupt signal, shutting down...")
        server.stop()

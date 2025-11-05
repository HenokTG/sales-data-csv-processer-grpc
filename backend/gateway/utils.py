import os
import sys
import time
import uuid
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional, Any

import grpc

from fastapi import UploadFile

from fastapi.background import BackgroundTasks
from fastapi import UploadFile, Request, HTTPException, status

from concurrent.futures import ThreadPoolExecutor

from config import app_config
from processor import processing_pb2
from processor import processing_pb2_grpc

log = logging.getLogger("gateway.main")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
executor = ThreadPoolExecutor(max_workers=5)


# --- Configuration ---
CHUNK_SIZE = app_config.CHUNK_SIZE
RESULTS_DIR = app_config.RESULTS_DIR
RESULTS_DIR = app_config.RESULTS_DIR

GRPC_SERVER_ADDRESS = app_config.GRPC_SERVER_ADDRESS

# In-memory "database" for job status.
# In production, this MUST be a persistent store like Redis or a DB.
jobs_db: Dict[str, Dict[str, Any]] = {}


#  --- Utility Functions UPLOAD FILE ---
async def validate_and_extract_upload(request: Request) -> Tuple[UploadFile, int]:
    """
    Validate upload request and extract file data.

    Returns:
        Tuple of (UploadFile, file_size_bytes)

    Raises:
        HTTPException: For invalid requests
    """
    try:
        form = await request.form()
        uploaded_file = form.get("file")

        if not uploaded_file or not uploaded_file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing file in upload.",
            )

        if not uploaded_file.filename.lower().endswith(".csv"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only CSV files are allowed.",
            )

        file_size_bytes = _parse_file_size(form.get("file_size_bytes"))
        return uploaded_file, file_size_bytes

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Form data processing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid form data or missing 'file' part.",
        )


def _parse_file_size(file_size_str: Optional[str]) -> int:
    """Parse file size string to integer, return 0 if invalid."""
    if not file_size_str:
        return 0

    try:
        return int(file_size_str)
    except (ValueError, TypeError):
        log.warning(f"Invalid file size format: {file_size_str}")
        return 0


def create_processing_job(filename: str, file_size_bytes: int) -> str:
    """Initialize job record in database and return job ID."""
    job_id = str(uuid.uuid4())

    jobs_db[job_id] = {
        "job_id": job_id,
        "filename": filename,
        "file_size_bytes": file_size_bytes,
        "status": "uploading",
        "rows_processed": 0,
        "created_at": time.time(),
    }

    return job_id


def schedule_background_processing(
    job_id: str, uploaded_file: UploadFile, background_tasks: BackgroundTasks
) -> None:
    """Schedule the processing job in the background."""
    background_tasks.add_task(
        executor.submit, _run_processing_job, job_id, uploaded_file
    )


#  -- Background Processing Function for UPLOAD ---


def _run_processing_job(job_id: str, uploaded_file: UploadFile):
    """
    Execute processing job in a background thread.
    Handles bi-directional gRPC communication and file streaming.

    Args:
        job_id: Unique job identifier
        uploaded_file: FastAPI UploadFile object containing the file data
    """
    log.info(f"Job {job_id}: Connecting to gRPC server at {GRPC_SERVER_ADDRESS}")
    jobs_db[job_id]["status"] = "uploading"

    try:
        _process_with_grpc(job_id, uploaded_file)
    except grpc.RpcError as e:
        error_detail = e.details() if hasattr(e, "details") else str(e)
        log.error(f"Job {job_id} gRPC RPC failed: {error_detail}")
        jobs_db[job_id].update(
            {"status": "failed", "error": f"gRPC Error: {error_detail}"}
        )
    except Exception as e:
        log.error(f"Job {job_id} failed: {e}")
        jobs_db[job_id].update({"status": "failed", "error": str(e)})


def _process_with_grpc(job_id: str, uploaded_file: UploadFile):
    """Handle gRPC communication and file processing."""
    with grpc.insecure_channel(GRPC_SERVER_ADDRESS) as channel:
        stub = processing_pb2_grpc.CsvProcessorStub(channel)
        request_iterator = _create_request_iterator(job_id, uploaded_file)
        response_iterator = stub.ProcessCsv(request_iterator)

        _process_responses(job_id, response_iterator)


def _create_request_iterator(job_id: str, uploaded_file: UploadFile):
    """Create synchronous generator for streaming file chunks to gRPC server."""
    log.info(
        f"Starting synchronous file read and gRPC chunking (Chunk Size: {CHUNK_SIZE} bytes)..."
    )

    is_first_chunk = True
    file_handle = uploaded_file.file

    while True:
        chunk = file_handle.read(CHUNK_SIZE)
        if not chunk:
            break

        if is_first_chunk:
            yield processing_pb2.CsvChunk(
                data=chunk,
                file_size_bytes=jobs_db[job_id].get("file_size_bytes", 0),
            )
            is_first_chunk = False
        else:
            yield processing_pb2.CsvChunk(data=chunk)


def _process_responses(job_id: str, response_iterator):
    """Process gRPC response stream and update job status."""
    summary_received = False

    for progress_update in response_iterator:
        if progress_update.HasField("status_update"):
            _handle_progress_update(job_id, progress_update.status_update)
        elif progress_update.HasField("summary"):
            _handle_final_summary(job_id, progress_update.summary)
            summary_received = True
            return

    if not summary_received:
        raise Exception(
            "gRPC stream closed unexpectedly before receiving final summary."
        )


def _handle_progress_update(job_id: str, status_update):
    """Update job progress with status update from server."""
    jobs_db[job_id].update(
        {
            "status": "processing",
            "rows_processed": status_update.rows_processed,
            "malformed_rows": status_update.malformed_rows,
            "processed_percentage": status_update.processed_percentage,
            "message": status_update.message,
            "last_update": time.time(),
        }
    )
    log.debug(f"Job {job_id}: Progress - {status_update.rows_processed} rows")


def _handle_final_summary(job_id: str, summary):
    """Handle final job summary and mark job as complete."""

    jobs_db[job_id].update(
        {
            "status": "complete",
            "rows_processed": summary.rows_processed,
            "malformed_rows": summary.malformed_rows,
            "processed_percentage": summary.processed_percentage,
            "total_sales": summary.total_sales,
            "unique_departments": summary.unique_departments,
            "processing_time_seconds": summary.processing_time_seconds,
            "result_file_name": summary.result_file_name,
            "result_file_url": f"/download/{summary.result_file_name}",
            "storage_result_file_url": summary.storage_result_file_url or None,
        }
    )
    log.info(f"Job {job_id}: COMPLETE. File: {summary.result_file_name}")


# --- Utilitues for DOWNLOAD api ---------


def validate_filename(filename: str) -> None:
    """
    Validate filename to prevent directory traversal and other attacks.

    Raises:
        HTTPException: If filename is invalid
    """
    if not filename or not filename.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Filename cannot be empty."
        )

    # More comprehensive path traversal prevention
    forbidden_patterns = ["..", "/", "\\", "~"]
    if any(pattern in filename for pattern in forbidden_patterns):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename."
        )

    # Validate file extension
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are available for download.",
        )

    # Additional security: ensure filename is safe
    if not _is_safe_filename(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename format."
        )


def _is_safe_filename(filename: str) -> bool:
    """Check if filename contains only safe characters."""
    # Allow alphanumeric, dots, hyphens, underscores
    safe_chars = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
    )
    return all(c in safe_chars for c in filename)


def get_safe_file_path(filename: str) -> Path:
    """Get safe filesystem path for the requested file."""
    results_dir = Path(RESULTS_DIR)

    # Ensure results directory exists and is a directory
    if not results_dir.exists() or not results_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Results directory not available.",
        )

    # Use resolve() to get absolute path and check if it's within results directory
    try:
        file_path = (results_dir / filename).resolve()
        results_dir_resolved = results_dir.resolve()

        # Security check: ensure the resolved path is within results directory
        if not str(file_path).startswith(str(results_dir_resolved)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path."
            )

        return file_path

    except (ValueError, RuntimeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename."
        )


def get_original_filename(result_filename: str) -> str:
    """
    Find the original filename associated with the result file.

    Returns:
        Original filename with 'processed_' prefix, or default name if not found.
    """
    # Create a reverse lookup for better performance
    for job in jobs_db.values():
        if job.get("result_file_name") == result_filename:
            original_name = job.get("filename", "results")
            # Clean the original filename for safety
            timestamp_float = time.time()
            safe_name = _make_filename_safe(original_name)
            return f"Processed_{safe_name}_{timestamp_float}.csv"

    # Default name if no match found
    return "Processed_results.csv"


def _make_filename_safe(filename: str) -> str:
    """Make a filename safe by removing path components and special characters."""
    # Remove any path components and get just the base name
    base_name = Path(filename).name

    # Remove extension and replace unsafe characters
    name_without_ext = base_name.rsplit(".", 1)[0] if "." in base_name else base_name
    safe_name = "".join(c for c in name_without_ext if c.isalnum() or c in ("-", "_"))

    return safe_name or "results"

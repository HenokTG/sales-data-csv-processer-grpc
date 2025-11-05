"""
FastAPI HTTP Gateway

This service acts as a proxy between the React frontend (HTTP) and the
Python gRPC backend. It handles:
1. HTTP File Uploads (Streaming) -> gRPC Client Stream.
2. Background Job Management (using in-memory dict).
3. Status Polling and File Download.
"""

import logging

from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.background import BackgroundTasks

from .utils import (
    jobs_db,
    create_processing_job,
    validate_and_extract_upload,
    schedule_background_processing,
    get_original_filename,
    get_safe_file_path,
    validate_filename,
)
from config import setup_cors_middleware, app_config
from .middleware.auth import api_key_auth_middleware


log = logging.getLogger("gateway.main")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Thread pool for running the blocking gRPC call asynchronously
executor = ThreadPoolExecutor(max_workers=5)

# --- Setup ---
app = FastAPI(
    title="gRPC Sales Processor Gateway",
    description="API for processing CSV files with gRPC",
    version="1.0.0",
)
# Add authentication middleware
app.middleware("http")(api_key_auth_middleware)

setup_cors_middleware(app)


@app.post("/upload")
async def upload_csv(
    request: Request, background_tasks: BackgroundTasks
) -> JSONResponse:
    """
    Initiates a processing job for an uploaded CSV file.

    Returns a Job ID immediately and delegates blocking gRPC communication
    to a background task.
    """
    try:
        uploaded_file, file_size = await validate_and_extract_upload(request)
        job_id = create_processing_job(uploaded_file.filename, file_size)
        schedule_background_processing(job_id, uploaded_file, background_tasks)

        log.info(f"Job {job_id} created for file: {uploaded_file.filename}")
        return JSONResponse(
            content={"job_id": job_id}, status_code=status.HTTP_202_ACCEPTED
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Unexpected error during upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during upload processing",
        )


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    """
    Returns the current status and progress of a background job,
    including the file size for frontend progress estimation.
    """
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job ID {job_id} not found.")

    # Return the full job dictionary.
    return JSONResponse(content=job)


@app.get("/download/{filename}")
async def download_result(filename: str) -> FileResponse:
    """
    Serve the final processed CSV file for download.

    Args:
        filename: The name of the processed result file

    Returns:
        FileResponse: The CSV file for download

    Raises:
        HTTPException: For invalid requests or file not found
    """
    validate_filename(filename)
    file_path = get_safe_file_path(filename)

    print("FILE PATH: ", file_path)

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Result file not found."
        )

    original_filename = get_original_filename(filename)

    """Create FileResponse with appropriate headers."""
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{original_filename}"',
            "Cache-Control": "no-cache",  # Prevent caching of results
        },
    )


@app.get("/")
def read_root():
    return {"message": "gRPC CSV Processor Gateway is running."}


if __name__ == "__main__":
    import uvicorn

    # This is for debugging only.
    # Run in production with `uvicorn gateway.main:app --host 0.0.0.0 --port 8000`
    uvicorn.run(app, host=app_config.GATEWAY_HOST, port=app_config.GATEWAY_PORT)

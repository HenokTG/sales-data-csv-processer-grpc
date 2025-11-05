import os
import logging

from fastapi import HTTPException, status, Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


from config import app_config


async def api_key_auth_middleware(request: Request, call_next):
    """
    Middleware to validate API key in request headers.
    """
    # Skip auth for health checks and docs in development
    if not app_config.REQUIRE_API_KEY:
        return await call_next(request)

    # Get API key from header
    api_key = request.headers.get("X-API-Key")

    if not api_key:
        log.warning(f"Missing API key for {request.method} {request.url.path}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="API key required"
        )

    if not app_config.API_KEY:
        log.error("API_KEY environment variable not set")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error",
        )

    if api_key != app_config.API_KEY:
        log.warning(f"Invalid API key attempt for {request.method} {request.url.path}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )

    # API key is valid, proceed
    response = await call_next(request)
    return response

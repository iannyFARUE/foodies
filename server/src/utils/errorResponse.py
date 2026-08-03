"""Utility functions for creating standardized error responses."""

from datetime import datetime, timezone
from typing import Optional, Any

from fastapi.responses import JSONResponse

from src.utils.logger import logger


def create_error_response(
    message: str,
    code: Optional[str] = None,
    details: Optional[Any] = None
) -> dict:
    return {
        "success": False,
        "message": message,
        "error": {
            "message": message,
            "code": code,
            "details": details
        },
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    }


def server_error_response(
    message: str,
    code: str,
    *,
    log_context: str,
    status_code: int = 500,
) -> JSONResponse:
    """Log the current exception and return a generic error payload (no stack traces). Call only from an except block."""
    logger.exception("%s failed", log_context)
    return JSONResponse(
        status_code=status_code,
        content=create_error_response(message=message, code=code),
    )

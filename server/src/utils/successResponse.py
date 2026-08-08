from datetime import datetime, timezone
from typing import Optional
from src.models.models import SuccessResponse, Pagination, T


def create_success_response(
    data: T,
    message: Optional[str] = None,
    pagination: Optional[Pagination] = None,
) -> SuccessResponse[T]:
    return SuccessResponse(
        message=message or "Operation completed successfully.",
        data=data,
        timestamp=datetime.now(timezone.utc).isoformat() + "Z",
        pagination=pagination,
    )

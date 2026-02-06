"""Generic pagination schema for list endpoints."""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper.

    Usage:
        PaginatedResponse[APIResponse]
    """

    items: list[T]
    total: int
    page: int
    page_size: int

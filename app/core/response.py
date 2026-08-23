from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应格式：{code, message, data}，code=0 表示成功。"""

    code: int = 0
    message: str = "ok"
    data: T | None = None


class Page(BaseModel, Generic[T]):
    model_config = ConfigDict(from_attributes=True)

    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


def ok(data: T | None = None, message: str = "ok") -> ApiResponse[T]:
    return ApiResponse(message=message, data=data)

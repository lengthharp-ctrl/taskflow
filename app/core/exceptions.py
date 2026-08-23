from typing import Any


class AppError(Exception):
    """业务异常基类，由全局异常处理器统一转成统一响应格式。"""

    status_code: int = 400
    code: str = "BAD_REQUEST"
    message: str = "请求错误"
    data: Any = None

    def __init__(self, message: str | None = None, *, data: Any = None):
        super().__init__(message or self.message)
        if message is not None:
            self.message = message
        if data is not None:
            self.data = data


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "资源不存在"


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"
    message = "请先登录"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"
    message = "没有权限执行该操作"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    message = "数据冲突"


class ValidationFailedError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"
    message = "参数校验失败"

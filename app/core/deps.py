import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_token
from app.models import Project, ProjectMember, ProjectRole, Task, User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None:
        raise UnauthorizedError("请先登录")
    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise UnauthorizedError("登录凭证无效或已过期") from None
    if payload.get("type") != "access":
        raise UnauthorizedError("登录凭证类型错误")
    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError()
    try:
        uid = uuid.UUID(str(user_id))
    except ValueError:
        raise UnauthorizedError() from None
    user = await db.get(User, uid)
    if user is None or not user.is_active:
        raise UnauthorizedError("用户不存在或已被禁用")
    return user


async def get_project_membership(
    project_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectMember:
    project = await db.get(Project, project_id)
    if project is None:
        raise NotFoundError("项目不存在")
    membership = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id,
        )
    )
    if membership is None:
        raise ForbiddenError("只有项目成员才能访问该项目")
    return membership


async def get_project_admin(
    project_id: uuid.UUID,
    membership: Annotated[ProjectMember, Depends(get_project_membership)],
) -> ProjectMember:
    if membership.role != ProjectRole.ADMIN.value:
        raise ForbiddenError("该操作需要项目管理员权限")
    return membership


async def get_task_for_member(
    task_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> tuple[Task, ProjectMember]:
    task = await db.get(Task, task_id)
    if task is None:
        raise NotFoundError("任务不存在")
    membership = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == task.project_id,
            ProjectMember.user_id == user.id,
        )
    )
    if membership is None:
        raise ForbiddenError("只有项目成员才能访问该任务")
    return task, membership

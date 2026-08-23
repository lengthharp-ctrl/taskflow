import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import (
    get_current_user,
    get_project_membership,
    get_task_for_member,
)
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.query import apply_task_filters, apply_task_sort, paginate
from app.core.response import ApiResponse, Page, ok
from app.models import ProjectMember, Task, TaskPriority, TaskStatus, User
from app.schemas.task import TaskCreate, TaskOut, TaskStatusUpdate, TaskUpdate

router = APIRouter(tags=["任务"])

ALLOWED_STATUS_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.TODO: {TaskStatus.IN_PROGRESS, TaskStatus.DONE},
    TaskStatus.IN_PROGRESS: {TaskStatus.TODO, TaskStatus.DONE},
    TaskStatus.DONE: {TaskStatus.TODO},
}


class TaskFilters(BaseModel):
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee_id: uuid.UUID | None = None
    search: str | None = Field(default=None, max_length=100)
    due_after: datetime | None = None
    due_before: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort: str = Field(default="-created_at", pattern=r"^-?[a-zA-Z_]+$")


async def _ensure_assignee_is_member(
    db: AsyncSession, project_id: uuid.UUID, assignee_id: uuid.UUID
) -> None:
    membership = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == assignee_id,
        )
    )
    if membership is None:
        raise ValidationFailedError("负责人必须是项目成员")


async def _load_task(db: AsyncSession, task_id: uuid.UUID) -> Task:
    task = await db.scalar(
        select(Task)
        .where(Task.id == task_id)
        .options(selectinload(Task.assignee))
        .execution_options(populate_existing=True)
    )
    if task is None:
        raise NotFoundError("任务不存在")
    return task


@router.post(
    "/projects/{project_id}/tasks",
    response_model=ApiResponse[TaskOut],
    status_code=201,
    summary="创建任务",
)
async def create_task(
    project_id: uuid.UUID,
    payload: TaskCreate,
    user: Annotated[User, Depends(get_current_user)],
    _membership: Annotated[ProjectMember, Depends(get_project_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    if payload.assignee_id is not None:
        await _ensure_assignee_is_member(db, project_id, payload.assignee_id)
    task = Task(
        project_id=project_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        assignee_id=payload.assignee_id,
        due_date=payload.due_date,
        created_by_id=user.id,
        status=TaskStatus.TODO,
    )
    db.add(task)
    await db.commit()
    task = await _load_task(db, task.id)
    return ok(task, message="任务创建成功")


@router.get(
    "/projects/{project_id}/tasks",
    response_model=ApiResponse[Page[TaskOut]],
    summary="任务列表（筛选/分页/排序）",
)
async def list_tasks(
    project_id: uuid.UUID,
    filters: Annotated[TaskFilters, Depends()],
    _membership: Annotated[ProjectMember, Depends(get_project_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    stmt = (
        select(Task)
        .where(Task.project_id == project_id)
        .options(selectinload(Task.assignee))
    )
    stmt = apply_task_filters(stmt, filters)
    stmt = apply_task_sort(stmt, filters.sort)
    page = await paginate(db, stmt, filters.page, filters.page_size)
    return ok(page)


@router.get(
    "/tasks/{task_id}",
    response_model=ApiResponse[TaskOut],
    summary="任务详情",
)
async def get_task(
    task_id: uuid.UUID,
    _ctx: Annotated[tuple[Task, ProjectMember], Depends(get_task_for_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    task = await _load_task(db, task_id)
    return ok(task)


@router.patch(
    "/tasks/{task_id}",
    response_model=ApiResponse[TaskOut],
    summary="更新任务",
)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    _ctx: Annotated[tuple[Task, ProjectMember], Depends(get_task_for_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    task = _ctx[0]
    data = payload.model_dump(exclude_unset=True)
    if data.get("assignee_id") is not None:
        await _ensure_assignee_is_member(db, task.project_id, data["assignee_id"])
    for field, value in data.items():
        setattr(task, field, value)
    await db.commit()
    task = await _load_task(db, task.id)
    return ok(task, message="任务已更新")


@router.patch(
    "/tasks/{task_id}/status",
    response_model=ApiResponse[TaskOut],
    summary="流转任务状态",
)
async def update_task_status(
    task_id: uuid.UUID,
    payload: TaskStatusUpdate,
    _ctx: Annotated[tuple[Task, ProjectMember], Depends(get_task_for_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    task = _ctx[0]
    if payload.status != task.status:
        allowed = ALLOWED_STATUS_TRANSITIONS.get(task.status, set())
        if payload.status not in allowed:
            raise ValidationFailedError(
                f"不允许从「{task.status.value}」流转到「{payload.status.value}」"
            )
        task.status = payload.status
        task.status_changed_at = datetime.now(timezone.utc)
        await db.commit()
    task = await _load_task(db, task.id)
    return ok(task, message="任务状态已更新")


@router.delete(
    "/tasks/{task_id}",
    response_model=ApiResponse,
    summary="删除任务",
)
async def delete_task(
    task_id: uuid.UUID,
    _ctx: Annotated[tuple[Task, ProjectMember], Depends(get_task_for_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    task = _ctx[0]
    await db.delete(task)
    await db.commit()
    return ok(None, message="任务已删除")

import math
from datetime import datetime

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Page
from app.models import Task


async def paginate(db: AsyncSession, stmt: Select, page: int, page_size: int) -> Page:
    """统一分页：返回 Page 结构（items/total/page/page_size/pages）。"""
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await db.scalar(count_stmt)) or 0
    rows = (
        await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    pages = math.ceil(total / page_size) if total else 0
    return Page(items=list(rows), total=total, page=page, page_size=page_size, pages=pages)


def apply_task_filters(stmt: Select, filters) -> Select:
    """按状态 / 负责人 / 优先级 / 关键字 / 截止日期筛选任务。"""
    if filters.status is not None:
        stmt = stmt.where(Task.status == filters.status)
    if filters.priority is not None:
        stmt = stmt.where(Task.priority == filters.priority)
    if filters.assignee_id is not None:
        stmt = stmt.where(Task.assignee_id == filters.assignee_id)
    if filters.search:
        like = f"%{filters.search}%"
        stmt = stmt.where(
            or_(Task.title.ilike(like), Task.description.ilike(like))
        )
    if filters.due_after is not None:
        stmt = stmt.where(Task.due_date >= filters.due_after)
    if filters.due_before is not None:
        stmt = stmt.where(Task.due_date <= filters.due_before)
    return stmt


_SORT_COLUMNS = {
    "created_at": Task.created_at,
    "updated_at": Task.updated_at,
    "due_date": Task.due_date,
    "title": Task.title,
}

_PRIORITY_ORDER = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "urgent": 3,
}

_STATUS_ORDER = {
    "todo": 0,
    "in_progress": 1,
    "done": 2,
}


def apply_task_sort(stmt: Select, sort: str) -> Select:
    """白名单排序：支持 - 前缀表示倒序，priority/status 按业务顺序排序。"""
    descending = sort.startswith("-")
    key = sort.lstrip("-")
    if key == "priority":
        column = case(_PRIORITY_ORDER, value=Task.priority, else_=99)
    elif key == "status":
        column = case(_STATUS_ORDER, value=Task.status, else_=99)
    else:
        column = _SORT_COLUMNS.get(key, Task.created_at)
    return stmt.order_by(
        column.desc() if descending else column.asc(),
        Task.created_at.desc(),
    )

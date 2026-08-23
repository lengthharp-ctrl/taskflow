import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_current_user, get_task_for_member
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.response import ApiResponse, ok
from app.models import Comment, ProjectMember, ProjectRole, Task, User
from app.schemas.comment import CommentCreate, CommentOut, CommentUpdate

router = APIRouter(tags=["评论"])


async def _get_comment(db: AsyncSession, comment_id: uuid.UUID) -> Comment:
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise NotFoundError("评论不存在")
    return comment


async def _is_project_admin(
    db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    membership = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    return membership is not None and membership.role == ProjectRole.ADMIN.value


@router.get(
    "/tasks/{task_id}/comments",
    response_model=ApiResponse[list[CommentOut]],
    summary="任务评论列表",
)
async def list_comments(
    task_id: uuid.UUID,
    _ctx: Annotated[tuple[Task, ProjectMember], Depends(get_task_for_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    comments = (
        await db.execute(
            select(Comment)
            .where(Comment.task_id == task_id)
            .options(selectinload(Comment.author))
            .order_by(Comment.created_at)
        )
    ).scalars().all()
    return ok(comments)


@router.post(
    "/tasks/{task_id}/comments",
    response_model=ApiResponse[CommentOut],
    status_code=201,
    summary="发表评论",
)
async def create_comment(
    task_id: uuid.UUID,
    payload: CommentCreate,
    _ctx: Annotated[tuple[Task, ProjectMember], Depends(get_task_for_member)],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    task = _ctx[0]
    comment = Comment(
        task_id=task.id,
        author_id=user.id,
        content=payload.content,
    )
    db.add(comment)
    await db.commit()
    comment = await db.scalar(
        select(Comment)
        .where(Comment.id == comment.id)
        .options(selectinload(Comment.author))
        .execution_options(populate_existing=True)
    )
    return ok(comment, message="评论成功")


@router.patch(
    "/comments/{comment_id}",
    response_model=ApiResponse[CommentOut],
    summary="修改评论（仅作者）",
)
async def update_comment(
    comment_id: uuid.UUID,
    payload: CommentUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    comment = await _get_comment(db, comment_id)
    if comment.author_id != user.id:
        raise ForbiddenError("只能修改自己的评论")
    comment.content = payload.content
    await db.commit()
    comment = await db.scalar(
        select(Comment)
        .where(Comment.id == comment_id)
        .options(selectinload(Comment.author))
        .execution_options(populate_existing=True)
    )
    return ok(comment, message="评论已更新")


@router.delete(
    "/comments/{comment_id}",
    response_model=ApiResponse,
    summary="删除评论（作者或项目管理员）",
)
async def delete_comment(
    comment_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    comment = await _get_comment(db, comment_id)
    task = await db.get(Task, comment.task_id)
    if task is None:
        raise NotFoundError("任务不存在")
    is_admin = await _is_project_admin(db, task.project_id, user.id)
    if comment.author_id != user.id and not is_admin:
        raise ForbiddenError("没有权限删除该评论")
    await db.delete(comment)
    await db.commit()
    return ok(None, message="评论已删除")

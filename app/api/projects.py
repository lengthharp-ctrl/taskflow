import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_current_user, get_project_admin, get_project_membership
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.response import ApiResponse, Page, ok
from app.models import Project, ProjectMember, ProjectRole, Task, User
from app.schemas.project import (
    MemberAdd,
    MemberRoleUpdate,
    ProjectCreate,
    ProjectDetailOut,
    ProjectMemberOut,
    ProjectOut,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["项目"])


async def _counts(db: AsyncSession, project_id: uuid.UUID) -> tuple[int, int]:
    member_count = await db.scalar(
        select(func.count(ProjectMember.id)).where(
            ProjectMember.project_id == project_id
        )
    )
    task_count = await db.scalar(
        select(func.count(Task.id)).where(Task.project_id == project_id)
    )
    return member_count or 0, task_count or 0


def _project_out_from_row(
    project: Project, member_count: int, task_count: int
) -> ProjectOut:
    out = ProjectOut.model_validate(project)
    out.member_count = member_count
    out.task_count = task_count
    return out


async def _project_out(db: AsyncSession, project: Project) -> ProjectOut:
    out = ProjectOut.model_validate(project)
    out.member_count, out.task_count = await _counts(db, project.id)
    return out


@router.post(
    "",
    response_model=ApiResponse[ProjectOut],
    status_code=201,
    summary="创建项目",
)
async def create_project(
    payload: ProjectCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    project = Project(
        name=payload.name,
        description=payload.description,
        owner_id=user.id,
    )
    project.members.append(
        ProjectMember(user_id=user.id, role=ProjectRole.ADMIN.value)
    )
    db.add(project)
    await db.commit()
    return ok(await _project_out(db, project), message="项目创建成功")


@router.get(
    "",
    response_model=ApiResponse[Page[ProjectOut]],
    summary="我参与的项目列表（分页）",
)
async def list_projects(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ApiResponse:
    member_count_subq = (
        select(func.count(ProjectMember.id))
        .where(ProjectMember.project_id == Project.id)
        .correlate(Project)
        .scalar_subquery()
    )
    task_count_subq = (
        select(func.count(Task.id))
        .where(Task.project_id == Project.id)
        .correlate(Project)
        .scalar_subquery()
    )
    base = (
        select(
            Project,
            member_count_subq.label("member_count"),
            task_count_subq.label("task_count"),
        )
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user.id)
        .order_by(Project.created_at.desc())
    )
    total = (
        await db.scalar(
            select(func.count()).select_from(base.order_by(None).subquery())
        )
    ) or 0
    rows = (
        await db.execute(
            base.offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    items = [
        _project_out_from_row(project, mc, tc)
        for project, mc, tc in rows
    ]
    pages = math.ceil(total / page_size) if total else 0
    return ok(
        Page(items=items, total=total, page=page, page_size=page_size, pages=pages),
        message="ok",
    )


@router.get(
    "/{project_id}",
    response_model=ApiResponse[ProjectDetailOut],
    summary="项目详情（含成员）",
)
async def get_project(
    project_id: uuid.UUID,
    _membership: Annotated[ProjectMember, Depends(get_project_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    project = await db.get(
        Project,
        project_id,
        options=[
            selectinload(Project.members).selectinload(ProjectMember.user)
        ],
    )
    if project is None:
        raise NotFoundError("项目不存在")
    out = ProjectDetailOut.model_validate(project)
    out.members = project.members
    out.member_count, out.task_count = await _counts(db, project.id)
    return ok(out)


@router.patch(
    "/{project_id}",
    response_model=ApiResponse[ProjectOut],
    summary="更新项目（管理员）",
)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    _admin: Annotated[ProjectMember, Depends(get_project_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    project = await db.get(Project, project_id)
    if project is None:
        raise NotFoundError("项目不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await db.commit()
    return ok(await _project_out(db, project), message="项目已更新")


@router.delete(
    "/{project_id}",
    response_model=ApiResponse,
    summary="删除项目（管理员）",
)
async def delete_project(
    project_id: uuid.UUID,
    _admin: Annotated[ProjectMember, Depends(get_project_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    project = await db.get(Project, project_id)
    if project is None:
        raise NotFoundError("项目不存在")
    await db.delete(project)
    await db.commit()
    return ok(None, message="项目已删除")


@router.get(
    "/{project_id}/members",
    response_model=ApiResponse[list[ProjectMemberOut]],
    summary="项目成员列表",
)
async def list_members(
    project_id: uuid.UUID,
    _membership: Annotated[ProjectMember, Depends(get_project_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    members = (
        await db.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .options(selectinload(ProjectMember.user))
            .order_by(ProjectMember.joined_at)
        )
    ).scalars().all()
    return ok([ProjectMemberOut.model_validate(member) for member in members])


@router.post(
    "/{project_id}/members",
    response_model=ApiResponse[ProjectMemberOut],
    status_code=201,
    summary="添加成员（管理员）",
)
async def add_member(
    project_id: uuid.UUID,
    payload: MemberAdd,
    _admin: Annotated[ProjectMember, Depends(get_project_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    if payload.user_id:
        target = await db.get(User, payload.user_id)
    else:
        target = await db.scalar(select(User).where(User.email == payload.email))
    if target is None:
        raise NotFoundError("用户不存在")
    existing = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == target.id,
        )
    )
    if existing is not None:
        raise ConflictError("该用户已是项目成员")
    member = ProjectMember(
        project_id=project_id,
        user_id=target.id,
        role=payload.role.value,
    )
    db.add(member)
    await db.commit()
    member = await db.scalar(
        select(ProjectMember)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == target.id,
        )
        .options(selectinload(ProjectMember.user))
    )
    return ok(ProjectMemberOut.model_validate(member), message="成员已添加")


@router.patch(
    "/{project_id}/members/{user_id}",
    response_model=ApiResponse[ProjectMemberOut],
    summary="修改成员角色（管理员）",
)
async def update_member_role(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: MemberRoleUpdate,
    _admin: Annotated[ProjectMember, Depends(get_project_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    member = await db.scalar(
        select(ProjectMember)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
        .options(selectinload(ProjectMember.user))
    )
    if member is None:
        raise NotFoundError("成员不存在")
    project = await db.get(Project, project_id)
    if member.user_id == project.owner_id:
        raise ForbiddenError("不能修改项目创建者的角色")
    member.role = payload.role.value
    await db.commit()
    return ok(ProjectMemberOut.model_validate(member), message="成员角色已更新")


@router.delete(
    "/{project_id}/members/{user_id}",
    response_model=ApiResponse,
    summary="移除成员（管理员）",
)
async def remove_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    _admin: Annotated[ProjectMember, Depends(get_project_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    member = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    if member is None:
        raise NotFoundError("成员不存在")
    project = await db.get(Project, project_id)
    if member.user_id == project.owner_id:
        raise ForbiddenError("不能移除项目创建者")
    await db.delete(member)
    await db.commit()
    return ok(None, message="成员已移除")

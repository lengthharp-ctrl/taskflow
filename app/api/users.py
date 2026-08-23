import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.core.response import ApiResponse, ok
from app.core.security import hash_password
from app.models import User
from app.schemas.user import UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["用户"])


@router.get(
    "/me",
    response_model=ApiResponse[UserOut],
    summary="我的资料",
)
async def get_me(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    return ok(UserOut.model_validate(user))


@router.patch(
    "/me",
    response_model=ApiResponse[UserOut],
    summary="更新我的资料",
)
async def update_me(
    payload: UserUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    data = payload.model_dump(exclude_unset=True)
    if data.get("password"):
        user.hashed_password = hash_password(data.pop("password"))
    for field, value in data.items():
        setattr(user, field, value)
    await db.commit()
    return ok(UserOut.model_validate(user), message="资料已更新")


@router.get(
    "/{user_id}",
    response_model=ApiResponse[UserOut],
    summary="查看用户资料",
)
async def get_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    return ok(UserOut.model_validate(user))

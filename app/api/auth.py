import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.response import ApiResponse, ok
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import User
from app.schemas.auth import AuthResult, LoginRequest, RefreshRequest, TokenPair
from app.schemas.user import UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["认证"])
settings = get_settings()


def _token_pair(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def _find_by_account(db: AsyncSession, account: str) -> User | None:
    return await db.scalar(
        select(User).where(
            or_(User.email == account, User.username == account)
        )
    )


@router.post(
    "/register",
    response_model=ApiResponse[AuthResult],
    status_code=201,
    summary="用户注册",
)
async def register(
    payload: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    exists = await db.scalar(
        select(User).where(
            or_(User.email == payload.email, User.username == payload.username)
        )
    )
    if exists is not None:
        raise ConflictError("邮箱或用户名已被注册")
    user = User(
        email=payload.email,
        username=payload.username,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    return ok(
        AuthResult(user=UserOut.model_validate(user), tokens=_token_pair(user)),
        message="注册成功",
    )


@router.post(
    "/login",
    response_model=ApiResponse[AuthResult],
    summary="用户登录",
)
async def login(
    payload: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    user = await _find_by_account(db, payload.account)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise UnauthorizedError("用户名/邮箱或密码错误")
    if not user.is_active:
        raise UnauthorizedError("账号已被禁用")
    return ok(
        AuthResult(user=UserOut.model_validate(user), tokens=_token_pair(user)),
        message="登录成功",
    )


@router.post(
    "/refresh",
    response_model=ApiResponse[TokenPair],
    summary="刷新访问令牌",
)
async def refresh(
    payload: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse:
    try:
        claims = decode_token(payload.refresh_token)
    except Exception:
        raise UnauthorizedError("刷新令牌无效或已过期") from None
    if claims.get("type") != "refresh":
        raise UnauthorizedError("令牌类型错误")
    user_id = claims.get("sub")
    if not user_id:
        raise UnauthorizedError()
    try:
        uid = uuid.UUID(str(user_id))
    except ValueError:
        raise UnauthorizedError() from None
    user = await db.get(User, uid)
    if user is None or not user.is_active:
        raise UnauthorizedError("用户不存在或已被禁用")
    return ok(_token_pair(user), message="令牌已刷新")


@router.get(
    "/me",
    response_model=ApiResponse[UserOut],
    summary="当前登录用户",
)
async def me(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    return ok(UserOut.model_validate(user))

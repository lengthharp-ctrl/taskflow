import uuid

import pytest
from jose import JWTError

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.config import Settings


def test_password_hash_and_verify():
    hashed = hash_password("password123")
    assert hashed != "password123"
    assert verify_password("password123", hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token_roundtrip():
    uid = uuid.uuid4()
    token = create_access_token(uid)
    claims = decode_token(token)
    assert claims["sub"] == str(uid)
    assert claims["type"] == "access"


def test_refresh_token_type():
    claims = decode_token(create_refresh_token(uuid.uuid4()))
    assert claims["type"] == "refresh"


def test_expired_token_rejected():
    token = create_access_token(uuid.uuid4(), expires_minutes=-1)
    with pytest.raises(JWTError):
        decode_token(token)


def test_garbage_token_rejected():
    with pytest.raises(JWTError):
        decode_token("not-a-jwt")


def test_async_database_url_normalization():
    assert (
        Settings(DATABASE_URL="postgres://u:p@host:5432/db").async_database_url
        == "postgresql+asyncpg://u:p@host:5432/db"
    )
    assert (
        Settings(DATABASE_URL="postgresql://u:p@host:5432/db").async_database_url
        == "postgresql+asyncpg://u:p@host:5432/db"
    )
    assert (
        Settings(
            DATABASE_URL="postgresql+asyncpg://u:p@host:5432/db"
        ).async_database_url
        == "postgresql+asyncpg://u:p@host:5432/db"
    )
    assert (
        Settings(DATABASE_URL="sqlite+aiosqlite:///:memory:").async_database_url
        == "sqlite+aiosqlite:///:memory:"
    )

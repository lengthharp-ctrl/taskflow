import os
import sys
from pathlib import Path

# 必须在导入 app 之前设置测试环境变量
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("BACKEND_CORS_ORIGINS", "*")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.main import app
from app.models import Base


@pytest.fixture(scope="session")
async def db_engine():
    test_url = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    kwargs = {"poolclass": StaticPool} if test_url.startswith("sqlite") else {}
    engine = create_async_engine(test_url, **kwargs)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """function 级事务回滚：每个测试在独立事务中执行，结束自动回滚。"""
    conn = await db_engine.connect()
    trans = await conn.begin()
    # aiosqlite 下 SQLAlchemy 的 BEGIN 是延迟的；显式发出 BEGIN，
    # 否则 SAVEPOINT 会成为最外层事务，RELEASE 时即被提交、无法回滚。
    if str(db_engine.url).startswith("sqlite"):
        await conn.exec_driver_sql("BEGIN")
    session = AsyncSession(
        bind=conn,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    yield session
    await session.close()
    await trans.rollback()
    await conn.close()


@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def register_user(client, username="alice", email="alice@example.com",
                        password="password123", full_name=None):
    payload = {"username": username, "email": email, "password": password}
    if full_name:
        payload["full_name"] = full_name
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    return {"user": data["user"], "tokens": data["tokens"]}


def auth_headers(tokens) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
async def alice(client):
    return await register_user(client, username="alice", email="alice@example.com")


@pytest.fixture
async def bob(client):
    return await register_user(client, username="bob", email="bob@example.com")


@pytest.fixture
async def charlie(client):
    return await register_user(client, username="charlie", email="charlie@example.com")


@pytest.fixture
async def project(client, alice):
    resp = await client.post(
        "/api/v1/projects",
        json={"name": "Demo 项目", "description": "示例项目"},
        headers=auth_headers(alice["tokens"]),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


@pytest.fixture
async def task(client, project, alice):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/tasks",
        json={"title": "写测试", "priority": "high"},
        headers=auth_headers(alice["tokens"]),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]

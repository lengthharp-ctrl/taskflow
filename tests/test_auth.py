import uuid
from sqlalchemy import select

from tests.helpers import auth_headers, register_user
from app.models import User
from app.core.security import create_access_token, create_refresh_token


class TestRegister:
    async def test_register_success(self, client):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "alice",
                "email": "alice@example.com",
                "password": "password123",
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["user"]["username"] == "alice"
        assert data["user"]["email"] == "alice@example.com"
        assert data["tokens"]["access_token"]
        assert data["tokens"]["refresh_token"]
        assert data["tokens"]["token_type"] == "bearer"

    async def test_register_duplicate_email(self, client):
        await register_user(client)
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "alice2",
                "email": "alice@example.com",
                "password": "password123",
            },
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == 409

    async def test_register_duplicate_username(self, client):
        await register_user(client)
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "alice",
                "email": "other@example.com",
                "password": "password123",
            },
        )
        assert resp.status_code == 409

    async def test_register_validation_error(self, client):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "a",
                "email": "not-an-email",
                "password": "short",
            },
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == 422
        assert body["message"] == "参数校验失败"


class TestLogin:
    async def test_login_by_username(self, client):
        await register_user(client, username="alice", email="alice@example.com")
        resp = await client.post(
            "/api/v1/auth/login",
            json={"account": "alice", "password": "password123"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["user"]["username"] == "alice"

    async def test_login_by_email(self, client):
        await register_user(client, username="alice", email="alice@example.com")
        resp = await client.post(
            "/api/v1/auth/login",
            json={"account": "alice@example.com", "password": "password123"},
        )
        assert resp.status_code == 200

    async def test_login_wrong_password(self, client):
        await register_user(client)
        resp = await client.post(
            "/api/v1/auth/login",
            json={"account": "alice", "password": "wrong-password"},
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == 401

    async def test_login_unknown_account(self, client):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"account": "nobody", "password": "password123"},
        )
        assert resp.status_code == 401

    async def test_login_disabled_account(self, client, db_session):
        await register_user(client)
        user = await db_session.scalar(select(User).where(User.username == "alice"))
        user.is_active = False
        await db_session.commit()
        resp = await client.post(
            "/api/v1/auth/login",
            json={"account": "alice", "password": "password123"},
        )
        assert resp.status_code == 401


class TestMe:
    async def test_me_with_token(self, client, alice):
        resp = await client.get(
            "/api/v1/auth/me", headers=auth_headers(alice["tokens"])
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["username"] == "alice"

    async def test_me_without_token(self, client):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401
        assert resp.json()["code"] == 401

    async def test_me_with_garbage_token(self, client):
        resp = await client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-token"}
        )
        assert resp.status_code == 401

    async def test_me_with_refresh_token_rejected(self, client, alice):
        resp = await client.get(
            "/api/v1/auth/me",
            headers=auth_headers(
                {"access_token": alice["tokens"]["refresh_token"]}
            ),
        )
        assert resp.status_code == 401

    async def test_me_with_non_uuid_subject(self, client):
        token = create_access_token("not-a-uuid")
        resp = await client.get(
            "/api/v1/auth/me", headers=auth_headers({"access_token": token})
        )
        assert resp.status_code == 401

    async def test_me_with_unknown_user(self, client):
        token = create_access_token(uuid.uuid4())
        resp = await client.get(
            "/api/v1/auth/me", headers=auth_headers({"access_token": token})
        )
        assert resp.status_code == 401


class TestRefresh:
    async def test_refresh_returns_new_tokens(self, client, alice):
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": alice["tokens"]["refresh_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["access_token"]
        assert data["refresh_token"]
        # 新 access token 可用
        me = await client.get(
            "/api/v1/auth/me", headers=auth_headers({"access_token": data["access_token"]})
        )
        assert me.status_code == 200

    async def test_refresh_with_access_token_rejected(self, client, alice):
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": alice["tokens"]["access_token"]},
        )
        assert resp.status_code == 401

    async def test_refresh_with_garbage_token(self, client):
        resp = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "garbage"}
        )
        assert resp.status_code == 401

    async def test_refresh_with_unknown_user(self, client, alice):
        # 构造一个指向不存在用户的刷新令牌
        token = create_refresh_token(uuid.uuid4())
        resp = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": token}
        )
        assert resp.status_code == 401

    async def test_refresh_with_expired_token(self, client):
        token = create_refresh_token(uuid.uuid4(), expires_days=-1)
        resp = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": token}
        )
        assert resp.status_code == 401

    async def test_refresh_with_non_uuid_subject(self, client):
        from jose import jwt as jose_jwt

        from app.core.config import get_settings

        settings = get_settings()
        token = jose_jwt.encode(
            {"sub": "not-a-uuid", "type": "refresh", "exp": 9999999999},
            settings.SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        resp = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": token}
        )
        assert resp.status_code == 401

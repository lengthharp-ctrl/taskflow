from tests.helpers import auth_headers, register_user


class TestUsers:
    async def test_get_me(self, client, alice):
        resp = await client.get(
            "/api/v1/users/me", headers=auth_headers(alice["tokens"])
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["email"] == "alice@example.com"

    async def test_update_me(self, client, alice):
        resp = await client.patch(
            "/api/v1/users/me",
            json={"full_name": "Alice Wang", "bio": "后端工程师"},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["full_name"] == "Alice Wang"
        assert data["bio"] == "后端工程师"

    async def test_update_me_password_then_login(self, client, alice):
        resp = await client.patch(
            "/api/v1/users/me",
            json={"password": "new-password-123"},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        old = await client.post(
            "/api/v1/auth/login",
            json={"account": "alice", "password": "password123"},
        )
        assert old.status_code == 401
        new = await client.post(
            "/api/v1/auth/login",
            json={"account": "alice", "password": "new-password-123"},
        )
        assert new.status_code == 200

    async def test_get_user_profile(self, client, alice, bob):
        resp = await client.get(f"/api/v1/users/{alice['user']['id']}")
        assert resp.status_code == 200
        assert resp.json()["data"]["username"] == "alice"

    async def test_get_user_not_found(self, client):
        import uuid

        resp = await client.get(f"/api/v1/users/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["code"] == 404

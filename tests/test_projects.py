import uuid

from tests.helpers import auth_headers, register_user


async def _add_member(client, project_id, tokens, user_id=None, email=None, role="member"):
    payload = {"role": role}
    if user_id:
        payload["user_id"] = user_id
    if email:
        payload["email"] = email
    resp = await client.post(
        f"/api/v1/projects/{project_id}/members",
        json=payload,
        headers=auth_headers(tokens),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


class TestProjectCRUD:
    async def test_create_project(self, client, alice):
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "我的项目", "description": "描述"},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "我的项目"
        assert data["owner_id"] == alice["user"]["id"]
        assert data["member_count"] == 1
        assert data["task_count"] == 0

    async def test_create_project_validation(self, client, alice):
        resp = await client.post(
            "/api/v1/projects",
            json={"name": ""},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 422

    async def test_create_requires_auth(self, client):
        resp = await client.post("/api/v1/projects", json={"name": "x"})
        assert resp.status_code == 401

    async def test_list_projects_only_mine(self, client, alice, bob):
        await client.post(
            "/api/v1/projects",
            json={"name": "A 的项目"},
            headers=auth_headers(alice["tokens"]),
        )
        await client.post(
            "/api/v1/projects",
            json={"name": "B 的项目"},
            headers=auth_headers(bob["tokens"]),
        )
        resp = await client.get(
            "/api/v1/projects", headers=auth_headers(alice["tokens"])
        )
        body = resp.json()["data"]
        assert body["total"] == 1
        assert body["items"][0]["name"] == "A 的项目"

    async def test_list_projects_pagination(self, client, alice):
        for i in range(3):
            await client.post(
                "/api/v1/projects",
                json={"name": f"项目 {i}"},
                headers=auth_headers(alice["tokens"]),
            )
        resp = await client.get(
            "/api/v1/projects",
            params={"page": 2, "page_size": 2},
            headers=auth_headers(alice["tokens"]),
        )
        data = resp.json()["data"]
        assert data["total"] == 3
        assert data["pages"] == 2
        assert len(data["items"]) == 1

    async def test_project_detail_includes_members(self, client, alice, project):
        resp = await client.get(
            f"/api/v1/projects/{project['id']}",
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["member_count"] == 1
        assert data["members"][0]["role"] == "admin"
        assert data["members"][0]["user"]["username"] == "alice"

    async def test_non_member_forbidden(self, client, project, bob):
        resp = await client.get(
            f"/api/v1/projects/{project['id']}",
            headers=auth_headers(bob["tokens"]),
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == 403

    async def test_project_not_found(self, client, alice):
        resp = await client.get(
            f"/api/v1/projects/{uuid.uuid4()}",
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 404

    async def test_update_project_by_admin(self, client, alice, project):
        resp = await client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"name": "新名字"},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "新名字"

    async def test_update_project_validation(self, client, alice, project):
        resp = await client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"name": ""},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 422

    async def test_update_project_by_member_forbidden(
        self, client, alice, bob, project
    ):
        await _add_member(
            client, project["id"], alice["tokens"], email="bob@example.com"
        )
        resp = await client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"name": "hack"},
            headers=auth_headers(bob["tokens"]),
        )
        assert resp.status_code == 403

    async def test_delete_project_by_admin(self, client, alice, project):
        resp = await client.delete(
            f"/api/v1/projects/{project['id']}",
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        after = await client.get(
            f"/api/v1/projects/{project['id']}",
            headers=auth_headers(alice["tokens"]),
        )
        assert after.status_code == 404

    async def test_delete_project_by_member_forbidden(
        self, client, alice, bob, project
    ):
        await _add_member(
            client, project["id"], alice["tokens"], email="bob@example.com"
        )
        resp = await client.delete(
            f"/api/v1/projects/{project['id']}",
            headers=auth_headers(bob["tokens"]),
        )
        assert resp.status_code == 403


class TestProjectMembers:
    async def test_add_member_by_email(self, client, alice, bob, project):
        member = await _add_member(
            client, project["id"], alice["tokens"], email="bob@example.com"
        )
        assert member["role"] == "member"
        assert member["user"]["username"] == "bob"
        # bob 现在可以访问
        resp = await client.get(
            f"/api/v1/projects/{project['id']}",
            headers=auth_headers(bob["tokens"]),
        )
        assert resp.status_code == 200

    async def test_add_member_by_user_id(self, client, alice, charlie, project):
        member = await _add_member(
            client,
            project["id"],
            alice["tokens"],
            user_id=charlie["user"]["id"],
            role="admin",
        )
        assert member["role"] == "admin"

    async def test_add_member_validation_error(self, client, alice, project):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/members",
            json={"user_id": str(uuid.uuid4()), "email": "x@example.com"},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 422

    async def test_add_member_already_member(self, client, alice, project):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/members",
            json={"email": "alice@example.com"},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 409

    async def test_add_member_not_found(self, client, alice, project):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/members",
            json={"email": "nobody@example.com"},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 404

    async def test_add_member_requires_admin(self, client, alice, bob, project):
        await _add_member(
            client, project["id"], alice["tokens"], email="bob@example.com"
        )
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/members",
            json={"email": "nobody@example.com"},
            headers=auth_headers(bob["tokens"]),
        )
        assert resp.status_code == 403

    async def test_member_list(self, client, alice, bob, project):
        await _add_member(
            client, project["id"], alice["tokens"], email="bob@example.com"
        )
        resp = await client.get(
            f"/api/v1/projects/{project['id']}/members",
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2
        usernames = {m["user"]["username"] for m in data}
        assert usernames == {"alice", "bob"}

    async def test_update_member_role(self, client, alice, bob, project):
        await _add_member(
            client, project["id"], alice["tokens"], email="bob@example.com"
        )
        resp = await client.patch(
            f"/api/v1/projects/{project['id']}/members/{bob['user']['id']}",
            json={"role": "admin"},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["role"] == "admin"
        # bob 现在拥有管理员权限
        resp = await client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"name": "bob 改名"},
            headers=auth_headers(bob["tokens"]),
        )
        assert resp.status_code == 200

    async def test_update_owner_role_forbidden(self, client, alice, bob, project):
        await _add_member(
            client, project["id"], alice["tokens"], email="bob@example.com", role="admin"
        )
        resp = await client.patch(
            f"/api/v1/projects/{project['id']}/members/{alice['user']['id']}",
            json={"role": "member"},
            headers=auth_headers(bob["tokens"]),
        )
        assert resp.status_code == 403

    async def test_update_member_not_found(self, client, alice, project):
        resp = await client.patch(
            f"/api/v1/projects/{project['id']}/members/{uuid.uuid4()}",
            json={"role": "member"},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 404

    async def test_remove_member(self, client, alice, bob, project):
        await _add_member(
            client, project["id"], alice["tokens"], email="bob@example.com"
        )
        resp = await client.delete(
            f"/api/v1/projects/{project['id']}/members/{bob['user']['id']}",
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        after = await client.get(
            f"/api/v1/projects/{project['id']}",
            headers=auth_headers(bob["tokens"]),
        )
        assert after.status_code == 403

    async def test_remove_owner_forbidden(self, client, alice, project):
        resp = await client.delete(
            f"/api/v1/projects/{project['id']}/members/{alice['user']['id']}",
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 403

    async def test_remove_member_not_found(self, client, alice, project):
        resp = await client.delete(
            f"/api/v1/projects/{project['id']}/members/{uuid.uuid4()}",
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 404

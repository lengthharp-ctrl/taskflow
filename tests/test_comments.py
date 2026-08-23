import uuid

from tests.helpers import auth_headers


async def _add_member(client, project_id, tokens, email):
    resp = await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"email": email},
        headers=auth_headers(tokens),
    )
    assert resp.status_code == 201, resp.text


async def _create_comment(client, task_id, tokens, content="不错"):
    resp = await client.post(
        f"/api/v1/tasks/{task_id}/comments",
        json={"content": content},
        headers=auth_headers(tokens),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


class TestComments:
    async def test_create_and_list(self, client, alice, task):
        comment = await _create_comment(
            client, task["id"], alice["tokens"], content="第一个评论"
        )
        assert comment["content"] == "第一个评论"
        assert comment["author"]["username"] == "alice"
        assert comment["task_id"] == task["id"]

        resp = await client.get(
            f"/api/v1/tasks/{task['id']}/comments",
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["id"] == comment["id"]

    async def test_create_by_non_member(self, client, task, bob):
        resp = await client.post(
            f"/api/v1/tasks/{task['id']}/comments",
            json={"content": "x"},
            headers=auth_headers(bob["tokens"]),
        )
        assert resp.status_code == 403

    async def test_create_empty_content(self, client, alice, task):
        resp = await client.post(
            f"/api/v1/tasks/{task['id']}/comments",
            json={"content": ""},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 422

    async def test_update_own_comment(self, client, alice, task):
        comment = await _create_comment(client, task["id"], alice["tokens"])
        resp = await client.patch(
            f"/api/v1/comments/{comment['id']}",
            json={"content": "修改后的评论"},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["content"] == "修改后的评论"

    async def test_update_others_comment_forbidden(
        self, client, alice, bob, project, task
    ):
        await _add_member(client, project["id"], alice["tokens"], "bob@example.com")
        comment = await _create_comment(client, task["id"], bob["tokens"])
        resp = await client.patch(
            f"/api/v1/comments/{comment['id']}",
            json={"content": "hack"},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 403

    async def test_delete_own_comment(self, client, alice, task):
        comment = await _create_comment(client, task["id"], alice["tokens"])
        resp = await client.delete(
            f"/api/v1/comments/{comment['id']}",
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        after = await client.get(
            f"/api/v1/tasks/{task['id']}/comments",
            headers=auth_headers(alice["tokens"]),
        )
        assert len(after.json()["data"]) == 0

    async def test_delete_others_comment_by_admin(
        self, client, alice, bob, project, task
    ):
        await _add_member(client, project["id"], alice["tokens"], "bob@example.com")
        comment = await _create_comment(client, task["id"], bob["tokens"])
        resp = await client.delete(
            f"/api/v1/comments/{comment['id']}",
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200

    async def test_delete_others_comment_forbidden(
        self, client, alice, bob, charlie, project, task
    ):
        await _add_member(client, project["id"], alice["tokens"], "bob@example.com")
        await _add_member(client, project["id"], alice["tokens"], "charlie@example.com")
        comment = await _create_comment(client, task["id"], bob["tokens"])
        resp = await client.delete(
            f"/api/v1/comments/{comment['id']}",
            headers=auth_headers(charlie["tokens"]),
        )
        assert resp.status_code == 403

    async def test_comment_not_found(self, client, alice):
        resp = await client.patch(
            f"/api/v1/comments/{uuid.uuid4()}",
            json={"content": "x"},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 404
        resp = await client.delete(
            f"/api/v1/comments/{uuid.uuid4()}",
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 404

    async def test_comments_cascade_when_task_deleted(
        self, client, alice, task
    ):
        await _create_comment(client, task["id"], alice["tokens"])
        resp = await client.delete(
            f"/api/v1/tasks/{task['id']}",
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        resp = await client.get(
            f"/api/v1/tasks/{task['id']}/comments",
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 404

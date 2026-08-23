import uuid

from tests.helpers import auth_headers, register_user


async def _add_member(client, project_id, tokens, email):
    resp = await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"email": email},
        headers=auth_headers(tokens),
    )
    assert resp.status_code == 201, resp.text


async def _create_task(client, project_id, tokens, **overrides):
    payload = {"title": "任务", "priority": "medium"}
    payload.update(overrides)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json=payload,
        headers=auth_headers(tokens),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


class TestTaskCRUD:
    async def test_create_task_defaults(self, client, alice, project):
        task = await _create_task(client, project["id"], alice["tokens"])
        assert task["status"] == "todo"
        assert task["priority"] == "medium"
        assert task["project_id"] == project["id"]
        assert task["created_by_id"] == alice["user"]["id"]

    async def test_create_task_with_assignee(self, client, alice, bob, project):
        await _add_member(
            client, project["id"], alice["tokens"], "bob@example.com"
        )
        task = await _create_task(
            client,
            project["id"],
            alice["tokens"],
            title="交给 bob",
            assignee_id=bob["user"]["id"],
            priority="urgent",
        )
        assert task["assignee_id"] == bob["user"]["id"]
        assert task["assignee"]["username"] == "bob"
        assert task["priority"] == "urgent"

    async def test_create_task_invalid_assignee(self, client, alice, charlie, project):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/tasks",
            json={
                "title": "x",
                "assignee_id": charlie["user"]["id"],
            },
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 422

    async def test_create_task_by_non_member(self, client, project, bob):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/tasks",
            json={"title": "x"},
            headers=auth_headers(bob["tokens"]),
        )
        assert resp.status_code == 403

    async def test_get_task_detail(self, client, alice, task):
        resp = await client.get(
            f"/api/v1/tasks/{task['id']}",
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "写测试"

    async def test_get_task_by_non_member(self, client, task, bob):
        resp = await client.get(
            f"/api/v1/tasks/{task['id']}",
            headers=auth_headers(bob["tokens"]),
        )
        assert resp.status_code == 403

    async def test_get_task_not_found(self, client, alice):
        resp = await client.get(
            f"/api/v1/tasks/{uuid.uuid4()}",
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 404

    async def test_update_task(self, client, alice, bob, project, task):
        await _add_member(
            client, project["id"], alice["tokens"], "bob@example.com"
        )
        resp = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            json={
                "title": "改标题",
                "priority": "high",
                "assignee_id": bob["user"]["id"],
            },
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["title"] == "改标题"
        assert data["priority"] == "high"
        assert data["assignee_id"] == bob["user"]["id"]

    async def test_update_task_clear_assignee(self, client, alice, bob, project, task):
        await _add_member(
            client, project["id"], alice["tokens"], "bob@example.com"
        )
        await client.patch(
            f"/api/v1/tasks/{task['id']}",
            json={"assignee_id": bob["user"]["id"]},
            headers=auth_headers(alice["tokens"]),
        )
        resp = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            json={"assignee_id": None},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["assignee_id"] is None

    async def test_update_task_invalid_assignee(self, client, alice, charlie, task):
        resp = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            json={"assignee_id": charlie["user"]["id"]},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 422

    async def test_delete_task(self, client, alice, task):
        resp = await client.delete(
            f"/api/v1/tasks/{task['id']}",
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        after = await client.get(
            f"/api/v1/tasks/{task['id']}",
            headers=auth_headers(alice["tokens"]),
        )
        assert after.status_code == 404


class TestStatusFlow:
    async def test_todo_to_in_progress(self, client, alice, task):
        resp = await client.patch(
            f"/api/v1/tasks/{task['id']}/status",
            json={"status": "in_progress"},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "in_progress"

    async def test_in_progress_to_done(self, client, alice, task):
        await client.patch(
            f"/api/v1/tasks/{task['id']}/status",
            json={"status": "in_progress"},
            headers=auth_headers(alice["tokens"]),
        )
        resp = await client.patch(
            f"/api/v1/tasks/{task['id']}/status",
            json={"status": "done"},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "done"

    async def test_done_reopen_to_todo(self, client, alice, task):
        for status in ("in_progress", "done", "todo"):
            resp = await client.patch(
                f"/api/v1/tasks/{task['id']}/status",
                json={"status": status},
                headers=auth_headers(alice["tokens"]),
            )
            assert resp.status_code == 200

    async def test_invalid_transition(self, client, alice, task):
        await client.patch(
            f"/api/v1/tasks/{task['id']}/status",
            json={"status": "in_progress"},
            headers=auth_headers(alice["tokens"]),
        )
        await client.patch(
            f"/api/v1/tasks/{task['id']}/status",
            json={"status": "done"},
            headers=auth_headers(alice["tokens"]),
        )
        resp = await client.patch(
            f"/api/v1/tasks/{task['id']}/status",
            json={"status": "in_progress"},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 422

    async def test_same_status_is_noop(self, client, alice, task):
        resp = await client.patch(
            f"/api/v1/tasks/{task['id']}/status",
            json={"status": "todo"},
            headers=auth_headers(alice["tokens"]),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "todo"

    async def test_status_change_by_non_member(self, client, task, bob):
        resp = await client.patch(
            f"/api/v1/tasks/{task['id']}/status",
            json={"status": "done"},
            headers=auth_headers(bob["tokens"]),
        )
        assert resp.status_code == 403


class TestTaskFilters:
    async def _setup(self, client, alice, bob, project):
        await _add_member(
            client, project["id"], alice["tokens"], "bob@example.com"
        )
        t1 = await _create_task(
            client, project["id"], alice["tokens"],
            title="登录页联调",
            priority="high",
            assignee_id=alice["user"]["id"],
            due_date="2026-09-01T00:00:00",
        )
        t2 = await _create_task(
            client, project["id"], alice["tokens"],
            title="修复支付 bug",
            priority="urgent",
            assignee_id=bob["user"]["id"],
            due_date="2026-07-01T00:00:00",
        )
        t3 = await _create_task(
            client, project["id"], alice["tokens"],
            title="写文档",
            priority="low",
            due_date="2026-08-15T00:00:00",
        )
        # t1 -> in_progress, t3 -> done
        await client.patch(
            f"/api/v1/tasks/{t1['id']}/status",
            json={"status": "in_progress"},
            headers=auth_headers(alice["tokens"]),
        )
        await client.patch(
            f"/api/v1/tasks/{t3['id']}/status",
            json={"status": "done"},
            headers=auth_headers(alice["tokens"]),
        )
        return t1, t2, t3

    async def _list(self, client, project_id, tokens, **params):
        resp = await client.get(
            f"/api/v1/projects/{project_id}/tasks",
            params=params,
            headers=auth_headers(tokens),
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]

    async def test_filter_by_status(self, client, alice, bob, project):
        t1, t2, t3 = await self._setup(client, alice, bob, project)
        data = await self._list(
            client, project["id"], alice["tokens"], status="done"
        )
        assert data["total"] == 1
        assert data["items"][0]["id"] == t3["id"]

    async def test_filter_by_priority(self, client, alice, bob, project):
        t1, t2, t3 = await self._setup(client, alice, bob, project)
        data = await self._list(
            client, project["id"], alice["tokens"], priority="urgent"
        )
        assert data["total"] == 1
        assert data["items"][0]["id"] == t2["id"]

    async def test_filter_by_assignee(self, client, alice, bob, project):
        t1, t2, t3 = await self._setup(client, alice, bob, project)
        data = await self._list(
            client,
            project["id"],
            alice["tokens"],
            assignee_id=alice["user"]["id"],
        )
        assert data["total"] == 1
        assert data["items"][0]["id"] == t1["id"]

    async def test_filter_by_search(self, client, alice, bob, project):
        t1, t2, t3 = await self._setup(client, alice, bob, project)
        data = await self._list(
            client, project["id"], alice["tokens"], search="支付"
        )
        assert data["total"] == 1
        assert data["items"][0]["id"] == t2["id"]

    async def test_filter_by_due_date(self, client, alice, bob, project):
        t1, t2, t3 = await self._setup(client, alice, bob, project)
        data = await self._list(
            client,
            project["id"],
            alice["tokens"],
            due_before="2026-08-01T00:00:00",
        )
        assert data["total"] == 1
        assert data["items"][0]["id"] == t2["id"]

        data = await self._list(
            client,
            project["id"],
            alice["tokens"],
            due_after="2026-08-01T00:00:00",
        )
        assert data["total"] == 2

    async def test_pagination(self, client, alice, project):
        for i in range(25):
            await _create_task(
                client, project["id"], alice["tokens"], title=f"批量任务 {i+1}"
            )
        data = await self._list(
            client, project["id"], alice["tokens"], page=2, page_size=10
        )
        assert data["total"] == 25
        assert len(data["items"]) == 10
        assert data["pages"] == 3

    async def test_sort_by_title(self, client, alice, project):
        await _create_task(client, project["id"], alice["tokens"], title="Beta")
        await _create_task(client, project["id"], alice["tokens"], title="Alpha")
        data = await self._list(
            client, project["id"], alice["tokens"], sort="title"
        )
        assert data["items"][0]["title"] == "Alpha"
        data = await self._list(
            client, project["id"], alice["tokens"], sort="-title"
        )
        assert data["items"][0]["title"] == "Beta"

    async def test_sort_by_priority_order(self, client, alice, project):
        await _create_task(client, project["id"], alice["tokens"], title="urgent", priority="urgent")
        await _create_task(client, project["id"], alice["tokens"], title="low", priority="low")
        await _create_task(client, project["id"], alice["tokens"], title="high", priority="high")
        data = await self._list(
            client, project["id"], alice["tokens"], sort="priority"
        )
        assert [t["title"] for t in data["items"]][0] == "low"
        data = await self._list(
            client, project["id"], alice["tokens"], sort="-priority"
        )
        assert [t["title"] for t in data["items"]][0] == "urgent"

    async def test_list_by_non_member(self, client, project, bob):
        resp = await client.get(
            f"/api/v1/projects/{project['id']}/tasks",
            headers=auth_headers(bob["tokens"]),
        )
        assert resp.status_code == 403

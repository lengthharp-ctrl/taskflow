import json

from starlette.requests import Request

from app.main import app


def _make_request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "raw_path": b"/x",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "scheme": "http",
    }
    return Request(scope)


class TestUnifiedErrors:
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_unknown_route_returns_unified_error(self, client):
        resp = await client.get("/api/v1/does-not-exist")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == 404
        assert "message" in body
        assert "data" in body

    async def test_unhandled_exception_returns_500(self, client):
        from app.core.database import get_db

        async def broken_db():
            raise RuntimeError("boom")

        app.dependency_overrides[get_db] = broken_db
        try:
            resp = await client.get("/api/v1/auth/me")
            assert resp.status_code == 500
            assert resp.json()["message"] == "服务器内部错误"
        finally:
            app.dependency_overrides.clear()

    async def test_integrity_error_handler(self):
        from sqlalchemy.exc import IntegrityError

        exc = IntegrityError("stmt", {}, Exception("unique constraint"))
        resp = await app.exception_handlers[IntegrityError](_make_request(), exc)
        assert resp.status_code == 409
        assert json.loads(resp.body)["code"] == 409

    async def test_app_error_handler(self):
        from app.core.exceptions import AppError, NotFoundError

        resp = await app.exception_handlers[AppError](
            _make_request(), NotFoundError("没找到")
        )
        assert resp.status_code == 404
        assert json.loads(resp.body)["message"] == "没找到"

    async def test_validation_handler(self):
        from fastapi.exceptions import RequestValidationError

        exc = RequestValidationError(
            [{"loc": ("body", "x"), "msg": "missing", "type": "missing"}]
        )
        resp = await app.exception_handlers[RequestValidationError](
            _make_request(), exc
        )
        assert resp.status_code == 422
        assert json.loads(resp.body)["code"] == 422

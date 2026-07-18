"""Phase 2 checkpoint: health endpoints, clean 404/500, module imports, rate limit."""

import importlib

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.main import app
from app.rate_limit import rate_limit

MODULES = (
    "auth",
    "tickets",
    "workflow",
    "ai",
    "routing",
    "search",
    "reporting",
    "notifications",
    "sla",
    "admin_config",
    "knowledge_base",
    "audit",
)


def test_health():
    assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_health_ready_checks_db():
    response = TestClient(app).get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_undefined_route_returns_clean_404():
    response = TestClient(app).get("/nope")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_unhandled_error_returns_generic_500():
    @app.get("/_boom")
    def boom():
        raise RuntimeError("secret internals")

    try:
        response = TestClient(app, raise_server_exceptions=False).get("/_boom")
        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error"}
        assert "secret internals" not in response.text
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", "") != "/_boom"]


def test_all_modules_import_cleanly():
    for module in MODULES:
        importlib.import_module(f"app.{module}")


def test_rate_limit_dependency():
    limited = FastAPI()

    @limited.get("/x", dependencies=[Depends(rate_limit(2))])
    def x():
        return {}

    client = TestClient(limited)
    assert client.get("/x").status_code == 200
    assert client.get("/x").status_code == 200
    assert client.get("/x").status_code == 429

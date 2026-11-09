from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.db import get_session
from app.images.api.dependencies import get_storage
from tests.fakes import InMemoryStorage


class _UnreachableDatabase:
    """Stands in for a Session whose connection fails."""

    def execute(self, *args: object, **kwargs: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))


def _unreachable_session() -> Iterator[_UnreachableDatabase]:
    yield _UnreachableDatabase()


class TestLiveness:
    def test_is_ok_without_credentials(self, anonymous_client: TestClient) -> None:
        response = anonymous_client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_stays_ok_when_dependencies_are_down(self, anonymous_client: TestClient) -> None:
        anonymous_client.app.dependency_overrides[get_session] = _unreachable_session  # type: ignore[attr-defined]
        assert anonymous_client.get("/healthz").status_code == 200


class TestReadiness:
    def test_is_ready_without_credentials_when_db_and_storage_are_up(self, anonymous_client: TestClient) -> None:
        response = anonymous_client.get("/readyz")
        assert response.status_code == 200
        assert response.json() == {"status": "ready", "checks": {"database": "ok", "storage": "ok"}}

    def test_is_503_when_storage_fails(self, anonymous_client: TestClient) -> None:
        anonymous_client.app.dependency_overrides[get_storage] = lambda: InMemoryStorage(healthy=False)  # type: ignore[attr-defined]
        response = anonymous_client.get("/readyz")
        assert response.status_code == 503
        assert response.json() == {"status": "not ready", "checks": {"database": "ok", "storage": "error"}}

    def test_is_503_when_database_fails(self, anonymous_client: TestClient) -> None:
        anonymous_client.app.dependency_overrides[get_session] = _unreachable_session  # type: ignore[attr-defined]
        response = anonymous_client.get("/readyz")
        assert response.status_code == 503
        assert response.json() == {"status": "not ready", "checks": {"database": "error", "storage": "ok"}}

    def test_does_not_leak_error_details(self, anonymous_client: TestClient) -> None:
        anonymous_client.app.dependency_overrides[get_session] = _unreachable_session  # type: ignore[attr-defined]
        assert "connection refused" not in anonymous_client.get("/readyz").text

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import PASSWORD, USERNAME


class TestBasicAuth:
    def test_missing_credentials_is_401_with_challenge(self, anonymous_client: TestClient) -> None:
        response = anonymous_client.get(f"/images/{uuid.uuid4()}")
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Basic"

    @pytest.mark.parametrize(("username", "password"), [(USERNAME, "wrong"), ("wrong", PASSWORD), ("", "")])
    def test_wrong_credentials_is_401(self, anonymous_client: TestClient, username: str, password: str) -> None:
        response = anonymous_client.get(f"/images/{uuid.uuid4()}", auth=(username, password))
        assert response.status_code == 401

    def test_upload_is_protected(self, anonymous_client: TestClient) -> None:
        response = anonymous_client.post("/images", files={"file": ("a.png", b"x", "image/png")})
        assert response.status_code == 401

    def test_valid_credentials_are_accepted(self, client: TestClient) -> None:
        assert client.get(f"/images/{uuid.uuid4()}").status_code == 404

import httpx2


class TestHealthProbes:
    def test_liveness_over_real_http(self, anonymous_http: httpx2.Client) -> None:
        assert anonymous_http.get("/healthz").json() == {"status": "ok"}

    def test_readiness_over_real_http(self, anonymous_http: httpx2.Client) -> None:
        response = anonymous_http.get("/readyz")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"

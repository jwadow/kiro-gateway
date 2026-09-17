class TestPrivateNetworkAccessPreflight:
    def test_requested_private_network_is_allowed(self, test_client):
        response = test_client.options(
            "/v1/models?limit=1000",
            headers={
                "Origin": "https://pivot.claude.ai",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-api-key,anthropic-version",
                "Access-Control-Request-Private-Network": "true",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "https://pivot.claude.ai"
        assert response.headers["access-control-allow-credentials"] == "true"
        assert "GET" in response.headers["access-control-allow-methods"]
        assert response.headers["access-control-allow-headers"] == "x-api-key,anthropic-version"
        assert response.headers["access-control-allow-private-network"] == "true"

    def test_ordinary_preflight_does_not_add_private_network_permission(self, test_client):
        response = test_client.options(
            "/v1/models?limit=1000",
            headers={
                "Origin": "https://pivot.claude.ai",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-api-key,anthropic-version",
            },
        )

        assert response.status_code == 200
        assert "access-control-allow-private-network" not in response.headers

    def test_non_true_private_network_marker_does_not_add_permission(self, test_client):
        response = test_client.options(
            "/v1/models?limit=1000",
            headers={
                "Origin": "https://pivot.claude.ai",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-api-key,anthropic-version",
                "Access-Control-Request-Private-Network": "TRUE",
            },
        )

        assert response.status_code == 200
        assert "access-control-allow-private-network" not in response.headers

    def test_failed_preflight_does_not_add_private_network_permission(self, test_client):
        response = test_client.options(
            "/v1/models?limit=1000",
            headers={
                "Origin": "https://pivot.claude.ai",
                "Access-Control-Request-Method": "CONNECT",
                "Access-Control-Request-Headers": "x-api-key,anthropic-version",
                "Access-Control-Request-Private-Network": "true",
            },
        )

        assert response.status_code == 400
        assert "access-control-allow-private-network" not in response.headers

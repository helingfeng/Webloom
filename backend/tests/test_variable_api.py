from test_open_platform import client


def test_list_masks_values_and_partial_update_preserves_secret(client):
    response = client.post(
        "/api/global-variables",
        json={
            "name": "Authorization",
            "type": "header",
            "domain": "https://API.Example.com:8080/login",
            "value": "private-token",
        },
    )
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["domain"] == "api.example.com" and item["has_value"]
    assert "value" not in item
    assert "private-token" not in client.get("/api/global-variables").text
    id = item["id"]
    response = client.put(
        f"/api/global-variables/{id}", json={"enabled": False, "description": "changed"}
    )
    assert response.status_code == 200 and response.json()["has_value"]
    assert client.get(f"/api/global-variables/{id}").json()["value"] == "private-token"
    client.put(f"/api/global-variables/{id}", json={"value": ""})
    assert not client.get("/api/global-variables").json()[0]["has_value"]


def test_duplicate_domain_configuration_is_rejected(client):
    payload = {
        "name": "Authorization",
        "type": "header",
        "domain": "example.com",
        "value": "v",
    }
    assert client.post("/api/global-variables", json=payload).status_code == 201
    assert (
        client.post(
            "/api/global-variables",
            json={
                **payload,
                "name": "authorization",
                "domain": "https://example.com:8443/path",
            },
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/global-variables", json={**payload, "domain": "api.example.com"}
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/global-variables", json={**payload, "name": "bad header"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/global-variables", json={**payload, "domain": "bad domain"}
        ).status_code
        == 400
    )

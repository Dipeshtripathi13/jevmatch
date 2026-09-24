from fastapi.testclient import TestClient

from api.main import app, match_pipeline, settings

client = TestClient(app)


def test_validates_imported_requirements_without_extraction():
    response = client.post(
        "/requirements/validate",
        json={
            "requirements": [
                {
                    "id": "r1",
                    "text": "Production Python experience",
                    "kind": "must_have",
                    "weight": 3,
                }
            ],
            "hard_constraints": {"min_years_experience": 3, "remote": True},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requirements"][0]["kind"] == "must_have"
    assert payload["hard_constraints"]["remote"] is True
    assert payload["hard_constraints"]["required_degree"] is None


def test_rejects_duplicate_requirement_ids():
    requirement = {"id": "same", "text": "Python", "kind": "skill", "weight": 1}
    response = client.post(
        "/requirements/validate",
        json={"requirements": [requirement, {**requirement, "text": "FastAPI"}]},
    )

    assert response.status_code == 422
    assert "unique" in response.text


def test_rejects_empty_requirement_list():
    response = client.post("/requirements/validate", json={"requirements": []})

    assert response.status_code == 422


def test_rejects_unknown_imported_fields_instead_of_silently_dropping_them():
    response = client.post(
        "/requirements/validate",
        json={
            "requirements": [
                {
                    "id": "r1",
                    "text": "Python",
                    "kind": "skill",
                    "weight": 2,
                    "unexpected": "typo",
                }
            ]
        },
    )

    assert response.status_code == 422
    assert "Extra inputs are not permitted" in response.text


def test_match_endpoint_rate_limit_returns_retry_headers():
    original_limit = settings.match_rate_limit_per_window
    settings.match_rate_limit_per_window = 1
    isolated_client = TestClient(app, client=("rate-limit-test", 50_001))
    headers = {"Origin": "http://localhost:5173"}
    try:
        first = isolated_client.post("/match", json={}, headers=headers)
        blocked = isolated_client.post("/match", json={}, headers=headers)
    finally:
        settings.match_rate_limit_per_window = original_limit

    assert first.status_code == 400
    assert first.headers["x-ratelimit-remaining"] == "0"
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.headers["x-ratelimit-limit"] == "1"
    assert blocked.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_match_service_failure_returns_json_with_cors(monkeypatch):
    async def fail_match(*_args, **_kwargs):
        raise RuntimeError("TypeSafe Jev is temporarily unavailable.")

    monkeypatch.setattr(match_pipeline, "match_many", fail_match)
    isolated_client = TestClient(app, client=("service-failure-test", 50_002))
    response = isolated_client.post(
        "/match",
        headers={"Origin": "http://localhost:5173"},
        json={
            "resumes": [{"name": "synthetic.txt", "text": "Python software engineer"}],
            "requirements": [
                {"id": "r1", "text": "Python experience", "kind": "skill", "weight": 1}
            ],
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "TypeSafe Jev is temporarily unavailable."
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"

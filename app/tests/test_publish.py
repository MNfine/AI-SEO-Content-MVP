from app.core.config import get_settings
from app.services.wordpress_service import WordPressPublishError, WordPressService
import requests


def test_publish_draft_success(client, monkeypatch):
    def fake_create_draft(self, title, content_html, excerpt, slug, meta_description):
        return "123"

    monkeypatch.setattr(WordPressService, "create_draft", fake_create_draft)

    generate_response = client.post(
        "/articles/generate",
        json={"keyword": "fastapi vs django", "language": "vi", "tone": "professional"},
    )
    assert generate_response.status_code == 200

    article_id = generate_response.json()["id"]

    publish_response = client.post(f"/articles/{article_id}/publish-draft")
    assert publish_response.status_code == 200
    payload = publish_response.json()
    assert payload["status"] == "drafted"
    assert payload["wp_post_id"] == "123"


def test_publish_draft_mock_mode_without_credentials(client):
    generate_response = client.post(
        "/articles/generate",
        json={"keyword": "python roadmap", "language": "vi", "tone": "professional"},
    )
    assert generate_response.status_code == 200

    article_id = generate_response.json()["id"]
    publish_response = client.post(f"/articles/{article_id}/publish-draft")

    assert publish_response.status_code == 200
    payload = publish_response.json()
    assert payload["status"] == "drafted"
    assert payload["wp_post_id"].startswith("local-draft-")


def test_publish_retries_without_meta_on_forbidden(client, monkeypatch):
    monkeypatch.setenv("WORDPRESS_BASE_URL", "https://example.com")
    monkeypatch.setenv("WORDPRESS_USERNAME", "demo")
    monkeypatch.setenv("WORDPRESS_APP_PASSWORD", "demo-pass")
    monkeypatch.setenv("WORDPRESS_MOCK_PUBLISH", "false")
    get_settings.cache_clear()

    class FakeResponse:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body
            self.ok = status_code < 400
            self.text = str(body)
            self.reason = "error"

        def json(self):
            return self._body

    calls = []

    def fake_post_draft(self, endpoint, payload):
        calls.append(payload)
        if len(calls) == 1:
            return FakeResponse(403, {"message": "meta is not allowed"})
        return FakeResponse(201, {"id": 999})

    monkeypatch.setattr(WordPressService, "_post_draft", fake_post_draft)

    generate_response = client.post(
        "/articles/generate",
        json={"keyword": "fastapi vs django", "language": "vi", "tone": "professional"},
    )
    article_id = generate_response.json()["id"]
    publish_response = client.post(f"/articles/{article_id}/publish-draft")

    assert publish_response.status_code == 200
    assert publish_response.json()["wp_post_id"] == "999"
    assert "meta" in calls[0]
    assert "meta" not in calls[1]

    get_settings.cache_clear()


def test_publish_maps_request_exception_to_domain_error(monkeypatch):
    monkeypatch.setenv("WORDPRESS_BASE_URL", "https://example.com")
    monkeypatch.setenv("WORDPRESS_USERNAME", "demo")
    monkeypatch.setenv("WORDPRESS_APP_PASSWORD", "demo-pass")
    monkeypatch.setenv("WORDPRESS_MOCK_PUBLISH", "false")
    get_settings.cache_clear()

    service = WordPressService()

    def fake_post(*args, **kwargs):
        raise requests.ConnectionError("reset by peer")

    monkeypatch.setattr(requests, "post", fake_post)

    try:
        service.create_draft("title", "<p>x</p>", "excerpt", "slug", "meta")
        assert False, "Expected WordPressPublishError"
    except WordPressPublishError as exc:
        assert "WordPress connection failed" in str(exc)

    get_settings.cache_clear()

from app.services.gemini_service import GeminiService


def test_generate_article_success(client, monkeypatch):
    def fake_generate(self, keyword, language, tone):
        return {
            "title": "FastAPI vs Django",
            "slug": "fastapi-vs-django",
            "meta_description": "So sanh FastAPI va Django",
            "excerpt": "Tong quan nhanh",
            "content_html": "<h2>Mo dau</h2><p>Noi dung</p>",
        }

    monkeypatch.setattr(GeminiService, "generate_article", fake_generate)

    response = client.post(
        "/articles/generate",
        json={"keyword": "fastapi vs django", "language": "vi", "tone": "professional"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["keyword"] == "fastapi vs django"
    assert payload["status"] == "generated"
    assert payload["slug"] == "fastapi-vs-django"


def test_generate_article_duplicate_slug_gets_suffix(client, monkeypatch):
    def fake_generate(self, keyword, language, tone):
        return {
            "title": "Flask da loi thoi",
            "slug": "flask-da-loi-thoi",
            "meta_description": "meta",
            "excerpt": "excerpt",
            "content_html": "<h2>Mo dau</h2><p>Noi dung</p>",
        }

    monkeypatch.setattr(GeminiService, "generate_article", fake_generate)

    first = client.post(
        "/articles/generate",
        json={"keyword": "flask da loi thoi", "language": "vi", "tone": "professional"},
    )
    second = client.post(
        "/articles/generate",
        json={"keyword": "flask da loi thoi", "language": "vi", "tone": "professional"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["slug"] == "flask-da-loi-thoi"
    assert second.json()["slug"] == "flask-da-loi-thoi-2"


def test_generate_article_fallback_escapes_html_keyword(client):
    response = client.post(
        "/articles/generate",
        json={"keyword": "flask <script>", "language": "vi", "tone": "professional"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "<script>" not in payload["content_html"]
    assert "script" in payload["content_html"]


def test_generate_article_fallback_builds_article_structure(client):
    response = client.post(
        "/articles/generate",
        json={"keyword": "phong van sql", "language": "vi", "tone": "professional"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "Checklist" in payload["title"]
    assert "Muc luc" not in payload["content_html"]
    assert "Table of Contents" not in payload["content_html"]
    assert "article-toc" not in payload["content_html"]
    assert payload["content_html"].count("<h2") >= 5
    assert "<pre><code>" in payload["content_html"]
    assert "id=" in payload["content_html"]
    assert "1.1" in payload["content_html"]
    assert payload["content_html"].count("<figure class=\"article-figure\">") >= 2
    assert "data:image/svg+xml;base64," in payload["content_html"]
    assert "href=\"https://" in payload["content_html"]
    assert "https://itprep.com.vn/" in payload["content_html"]
    assert "href=\"/articles" not in payload["content_html"]

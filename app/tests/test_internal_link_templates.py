from app.services.seo_link_service import enrich_seo_links


def _extract_recommendation(html: str) -> str:
    start = html.find('<p class="internal-link-recommendation">')
    if start == -1:
        return ""
    end = html.find("</p>", start)
    if end == -1:
        return ""
    return html[start : end + 4]


def test_internal_link_template_is_deterministic_for_same_keyword():
    html = "<h2>Mo dau</h2><p>Noi dung backend.</p>"
    first = enrich_seo_links(html, keyword="fastapi backend", language="vi")
    second = enrich_seo_links(html, keyword="fastapi backend", language="vi")

    assert _extract_recommendation(first) == _extract_recommendation(second)


def test_internal_link_template_varies_across_keywords():
    html = "<h2>Mo dau</h2><p>Noi dung backend.</p>"
    keywords = [
        "fastapi backend",
        "django backend",
        "flask backend",
        "nodejs backend",
    ]
    recommendations = {
        _extract_recommendation(enrich_seo_links(html, keyword=kw, language="vi"))
        for kw in keywords
    }

    assert len(recommendations) >= 2

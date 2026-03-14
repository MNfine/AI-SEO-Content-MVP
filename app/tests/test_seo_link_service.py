from app.services.seo_link_service import enrich_seo_links


def test_enrich_seo_links_uses_curated_internal_links():
    html = "<h2>Mo dau</h2><p>Noi dung backend.</p>"
    enriched = enrich_seo_links(html, keyword="fastapi backend", language="vi")

    assert "internal-link-recommendation" in enriched
    assert "itprep" in enriched
    assert "backend" in enriched
    assert "https://itprep.com.vn/fastapi-vs-django-for-backend/" in enriched
    assert "css-flexbox-grid-cheat-sheet" not in enriched
    assert "javascript-es6-cheat-sheet" not in enriched
    assert "href=\"/articles" not in enriched


def test_enrich_seo_links_database_keyword_picks_database_links():
    html = "<h2>Mo dau</h2><p>Noi dung SQL.</p>"
    enriched = enrich_seo_links(html, keyword="phong van sql", language="vi")

    assert "https://itprep.com.vn/kien-thuc-trong-phong-van-sql/" in enriched
    assert "https://itprep.com.vn/sql-join-cheat-sheet/" in enriched

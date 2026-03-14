import json
import hashlib
import re
import unicodedata
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from app.services.intent_service import ArticleIntent, detect_article_intent


LINKS_FILE = Path(__file__).resolve().parents[1] / "data" / "internal_links.json"
TEMPLATES_FILE = Path(__file__).resolve().parents[1] / "data" / "internal_link_templates.json"

CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "Backend": ("backend", "api", "fastapi", "django", "flask", "node", "spring"),
    "Frontend": ("frontend", "react", "javascript", "typescript", "css", "html", "vue", "angular"),
    "Career": ("cv", "resume", "career", "phong van", "interview", "ats", "lo trinh"),
    "AI-ML": ("ai", "ml", "machine learning", "deep learning", "cnn", "rnn", "transformer", "llm"),
    "Database": ("sql", "database", "db", "join", "query", "postgres", "mysql"),
}

CATEGORY_PRIORITY: dict[str, int] = {
    "Backend": 5,
    "Frontend": 5,
    "Database": 5,
    "AI-ML": 4,
    "Career": 3,
}

RELATED_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Backend": ("Database", "Career"),
    "Frontend": ("Career", "Backend"),
    "Database": ("Backend", "Career"),
    "AI-ML": ("Career", "Backend", "Database"),
    "Career": ("Backend", "Database", "Frontend", "AI-ML"),
}


DEFAULT_VI_INTERNAL_LINK_TEMPLATES: tuple[str, ...] = (
    "Nếu bạn đang tìm hiểu {keyword}, bạn có thể tham khảo thêm {anchor_phrase} trên itprep.",
    "Để mở rộng góc nhìn về {category_label}, hãy đọc tiếp {anchor_phrase} trên itprep.",
    "Trong lộ trình học {category_label}, {anchor_phrase} là các tài liệu nên xem để áp dụng thực tế tốt hơn.",
    "Nếu muốn đào sâu hơn về {keyword}, bạn nên xem {anchor_phrase} trên itprep.",
    "Một gợi ý đọc tiếp cho chủ đề {category_label}: {anchor_phrase} trên itprep.",
    "Để có thêm case study và kinh nghiệm triển khai, bạn có thể tham khảo {anchor_phrase} trên itprep.",
    "Bạn có thể kết hợp bài này với {anchor_phrase} trên itprep để nắm vấn đề {category_label} một cách hệ thống.",
)

DEFAULT_EN_INTERNAL_LINK_TEMPLATES: tuple[str, ...] = (
    "If you are exploring {category_label}, you can also read {anchor_phrase} on itprep.",
    "For deeper context on {category_label}, consider reviewing {anchor_phrase} on itprep.",
    "To expand your view of {category_label}, the articles {anchor_phrase} on itprep are useful.",
    "A practical next read for {category_label} is {anchor_phrase} on itprep.",
    "If you want a broader perspective on {category_label}, check out {anchor_phrase} on itprep.",
)

SINGLE_LINK_TEMPLATES_VI: tuple[str, ...] = (
    "Nếu bạn đang tìm hiểu {keyword}, bạn có thể đọc thêm {anchor} trên itprep.",
    "Để đào sâu hơn về {keyword}, bài {anchor} trên itprep sẽ giúp bạn có thêm góc nhìn thực tế.",
    "Một tài liệu nên tham khảo tiếp theo cho chủ đề {keyword} là {anchor} trên itprep.",
    "Nếu muốn mở rộng kiến thức {keyword}, bạn nên xem {anchor} trên itprep.",
)

SINGLE_LINK_TEMPLATES_EN: tuple[str, ...] = (
    "If you are exploring {keyword}, you can also read {anchor} on itprep.",
    "A practical follow-up for {keyword} is {anchor} on itprep.",
    "For deeper context on {category_label}, consider {anchor} on itprep.",
)

DEFAULT_VI_CATEGORY_TEMPLATES: dict[str, tuple[str, ...]] = {
    "Backend": (
        "Nếu bạn đang triển khai backend cho dự án thực tế, bạn có thể đọc thêm {anchor_phrase} trên itprep.",
        "Để hiểu rõ hơn các quyết định kiến trúc backend, hãy tham khảo {anchor_phrase} trên itprep.",
        "Một hướng đọc tiếp phù hợp cho mảng backend là {anchor_phrase} trên itprep.",
    ),
    "Frontend": (
        "Nếu bạn đang tối ưu front-end và trải nghiệm người dùng, hãy xem thêm {anchor_phrase} trên itprep.",
        "Để củng cố nền tảng front-end thực chiến, bạn có thể tham khảo {anchor_phrase} trên itprep.",
        "Một tài liệu đọc tiếp hữu ích cho front-end là {anchor_phrase} trên itprep.",
    ),
    "Database": (
        "Nếu bạn muốn chắc phần cơ sở dữ liệu, hãy đọc thêm {anchor_phrase} trên itprep.",
        "Để xử lý tốt hơn các bài toán SQL và dữ liệu, bạn có thể tham khảo {anchor_phrase} trên itprep.",
        "Một nguồn đọc tiếp đáng tham khảo cho database là {anchor_phrase} trên itprep.",
    ),
    "AI-ML": (
        "Nếu bạn đang học AI/ML theo hướng ứng dụng, hãy xem thêm {anchor_phrase} trên itprep.",
        "Để mở rộng góc nhìn về mô hình và bài toán AI/ML, bạn có thể tham khảo {anchor_phrase} trên itprep.",
        "Một tài liệu đọc tiếp phù hợp cho AI/ML là {anchor_phrase} trên itprep.",
    ),
    "Career": (
        "Nếu bạn đang chuẩn bị cho lộ trình nghề nghiệp IT, hãy xem thêm {anchor_phrase} trên itprep.",
        "Để chuẩn bị tốt hơn cho hồ sơ và phỏng vấn IT, bạn có thể tham khảo {anchor_phrase} trên itprep.",
        "Một hướng đọc tiếp hữu ích cho career IT là {anchor_phrase} trên itprep.",
    ),
}

DEFAULT_VI_INTENT_CONTEXT: dict[str, str] = {
    "interview_checklist": "Trong ngữ cảnh phỏng vấn, ",
    "comparison": "Ở góc nhìn so sánh lựa chọn, ",
    "tutorial": "Trong lộ trình học và thực hành, ",
    "tool_roundup": "Nếu bạn đang chọn công cụ phù hợp, ",
    "expert_guide": "Ở góc nhìn triển khai thực tế, ",
}


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


def _load_internal_links() -> dict[str, list[dict[str, str]]]:
    if not LINKS_FILE.exists():
        return {}
    try:
        payload = json.loads(LINKS_FILE.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        return {
            str(category): [item for item in links if isinstance(item, dict)]
            for category, links in payload.items()
            if isinstance(links, list)
        }
    except Exception:
        return {}


def _load_internal_link_templates() -> dict[str, Any]:
    if not TEMPLATES_FILE.exists():
        return {
            "vi": DEFAULT_VI_INTERNAL_LINK_TEMPLATES,
            "en": DEFAULT_EN_INTERNAL_LINK_TEMPLATES,
            "vi_by_category": DEFAULT_VI_CATEGORY_TEMPLATES,
            "vi_intent_context": DEFAULT_VI_INTENT_CONTEXT,
        }

    try:
        payload = json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Invalid template config")

        vi_templates = payload.get("vi", [])
        en_templates = payload.get("en", [])
        by_category = payload.get("vi_by_category", {})
        intent_context = payload.get("vi_intent_context", {})

        vi_cleaned = tuple(item.strip() for item in vi_templates if isinstance(item, str) and item.strip())
        en_cleaned = tuple(item.strip() for item in en_templates if isinstance(item, str) and item.strip())

        cleaned_by_category: dict[str, tuple[str, ...]] = {}
        if isinstance(by_category, dict):
            for category, templates in by_category.items():
                if isinstance(templates, list):
                    cleaned = tuple(item.strip() for item in templates if isinstance(item, str) and item.strip())
                    if cleaned:
                        cleaned_by_category[str(category)] = cleaned

        cleaned_intent_context: dict[str, str] = {}
        if isinstance(intent_context, dict):
            for name, prefix in intent_context.items():
                if isinstance(prefix, str) and prefix.strip():
                    cleaned_intent_context[str(name)] = prefix

        return {
            "vi": vi_cleaned or DEFAULT_VI_INTERNAL_LINK_TEMPLATES,
            "en": en_cleaned or DEFAULT_EN_INTERNAL_LINK_TEMPLATES,
            "vi_by_category": cleaned_by_category or DEFAULT_VI_CATEGORY_TEMPLATES,
            "vi_intent_context": cleaned_intent_context or DEFAULT_VI_INTENT_CONTEXT,
        }
    except Exception:
        return {
            "vi": DEFAULT_VI_INTERNAL_LINK_TEMPLATES,
            "en": DEFAULT_EN_INTERNAL_LINK_TEMPLATES,
            "vi_by_category": DEFAULT_VI_CATEGORY_TEMPLATES,
            "vi_intent_context": DEFAULT_VI_INTENT_CONTEXT,
        }


def _rank_categories(keyword: str, categories: list[str]) -> list[str]:
    normalized = _normalize_text(keyword)
    scored: list[tuple[int, str]] = []

    for category in categories:
        hints = CATEGORY_HINTS.get(category, ())
        score = sum(1 for hint in hints if hint in normalized)
        if score > 0:
            scored.append((score, category))

    if scored:
        scored.sort(key=lambda item: (-item[0], -CATEGORY_PRIORITY.get(item[1], 0), item[1]))
        return [category for _, category in scored]

    # Fallback deterministic order for generic topics.
    preferred_order = ["Backend", "Frontend", "Database", "AI-ML", "Career"]
    ordered = [category for category in preferred_order if category in categories]
    ordered.extend([category for category in categories if category not in ordered])
    return ordered


def _has_external_link(content_html: str) -> bool:
    return bool(re.search(r'<a[^>]+href="https?://', content_html, flags=re.IGNORECASE))


def _has_internal_link(content_html: str, base_url: str | None) -> bool:
    internal_domains = ["itprep.com.vn"]
    if base_url:
        normalized_base = base_url.replace("https://", "").replace("http://", "").strip("/")
        if normalized_base:
            internal_domains.append(normalized_base)

    for domain in internal_domains:
        escaped = re.escape(domain)
        if re.search(rf'<a[^>]+href="https?://{escaped}/', content_html, flags=re.IGNORECASE):
            return True
    return False


def _external_links_html(keyword: str, language: str) -> str:
    if language.lower() == "vi":
        return (
            '<h2>Tai nguyen tham khao ben ngoai</h2>'
            '<ul>'
            '<li><a href="https://developers.google.com/search/docs" target="_blank" rel="noopener">Google Search Central Documentation</a></li>'
            f'<li><a href="https://www.google.com/search?q={quote_plus(keyword)}" target="_blank" rel="noopener">Nguon tham khao bo sung theo chu de</a></li>'
            '</ul>'
        )
    return (
        '<h2>External Resources</h2>'
        '<ul>'
        '<li><a href="https://developers.google.com/search/docs" target="_blank" rel="noopener">Google Search Central Documentation</a></li>'
        '<li><a href="https://schema.org" target="_blank" rel="noopener">Schema.org</a></li>'
        '</ul>'
    )


def _anchor_phrase(anchors: list[str], language: str) -> str:
    if len(anchors) == 1:
        return anchors[0]
    if len(anchors) == 2:
        if language.lower() == "vi":
            return f"{anchors[0]} và {anchors[1]}"
        return f"{anchors[0]} and {anchors[1]}"

    if language.lower() == "vi":
        return f"{anchors[0]}, {anchors[1]} hoặc {anchors[2]}"
    return f"{anchors[0]}, {anchors[1]}, or {anchors[2]}"


def _pick_template_index(keyword: str, category: str, template_count: int) -> int:
    token = f"{_normalize_text(keyword)}::{category}".encode("utf-8")
    digest = hashlib.md5(token).hexdigest()
    return int(digest[:8], 16) % max(template_count, 1)


def _selection_order(primary: str, ranked_categories: list[str]) -> list[str]:
    # Keep recommendation focused: primary category first, then curated related categories.
    order: list[str] = [primary]

    for related in RELATED_CATEGORIES.get(primary, ()): 
        if related in ranked_categories and related not in order:
            order.append(related)

    for category in ranked_categories:
        if category not in order:
            order.append(category)

    return order


def _resolve_intent(intent: ArticleIntent | str | None, keyword: str) -> ArticleIntent:
    if isinstance(intent, ArticleIntent):
        return intent
    if isinstance(intent, str):
        try:
            return ArticleIntent(intent)
        except ValueError:
            pass
    return detect_article_intent(keyword)


def _internal_links_html(
    keyword: str,
    language: str,
    base_url: str | None,
    intent: ArticleIntent | str | None,
) -> str:
    links_by_category = _load_internal_links()
    if not links_by_category:
        return ""

    ranked_categories = _rank_categories(keyword, list(links_by_category.keys()))
    primary_category = ranked_categories[0]
    pick_order = _selection_order(primary_category, ranked_categories)

    selected: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    # Limit cross-category drift: mostly from primary category, then one or two related links.
    max_from_primary = 2
    selected_from_primary = 0

    for category in pick_order:
        for item in links_by_category.get(category, []):
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            if not title or not url or url in seen_urls:
                continue

            if category == primary_category and selected_from_primary >= max_from_primary:
                continue

            selected.append({"title": title, "url": url, "category": category})
            seen_urls.add(url)
            if category == primary_category:
                selected_from_primary += 1
            if len(selected) >= 3:
                break
        if len(selected) >= 3:
            break

    if not selected:
        return ""

    primary_category = selected[0]["category"]
    safe_keyword = escape(keyword)
    anchors = [f'<a href="{entry["url"]}">{entry["title"]}</a>' for entry in selected]
    template_config = _load_internal_link_templates()
    vi_templates = template_config["vi"]
    en_templates = template_config["en"]
    vi_by_category = template_config["vi_by_category"]
    vi_intent_context = template_config["vi_intent_context"]
    resolved_intent = _resolve_intent(intent, keyword)

    if language.lower() == "vi":
        category_label = {
            "Backend": "backend",
            "Frontend": "frontend",
            "Career": "sự nghiệp IT",
            "AI-ML": "AI/ML",
            "Database": "cơ sở dữ liệu",
        }.get(primary_category, "chủ đề này")

        intent_prefix = vi_intent_context.get(resolved_intent.value, "")
        category_templates = vi_by_category.get(primary_category, vi_templates)

        if len(anchors) == 1:
            index = _pick_template_index(keyword, primary_category, len(SINGLE_LINK_TEMPLATES_VI))
            sentence = SINGLE_LINK_TEMPLATES_VI[index].format(
                category_label=category_label,
                keyword=safe_keyword,
                anchor=anchors[0],
            )
        else:
            anchor_phrase = _anchor_phrase(anchors, language)
            index = _pick_template_index(keyword, primary_category, len(category_templates))
            sentence = category_templates[index].format(
                category_label=category_label,
                anchor_phrase=anchor_phrase,
                keyword=safe_keyword,
            )
        sentence = f"{intent_prefix}{sentence}" if intent_prefix else sentence
        return f'<p class="internal-link-recommendation">{sentence}</p>'

    category_label = {
        "Backend": "backend",
        "Frontend": "frontend",
        "Career": "IT career",
        "AI-ML": "AI/ML",
        "Database": "database",
    }.get(primary_category, "this topic")
    if len(anchors) == 1:
        index = _pick_template_index(keyword, primary_category, len(SINGLE_LINK_TEMPLATES_EN))
        sentence = SINGLE_LINK_TEMPLATES_EN[index].format(
            category_label=category_label,
            keyword=safe_keyword,
            anchor=anchors[0],
        )
    else:
        anchor_phrase = _anchor_phrase(anchors, language)
        index = _pick_template_index(keyword, primary_category, len(en_templates))
        sentence = en_templates[index].format(
            category_label=category_label,
            anchor_phrase=anchor_phrase,
            keyword=safe_keyword,
        )
    return f'<p class="internal-link-recommendation">{sentence}</p>'


def enrich_seo_links(
    content_html: str,
    keyword: str,
    language: str,
    base_url: str | None = None,
    intent: ArticleIntent | str | None = None,
) -> str:
    enriched = content_html

    if not _has_external_link(enriched):
        enriched = f"{enriched}{_external_links_html(keyword, language)}"

    if not _has_internal_link(enriched, base_url):
        enriched = f"{enriched}{_internal_links_html(keyword, language, base_url, intent=intent)}"

    return enriched

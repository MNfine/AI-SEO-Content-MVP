import json
import hashlib
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote_plus


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


DEFAULT_VI_INTERNAL_LINK_TEMPLATES: tuple[str, ...] = (
    "Neu ban dang tim hieu {category_label}, co the xem them {anchor_phrase} tren itprep.",
    "De dao sau hon ve {category_label}, ban co the tham khao {anchor_phrase} tren itprep.",
    "Trong qua trinh hoc {category_label}, nhom bai {anchor_phrase} tren itprep se rat huu ich.",
    "Neu muon mo rong kien thuc {category_label}, ban nen doc them {anchor_phrase} tren itprep.",
    "Mot goi y nho cho chu de {category_label}: ban co the xem {anchor_phrase} tren itprep.",
    "De co goc nhin thuc te hon ve {category_label}, hay tham khao {anchor_phrase} tren itprep.",
    "Ban co the ket hop bai nay voi {anchor_phrase} tren itprep de hieu ro hon ve {category_label}.",
)

DEFAULT_EN_INTERNAL_LINK_TEMPLATES: tuple[str, ...] = (
    "If you are exploring {category_label}, you can also read {anchor_phrase} on itprep.",
    "For deeper context on {category_label}, consider reviewing {anchor_phrase} on itprep.",
    "To expand your view of {category_label}, the articles {anchor_phrase} on itprep are useful.",
    "A practical next read for {category_label} is {anchor_phrase} on itprep.",
    "If you want a broader perspective on {category_label}, check out {anchor_phrase} on itprep.",
)


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


def _load_internal_link_templates() -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not TEMPLATES_FILE.exists():
        return DEFAULT_VI_INTERNAL_LINK_TEMPLATES, DEFAULT_EN_INTERNAL_LINK_TEMPLATES

    try:
        payload = json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return DEFAULT_VI_INTERNAL_LINK_TEMPLATES, DEFAULT_EN_INTERNAL_LINK_TEMPLATES

        vi_templates = payload.get("vi", [])
        en_templates = payload.get("en", [])

        vi_cleaned = tuple(item.strip() for item in vi_templates if isinstance(item, str) and item.strip())
        en_cleaned = tuple(item.strip() for item in en_templates if isinstance(item, str) and item.strip())

        return (
            vi_cleaned or DEFAULT_VI_INTERNAL_LINK_TEMPLATES,
            en_cleaned or DEFAULT_EN_INTERNAL_LINK_TEMPLATES,
        )
    except Exception:
        return DEFAULT_VI_INTERNAL_LINK_TEMPLATES, DEFAULT_EN_INTERNAL_LINK_TEMPLATES


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
        joiner = " va " if language.lower() == "vi" else " and "
        return f"{anchors[0]}{joiner}{anchors[1]}"

    if language.lower() == "vi":
        return f"{anchors[0]}, {anchors[1]} hoac {anchors[2]}"
    return f"{anchors[0]}, {anchors[1]}, or {anchors[2]}"


def _pick_template_index(keyword: str, category: str, template_count: int) -> int:
    token = f"{_normalize_text(keyword)}::{category}".encode("utf-8")
    digest = hashlib.md5(token).hexdigest()
    return int(digest[:8], 16) % max(template_count, 1)


def _internal_links_html(keyword: str, language: str, base_url: str | None) -> str:
    links_by_category = _load_internal_links()
    if not links_by_category:
        return ""

    ranked_categories = _rank_categories(keyword, list(links_by_category.keys()))
    selected: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for category in ranked_categories:
        for item in links_by_category.get(category, []):
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            if not title or not url or url in seen_urls:
                continue
            selected.append({"title": title, "url": url, "category": category})
            seen_urls.add(url)
            if len(selected) >= 3:
                break
        if len(selected) >= 3:
            break

    if not selected:
        return ""

    primary_category = selected[0]["category"]
    anchors = [f'<a href="{entry["url"]}">{entry["title"]}</a>' for entry in selected]
    vi_templates, en_templates = _load_internal_link_templates()

    if language.lower() == "vi":
        category_label = {
            "Backend": "backend",
            "Frontend": "frontend",
            "Career": "career IT",
            "AI-ML": "AI/ML",
            "Database": "database",
        }.get(primary_category, "chu de nay")

        anchor_phrase = _anchor_phrase(anchors, language)
        index = _pick_template_index(keyword, primary_category, len(vi_templates))
        sentence = vi_templates[index].format(
            category_label=category_label,
            anchor_phrase=anchor_phrase,
        )
        return f'<p class="internal-link-recommendation">{sentence}</p>'

    category_label = {
        "Backend": "backend",
        "Frontend": "frontend",
        "Career": "IT career",
        "AI-ML": "AI/ML",
        "Database": "database",
    }.get(primary_category, "this topic")
    anchor_phrase = _anchor_phrase(anchors, language)
    index = _pick_template_index(keyword, primary_category, len(en_templates))
    sentence = en_templates[index].format(
        category_label=category_label,
        anchor_phrase=anchor_phrase,
    )
    return f'<p class="internal-link-recommendation">{sentence}</p>'


def enrich_seo_links(content_html: str, keyword: str, language: str, base_url: str | None = None) -> str:
    enriched = content_html

    if not _has_external_link(enriched):
        enriched = f"{enriched}{_external_links_html(keyword, language)}"

    if not _has_internal_link(enriched, base_url):
        enriched = f"{enriched}{_internal_links_html(keyword, language, base_url)}"

    return enriched

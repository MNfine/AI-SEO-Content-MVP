import re


def _slugify_heading(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", text)
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", "", cleaned).strip().lower()
    return re.sub(r"[-\s]+", "-", cleaned) or "section"


def _add_heading_ids(content: str) -> tuple[str, list[tuple[int, str, str]]]:
    headings: list[tuple[int, str, str]] = []

    def replace(match: re.Match[str]) -> str:
        level = int(match.group(1))
        attrs = match.group(2) or ""
        inner = match.group(3).strip()
        heading_id_match = re.search(r'id="([^"]+)"', attrs)
        heading_id = heading_id_match.group(1) if heading_id_match else _slugify_heading(inner)
        headings.append((level, inner, heading_id))
        if heading_id_match:
            return match.group(0)
        return f'<h{level}{attrs} id="{heading_id}">{inner}</h{level}>'

    updated = re.sub(r"<h([23])([^>]*)>(.*?)</h\1>", replace, content, flags=re.IGNORECASE | re.DOTALL)
    return updated, headings


def ensure_html_structure(content: str) -> str:
    stripped = content.strip()
    if not stripped:
        return "<p>No content</p>"
    if not stripped.startswith("<"):
        stripped = f"<p>{stripped}</p>"

    enriched, _ = _add_heading_ids(stripped)
    return enriched

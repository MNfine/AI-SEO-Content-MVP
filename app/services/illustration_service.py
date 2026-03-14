import base64
import json
import logging
import re
from html import escape

import google.generativeai as genai

from app.core.config import get_settings
from app.services.intent_service import ArticleIntent


logger = logging.getLogger(__name__)
_settings = get_settings()


def _figure_html(image_url: str, alt_text: str, caption: str) -> str:
    safe_alt_text = escape(alt_text)
    safe_caption = escape(caption)
    return (
        '<figure class="article-figure">'
        f'<img src="{image_url}" alt="{safe_alt_text}" loading="lazy" />'
        f'<figcaption>{safe_caption}</figcaption>'
        '</figure>'
    )


def _svg_to_data_url(svg_markup: str) -> str:
    encoded = base64.b64encode(svg_markup.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _simple_fallback_svg(topic: str, accent: str) -> str:
    safe_topic = escape(topic)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">'
        '<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{accent}"/><stop offset="100%" stop-color="#0B172A"/>'
        '</linearGradient></defs>'
        '<rect width="1200" height="675" fill="url(#bg)"/>'
        '<rect x="80" y="110" width="1040" height="455" rx="24" fill="#0F213D" opacity="0.88"/>'
        '<circle cx="250" cy="210" r="52" fill="#2DE0C2" opacity="0.8"/>'
        '<rect x="340" y="170" width="640" height="20" rx="10" fill="#A9BCD8" opacity="0.9"/>'
        '<rect x="340" y="210" width="480" height="16" rx="8" fill="#8EA6C7" opacity="0.8"/>'
        '<rect x="220" y="320" width="760" height="18" rx="9" fill="#A9BCD8" opacity="0.9"/>'
        '<rect x="220" y="356" width="620" height="16" rx="8" fill="#8EA6C7" opacity="0.8"/>'
        '<rect x="220" y="434" width="220" height="64" rx="14" fill="#2DE0C2" opacity="0.35"/>'
        '<text x="220" y="558" font-family="Segoe UI, Arial, sans-serif" font-size="40" fill="#EAF2FF">'
        f'{safe_topic}</text>'
        '</svg>'
    )


def _extract_json_block(raw_text: str) -> list[dict[str, str]]:
    stripped = raw_text.strip()
    fenced = re.search(r"```(?:json)?\s*(\[.*\])\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1) if fenced else stripped
    payload = json.loads(candidate)
    if not isinstance(payload, list):
        raise ValueError("Gemini illustrations payload must be an array")
    return [item for item in payload if isinstance(item, dict)]


def _generate_with_gemini(keyword: str, intent: ArticleIntent, language: str, count: int) -> list[dict[str, str]]:
    if not _settings.gemini_api_key:
        return []

    prompt = f"""
Ban la art director cho bai viet cong nghe.
Hay tao chinh xac {count} minh hoa SVG phang, phong cach chuyen nghiep, IT, bo cuc sach.
Chu de: {keyword}
Intent: {intent.value}
Ngon ngu caption: {language}

Tra ve DUY NHAT mot JSON array, moi phan tu co:
- alt: string
- caption: string
- svg: string (markup <svg>...</svg>, khong script, khong external image)

Yeu cau chat luong:
- Ti le 16:9, width 1200, height 675.
- Mau sac hien dai, phu hop blog cong nghe.
- Noi dung dung chu de, khong generic.
- Chu trong SVG ngan gon, de doc, khong qua 6000 ky tu moi anh.
""".strip()

    try:
        genai.configure(api_key=_settings.gemini_api_key)
        model = genai.GenerativeModel(_settings.gemini_model)
        response = model.generate_content(prompt)
        raw_text = getattr(response, "text", "") or ""
        rows = _extract_json_block(raw_text)
        cleaned: list[dict[str, str]] = []
        for row in rows:
            alt = str(row.get("alt", "")).strip()
            caption = str(row.get("caption", "")).strip()
            svg = str(row.get("svg", "")).strip()
            if not svg.startswith("<svg") or "</svg>" not in svg:
                continue
            cleaned.append({"alt": alt or f"Minh hoa {keyword}", "caption": caption or f"Visual cho {keyword}", "svg": svg})
            if len(cleaned) >= count:
                break
        return cleaned
    except Exception:
        logger.exception("Gemini illustration generation failed, fallback to local SVG")
        return []


def build_article_illustrations(keyword: str, intent: ArticleIntent, language: str) -> list[str]:
    label = keyword.strip() or "SEO Article"
    target_count = 3 if language.lower() == "vi" else 2

    generated = _generate_with_gemini(label, intent, language, target_count)
    if generated:
        return [_figure_html(_svg_to_data_url(item["svg"]), item["alt"], item["caption"]) for item in generated]

    palette = ["#0EA5E9", "#14B8A6", "#F59E0B"]
    fallback = []
    for index in range(target_count):
        svg = _simple_fallback_svg(f"{label} - Visual {index + 1}", palette[index % len(palette)])
        fallback.append(
            _figure_html(
                _svg_to_data_url(svg),
                f"Minh hoa {index + 1} cho {label}",
                f"Hinh minh hoa theo chu de {label} (anh {index + 1}).",
            )
        )
    return fallback


def inject_illustrations(content_html: str, keyword: str, intent: ArticleIntent, language: str) -> str:
    figures = build_article_illustrations(keyword, intent, language)
    if not figures:
        return content_html

    enriched = content_html
    if figures:
        first_paragraph_end = enriched.lower().find("</p>")
        if first_paragraph_end != -1:
            insert_at = first_paragraph_end + 4
            enriched = f"{enriched[:insert_at]}{figures[0]}{enriched[insert_at:]}"
        else:
            enriched = f"{figures[0]}{enriched}"

    if len(figures) > 1:
        faq_index = enriched.lower().find("<h2 id=\"cau-hoi-thuong-gap\"")
        if faq_index == -1:
            faq_index = enriched.lower().find("<h2>cau hoi thuong gap")
        if faq_index != -1:
            enriched = f"{enriched[:faq_index]}{figures[1]}{enriched[faq_index:]}"
        else:
            enriched = f"{enriched}{figures[1]}"

    if len(figures) > 2:
        conclusion_index = enriched.lower().find("<h2 id=\"ket-luan\"")
        if conclusion_index == -1:
            conclusion_index = enriched.lower().find("<h2>ket luan")
        if conclusion_index != -1:
            enriched = f"{enriched[:conclusion_index]}{figures[2]}{enriched[conclusion_index:]}"
        else:
            enriched = f"{enriched}{figures[2]}"

    return enriched

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


def _keyword_labels(keyword: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9+#]+", keyword)
    stopwords = {"cho", "nguoi", "moi", "la", "va", "for", "the", "to", "in", "of"}
    labels: list[str] = []
    for token in tokens:
        cleaned = token.strip()
        if len(cleaned) < 2:
            continue
        lowered = cleaned.lower()
        if lowered in stopwords:
            continue
        normalized = cleaned.upper() if len(cleaned) <= 4 else cleaned.title()
        if normalized not in labels:
            labels.append(normalized)
        if len(labels) >= 4:
            break
    return labels or ["IT", "Architecture", "Scale"]


def _svg_architecture(topic: str, chips: list[str], accent: str) -> str:
    safe_topic = escape(topic[:60])
    chip_a = escape(chips[0])
    chip_b = escape(chips[1] if len(chips) > 1 else "Service")
    chip_c = escape(chips[2] if len(chips) > 2 else "Data")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">'
        '<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{accent}"/><stop offset="100%" stop-color="#0B172A"/>'
        '</linearGradient></defs>'
        '<rect width="1200" height="675" fill="url(#bg)"/>'
        '<rect x="70" y="90" width="1060" height="500" rx="24" fill="#0E1C34" opacity="0.88"/>'
        '<rect x="130" y="165" width="250" height="120" rx="16" fill="#18385D"/>'
        '<rect x="475" y="165" width="250" height="120" rx="16" fill="#204770"/>'
        '<rect x="820" y="165" width="250" height="120" rx="16" fill="#285985"/>'
        '<path d="M380 225 L475 225" stroke="#6EE7D9" stroke-width="6" />'
        '<path d="M725 225 L820 225" stroke="#6EE7D9" stroke-width="6" />'
        f'<text x="165" y="235" font-family="Segoe UI, Arial" font-size="26" fill="#EAF2FF">{chip_a}</text>'
        f'<text x="535" y="235" font-family="Segoe UI, Arial" font-size="26" fill="#EAF2FF">{chip_b}</text>'
        f'<text x="885" y="235" font-family="Segoe UI, Arial" font-size="26" fill="#EAF2FF">{chip_c}</text>'
        '<rect x="130" y="350" width="940" height="155" rx="18" fill="#0F2A49"/>'
        '<rect x="165" y="388" width="420" height="18" rx="9" fill="#A8C0DE" />'
        '<rect x="165" y="422" width="350" height="14" rx="7" fill="#8FAAD0" />'
        '<rect x="165" y="452" width="500" height="14" rx="7" fill="#8FAAD0" />'
        '<circle cx="910" cy="428" r="42" fill="#2DE0C2" opacity="0.75"/>'
        '<text x="180" y="556" font-family="Segoe UI, Arial, sans-serif" font-size="38" fill="#EAF2FF">'
        f'{safe_topic}</text>'
        '</svg>'
    )


def _svg_pipeline(topic: str, chips: list[str], accent: str) -> str:
    safe_topic = escape(topic[:60])
    chip_a = escape(chips[0])
    chip_b = escape(chips[1] if len(chips) > 1 else "Flow")
    chip_c = escape(chips[2] if len(chips) > 2 else "Deploy")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">'
        '<defs><linearGradient id="bg2" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{accent}"/><stop offset="100%" stop-color="#10223A"/>'
        '</linearGradient></defs>'
        '<rect width="1200" height="675" fill="url(#bg2)"/>'
        '<rect x="90" y="92" width="1020" height="490" rx="26" fill="#0D1D34" opacity="0.9"/>'
        '<rect x="150" y="240" width="220" height="96" rx="14" fill="#1B3D63"/>'
        '<rect x="490" y="240" width="220" height="96" rx="14" fill="#255178"/>'
        '<rect x="830" y="240" width="220" height="96" rx="14" fill="#2F6892"/>'
        '<path d="M370 288 L490 288" stroke="#9FE8D9" stroke-width="8" marker-end="url(#arrow)"/>'
        '<path d="M710 288 L830 288" stroke="#9FE8D9" stroke-width="8" marker-end="url(#arrow)"/>'
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#9FE8D9"/></marker></defs>'
        f'<text x="210" y="300" font-family="Segoe UI, Arial" font-size="26" fill="#EAF2FF">{chip_a}</text>'
        f'<text x="560" y="300" font-family="Segoe UI, Arial" font-size="26" fill="#EAF2FF">{chip_b}</text>'
        f'<text x="890" y="300" font-family="Segoe UI, Arial" font-size="26" fill="#EAF2FF">{chip_c}</text>'
        '<rect x="150" y="388" width="900" height="22" rx="11" fill="#A8C0DE" opacity="0.9"/>'
        '<rect x="150" y="424" width="760" height="16" rx="8" fill="#8FAAD0" opacity="0.85"/>'
        '<text x="160" y="548" font-family="Segoe UI, Arial, sans-serif" font-size="38" fill="#EAF2FF">'
        f'{safe_topic}</text>'
        '</svg>'
    )


def _svg_dashboard(topic: str, chips: list[str], accent: str) -> str:
    safe_topic = escape(topic[:60])
    chip_a = escape(chips[0])
    chip_b = escape(chips[1] if len(chips) > 1 else "Metrics")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">'
        '<defs><linearGradient id="bg3" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{accent}"/><stop offset="100%" stop-color="#0B1A2B"/>'
        '</linearGradient></defs>'
        '<rect width="1200" height="675" fill="url(#bg3)"/>'
        '<rect x="80" y="90" width="1040" height="500" rx="24" fill="#0D1E33" opacity="0.9"/>'
        '<rect x="140" y="150" width="470" height="170" rx="16" fill="#163A5F"/>'
        '<rect x="650" y="150" width="410" height="170" rx="16" fill="#214A73"/>'
        '<rect x="140" y="350" width="300" height="170" rx="16" fill="#2B5B85"/>'
        '<rect x="470" y="350" width="590" height="170" rx="16" fill="#1E4468"/>'
        '<path d="M170 270 L220 235 L275 250 L335 210 L400 230 L460 195 L560 180" stroke="#6EE7D9" stroke-width="6" fill="none"/>'
        '<circle cx="780" cy="236" r="56" fill="#2DE0C2" opacity="0.75"/>'
        f'<text x="725" y="245" font-family="Segoe UI, Arial" font-size="24" fill="#0D1E33">{chip_a}</text>'
        f'<text x="175" y="452" font-family="Segoe UI, Arial" font-size="25" fill="#EAF2FF">{chip_b}</text>'
        '<rect x="500" y="398" width="510" height="16" rx="8" fill="#A8C0DE"/>'
        '<rect x="500" y="430" width="420" height="14" rx="7" fill="#8FAAD0"/>'
        '<rect x="500" y="458" width="360" height="14" rx="7" fill="#8FAAD0"/>'
        '<text x="165" y="556" font-family="Segoe UI, Arial, sans-serif" font-size="38" fill="#EAF2FF">'
        f'{safe_topic}</text>'
        '</svg>'
    )


def _build_fallback_svg(topic: str, chips: list[str], accent: str, variant: int) -> str:
    if variant % 3 == 0:
        return _svg_architecture(topic, chips, accent)
    if variant % 3 == 1:
        return _svg_pipeline(topic, chips, accent)
    return _svg_dashboard(topic, chips, accent)


def _rich_caption(keyword: str, intent: ArticleIntent, language: str, index: int) -> str:
    if language.lower() != "vi":
        return (
            f"This visual highlights the practical side of {keyword}: architecture decisions, delivery flow, "
            "and the trade-offs teams usually face in real production systems."
        )

    if intent == ArticleIntent.INTERVIEW_CHECKLIST:
        lines = [
            f"Minh hoa nay mo ta boi canh phong van {keyword} theo huong thuc chien: tu cau hoi nen tang den cach tra loi co logic.",
            f"Hinh nay nhan manh cac diem nha tuyen dung quan tam khi danh gia nang luc {keyword}, giup ban on tap co trong tam hon.",
            f"Visual tap trung vao khung tra loi {keyword}: y chinh, trade-off va tinh huong thuc te de tranh tra loi may moc.",
        ]
        return lines[index % len(lines)]

    if intent == ArticleIntent.COMPARISON:
        lines = [
            f"Minh hoa nay the hien cach so sanh {keyword} theo tieu chi ky thuat va boi canh van hanh thay vi chi nhin trend.",
            f"Visual nhan manh diem manh, gioi han va dieu kien ap dung cua {keyword} de ho tro quyet dinh chon cong nghe.",
            f"Hinh nay tom tat logic chon {keyword} dua tren team size, deadline va chi phi bao tri ve dai han.",
        ]
        return lines[index % len(lines)]

    if intent == ArticleIntent.TUTORIAL:
        lines = [
            f"Minh hoa nay mo ta lo trinh hoc {keyword} theo tung giai doan, giup nguoi moi biet ro nen hoc gi truoc sau.",
            f"Visual nhan manh cach ap dung {keyword} vao bai toan thuc te, khong dung lai o muc ly thuyet.",
            f"Hinh nay the hien ban do thuc hanh {keyword} voi cac moc checkpoint de do tien do hoc tap.",
        ]
        return lines[index % len(lines)]

    if intent == ArticleIntent.TOOL_ROUNDUP:
        lines = [
            f"Minh hoa tong hop cac huong tiep can {keyword} de ban shortlist cong cu nhanh hon theo muc tieu su dung.",
            f"Visual nay cho thay cach danh gia {keyword} theo gia tri thuc te, do phuc tap va kha nang mo rong.",
            f"Hinh minh hoa tap trung vao framework lua chon {keyword} cho team moi, team vua va team da scale.",
        ]
        return lines[index % len(lines)]

    lines = [
        f"Minh hoa nay the hien vai tro cua {keyword} trong he thong IT hien dai, tu kien truc den van hanh thuc te.",
        f"Visual nhan manh cach {keyword} duoc dung de giai quyet bai toan hieu nang, kha nang mo rong va do tin cay.",
        f"Hinh nay mo ta goc nhin thuc chien ve {keyword}, tap trung vao cac quyet dinh ky thuat co tac dong cao.",
    ]
    return lines[index % len(lines)]


def _rich_alt_text(keyword: str, intent: ArticleIntent, language: str, index: int) -> str:
    if language.lower() == "vi":
        return f"Minh hoa chuyen nghiep ve {keyword}, goc nhin {intent.value}, anh {index + 1}"
    return f"Professional illustration for {keyword}, {intent.value}, visual {index + 1}"


def _is_generic_caption(text: str) -> bool:
    normalized = text.lower().strip()
    generic_markers = [
        "hinh minh hoa",
        "visual cho",
        "illustration for",
        "minh hoa cho",
    ]
    return any(marker in normalized for marker in generic_markers)


def _extract_json_block(raw_text: str) -> list[dict[str, str]]:
    stripped = raw_text.strip()
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1) if fenced else stripped
    if not candidate.startswith("["):
        start = candidate.find("[")
        end = candidate.rfind("]")
        if start != -1 and end != -1 and end > start:
            candidate = candidate[start:end + 1]
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
        response = model.generate_content(
            prompt,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.7,
            },
        )
        raw_text = getattr(response, "text", "") or ""
        rows = _extract_json_block(raw_text)
        cleaned: list[dict[str, str]] = []
        for row in rows:
            alt = str(row.get("alt", "")).strip()
            caption = str(row.get("caption", "")).strip()
            svg = str(row.get("svg", "")).strip()
            if not svg.startswith("<svg") or "</svg>" not in svg:
                continue
            if not caption or _is_generic_caption(caption):
                caption = _rich_caption(keyword, intent, language, len(cleaned))
            if not alt:
                alt = _rich_alt_text(keyword, intent, language, len(cleaned))
            cleaned.append({"alt": alt, "caption": caption, "svg": svg})
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
    chips = _keyword_labels(label)
    fallback = []
    for index in range(target_count):
        svg = _build_fallback_svg(f"{label} - Visual {index + 1}", chips, palette[index % len(palette)], index)
        fallback.append(
            _figure_html(
                _svg_to_data_url(svg),
                _rich_alt_text(label, intent, language, index),
                _rich_caption(label, intent, language, index),
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

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any

import google.generativeai as genai
from sqlalchemy import exc

from app.core.config import get_settings
from app.services.illustration_service import inject_illustrations
from app.services.intent_service import ArticleIntent, detect_article_intent
from app.services.seo_link_service import enrich_seo_links
from app.services.slug_service import slugify
from app.utils.html_formatter import ensure_html_structure

logger = logging.getLogger(__name__)

_MODEL_CACHE_KEY: str | None = None
_MODEL_CACHE_VALUE: str | None = None
_GEMINI_BACKOFF_UNTIL: datetime | None = None


REQUIRED_PAYLOAD_KEYS = {"title", "meta_description", "excerpt", "content_html"}
RAW_DEBUG_LOG_FILE = Path("logs") / "gemini_raw_responses.jsonl"


def _is_quota_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "429" in message or "quota" in message or "rate limit" in message


def _is_model_not_found_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "not found" in message and "model" in message


def _candidate_models(primary_model: str) -> list[str]:
    fallback_chain = [
        primary_model,
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash",
        "gemini-flash-lite-latest",
    ]
    unique: list[str] = []
    for name in fallback_chain:
        normalized = name.replace("models/", "").strip()
        if normalized and normalized not in unique:
            unique.append(normalized)
    return unique


def _sanitize_plain_text(text: str) -> str:
    return re.sub(r"[<>]", "", text).strip()


def _extract_text_from_response(response: Any) -> str:
    """Extract text safely from multiple Gemini response shapes."""
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    # Fallback for older SDK response shapes.
    candidates = getattr(response, "candidates", None)
    if candidates:
        chunks: list[str] = []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) if content else None
            if not parts:
                continue
            for part in parts:
                part_text = getattr(part, "text", None)
                if isinstance(part_text, str) and part_text.strip():
                    chunks.append(part_text)
        if chunks:
            return "\n".join(chunks).strip()

    raise ValueError("Gemini response did not contain readable text")


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", flags=re.DOTALL | re.IGNORECASE)


def _escape_control_chars_in_json_strings(raw: str) -> str:
    """Escape illegal control chars when they appear inside JSON string literals."""
    out: list[str] = []
    in_string = False
    escaped = False

    for ch in raw:
        code = ord(ch)

        if escaped:
            out.append(ch)
            escaped = False
            continue

        if ch == "\\":
            out.append(ch)
            escaped = True
            continue

        if ch == '"':
            out.append(ch)
            in_string = not in_string
            continue

        if in_string and code < 0x20:
            if ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                out.append("\\r")
            elif ch == "\t":
                out.append("\\t")
            else:
                out.append(f"\\u{code:04x}")
            continue

        out.append(ch)

    return "".join(out)


def _loads_json_with_repair(candidate: str) -> dict:
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        repaired = _escape_control_chars_in_json_strings(candidate)
        data = json.loads(repaired)

    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                return item
    raise ValueError("Gemini returned JSON, but it was not an object")


def _iter_json_object_candidates(text: str) -> list[str]:
    """Find all balanced JSON object substrings inside mixed model output text."""
    candidates: list[str] = []
    stack = 0
    start = -1
    in_string = False
    escaped = False

    for index, ch in enumerate(text):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue

        if ch == "{":
            if stack == 0:
                start = index
            stack += 1
        elif ch == "}":
            if stack > 0:
                stack -= 1
                if stack == 0 and start != -1:
                    candidates.append(text[start:index + 1])

    return candidates


def _extract_json_string_field(text: str, field: str) -> str | None:
    pattern = re.compile(rf'"{re.escape(field)}"\s*:\s*"', flags=re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return None

    cursor = match.end()
    chunks: list[str] = []
    escaped = False

    while cursor < len(text):
        ch = text[cursor]
        if escaped:
            chunks.append(ch)
            escaped = False
            cursor += 1
            continue
        if ch == "\\":
            chunks.append(ch)
            escaped = True
            cursor += 1
            continue
        if ch == '"':
            raw_value = "".join(chunks)
            try:
                return json.loads(f'"{raw_value}"')
            except Exception:
                repaired = _escape_control_chars_in_json_strings(raw_value)
                try:
                    return json.loads(f'"{repaired}"')
                except Exception:
                    return repaired
        chunks.append(ch)
        cursor += 1

    return None


def _extract_payload_by_fields(raw_text: str) -> dict | None:
    required_keys = ["title", "meta_description", "excerpt", "content_html"]
    payload: dict[str, str] = {}

    for key in required_keys:
        value = _extract_json_string_field(raw_text, key)
        if not value:
            return None
        payload[key] = value

    optional_slug = _extract_json_string_field(raw_text, "slug")
    if optional_slug:
        payload["slug"] = optional_slug

    return payload


def _extract_json_block(raw_text: str) -> dict:
    """Parse JSON even when the model wraps it in prose or fenced code blocks."""
    if not raw_text or not raw_text.strip():
        raise ValueError("Empty response from Gemini")

    candidate = raw_text.strip()

    fenced = _JSON_BLOCK_RE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
        return _loads_json_with_repair(candidate)

    # Try direct parse first.
    try:
        return _loads_json_with_repair(candidate)
    except json.JSONDecodeError:
        pass
    except ValueError:
        pass

    # Then try extracting the outermost JSON object.
    first_brace = candidate.find("{")
    last_brace = candidate.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        sliced = candidate[first_brace:last_brace + 1]
        try:
            return _loads_json_with_repair(sliced)
        except (json.JSONDecodeError, ValueError):
            pass

    # Finally, try all balanced JSON object candidates from mixed text.
    for chunk in _iter_json_object_candidates(candidate):
        try:
            return _loads_json_with_repair(chunk)
        except (json.JSONDecodeError, ValueError):
            continue

    # Last resort: extract required string fields directly from malformed near-JSON output.
    fallback_payload = _extract_payload_by_fields(candidate)
    if fallback_payload:
        return fallback_payload

    raise ValueError("Could not extract a valid JSON object from Gemini response")


def _prompt_template(intent: ArticleIntent) -> str:
    prompts_dir = Path(__file__).resolve().parents[1] / "prompts"
    prompt_path = prompts_dir / f"{intent.value}_prompt.txt"
    if not prompt_path.exists():
        prompt_path = prompts_dir / "expert_guide_prompt.txt"
    return prompt_path.read_text(encoding="utf-8")


def _render_prompt(template: str, *, keyword: str, language: str, tone: str) -> str:
    """
    Render prompt safely.

    Preferred placeholders inside prompt files:
      {{keyword}}, {{language}}, {{tone}}

    This avoids collisions with literal JSON braces in the prompt.
    For backward compatibility, we still try str.format() if the explicit
    placeholders are not present.
    """
    rendered = (
        template.replace("{{keyword}}", keyword)
        .replace("{{language}}", language)
        .replace("{{tone}}", tone)
    )

    # Replace only explicit single-brace placeholders while preserving unrelated JSON braces.
    rendered = re.sub(r"(?<!\{)\{keyword\}(?!\})", keyword, rendered)
    rendered = re.sub(r"(?<!\{)\{language\}(?!\})", language, rendered)
    rendered = re.sub(r"(?<!\{)\{tone\}(?!\})", tone, rendered)
    return rendered


def _build_prompt(template: str, keyword: str, language: str, tone: str) -> str:
    """Backward-compatible alias for existing tests/tools."""
    return _render_prompt(template, keyword=keyword, language=language, tone=tone)


def _validate_payload(payload: dict, keyword: str) -> dict:
    missing = [key for key in REQUIRED_PAYLOAD_KEYS if not str(payload.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Gemini payload missing required fields: {', '.join(missing)}")

    payload = dict(payload)
    payload.setdefault("slug", slugify(payload.get("title") or keyword))
    payload["title"] = str(payload["title"]).strip()
    payload["slug"] = slugify(str(payload["slug"]).strip() or keyword)
    payload["meta_description"] = str(payload["meta_description"]).strip()
    payload["excerpt"] = str(payload["excerpt"]).strip()
    payload["content_html"] = ensure_html_structure(str(payload["content_html"]))
    return payload


class GeminiService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _build_local_fallback(
        self,
        keyword: str,
        language: str,
        tone: str,
        intent: ArticleIntent | None = None,
    ) -> dict:
        resolved_intent = intent or detect_article_intent(keyword)
        keyword_plain = _sanitize_plain_text(keyword)
        keyword_html = escape(keyword_plain)

        if language.lower() != "vi":
            return self._build_en_generic_fallback(keyword_plain, keyword_html)

        if resolved_intent == ArticleIntent.INTERVIEW_CHECKLIST:
            return self._build_vi_interview_fallback(keyword_plain, keyword_html)
        if resolved_intent == ArticleIntent.COMPARISON:
            return self._build_vi_comparison_fallback(keyword_plain, keyword_html)
        if resolved_intent == ArticleIntent.TUTORIAL:
            return self._build_vi_tutorial_fallback(keyword_plain, keyword_html)
        if resolved_intent == ArticleIntent.TOOL_ROUNDUP:
            return self._build_vi_tool_roundup_fallback(keyword_plain, keyword_html)
        return self._build_vi_expert_guide_fallback(keyword_plain, keyword_html)

    def _build_vi_interview_fallback(self, keyword_plain: str, keyword_html: str) -> dict:
        title = f"{keyword_plain.capitalize()}: Checklist kien thuc quan trong de tranh mat diem"
        meta_description = (
            f"Tong hop cac cau hoi va kien thuc cot loi ve {keyword_plain} theo dang checklist Q&A, giup on tap nhanh va dung trong tam."
        )
        excerpt = (
            f"Bai viet tong hop {keyword_plain} theo format phong van: co muc luc, nhom cau hoi, giai thich ngan gon va tinh huong thuc te. "
            f"Phu hop de on tap nhanh truoc buoi trao doi ky thuat."
        )
        content_html = ensure_html_structure(
            f"<p>{keyword_html} thuong khong chi kiem tra viec nho cu phap ma con do kha nang tu duy du lieu, cach giai thich logic va muc do hieu he thong. Vi vay, on tap theo checklist Q&A se hieu qua hon viec hoc tung manh kien thuc roi rac.</p>"
            f"<p>Trong bai viet nay, noi dung ve {keyword_html} duoc chia theo nhom cau hoi co ban, truy van, toi uu, transaction va tinh huong production de ban de xac dinh phan nao dang yeu nhat.</p>"
            "<h2>Kien thuc co ban thuong gap</h2>"
            f"<h3>1.1 {keyword_html} la gi va vi sao thuong duoc hoi?</h3>"
            "<p>Nha tuyen dung dung nhom cau hoi nen tang de kiem tra xem ung vien co hieu dung vai tro cua cong nghe trong he thong hay chi nho manh menh cu phap. Cau tra loi tot can noi duoc muc dich, boi canh su dung va tac dong toi du lieu hoac van hanh.</p>"
            f"<h3>1.2 Khi tra loi cau hoi ve {keyword_html}, can nhan manh dieu gi?</h3>"
            "<p>Hay tap trung vao logic xu ly, trade-off va truong hop ap dung thay vi liet ke dinh nghia sach giao khoa. Nha tuyen dung thuong danh gia cach ban ket noi kien thuc co ban voi bai toan thuc te.</p>"
            "<h2>Truy van va xu ly du lieu</h2>"
            f"<h3>2.1 Nhung thao tac nao lien quan den {keyword_html} de gay nham lan?</h3>"
            "<p>Nhom cau hoi nay thuong xoay quanh thu tu xu ly logic, su khac nhau giua cac menh de va cach doc de bai. Ung vien de mat diem khi tra loi dung cu phap nhung sai ban chat xu ly du lieu.</p>"
            f"<h3>2.2 Cach trinh bay mot truy van lien quan den {keyword_html} sao cho thuyet phuc?</h3>"
            "<p>Hay giai thich tu input, cach loc, cach gom nhom den ket qua ky vong. Khi can, dua them vi du ngan de nha tuyen dung thay ro ban dang nghi theo quy trinh thay vi doan dap an.</p>"
            "<pre><code>SELECT department_id, COUNT(*)\nFROM employees\nGROUP BY department_id\nHAVING COUNT(*) > 5;\n</code></pre>"
            "<h2>Toi uu va hieu nang</h2>"
            f"<h3>3.1 Vi sao cau hoi toi uu lien quan den {keyword_html} de phan loai level?</h3>"
            "<p>Vi day la nhom cau hoi the hien ban co kinh nghiem production hay chi lam bai tap. Nha tuyen dung se de y cach ban noi ve chi phi doc ghi, so luong du lieu, index va kha nang giam rui ro khi fix query cham.</p>"
            f"<h3>3.2 Cach tra loi khi chua nho het chi tiet ky thuat cua {keyword_html}?</h3>"
            "<p>Khong nen doan mo ho. Hay trinh bay theo quy trinh: quan sat, do dac, xac dinh nguyen nhan, thu nghiem co so sanh truoc-sau. Cach tra loi nay the hien tu duy he thong va an toan hon viec nho tung meo vat.</p>"
            "<h2>Transaction, lock va do tin cay</h2>"
            f"<h3>4.1 Nhom cau hoi transaction trong {keyword_html} kiem tra dieu gi?</h3>"
            "<p>No kiem tra xem ban co hieu rang du lieu khong chi dung ma con phai on dinh khi co nhieu thao tac dong thoi. Day la diem khac nhau ro giua nguoi hoc syntax va nguoi da gap van de production.</p>"
            f"<h3>4.2 Cach giai thich lock, isolation hoac rollback lien quan den {keyword_html}?</h3>"
            "<p>Hay lien he truc tiep voi rui ro nghiep vu: doc du lieu chua commit, du lieu mat nhat quan hoac giao dich chan nhau qua lau. Nha tuyen dung danh gia cao cau tra loi co tinh he thong va gan voi tac dong thuc te.</p>"
            "<h2>Tinh huong thuc te trong phong van</h2>"
            f"<h3>5.1 Neu gap bai toan production lien quan den {keyword_html}, nen tra loi theo trinh tu nao?</h3>"
            "<p>Bat dau bang pham vi anh huong, cach tai hien, cach do dac va cach giam rui ro truoc khi toi uu. Day la khung tra loi an toan va thuyet phuc trong nhung cau hoi tinh huong.</p>"
            f"<h3>5.2 Loi pho bien khi tra loi tinh huong ve {keyword_html} la gi?</h3>"
            "<p>Loi de gap nhat la nhay vao giai phap qua som, khong hoi ro rang buoc, khong noi toi rollback va khong dua ra cach xac minh ket qua sau khi fix. Day la ly do nhieu cau tra loi nghe co ve hop ly nhung van khong dat diem cao.</p>"
            "<h2>Cau hoi thuong gap</h2>"
            f"<h3>{keyword_html} nen on theo chu de hay theo cau hoi?</h3>"
            "<p>Tot nhat nen ket hop ca hai, nhung khi gan ngay phong van thi on theo nhom cau hoi se giup ban ra quyet dinh nhanh va de phat hien lo hong kien thuc hon.</p>"
            f"<h3>Lam sao de hoc {keyword_html} ma khong hoc vat?</h3>"
            "<p>Hay hoc theo cau truc: khai niem, vi du, sai lam pho bien, trade-off va tinh huong ap dung. Day la cach bien kien thuc thanh kha nang tra loi co logic.</p>"
            "<h2>Ket luan</h2>"
            f"<p>Voi chu de {keyword_html}, cach on tap hieu qua nhat la chuyen noi dung ve dang checklist Q&A va gom theo nhom tu duy. Khi ban tra loi duoc vi sao, khi nao va rui ro la gi, ban da vuot xa muc nho cu phap don thuan.</p>"
        )
        return {
            "title": title,
            "slug": slugify(keyword_plain),
            "meta_description": meta_description,
            "excerpt": excerpt,
            "content_html": content_html,
        }

    def _build_vi_comparison_fallback(self, keyword_plain: str, keyword_html: str) -> dict:
        title = f"{keyword_plain.capitalize()}: So sanh chi tiet va cach chon theo nhu cau"
        meta_description = (
            f"So sanh {keyword_plain} theo tieu chi thuc te: toc do, do phuc tap, kha nang mo rong va boi canh ap dung."
        )
        excerpt = (
            f"Bai viet phan tach {keyword_plain} theo nhom tieu chi de giup ban chon dung phuong an thay vi chi doc tong quan ly thuyet."
        )
        content_html = ensure_html_structure(
            f"<p>{keyword_html} thuong la kieu keyword co intent rat ro: nguoi doc khong can dinh nghia chung chung ma can mot khung ra quyet dinh. Boi vay, bai viet can di thang vao tieu chi so sanh, trade-off va tinh huong ap dung.</p>"
            f"<p>Neu chi liet ke uu diem cua tung ben ma khong noi khi nao nen chon, article se khong giai quyet dung search intent cua {keyword_html}.</p>"
            "<h2>Tieu chi so sanh quan trong</h2>"
            "<ul><li>Toc do trien khai.</li><li>Do phuc tap khi mo rong.</li><li>Chi phi hoc va onboard.</li><li>Kha nang van hanh va bao tri.</li></ul>"
            "<h2>Diem khac nhau cot loi</h2>"
            "<p>Phan nay nen tap trung vao su khac nhau ve triet ly thiet ke, trai nghiem phat trien va tong chi phi su dung, khong dung lai o muc khac cu phap.</p>"
            "<h2>Khi nao nen chon phuong an A</h2>"
            "<p>Hay neu ro rang buoc va dieu kien de nguoi doc co the tu map vao du an cua ho.</p>"
            "<h2>Khi nao nen chon phuong an B</h2>"
            "<p>Phan nay can doi xung voi phan tren va giup nguoi doc thay trade-off mot cach cong bang.</p>"
            "<h2>Sai lam pho bien khi so sanh</h2>"
            "<p>Sai lam lon nhat la so sanh theo trend hoac benchmark roi rac ma khong xet toi muc tieu cua he thong.</p>"
            "<h2>Cau hoi thuong gap</h2>"
            f"<h3>{keyword_html} co dap an tuyet doi khong?</h3><p>Khong. Dap an dung phu thuoc vao boi canh, team va rang buoc van hanh.</p>"
            "<h2>Ket luan</h2>"
            "<p>Muc tieu cua bai so sanh tot khong phai de ket luan mot ben luon tot hon, ma la de giup nguoi doc chon dung hon cho bai toan cua minh.</p>"
        )
        return {
            "title": title,
            "slug": slugify(keyword_plain),
            "meta_description": meta_description,
            "excerpt": excerpt,
            "content_html": content_html,
        }

    def _build_vi_tutorial_fallback(self, keyword_plain: str, keyword_html: str) -> dict:
        title = f"{keyword_plain.capitalize()}: Lo trinh hoc va cach ap dung cho nguoi moi"
        meta_description = (
            f"Huong dan {keyword_plain} theo lo trinh ro rang: nen bat dau tu dau, hoc theo thu tu nao va tranh sai lam gi."
        )
        excerpt = (
            f"Bai viet theo form tutorial SEO cho chu de {keyword_plain}, tap trung vao lo trinh, muc tieu hoc va cach thuc hanh de de theo doi."
        )
        content_html = ensure_html_structure(
            f"<p>Voi keyword nhu {keyword_html}, nguoi doc thuong can mot lo trinh ro rang hon la mot bai viet tong hop chung chung. Boi vay, article can chia theo giai doan hoc va cac dau viec cu the.</p>"
            f"<p>Muc tieu cua bai nay la giup ban hinh dung nhanh phai bat dau tu dau, hoc theo thu tu nao va can tranh nhung sai lam gi khi tiep can {keyword_html}.</p>"
            "<h2>Bat dau tu dau</h2><p>Hay xac dinh muc tieu hoc: de di lam, de lam du an rieng hay de on phong van. Muc tieu khac nhau se dan toi lo trinh khac nhau.</p>"
            "<h2>Lo trinh hoc de xuat</h2><h3>Buoc 1: Nen tang</h3><p>Nam chac khai niem va boi canh ap dung truoc khi lao vao framework hoac tool cu the.</p><h3>Buoc 2: Thuc hanh nho</h3><p>Lam du an nho de noi ly thuyet voi dau viec thuc te.</p>"
            "<h2>Checklist truoc khi chuyen sang muc nang cao</h2><ul><li>Hieu input-output.</li><li>Tu viet duoc vi du nho.</li><li>Giai thich duoc trade-off.</li></ul>"
            "<h2>Sai lam de gap</h2><p>Sai lam pho bien la hoc qua rong, qua nhanh va khong co du an nho de kiem chung muc do hieu.</p>"
            "<h2>Vi du thuc hanh</h2><pre><code>learning_plan = [\n  \"foundation\",\n  \"small_project\",\n  \"review_and_refactor\"\n]\n</code></pre>"
            "<h2>Cau hoi thuong gap</h2><h3>Mat bao lau de hoc?</h3><p>Phu thuoc tan suat hoc va muc tieu, nhung nen do tien do bang kha nang lam duoc viec cu the thay vi so gio hoc.</p>"
            "<h2>Ket luan</h2><p>Mot tutorial tot can giup nguoi doc biet bat dau, biet uu tien va biet cach tu danh gia tien do, thay vi tao cam giac hoc nhieu nhung khong ra ket qua.</p>"
        )
        return {
            "title": title,
            "slug": slugify(keyword_plain),
            "meta_description": meta_description,
            "excerpt": excerpt,
            "content_html": content_html,
        }

    def _build_vi_tool_roundup_fallback(self, keyword_plain: str, keyword_html: str) -> dict:
        title = f"{keyword_plain.capitalize()}: Tieu chi lua chon va danh sach goi y nen xem"
        meta_description = (
            f"Tong hop {keyword_plain} theo huong roundup: tieu chi lua chon, uu nhuoc diem va boi canh su dung cua tung nhom giai phap."
        )
        excerpt = (
            f"Bai viet dang listicle/roundup giup ban loc nhanh cac lua chon lien quan den {keyword_plain} thay vi doc tung cong cu mot cach roi rac."
        )
        content_html = ensure_html_structure(
            f"<p>Voi keyword kieu {keyword_html}, nguoi doc can duoc giup thu hep lua chon. Vi vay, bai viet can dua ra tieu chi loc truoc, sau do moi di vao tung nhom cong cu hoac giai phap.</p>"
            f"<p>Muc tieu khong phai la goi ten cang nhieu cong cu cang tot, ma la giup nguoi doc tim nhanh lua chon phu hop hon voi bai toan cua ho.</p>"
            "<h2>Tieu chi lua chon</h2><ul><li>Do de su dung.</li><li>Gia tri so voi chi phi.</li><li>Kha nang tich hop.</li><li>Do phu hop voi quy mo team.</li></ul>"
            "<h2>Nhom lua chon phu hop cho nguoi moi</h2><p>Uu tien cong cu de onboard, giao dien ro rang va co quy trinh don gian.</p>"
            "<h2>Nhom lua chon phu hop cho team da co quy trinh</h2><p>Can uu tien kha nang tich hop, phan quyen va bao tri lau dai.</p>"
            "<h2>Sai lam khi chon cong cu</h2><p>De bi hap dan boi tinh nang nhieu nhung bo qua workflow thuc te cua team la sai lam rat pho bien.</p>"
            "<h2>Cach shortlist nhanh</h2><ol><li>Loc theo muc tieu.</li><li>Bo cac lua chon vuot budget.</li><li>Test tren use case nho.</li></ol>"
            "<h2>Cau hoi thuong gap</h2><h3>Co nen chon cong cu tot nhat theo review khong?</h3><p>Khong. Nen chon cong cu phu hop nhat voi workflow va rang buoc cua ban.</p>"
            "<h2>Ket luan</h2><p>Mot roundup tot khong ket luan thay nguoi doc, ma giup ho shortlist nhanh hon va giam rui ro chon sai.</p>"
        )
        return {
            "title": title,
            "slug": slugify(keyword_plain),
            "meta_description": meta_description,
            "excerpt": excerpt,
            "content_html": content_html,
        }

    def _build_vi_expert_guide_fallback(self, keyword_plain: str, keyword_html: str) -> dict:
        title = f"{keyword_plain.capitalize()}: Huong dan danh gia va ung dung thuc te"
        meta_description = (
            f"Phan tich {keyword_plain} theo goc nhin thuc te: nen dung khi nao, can tranh dieu gi va cach danh gia cho du an."
        )
        excerpt = (
            f"Bai viet tong hop cac diem can biet ve {keyword_plain} theo kieu guide SEO co cau truc ro rang. "
            f"Noi dung tap trung vao cach danh gia, tinh huong ap dung va nhung sai lam de gap."
        )
        content_html = ensure_html_structure(
            f"<p>{keyword_html} khong nen duoc danh gia bang cam tinh hoac theo phong trao. Trong thuc te, chat luong lua chon phu thuoc vao bai toan nghiep vu, toc do trien khai, ky nang team va muc tieu van hanh dai han.</p>"
            f"<p>Bai viet nay tong hop theo huong article SEO: co tong quan, checklist danh gia, tinh huong ap dung, sai lam pho bien va cau hoi thuong gap de ban nhanh chong ra quyet dinh voi chu de {keyword_html}.</p>"
            "<h2>Tong quan ve chu de</h2>"
            f"<p>Neu ban dang tim hieu {keyword_html}, dieu quan trong nhat khong phai la no co hot hay khong ma la no co giai quyet dung nhu cau hay khong. Day la cach tiep can giam nhieu quyet dinh sai trong giai doan MVP va scale.</p>"
            "<h3>Tieu chi danh gia nhanh</h3>"
            "<ul><li>Muc tieu nghiep vu va pham vi san pham.</li><li>Do phuc tap ky thuat va toc do giao hang mong muon.</li><li>Nang luc hien tai cua team phat trien va van hanh.</li><li>Yeu cau bao tri, mo rong va toi uu hieu nang.</li></ul>"
            "<h2>Khi nao nen ap dung</h2>"
            f"<p>{keyword_html} thuong phu hop khi ban can dua san pham ra nhanh, muon giam overhead va uu tien cau truc don gian de kiem chung gia thuyet. Nhung du an co yeu cau ro, pham vi vua phai va doi ngu da quen cong nghe se tan dung duoc loi the nay tot nhat.</p>"
            "<h2>Nhung rui ro va sai lam de gap</h2>"
            f"<p>Sai lam pho bien khi danh gia {keyword_html} la chi nhin vao trend, benchmark mot chieu hoac danh dong cong nghe voi nang luc team. Cach lam nay de dan den quyet dinh nghe co ve hien dai nhung lai tang chi phi hoc, chi phi bao tri va do phuc tap van hanh.</p>"
            "<h2>Checklist de danh gia trong du an thuc te</h2>"
            "<ul><li>Co the release nhanh ma khong can qua nhieu boilerplate.</li><li>Phu hop voi skill hien tai cua team.</li><li>Chi phi maintain chap nhan duoc sau 6-12 thang.</li><li>Khong tao kho khan khi scale hoac tich hop ve sau.</li></ul>"
            "<h2>Vi du minh hoa</h2>"
            "<pre><code>project_goal = {\n  \"time_to_market\": \"fast\",\n  \"team_experience\": \"medium\",\n  \"maintenance_priority\": \"high\"\n}\n</code></pre>"
            "<h2>Cau hoi thuong gap</h2>"
            f"<h3>{keyword_html} co phu hop cho nguoi moi khong?</h3><p>Co, neu nguoi hoc can mot boi canh ro rang, pham vi hieu biet vua phai va co tai lieu de thuc hanh.</p>"
            "<h2>Ket luan</h2>"
            f"<p>{keyword_html} co tot hay khong phu thuoc vao bai toan, khong phai vao nhan dinh tuyet doi. Cach tiep can dung la dua tren checklist, rang buoc va toc do giao hang thay vi danh gia theo cam tinh.</p>"
        )
        return {
            "title": title,
            "slug": slugify(keyword_plain),
            "meta_description": meta_description,
            "excerpt": excerpt,
            "content_html": content_html,
        }

    def _build_en_generic_fallback(self, keyword_plain: str, keyword_html: str) -> dict:
        title = f"{keyword_plain.title()}: Practical Guide, Use Cases, And Trade-Offs"
        meta_description = (
            f"A practical guide to {keyword_plain}: when it fits, where it fails, and how to evaluate it for real projects."
        )
        excerpt = (
            f"A structured SEO-style article covering evaluation criteria, trade-offs, practical use cases, and common mistakes around {keyword_plain}."
        )
        content_html = ensure_html_structure(
            f"<p>{keyword_html} should be evaluated against product scope, delivery speed, team skill level, and maintenance cost rather than hype or personal preference.</p>"
            f"<p>This article follows a practical SEO article structure with overview, evaluation criteria, mistakes to avoid, examples, FAQs, and a conclusion for {keyword_html}.</p>"
            "<h2>Overview</h2>"
            f"<p>{keyword_html} can still be a strong choice when matched to the right problem. The real question is whether it improves delivery quality without adding unnecessary complexity.</p>"
            "<h2>When It Fits Best</h2>"
            "<p>It works well for lightweight systems, fast MVP delivery, and projects where flexibility and low overhead matter more than a batteries-included stack.</p>"
            "<h2>Common Risks And Mistakes</h2>"
            "<p>A common mistake is choosing tools based on trend signals instead of operational constraints, maintenance needs, and team readiness.</p>"
            "<h2>Evaluation Checklist</h2>"
            "<ul><li>Fast enough to ship with your current team.</li><li>Easy to maintain after initial release.</li><li>Reasonable path for scaling and integration.</li></ul>"
            "<h2>Example</h2>"
            "<pre><code>decision = {\n  \"delivery_speed\": \"high\",\n  \"team_fit\": \"good\",\n  \"operational_risk\": \"acceptable\"\n}\n</code></pre>"
            "<h2>FAQ</h2>"
            f"<h3>Is {keyword_html} good for beginners?</h3><p>Yes, if the learning path is tied to concrete use cases and not just abstract syntax.</p>"
            f"<h3>When should you switch away from {keyword_html}?</h3><p>When operational complexity, scale requirements, or architecture constraints outweigh the benefits it currently provides.</p>"
            "<h2>Conclusion</h2>"
            "<p>The best choice is the one that matches your system constraints, team capability, and delivery goals with the least unnecessary complexity.</p>"
        )
        return {
            "title": title,
            "slug": slugify(keyword_plain),
            "meta_description": meta_description,
            "excerpt": excerpt,
            "content_html": content_html,
        }

    def _resolve_model_name(self) -> str:
        global _MODEL_CACHE_KEY, _MODEL_CACHE_VALUE

        configured = self.settings.gemini_model.strip()
        candidate_config = configured.replace("models/", "")

        if _MODEL_CACHE_KEY == candidate_config and _MODEL_CACHE_VALUE:
            return _MODEL_CACHE_VALUE

        preferred = [
            candidate_config,
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
            "gemini-1.5-flash-8b",
            "gemini-1.5-pro",
        ]

        try:
            available = list(genai.list_models())
            compatible = {
                m.name.replace("models/", "")
                for m in available
                if "generateContent" in getattr(m, "supported_generation_methods", [])
            }
            logger.info("Gemini compatible models found: %s", sorted(compatible))
            for name in preferred:
                if name in compatible:
                    _MODEL_CACHE_KEY = candidate_config
                    _MODEL_CACHE_VALUE = name
                    return name
            if compatible:
                resolved = sorted(compatible)[0]
                _MODEL_CACHE_KEY = candidate_config
                _MODEL_CACHE_VALUE = resolved
                return resolved
        except Exception:
            logger.exception("Could not list Gemini models, using configured model")

        _MODEL_CACHE_KEY = candidate_config
        _MODEL_CACHE_VALUE = candidate_config
        return candidate_config

    def _build_gemini_prompt(self, keyword: str, language: str, tone: str, intent: ArticleIntent) -> str:
        template = _prompt_template(intent)
        rendered = _render_prompt(template, keyword=keyword, language=language, tone=tone)
        schema_instruction = """
Return exactly one JSON object and nothing else.
Do not wrap the JSON in markdown fences.
Required JSON fields:
- title: string
- slug: string
- meta_description: string
- excerpt: string
- content_html: string
The content_html must contain valid semantic HTML with headings, paragraphs, and at least one FAQ section.
""".strip()
        return f"{rendered}\n\n{schema_instruction}"

    def _fallback_with_illustrations(self, keyword: str, language: str, tone: str, intent: ArticleIntent) -> dict:
        payload = self._build_local_fallback(keyword, language, tone, intent)
        payload["content_html"] = inject_illustrations(payload["content_html"], keyword, intent, language)
        payload["content_html"] = enrich_seo_links(
            payload["content_html"],
            keyword=keyword,
            language=language,
            base_url=self.settings.wordpress_base_url,
        )
        return payload

    def _save_raw_response_debug(
        self,
        *,
        keyword: str,
        intent: ArticleIntent,
        model_name: str,
        prompt: str,
        raw_text: str,
        status: str,
        error: str | None = None,
    ) -> None:
        """Persist a compact debug trail to inspect model formatting failures."""
        try:
            RAW_DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            row = {
                "ts": datetime.now(UTC).isoformat(),
                "keyword": keyword,
                "intent": intent.value,
                "model": model_name,
                "status": status,
                "error": (error or "")[:300],
                "prompt_preview": prompt[:1200],
                "raw_preview": raw_text[:2000],
                "raw_len": len(raw_text),
            }
            with RAW_DEBUG_LOG_FILE.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("Could not save Gemini raw debug payload")

    def generate_article(self, keyword: str, language: str, tone: str) -> dict:
        global _GEMINI_BACKOFF_UNTIL

        intent = detect_article_intent(keyword)
        logger.info("generate_article keyword=%r language=%r tone=%r intent=%s", keyword, language, tone, intent.value)

        if not self.settings.gemini_api_key:
            logger.warning("Gemini API key missing, using fallback")
            return self._fallback_with_illustrations(keyword, language, tone, intent)

        now = datetime.now(UTC)
        if _GEMINI_BACKOFF_UNTIL and now < _GEMINI_BACKOFF_UNTIL:
            logger.warning("Gemini backoff active until %s, using fallback", _GEMINI_BACKOFF_UNTIL.isoformat())
            return self._fallback_with_illustrations(keyword, language, tone, intent)

        try:
            genai.configure(api_key=self.settings.gemini_api_key)

            primary_model = self._resolve_model_name()
            logger.info("Resolved Gemini model: %s", primary_model)

            prompt = self._build_gemini_prompt(keyword, language, tone, intent)
            logger.debug("Gemini prompt length=%d", len(prompt))

            last_exc: Exception | None = None
            model_name = primary_model
            raw_text = ""
            payload: dict | None = None

            candidates = _candidate_models(primary_model)
            for index, candidate_model in enumerate(candidates):
                model_name = candidate_model
                try:
                    model = genai.GenerativeModel(candidate_model)
                    response = model.generate_content(
                        prompt,
                        generation_config={
                            "response_mime_type": "application/json",
                            "temperature": 0.6,
                        },
                    )
                    raw_text = _extract_text_from_response(response)
                    logger.debug("Gemini raw response preview=%s", raw_text[:1200])

                    payload = _extract_json_block(raw_text)
                    break
                except Exception as exc:
                    last_exc = exc
                    if (_is_quota_error(exc) or _is_model_not_found_error(exc)) and index < len(candidates) - 1:
                        logger.warning(
                            "Model %s failed with retryable error (%s); trying fallback model",
                            candidate_model,
                            type(exc).__name__,
                        )
                        continue
                    raise

            if payload is None:
                if last_exc:
                    raise last_exc
                raise RuntimeError("Gemini returned empty payload")

            payload = _validate_payload(payload, keyword)
            payload["content_html"] = inject_illustrations(payload["content_html"], keyword, intent, language)
            payload["content_html"] = enrich_seo_links(
                payload["content_html"],
                keyword=keyword,
                language=language,
                base_url=self.settings.wordpress_base_url,
            )
            self._save_raw_response_debug(
                keyword=keyword,
                intent=intent,
                model_name=model_name,
                prompt=prompt,
                raw_text=raw_text,
                status="success",
            )

            _GEMINI_BACKOFF_UNTIL = None
            logger.info("Gemini article generation succeeded for keyword=%r", keyword)
            return payload
        except Exception as exc:
            logger.exception("Gemini generation failed: %r", exc)
            if _is_quota_error(exc):
                _GEMINI_BACKOFF_UNTIL = datetime.now(UTC) + timedelta(minutes=15)
                logger.warning("Gemini quota/rate-limit detected; activating backoff until %s", _GEMINI_BACKOFF_UNTIL.isoformat())
            # Store a compact trace for investigating prompt/model formatting failures.
            self._save_raw_response_debug(
                keyword=keyword,
                intent=intent,
                model_name=self.settings.gemini_model,
                prompt=locals().get("prompt", ""),
                raw_text=locals().get("raw_text", ""),
                status="error",
                error=str(exc),
            )
            if self.settings.gemini_strict_errors:
                raise RuntimeError(f"Gemini failed: {exc}")
            logger.warning("Gemini failed, fallback content will be used")
            return self._fallback_with_illustrations(keyword, language, tone, intent)

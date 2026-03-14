import re
import unicodedata


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    clean = re.sub(r"[^a-zA-Z0-9\s-]", "", ascii_text).strip().lower()
    return re.sub(r"[-\s]+", "-", clean) or "untitled"

from googletrans import Translator

_translator = Translator()

def translate_text_vi(text: str) -> str:
    """Dịch text sang tiếng Việt."""
    if not text or text.strip() == "":
        return text
    try:
        result = _translator.translate(text, dest="vi")
        return result.text
    except Exception:
        return text
from enum import StrEnum
import re
import unicodedata


class ArticleIntent(StrEnum):
    INTERVIEW_CHECKLIST = "interview_checklist"
    COMPARISON = "comparison"
    TUTORIAL = "tutorial"
    TOOL_ROUNDUP = "tool_roundup"
    EXPERT_GUIDE = "expert_guide"


def normalize_keyword(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower()
    return re.sub(r"\s+", " ", lowered).strip()


def detect_article_intent(keyword: str) -> ArticleIntent:
    normalized = f" {normalize_keyword(keyword)} "

    interview_markers = [" phong van ", " interview ", " cau hoi ", " checklist ", " on tap "]
    comparison_markers = [" vs ", " so sanh ", " khac nhau ", " nen chon ", " hay la ", " tot hon "]
    tutorial_markers = [" huong dan ", " how to ", " la gi ", " roadmap ", " cho nguoi moi ", " tutorial ", " cach "]
    roundup_markers = [" top ", " best ", " tot nhat ", " cong cu ", " tool ", " plugin ", " phan mem "]

    if any(marker in normalized for marker in interview_markers):
        return ArticleIntent.INTERVIEW_CHECKLIST
    if any(marker in normalized for marker in comparison_markers):
        return ArticleIntent.COMPARISON
    if any(marker in normalized for marker in tutorial_markers):
        return ArticleIntent.TUTORIAL
    if any(marker in normalized for marker in roundup_markers):
        return ArticleIntent.TOOL_ROUNDUP
    return ArticleIntent.EXPERT_GUIDE

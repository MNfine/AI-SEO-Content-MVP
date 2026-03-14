from app.services.intent_service import ArticleIntent, detect_article_intent


def test_detect_interview_intent():
    assert detect_article_intent("phong van sql") == ArticleIntent.INTERVIEW_CHECKLIST


def test_detect_comparison_intent():
    assert detect_article_intent("fastapi vs django") == ArticleIntent.COMPARISON


def test_detect_tutorial_intent():
    assert detect_article_intent("python roadmap cho nguoi moi") == ArticleIntent.TUTORIAL


def test_detect_tool_roundup_intent():
    assert detect_article_intent("top cong cu seo ai") == ArticleIntent.TOOL_ROUNDUP


def test_detect_default_expert_guide_intent():
    assert detect_article_intent("kubernetes production strategy") == ArticleIntent.EXPERT_GUIDE

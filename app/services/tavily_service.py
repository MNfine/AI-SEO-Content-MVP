import os
import requests
from typing import List

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
TAVILY_TRENDING_URL = "https://api.tavily.com/search"


def get_trending_github_topics(limit: int = 10, period: str = "week") -> list:
    """
    Lấy danh sách repo trending từ github, dịch title/description sang tiếng Việt.
    period: year, month, week, day
    Trả về list dict: name, url, description, stars, stars_in_period, vi_title, vi_description
    """
    from app.services.github_trending_service import get_github_trending_repos
    from app.services.translate_service import translate_text_vi
    # Map period
    period_map = {
        "year": "monthly",
        "month": "monthly",
        "week": "weekly",
        "day": "daily",
    }
    trending_period = period_map.get(period, "weekly")
    repos = get_github_trending_repos(period=trending_period, limit=limit)
    topics = []
    for repo in repos:
        vi_title = translate_text_vi(repo["name"])
        vi_description = translate_text_vi(repo["description"])
        topics.append({
            "name": repo["name"],
            "url": repo["url"],
            "description": repo["description"],
            "stars": repo["stars"],
            "stars_in_period": repo["stars_in_period"],
            "vi_title": vi_title,
            "vi_description": vi_description,
        })
    return topics

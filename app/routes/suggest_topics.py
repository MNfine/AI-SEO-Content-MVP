

from fastapi import APIRouter, HTTPException, Query
from typing import Any
from app.services.tavily_service import get_trending_github_topics

router = APIRouter()

@router.get("/suggest-topics", response_model=list[Any])
def suggest_topics(
    limit: int = 10,
    period: str = Query("week", enum=["year", "month", "week", "day"]),
):
    """
    Gợi ý các repo trending trên GitHub, trả về dict gồm name, url, description, stars, stars_in_period, vi_title, vi_description.
    """
    try:
        topics = get_trending_github_topics(limit=limit, period=period)
        return topics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

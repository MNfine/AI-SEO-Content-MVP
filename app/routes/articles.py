import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.schemas import ArticleResponse, GenerateArticleRequest, PublishDraftResponse
from app.services.article_service import ArticleService
from app.services.wordpress_service import WordPressPublishError

router = APIRouter(prefix="/articles", tags=["articles"])
logger = logging.getLogger(__name__)


@router.post("/generate", response_model=ArticleResponse)
def generate_article(request: GenerateArticleRequest, db: Session = Depends(get_db)) -> ArticleResponse:
    print("=== /articles/generate HIT ===", flush=True)
    print("request =", request, flush=True)

    service = ArticleService(db)

    try:
        article = service.generate_article(request)
        print("=== GENERATE SUCCESS ===", flush=True)
        return ArticleResponse.model_validate(article)
    except HTTPException:
        print("=== HTTPException raised ===", flush=True)
        raise
    except Exception as exc:
        print("=== GENERATE ERROR ===", repr(exc), flush=True)
        logger.exception("Generate failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{article_id}/publish-draft", response_model=PublishDraftResponse)
def publish_draft(article_id: int, db: Session = Depends(get_db)) -> PublishDraftResponse:
    service = ArticleService(db)
    try:
        article = service.publish_draft(article_id)
        return PublishDraftResponse(
            id=article.id,
            status=article.status,
            wp_post_id=article.wp_post_id or "",
            message="Draft created successfully",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WordPressPublishError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Publish failed")
        raise HTTPException(status_code=500, detail="Publish failed") from exc


@router.get("", response_model=list[ArticleResponse])
def list_articles(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[ArticleResponse]:
    service = ArticleService(db)
    articles = service.list_articles(limit=limit, offset=offset)
    return [ArticleResponse.model_validate(article) for article in articles]


@router.get("/{article_id}", response_model=ArticleResponse)
def get_article(article_id: int, db: Session = Depends(get_db)) -> ArticleResponse:
    service = ArticleService(db)
    article = service.get_article(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleResponse.model_validate(article)

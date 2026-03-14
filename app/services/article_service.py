from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Article
from app.db.schemas import GenerateArticleRequest
from app.services.gemini_service import GeminiService
from app.services.slug_service import slugify
from app.services.wordpress_service import WordPressPublishError, WordPressService
from app.utils.validators import validate_keyword


class ArticleService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.gemini_service = GeminiService()
        self.wordpress_service = WordPressService()

    def generate_article(self, request: GenerateArticleRequest) -> Article:
        keyword = validate_keyword(request.keyword)
        payload = self.gemini_service.generate_article(keyword, request.language, request.tone)
        base_slug = payload.get("slug") or slugify(payload.get("title", keyword))

        article = Article(
            keyword=keyword,
            title=payload.get("title", keyword.title()),
            slug=self._make_unique_slug(base_slug),
            meta_description=payload.get("meta_description", f"Thong tin ve {keyword}"),
            excerpt=payload.get("excerpt", f"Bai viet ve {keyword}"),
            content_html=payload.get("content_html", "<p>No content</p>"),
            status="generated",
        )

        self.db.add(article)
        try:
            self.db.commit()
        except IntegrityError:
            # Handle rare race condition where another row used the same slug between check and commit.
            self.db.rollback()
            article.slug = self._make_unique_slug(base_slug)
            self.db.add(article)
            self.db.commit()
        self.db.refresh(article)
        return article

    def publish_draft(self, article_id: int) -> Article:
        article = self.db.get(Article, article_id)
        if article is None:
            raise ValueError("Article not found")

        try:
            wp_post_id = self.wordpress_service.create_draft(
                title=article.title,
                content_html=article.content_html,
                excerpt=article.excerpt,
                slug=article.slug,
                meta_description=article.meta_description,
            )
        except WordPressPublishError as exc:
            article.status = "publish_failed"
            article.error_message = str(exc)
            self.db.commit()
            raise

        article.wp_post_id = wp_post_id
        article.status = "drafted"
        article.error_message = None
        self.db.commit()
        self.db.refresh(article)
        return article

    def list_articles(self, limit: int = 20, offset: int = 0) -> list[Article]:
        return self.db.query(Article).order_by(Article.created_at.desc()).offset(offset).limit(limit).all()

    def get_article(self, article_id: int) -> Article | None:
        return self.db.get(Article, article_id)

    def _make_unique_slug(self, base_slug: str) -> str:
        normalized = slugify(base_slug)
        if not self._slug_exists(normalized):
            return normalized

        suffix = 2
        while True:
            candidate = f"{normalized}-{suffix}"
            if not self._slug_exists(candidate):
                return candidate
            suffix += 1

    def _slug_exists(self, slug: str) -> bool:
        stmt = select(Article.id).where(Article.slug == slug).limit(1)
        return self.db.execute(stmt).scalar_one_or_none() is not None

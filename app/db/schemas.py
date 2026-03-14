from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GenerateArticleRequest(BaseModel):
    keyword: str = Field(min_length=3, max_length=255)
    language: str = Field(default="vi", min_length=2, max_length=10)
    tone: str = Field(default="professional", min_length=2, max_length=30)


class ArticleBase(BaseModel):
    keyword: str
    title: str
    slug: str
    meta_description: str
    excerpt: str
    content_html: str
    status: str
    wp_post_id: str | None = None
    error_message: str | None = None


class ArticleResponse(ArticleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PublishDraftResponse(BaseModel):
    id: int
    status: str
    wp_post_id: str
    message: str

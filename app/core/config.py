from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    database_url: str = Field(default="sqlite:///./ai_seo_content.db", alias="DATABASE_URL")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-1.5-flash", alias="GEMINI_MODEL")
    gemini_strict_errors: bool = Field(default=False, alias="GEMINI_STRICT_ERRORS")
    wordpress_base_url: str | None = Field(default=None, alias="WORDPRESS_BASE_URL")
    wordpress_username: str | None = Field(default=None, alias="WORDPRESS_USERNAME")
    wordpress_app_password: str | None = Field(default=None, alias="WORDPRESS_APP_PASSWORD")
    wordpress_mock_publish: bool = Field(default=True, alias="WORDPRESS_MOCK_PUBLISH")
    request_timeout: int = Field(default=30, alias="REQUEST_TIMEOUT")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

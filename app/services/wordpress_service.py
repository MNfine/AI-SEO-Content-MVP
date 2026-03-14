from uuid import uuid4

from requests.auth import HTTPBasicAuth
import requests

from app.core.config import get_settings


class WordPressPublishError(Exception):
    pass


class WordPressService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "AI-SEO-Content-MVP/0.1",
        }

    @staticmethod
    def _extract_error_message(response: requests.Response) -> str:
        try:
            body = response.json()
            message = body.get("message") or body.get("code") or response.text
            return f"WordPress publish failed ({response.status_code}): {message}"
        except ValueError:
            return f"WordPress publish failed ({response.status_code}): {response.text or response.reason}"

    def _post_draft(self, endpoint: str, payload: dict) -> requests.Response:
        try:
            return requests.post(
                endpoint,
                json=payload,
                headers=self.headers,
                auth=HTTPBasicAuth(self.settings.wordpress_username, self.settings.wordpress_app_password),
                timeout=self.settings.request_timeout,
            )
        except requests.RequestException as exc:
            raise WordPressPublishError(f"WordPress connection failed: {exc}") from exc

    def create_draft(self, title: str, content_html: str, excerpt: str, slug: str, meta_description: str) -> str:
        has_connection = bool(self.settings.wordpress_base_url)
        has_credentials = bool(self.settings.wordpress_username and self.settings.wordpress_app_password)

        if not has_connection or not has_credentials:
            if self.settings.wordpress_mock_publish:
                return f"local-draft-{uuid4().hex[:8]}"
            raise ValueError(
                "Missing WordPress configuration. Set WORDPRESS_BASE_URL, WORDPRESS_USERNAME, "
                "WORDPRESS_APP_PASSWORD or enable WORDPRESS_MOCK_PUBLISH=true"
            )

        endpoint = f"{self.settings.wordpress_base_url.rstrip('/')}/wp-json/wp/v2/posts"
        payload = {
            "title": title,
            "content": content_html,
            "excerpt": excerpt,
            "slug": slug,
            "status": "draft",
            "meta": {"_aioseo_description": meta_description},
        }
        response = self._post_draft(endpoint, payload)
        if response.status_code in {401, 403}:
            # Some WordPress installs reject custom meta writes via REST even when post creation is allowed.
            retry_payload = {key: value for key, value in payload.items() if key != "meta"}
            retry_response = self._post_draft(endpoint, retry_payload)
            if retry_response.ok:
                body = retry_response.json()
                return str(body["id"])
            raise WordPressPublishError(self._extract_error_message(retry_response))
        if not response.ok:
            raise WordPressPublishError(self._extract_error_message(response))
        body = response.json()
        return str(body["id"])

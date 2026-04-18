
# AI SEO Content MVP

Dự án MVP tạo bài viết SEO bằng AI, lưu vào cơ sở dữ liệu và đẩy lên WordPress ở trạng thái nháp.

## Tính năng nổi bật
- Gợi ý chủ đề hot (trending) lấy trực tiếp từ GitHub Trending, có số sao tăng, mô tả repo, dịch mô tả sang tiếng Việt.
- UI hiển thị loading khi tải chủ đề gợi ý, chọn nhanh chủ đề để sinh bài viết.
- Khi sinh bài viết, trending_topics chỉ gửi tên repo (không gửi object).
- Tên repo giữ nguyên, chỉ dịch phần mô tả (description).
- POST `/articles/generate`: nhận keyword và sinh nội dung bài viết
- POST `/articles/{id}/publish-draft`: đẩy bài viết lên WordPress dạng draft
- GET `/articles`: danh sách bài viết
- GET `/articles/{id}`: chi tiết bài viết
- GET `/health`: health check
- GET `/`: giao diện nhỏ để generate và publish trực tiếp
- Sinh 2-3 ảnh minh họa SVG theo chủ đề (ưu tiên Gemini, có fallback local)
- Tự động bổ sung internal links từ kho link có sẵn theo danh mục (không tạo link nội bộ ảo)

## Công nghệ sử dụng
- FastAPI
- SQLAlchemy + SQLite
- Gemini API (có sinh nội dung mẫu nếu chưa cấu hình key)
- WordPress REST API

## Cấu trúc thư mục
```text
app/
  main.py
  core/
    config.py
    logging_config.py
  db/
    database.py
    models.py
    schemas.py
  routes/
    articles.py
    suggest_topics.py
  services/
    gemini_service.py
    article_service.py
    wordpress_service.py
    slug_service.py
    tavily_service.py
    github_trending_service.py
    translate_service.py
  prompts/
    article_prompt.txt
  utils/
    html_formatter.py
    validators.py
  tests/
    conftest.py
    test_generate.py
    test_publish.py
.env.example
requirements.txt
README.md
```

## Cài đặt
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Biến môi trường
- `APP_ENV`
- `DATABASE_URL`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `WORDPRESS_BASE_URL`
- `WORDPRESS_USERNAME`
- `WORDPRESS_APP_PASSWORD`
- `WORDPRESS_MOCK_PUBLISH` (mặc định `true` cho demo local)
- `REQUEST_TIMEOUT`

## Quản lý Internal Links (liên kết nội bộ)
- File link nội bộ: `app/data/internal_links.json`
- File template câu gợi ý internal link: `app/data/internal_link_templates.json`
- Danh mục hiện tại: `Backend`, `Frontend`, `Career`, `AI-ML`, `Database`
- Hệ thống chỉ lấy internal link từ file này để gắn vào bài viết.
- Nếu cần cập nhật link, chỉ sửa file JSON trên, không cần sửa code.
- Team content có thể chỉnh nhiều mẫu câu trong file template JSON mà không cần sửa code.
- Trong file template có thể tùy biến theo:
  - `vi`: mẫu câu tiếng Việt chung
  - `vi_by_category`: mẫu câu theo từng danh mục (Backend/Frontend/...)
  - `vi_intent_context`: tiền tố theo intent bài viết (phỏng vấn, tutorial, so sánh...)

Nếu chưa có tài khoản WordPress, giữ `WORDPRESS_MOCK_PUBLISH=true` để vẫn test được toàn bộ luồng publish.
Khi có WordPress thật, đặt `WORDPRESS_MOCK_PUBLISH=false` và điền đầy đủ 3 biến WordPress.

## Chạy ứng dụng
```bash
uvicorn app.main:app --reload
```

Truy cập Swagger: `http://127.0.0.1:8000/docs`
Truy cập giao diện: `http://127.0.0.1:8000/`

## API nhanh
### Generate
```http
POST /articles/generate
Content-Type: application/json

{
  "keyword": "fastapi vs django",
  "language": "vi",
  "tone": "professional",
  "trending_topics": ["repo1", "repo2", ...] // chỉ gửi tên repo, không gửi object
}
```

### Lưu ý UI
- Chủ đề gợi ý sẽ hiển thị tên repo (giữ nguyên), mô tả đã dịch, số sao tăng, link repo.
- Khi chọn chủ đề, chỉ tên repo được đưa vào ô keyword.
- Có hiệu ứng loading khi đang tải chủ đề trending.

### Đăng draft lên WordPress
```http
POST /articles/1/publish-draft
```

## Chạy test
```bash
pytest -q
```

## Debug Gemini
- Khi Gemini trả về output sai format JSON, hệ thống sẽ tự động fallback (nếu `GEMINI_STRICT_ERRORS=false`).
- Raw response rút gọn được lưu tại: `logs/gemini_raw_responses.jsonl` để debug prompt/model.

## Ghi chú bảo mật
- Không commit file `.env`
- Dùng WordPress Application Password
- Không ghi log chứa thông tin bí mật

# AI SEO Content MVP

FastAPI MVP de tao bai SEO bang AI, luu database va day len WordPress o trang thai Draft.

## Tinh nang trong MVP
- POST `/articles/generate`: nhan keyword va sinh noi dung bai viet
- POST `/articles/{id}/publish-draft`: day bai viet len WordPress dang draft
- GET `/articles`: danh sach bai viet
- GET `/articles/{id}`: chi tiet bai viet
- GET `/health`: health check
- GET `/`: giao dien nho de generate va publish truc tiep
- Sinh 2-3 anh minh hoa SVG theo chu de (uu tien Gemini, co fallback local)
- Tu dong bo sung internal links tu kho link co san theo danh muc (khong tao link noi bo ao)

## Cong nghe
- FastAPI
- SQLAlchemy + SQLite
- Gemini API (co fallback noi dung mau neu chua set key)
- WordPress REST API

## Cau truc thu muc
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
  services/
    gemini_service.py
    article_service.py
    wordpress_service.py
    slug_service.py
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

## Cai dat
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Bien moi truong
- `APP_ENV`
- `DATABASE_URL`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `WORDPRESS_BASE_URL`
- `WORDPRESS_USERNAME`
- `WORDPRESS_APP_PASSWORD`
- `WORDPRESS_MOCK_PUBLISH` (mac dinh `true` cho local demo)
- `REQUEST_TIMEOUT`

## Quan ly Internal Links
- File link noi bo: `app/data/internal_links.json`
- File template cau goi y internal link: `app/data/internal_link_templates.json`
- Danh muc hien tai: `Backend`, `Frontend`, `Career`, `AI-ML`, `Database`
- He thong chi lay internal link tu file nay de gan vao bai viet.
- Neu can cap nhat link, chi sua file JSON tren, khong can sua code.
- Team content co the chinh 7+ mau cau trong file template JSON ma khong can sua code.

Neu chua co WordPress credentials, giu `WORDPRESS_MOCK_PUBLISH=true` de van test full flow publish.
Khi co WordPress that, dat `WORDPRESS_MOCK_PUBLISH=false` va dien day du 3 bien WordPress.

## Chay ung dung
```bash
uvicorn app.main:app --reload
```

Truy cap Swagger: `http://127.0.0.1:8000/docs`
Truy cap giao dien: `http://127.0.0.1:8000/`

## API nhanh
### Generate
```http
POST /articles/generate
Content-Type: application/json

{
  "keyword": "fastapi vs django",
  "language": "vi",
  "tone": "professional"
}
```

### Publish Draft
```http
POST /articles/1/publish-draft
```

## Chay test
```bash
pytest -q
```

## Debug Gemini
- Khi Gemini tra ve output sai format JSON, he thong se fallback (neu `GEMINI_STRICT_ERRORS=false`).
- Raw response rut gon duoc luu tai: `logs/gemini_raw_responses.jsonl` de debug prompt/model.

## Ghi chu bao mat
- Khong commit file `.env`
- Dung WordPress Application Password
- Khong ghi log secret

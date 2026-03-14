from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.core.logging_config import setup_logging
from app.db.database import Base, engine
from app.routes.articles import router as article_router

setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="AI SEO Content MVP", version="0.1.0", lifespan=lifespan)
FRONTEND_INDEX = Path(__file__).resolve().parent / "frontend" / "index.html"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def frontend() -> FileResponse:
    return FileResponse(FRONTEND_INDEX)


app.include_router(article_router)

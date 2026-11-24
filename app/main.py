# -*- coding: utf-8 -*-
"""FastAPI-приложение обёртки над Keitaro.

Поднимает REST API и раздаёт статический фронт. Миграции накатываются
при старте, чтобы `uvicorn app.main:app` работал из коробки.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app import services
from app.config import Settings, get_settings
from app.db import get_db
from app.kt import KeitaroClient, KtError
from app.schemas import CampaignCreateIn, StreamOffersIn

log = logging.getLogger(__name__)
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _run_migrations()
    settings = get_settings()
    if settings.kt_api_key:
        client = KeitaroClient(settings)
        try:
            with next(get_db()) as db:
                services.refresh_offer_cache(db, client)
        except Exception as exc:  # каталог подтянем позже по кнопке
            log.warning("Не удалось обновить каталог офферов при старте: %s", exc)
        finally:
            client.close()
    yield


app = FastAPI(title="Adrobot Keitaro Wrapper", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


def get_kt_client() -> KeitaroClient:
    client = KeitaroClient(get_settings())
    try:
        yield client
    finally:
        client.close()


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.exception_handler(KtError)
def kt_error_handler(request, exc: KtError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": {"error": "keitaro", "message": exc.message}},
    )


# -- создаватор ---------------------------------------------------------------

@app.post("/api/campaigns")
def create_campaign(
    body: CampaignCreateIn,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_kt_client),
) -> dict:
    return services.create_campaign(db, client, get_settings(), body)


# -- редактор -----------------------------------------------------------------

@app.get("/api/campaigns")
def list_campaigns(client: KeitaroClient = Depends(get_kt_client)) -> list[dict]:
    return client.campaigns()


@app.get("/api/campaigns/{campaign_id}")
def campaign_view(
    campaign_id: int,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_kt_client),
) -> dict:
    return services.campaign_view(db, client, get_settings(), campaign_id)


@app.put("/api/streams/{stream_id}/offers")
def save_stream_offers(
    stream_id: int,
    body: StreamOffersIn,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_kt_client),
) -> dict:
    offer_ids = [item.offer_id for item in body.offers]
    return services.apply_stream_offers(db, client, stream_id, offer_ids)


# -- каталог офферов ------------------------------------------------------------

@app.get("/api/catalog")
def catalog(db: Session = Depends(get_db)) -> list[dict]:
    return services.catalog(db)


@app.post("/api/catalog/refresh")
def refresh_catalog(
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_kt_client),
) -> dict:
    return services.refresh_offer_cache(db, client)

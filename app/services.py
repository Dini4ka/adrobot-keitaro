# -*- coding: utf-8 -*-
"""Бизнес-логика: создаватор кампаний и редактор офферов.

Обёртка ходит в Keitaro как в настоящий трекер: читает справочники,
создаёт кампанию и потоки, а состав офферов меняет через PUT /streams/{id}.
Локальная БД хранит реестр созданных кампаний и кэш имён офферов.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import Settings
from app.kt import KeitaroClient, KtError
from app.weights import normalize_shares

log = logging.getLogger(__name__)


def build_client() -> KeitaroClient:
    return KeitaroClient(Settings())


# ---------------------------------------------------------------------------
# Создаватор кампаний
# ---------------------------------------------------------------------------

def _pick_active(items: list[dict], prefer_name: str | None = None) -> dict:
    """Первый активный элемент справочника; если задано prefer_name —
    сначала ищем по имени, потом любой активный, потом первый."""
    active = [item for item in items if item.get("state", "active") == "active"]
    pool = active or items
    if prefer_name:
        for item in pool:
            if item.get("name") == prefer_name:
                return item
    return pool[0]


def _resolve_references(client: KeitaroClient) -> dict:
    """Домен, группа и источник для новой кампании из справочников Keitaro."""
    domains = client.domains()
    groups = client.groups("campaigns")
    sources = client.traffic_sources()
    if not domains or not groups or not sources:
        raise KtError(502, "На стенде пусты справочники: домены, группы или источники")
    domain = _pick_active(domains)
    group = groups[0]
    source = _pick_active(sources, prefer_name="FORTESTS")
    return {
        "domain": domain,
        "group": group,
        "source": source,
    }


def create_campaign(db: Session, client: KeitaroClient, settings: Settings,
                    data: "object") -> dict:
    """Создать кампанию с двумя потоками по правилам задания.

    Flow 1 (regular, redirect): ловит указанную страну и редиректит на Google.
    Flow 2 (default, landings): отдаёт трафик выбранному офферу с долей 100%.
    """
    from app.schemas import CampaignCreateIn  # локальный импорт ради тестов

    payload = data if isinstance(data, CampaignCreateIn) else CampaignCreateIn(**data)

    # Оффер должен существовать в каталоге стенда.
    try:
        client.offer(payload.offer_id)
    except KtError as exc:
        raise KtError(exc.status, f"Оффер {payload.offer_id} не найден в Keitaro") from exc

    refs = _resolve_references(client)
    full_name = f"test_{settings.candidate_prefix}_{payload.name}"

    campaign = client.create_campaign({
        "name": full_name,
        "type": "position",
        "domain_id": refs["domain"]["id"],
        "group_id": refs["group"]["id"],
        "traffic_source_id": refs["source"]["id"],
    })
    campaign_id = int(campaign["id"])

    geo_flow = client.create_stream({
        "campaign_id": campaign_id,
        "name": f"Geo {payload.geo}",
        "type": "regular",
        "schema": "redirect",
        "action_type": "http",
        "action_payload": settings.google_url,
        "filters": [{"name": "country", "mode": "accept", "payload": [payload.geo]}],
    })

    offers_flow = client.create_stream({
        "campaign_id": campaign_id,
        "name": "Offers",
        "type": "default",
        "schema": "landings",
        "offers": normalize_shares([payload.offer_id]),
    })

    # Локальный реестр: что создано, где офферный поток.
    db_campaign = models.Campaign(
        id=campaign_id,
        name=full_name,
        alias=campaign.get("alias"),
        domain_id=refs["domain"]["id"],
        group_id=refs["group"]["id"],
        traffic_source_id=refs["source"]["id"],
    )
    db.add(db_campaign)
    db.add(models.Stream(
        id=int(geo_flow["id"]), campaign_id=campaign_id,
        name=geo_flow.get("name", ""), type="regular", schema="redirect",
        position=1, is_offer_stream=False,
    ))
    db.add(models.Stream(
        id=int(offers_flow["id"]), campaign_id=campaign_id,
        name=offers_flow.get("name", ""), type="default", schema="landings",
        position=2, is_offer_stream=True,
    ))
    for sort, binding in enumerate(normalize_shares([payload.offer_id])):
        db.add(models.OfferBinding(
            stream_id=int(offers_flow["id"]), offer_id=binding["offer_id"],
            share=binding["share"], state=binding["state"], sort=sort,
        ))
    db.commit()

    return {
        "id": campaign_id,
        "name": full_name,
        "geo": payload.geo,
        "domain": refs["domain"],
        "group": refs["group"],
        "source": refs["source"],
        "streams": [geo_flow, offers_flow],
        "admin_url": f"{settings.kt_admin_url}#!/campaign.editor/{campaign_id}",
    }


# ---------------------------------------------------------------------------
# Редактор офферов
# ---------------------------------------------------------------------------

def _offer_name(db: Session, offer_id: int) -> str | None:
    row = db.get(models.OfferCache, offer_id)
    return row.name if row else None


def campaign_view(db: Session, client: KeitaroClient, settings: Settings,
                  campaign_id: int) -> dict:
    """Кампания со стенда + потоки с именами офферов из кэша."""
    campaign = client.campaign(campaign_id)
    streams = client.campaign_streams(campaign_id)
    enriched = []
    for stream in streams:
        offers = []
        for binding in stream.get("offers") or []:
            offer_id = int(binding["offer_id"])
            offers.append({
                "offer_id": offer_id,
                "share": int(binding.get("share", 0)),
                "state": binding.get("state", "active"),
                "name": _offer_name(db, offer_id) or f"оффер {offer_id}",
            })
        enriched.append({
            "id": int(stream["id"]),
            "campaign_id": campaign_id,
            "name": stream.get("name", ""),
            "type": stream.get("type"),
            "schema": stream.get("schema"),
            "action_type": stream.get("action_type"),
            "action_payload": stream.get("action_payload"),
            "filters": stream.get("filters"),
            "offers": offers,
            "is_offer_stream": bool(stream.get("offers"))
                               or stream.get("schema") == "landings",
        })
    campaign["streams"] = enriched
    campaign["admin_url"] = f"{settings.kt_admin_url}#!/campaign.editor/{campaign_id}"
    return campaign


def apply_stream_offers(db: Session, client: KeitaroClient, stream_id: int,
                        offer_ids: list[int]) -> dict:
    """Сохранить новый состав офферов потока в Keitaro.

    Доли пересчитываются так, чтобы сумма была ровно 100.
    Удалённый оффер просто отсутствует в списке: PUT заменяет состав целиком.
    """
    bindings = normalize_shares(offer_ids)
    updated = client.update_stream(stream_id, {"offers": bindings})
    return {
        "stream_id": stream_id,
        "offers": [{
            "offer_id": binding["offer_id"],
            "share": binding["share"],
            "state": binding["state"],
            "name": _offer_name(db, binding["offer_id"]) or f"оффер {binding['offer_id']}",
        } for binding in normalize_shares(offer_ids)],
        "raw": updated,
    }


def refresh_offer_cache(db: Session, client: KeitaroClient) -> dict:
    """Перечитать каталог офферов стенда в локальный кэш."""
    offers = client.offers(offset=0, limit=500)
    for offer in offers:
        row = db.get(models.OfferCache, int(offer["id"]))
        if row is None:
            row = models.OfferCache(offer_id=int(offer["id"]), name=offer.get("name", ""))
            db.add(row)
        row.name = offer.get("name", "")
        row.state = offer.get("state", "active")
    db.commit()
    return {"count": len(offers)}


def catalog(db: Session) -> list[dict]:
    """Каталог офферов из кэша, активные впереди."""
    rows = db.scalars(select(models.OfferCache).order_by(models.OfferCache.name)).all()
    items = [{"offer_id": row.offer_id, "name": row.name, "state": row.state} for row in rows]
    items.sort(key=lambda item: item["state"] != "active")
    return items

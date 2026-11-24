# -*- coding: utf-8 -*-
"""Локальные модели: реестр созданных кампаний и кэш каталога офферов."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Campaign(Base):
    """Кампания, созданная через обёртку (зеркало записи в Keitaro)."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    alias: Mapped[str | None] = mapped_column(String(64))
    domain_id: Mapped[int | None] = mapped_column(Integer)
    group_id: Mapped[int | None] = mapped_column(Integer)
    traffic_source_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Stream(Base):
    """Поток кампании: какой поток офферный, чтобы редактор знал, что открывать."""

    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str | None] = mapped_column(String(32))
    schema: Mapped[str | None] = mapped_column(String(32))
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_offer_stream: Mapped[bool] = mapped_column(default=True)


class OfferBinding(Base):
    """Рабочая копия состава офферов потока на момент создания кампании."""

    __tablename__ = "offer_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id"), index=True)
    offer_id: Mapped[int] = mapped_column(Integer)
    share: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(16), default="active")
    sort: Mapped[int] = mapped_column(Integer, default=0)


class OfferCache(Base):
    """Кэш каталога офферов стенда: id -> имя, чтобы не дёргать API на каждый рендер."""

    __tablename__ = "offer_cache"

    offer_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    state: Mapped[str | None] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

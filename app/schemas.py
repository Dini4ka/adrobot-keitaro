# -*- coding: utf-8 -*-
"""Pydantic-схемы входных тел API обёртки."""
import re

from pydantic import BaseModel, Field, field_validator

GEO_RE = re.compile(r"^[A-Z]{2}$")


class CampaignCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    geo: str = Field(min_length=2, max_length=2)
    offer_id: int

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Название кампании не может быть пустым")
        return value

    @field_validator("geo")
    @classmethod
    def check_geo(cls, value: str) -> str:
        value = value.strip().upper()
        if not GEO_RE.match(value):
            raise ValueError("Гео должно быть двухбуквенным кодом страны, например RU")
        return value


class OfferShareIn(BaseModel):
    offer_id: int
    share: int = Field(ge=0, le=100)


class StreamOffersIn(BaseModel):
    offers: list[OfferShareIn] = Field(max_length=100)

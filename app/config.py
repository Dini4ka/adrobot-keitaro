# -*- coding: utf-8 -*-
"""Настройки обёртки. Всё читается из переменных окружения / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Адрес стенда Keitaro (без /admin_api/v1) и ключ из шапки админки стенда.
    kt_base_url: str = "https://keitaro-for-tests.etolegko.com"
    kt_api_key: str = ""

    # Локальная БД обёртки (SQLAlchemy URL). SQLite по умолчанию.
    database_url: str = "sqlite:///./adrobot.db"

    # Префикс названий кампаний (требование стенда: test_фамилия_...).
    candidate_prefix: str = "karelov"

    # Куда редиректит первый поток (гео -> ...). По ТЗ — Google.
    google_url: str = "https://google.com"

    # Корень админки стенда для ссылок "открыть в Keitaro".
    kt_admin_url: str = "https://keitaro-for-tests.etolegko.com/admin/"


@lru_cache
def get_settings() -> Settings:
    return Settings()

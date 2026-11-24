# -*- coding: utf-8 -*-
"""HTTP-клиент Admin API стенда Keitaro.

Адрес: {kt_base_url}/admin_api/v1, авторизация — заголовок Api-Key.
Контракт: https://admin-api.docs.keitaro.io/ (стенд повторяет его
в части, нужной для задания).
"""
import logging

import httpx

from app.config import Settings

log = logging.getLogger(__name__)


class KtError(Exception):
    """Ошибка при обращении к Keitaro: код ответа и кусок тела."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class KeitaroClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.base = settings.kt_base_url.rstrip("/") + "/admin_api/v1"
        self._client = httpx.Client(
            base_url=self.base,
            headers={"Api-Key": settings.kt_api_key, "Accept": "application/json"},
            timeout=httpx.Timeout(30.0, connect=10.0),
            transport=transport,
            follow_redirects=False,
        )

    def close(self) -> None:
        self._client.close()

    # -- низкий уровень --------------------------------------------------------

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 json: dict | list | None = None) -> dict | list:
        """GET/PUT ретраим на временных ошибках; POST не ретраим,
        чтобы не создать дубликат кампании/потока при потерянном ответе."""
        attempts = 3 if method in ("GET", "PUT") else 1
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = self._client.request(method, path, params=params, json=json)
            except httpx.TransportError as exc:
                last = exc
                log.warning("Keitaro %s %s: транспортная ошибка, попытка %d", method, path, attempt + 1)
                continue
            if resp.status_code >= 500:
                last = KtError(resp.status_code, resp.text[:300])
                log.warning("Keitaro %s %s: %s, попытка %d", method, path, resp.status_code, attempt + 1)
                continue
            if resp.status_code >= 400:
                raise KtError(resp.status_code, f"{method} {path}: {resp.text[:300]}")
            if not resp.content:
                return {}
            try:
                return resp.json()
            except ValueError as exc:
                raise KtError(502, f"Keitaro вернул не-JSON на {method} {path}") from exc
        raise KtError(503, f"Keitaro недоступен: {last}")

    # -- чтение ----------------------------------------------------------------

    def campaigns(self) -> list[dict]:
        data = self._request("GET", "campaigns", params={"limit": 100})
        return data if isinstance(data, list) else data.get("items", [])

    def campaign(self, campaign_id: int) -> dict:
        return self._request("GET", f"campaigns/{campaign_id}")

    def campaign_streams(self, campaign_id: int) -> list[dict]:
        data = self._request("GET", f"campaigns/{campaign_id}/streams")
        return data if isinstance(data, list) else data.get("items", [])

    def stream(self, stream_id: int) -> dict:
        return self._request("GET", f"streams/{stream_id}")

    def offers(self, offset: int = 0, limit: int = 500) -> list[dict]:
        data = self._request("GET", "offers", params={"offset": offset, "limit": limit})
        return data if isinstance(data, list) else data.get("items", [])

    def offer(self, offer_id: int) -> dict:
        return self._request("GET", f"offers/{offer_id}")

    def domains(self) -> list[dict]:
        data = self._request("GET", "domains")
        return data if isinstance(data, list) else []

    def groups(self, group_type: str = "campaigns") -> list[dict]:
        data = self._request("GET", "groups", params={"type": group_type})
        return data if isinstance(data, list) else []

    def traffic_sources(self) -> list[dict]:
        data = self._request("GET", "traffic_sources")
        return data if isinstance(data, list) else []

    # -- запись ----------------------------------------------------------------

    def create_campaign(self, payload: dict) -> dict:
        return self._request("POST", "campaigns", json=payload)

    def create_stream(self, payload: dict) -> dict:
        return self._request("POST", "streams", json=payload)

    def update_stream(self, stream_id: int, payload: dict) -> dict:
        return self._request("PUT", f"streams/{stream_id}", json=payload)

# -*- coding: utf-8 -*-
"""HTTP-клиент: адреса, заголовок Api-Key, ретраи, ошибки."""
import httpx
import pytest

from app.config import Settings
from app.kt import KeitaroClient, KtError

SETTINGS = Settings(
    kt_base_url="https://keitaro-for-tests.etolegko.com",
    kt_api_key="test-key",
)


def test_requests_hit_admin_api_with_key():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("Api-Key")
        return httpx.Response(200, json=[])

    client = KeitaroClient(SETTINGS, transport=httpx.MockTransport(handler))
    client.offers()
    assert seen["url"].startswith("https://keitaro-for-tests.etolegko.com/admin_api/v1/offers")
    assert seen["key"] == "test-key"


def test_get_retries_on_500():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, json=[{"id": 1}])

    client = KeitaroClient(SETTINGS, transport=httpx.MockTransport(handler))
    assert client.campaigns() == [{"id": 1}]
    assert calls["n"] == 3


def test_post_is_not_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, json={"error": "boom"})

    client = KeitaroClient(SETTINGS, transport=httpx.MockTransport(handler))
    with pytest.raises(KtError) as exc:
        client.create_campaign({"name": "x"})
    assert exc.value.status == 503
    assert calls["n"] == 1


def test_404_raises_kt_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    client = KeitaroClient(SETTINGS, transport=httpx.MockTransport(handler))
    with pytest.raises(KtError) as exc:
        client.offer(12345)
    assert exc.value.status == 404

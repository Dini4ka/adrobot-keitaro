# -*- coding: utf-8 -*-
"""API обёртки против фейкового стенда: payload-ы, гео из ввода, веса."""
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import main as app_main
from app import models
from app.config import Settings
from app.db import Base, get_db
from app.kt import KtError

TEST_SETTINGS = Settings(
    kt_base_url="https://keitaro-for-tests.etolegko.com",
    kt_api_key="test-key",
    candidate_prefix="karelov",
    kt_admin_url="https://keitaro-for-tests.etolegko.com/admin/",
    database_url="sqlite:///./test_adrobot.db",
)


class FakeKeitaro:
    """Стенд в миниатюре: повторяет Admin API в части, нужной сервисам."""

    def __init__(self):
        self.campaigns_store: dict[int, dict] = {}
        self.streams_store: dict[int, dict] = {}
        self.stream_updates: list[tuple[int, dict]] = []
        self.next_id = 200
        self.offers_list = [
            {"id": 18001, "name": "18001 Detoxin", "state": "active"},
            {"id": 18002, "name": "18002 Oxys", "state": "active"},
        ]
        self.domains_list = [{"id": 1813, "name": "kt-emulator.test", "state": "active"}]
        self.groups_list = [{"id": 10332, "name": "FORTESTS", "type": "campaigns"}]
        self.sources_list = [{"id": 836, "name": "FORTESTS", "state": "active"}]

    # чтение
    def campaigns(self):
        return list(self.campaigns_store.values())

    def campaign(self, campaign_id: int):
        if campaign_id not in self.campaigns_store:
            raise KtError(404, "not found")
        return dict(self.campaigns_store[campaign_id])

    def campaign_streams(self, campaign_id: int):
        return [dict(s) for s in self.streams_store.values()
                if s["campaign_id"] == campaign_id]

    def offers(self, offset=0, limit=500):
        return self.offers_list

    def offer(self, offer_id: int):
        for offer in self.offers_list:
            if offer["id"] == offer_id:
                return dict(offer)
        raise KtError(404, f"offer {offer_id} not found")

    def domains(self):
        return self.domains_list

    def groups(self, group_type="campaigns"):
        return self.groups_list

    def traffic_sources(self):
        return self.sources_list

    # запись
    def create_campaign(self, payload: dict):
        self.next_id += 1
        record = {**payload, "id": self.next_id}
        self.campaigns_store[self.next_id] = record
        return dict(record)

    def create_stream(self, payload: dict):
        self.next_id += 1
        record = {**payload, "id": self.next_id, "position": len(self.streams_store) + 1}
        self.streams_store[self.next_id] = record
        return dict(record)

    def update_stream(self, stream_id: int, payload: dict):
        if stream_id not in self.streams_store:
            raise KtError(404, "not found")
        self.stream_updates.append((stream_id, payload))
        record = {**self.streams_store[stream_id], **payload}
        self.streams_store[stream_id] = record
        return dict(record)


@pytest.fixture()
def fake_kt() -> FakeKeitaro:
    return FakeKeitaro()


@pytest.fixture()
def db(tmp_path) -> Generator[Session, None, None]:
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture()
def client(fake_kt: FakeKeitaro, db: Session):
    def override_kt():
        yield fake_kt

    def override_db():
        yield db

    app_main.app.dependency_overrides[app_main.get_kt_client] = override_kt
    app_main.app.dependency_overrides[get_db] = override_db
    app_main.get_settings = lambda: TEST_SETTINGS
    yield TestClient(app_main.app)
    app_main.app.dependency_overrides.clear()


def create_campaign(client, geo="by", offer_id=18001, name="campaign1"):
    return client.post("/api/campaigns", json={
        "name": name, "geo": geo, "offer_id": offer_id,
    })


def test_creator_builds_campaign_and_two_streams(client: TestClient, fake_kt: FakeKeitaro):
    resp = create_campaign(client)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["name"] == "test_karelov_campaign1"
    assert body["geo"] == "BY"
    assert body["domain"]["id"] == 1813
    assert body["group"]["id"] == 10332
    assert body["source"]["id"] == 836
    assert body["admin_url"].endswith("#!/campaign.editor/%s" % body["id"])

    campaign = fake_kt.campaigns_store[body["id"]]
    assert campaign["type"] == "position"
    assert campaign["domain_id"] == 1813
    assert campaign["group_id"] == 10332
    assert campaign["traffic_source_id"] == 836

    geo_flow, offers_flow = body["streams"]
    assert geo_flow["schema"] == "redirect"
    assert geo_flow["type"] == "regular"
    assert geo_flow["action_type"] == "http"
    assert geo_flow["action_payload"] == "https://google.com"
    # Гео берётся из ввода пользователя, а не подменяется.
    assert geo_flow["filters"] == [{"name": "country", "mode": "accept", "payload": ["BY"]}]

    assert offers_flow["schema"] == "landings"
    assert offers_flow["type"] == "default"
    assert offers_flow["offers"] == [{"offer_id": 18001, "share": 100, "state": "active"}]


def test_creator_keeps_user_geo(client: TestClient, fake_kt: FakeKeitaro):
    resp = create_campaign(client, geo="mx")
    assert resp.status_code == 200, resp.text
    geo_flow = resp.json()["streams"][0]
    assert geo_flow["filters"][0]["payload"] == ["MX"]


def test_creator_rejects_unknown_offer(client: TestClient):
    resp = create_campaign(client, offer_id=99999)
    assert resp.status_code == 502
    assert "не найден" in resp.json()["detail"]["message"]


def test_creator_geos_are_uppercased_and_validated(client: TestClient):
    resp = create_campaign(client, geo="ru")
    assert resp.status_code == 200
    assert resp.json()["geo"] == "RU"

    resp = create_campaign(client, geo="RUS")
    assert resp.status_code == 422


def test_editor_put_replaces_offers_with_normalized_shares(client: TestClient, fake_kt: FakeKeitaro):
    created = create_campaign(client).json()
    offers_flow = created["streams"][1]
    stream_id = offers_flow["id"]

    # Добавляем второй оффер, сохраняем.
    resp = client.put(f"/api/streams/{stream_id}/offers", json={
        "offers": [
            {"offer_id": 18001, "share": 60},
            {"offer_id": 18002, "share": 40},
        ],
    })
    assert resp.status_code == 200, resp.text
    saved = resp.json()["offers"]
    assert {o["offer_id"] for o in saved} == {18001, 18002}
    assert sum(o["share"] for o in saved) == 100
    assert saved == sorted(saved, key=lambda o: o["offer_id"])

    # Удаляем первый оффер: его в PUT быть не должно, сумма всё ещё 100.
    resp = client.put(f"/api/streams/{stream_id}/offers", json={
        "offers": [{"offer_id": 18002, "share": 0}],
    })
    assert resp.status_code == 200, resp.text
    saved = resp.json()["offers"]
    assert [o["offer_id"] for o in saved] == [18002]
    assert sum(o["share"] for o in saved) == 100

    # На стенд ушёл состав без удалённого оффера.
    last = fake_kt.stream_updates[-1]
    assert last[0] == stream_id
    assert [o["offer_id"] for o in last[1]["offers"]] == [18002]


def test_editor_view_enriches_offer_names_from_cache(client: TestClient, db: Session):
    created = create_campaign(client).json()
    db.add(models.OfferCache(offer_id=18001, name="18001 Detoxin", state="active"))
    db.commit()

    resp = client.get(f"/api/campaigns/{created['id']}")
    assert resp.status_code == 200
    offers_flow = [s for s in resp.json()["streams"] if s["is_offer_stream"]][0]
    assert offers_flow["offers"][0]["name"] == "18001 Detoxin"
    assert resp.json()["admin_url"]


def test_campaign_list(client: TestClient):
    create_campaign(client)
    resp = client.get("/api/campaigns")
    assert resp.status_code == 200
    assert any(c["name"] == "test_karelov_campaign1" for c in resp.json())

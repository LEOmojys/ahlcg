"""场景间经验升级：接口能列出可购卡，并能用经验买到手。"""

import pytest
from fastapi.testclient import TestClient

from ahlcg.campaign import CampaignState
from ahlcg.data.deck import build_starter_deck, rules_for
from ahlcg.data.pool import CardPool
from ahlcg.web.cardimages import store_from_environment


@pytest.fixture(scope="module")
def pool():
    return CardPool.load()


def build_app(pool):
    """create_app() 内部的会话存储，测试需要直接拿到它来建局。"""
    import ahlcg.web.app as web_app

    captured: dict = {}
    original = web_app.SessionStore

    class _Patched(original):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            captured["store"] = self

    image_store = store_from_environment()
    image_store.enabled = False
    web_app.SessionStore = _Patched  # type: ignore[assignment]
    try:
        application = web_app.create_app(pool, image_store=image_store)
    finally:
        web_app.SessionStore = original  # type: ignore[assignment]
    return TestClient(application, raise_server_exceptions=False), captured["store"]


def test_upgrades_endpoint_lists_legal_cards(pool):
    client, store = build_app(pool)
    session = store.create("01001", "standard", 5)
    res = client.get("/api/campaign/upgrades", params={"session": session.id})
    assert res.status_code == 200
    data = res.json()
    assert data["available"] is True
    assert data["xp"] == 0
    assert data["candidates"], "至少应该能列出一些可购买的卡"

    rules = rules_for(pool.get("01001"))
    for candidate in data["candidates"][:40]:
        defn = pool.get(candidate["code"])
        assert rules.allows(defn), candidate["code"]
        assert candidate["cost"] == max(1, defn.level)


def test_spending_without_xp_is_refused_politely(pool):
    client, store = build_app(pool)
    session = store.create("01001", "standard", 5)
    listed = client.get("/api/campaign/upgrades", params={"session": session.id}).json()
    code = listed["candidates"][0]["code"]
    res = client.post("/api/campaign/spend", json={"session_id": session.id, "purchases": [{"code": code}]})
    assert res.status_code == 200
    assert res.json()["spent"], "没有经验时必须返回中文错误，而不是静默成功"


def test_unknown_session_is_rejected(pool):
    client, _ = build_app(pool)
    res = client.get("/api/campaign/upgrades", params={"session": "nope"})
    assert res.status_code in (400, 404)


def starter_campaign(pool, investigator="01001", seed=5):
    deck = build_starter_deck(pool, investigator)
    return CampaignState.new(
        "night_of_the_zealot", (investigator,), "standard", decks=[list(deck.cards)], seed=seed, pool=pool
    )


def test_buying_a_card_with_experience_changes_the_deck(pool):
    campaign = starter_campaign(pool)
    investigator = campaign.investigators[0]
    investigator.xp_earned = 6
    deck_before = list(investigator.deck)

    rules = rules_for(pool.get("01001"))
    victim = next(
        code
        for code in deck_before
        if pool.get(code).card_class.value in ("guardian", "seeker", "neutral") and not pool.get(code).weakness
    )
    candidate = next(
        defn
        for defn in pool.all()
        if defn.card_type.value in ("asset", "event", "skill")
        and rules.allows(defn)
        and 1 <= defn.level <= 2
        and defn.code != victim
        and not defn.weakness
        and defn.code not in deck_before
    )
    errors = campaign.spend_xp("p1", [{"code": candidate.code, "replace": victim}])
    assert errors == [], errors
    assert candidate.code in investigator.deck
    assert victim not in investigator.deck
    assert investigator.xp_available == 6 - max(1, candidate.level)


def test_illegal_purchase_reports_chinese_errors(pool):
    campaign = starter_campaign(pool)
    campaign.investigators[0].xp_earned = 20
    # Cryptic Research (01043) is a level 4 Seeker card: outside Roland's splash limit
    errors = campaign.spend_xp("p1", [{"code": "01043", "replace": campaign.investigators[0].deck[0]}])
    assert errors and any("01043" in e or "Cryptic" in e or "等级" in e or "范围" in e for e in errors)

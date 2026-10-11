"""中文卡面：翻译表与卡牌数据对得上，且所有上场的卡都有中文。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ahlcg.core.enums import CardType
from ahlcg.data.deck import CORE_PACKS
from ahlcg.data.loader import to_card_def
from ahlcg.data.pool import CardPool
from ahlcg.data.zh import lookup, table


@pytest.fixture(scope="module")
def pool():
    return CardPool.load()


def test_every_entry_matches_its_card(pool):
    for code, entry in table().items():
        if not pool.has(code):
            continue  # entries may cover reprints outside the current packs
        defn = pool.get(code)
        assert defn.name == entry["en"], f"{code}: 翻译表对应的英文标题与卡面不符"


def test_core_player_cards_all_have_chinese(pool):
    by_title = {}
    for defn in pool.all():
        record = defn.meta.get("arkhamdb") or {}
        if record.get("pack_code") not in CORE_PACKS or record.get("encounter_code"):
            continue
        if defn.card_type not in (CardType.ASSET, CardType.EVENT, CardType.SKILL, CardType.INVESTIGATOR):
            continue
        by_title.setdefault(defn.name, defn)
    missing = [d.name for d in by_title.values() if not d.name_zh]
    assert not missing, f"缺少中文卡名的玩家卡：{missing[:8]}"


def test_scenario_cards_all_have_chinese(pool):
    codes = [
        "01105", "01106", "01107", "01108", "01109", "01110", "01111", "01112",
        "01113", "01114", "01115", "01116", "01117", "01122", "01123", "01124",
        "01125", "01126", "01127", "01128", "01129", "01130", "01131", "01132",
        "01133", "01134", "01137", "01138", "01139", "01140", "01141", "01143",
        "01144", "01145", "01146", "01147", "01148", "01149", "01150", "01151",
        "01152", "01153", "01154", "01155", "01156", "01157",
    ]
    missing = [code for code in codes if pool.has(code) and not pool.get(code).name_zh]
    assert not missing, f"缺少中文的场景卡：{missing}"


def test_loader_attaches_zh_and_falls_back_by_title(pool):
    machete = pool.get("01020")
    assert machete.name_zh == "砍刀"
    assert "攻击" in (machete.text_zh or "")
    reprint = pool.get("01516")  # revised core printing of .45 Automatic
    assert reprint.name_zh == ".45 自动手枪", "旧印次应按英文标题回退"


def test_cards_outside_the_table_keep_english():
    record = {"code": "02016", "name": "Blackjack", "type_code": "asset", "pack_code": "dunwich"}
    defn = to_card_def(record)
    assert defn.name_zh is None
    assert defn.display_name == "Blackjack"

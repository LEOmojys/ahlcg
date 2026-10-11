"""Coverage over the whole core-set player pool (not just the starter decks)."""

import sys
from collections import Counter, defaultdict

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from ahlcg.core.enums import CardType
from ahlcg.data.deck import CORE_PACKS
from ahlcg.data.pool import CardPool

HOOK_KEYS = (
    "constant", "penalty", "in_test", "attack", "extra_action", "extra_slots",
    "location_actions", "play", "resolve", "weakness", "uses", "parley",
    "blanks_investigator", "blocks_enemy_movement", "reveal_choice", "attracts_code",
)

pool = CardPool.load()
want_all = "--all" in sys.argv


def data_only(defn) -> bool:
    text = (defn.text or "").strip()
    if defn.card_type is CardType.SKILL and (not text or text == "Max 1 committed per skill test."):
        return True
    if defn.card_type is CardType.ASSET and not text and (defn.health or defn.sanity):
        return True
    if defn.card_type is CardType.ENEMY and not text:
        return True
    return False


def implemented(defn) -> bool:
    if defn.abilities:
        return True
    if any(defn.meta.get(key) for key in HOOK_KEYS):
        return True
    return data_only(defn)


cards = []
for defn in pool.all():
    record = defn.meta.get("arkhamdb") or {}
    pack = record.get("pack_code")
    if pack not in CORE_PACKS:
        continue
    if record.get("encounter_code"):
        continue
    if defn.card_type not in (CardType.ASSET, CardType.EVENT, CardType.SKILL, CardType.TREACHERY, CardType.ENEMY):
        continue
    if defn.code == "01000":
        continue  # "Random Basic Weakness" placeholder, not a real card
    cards.append(defn)

# the revised core set reprints the same cards: keep one printing per title
by_title: dict[str, object] = {}
for defn in sorted(cards, key=lambda d: d.code):
    by_title.setdefault(defn.name, defn)
unique = list(by_title.values())

done = [d for d in unique if implemented(d)]
missing = [d for d in unique if not implemented(d)]

print(f"基础包玩家卡（按卡名去重）：{len(unique)} 种")
print(f"  已有卡面效果：{len(done)} 种")
print(f"  仍是纯数据：  {len(missing)} 种")
print("  按职业统计缺失：", dict(Counter(d.card_class.value for d in missing)))
print()
if want_all or True:
    groups = defaultdict(list)
    for defn in missing:
        groups[(defn.card_class.value, defn.card_type.value)].append(defn)
    for key in sorted(groups):
        defns = groups[key]
        print(f"--- {key[0]} / {key[1]} ({len(defns)}) ---")
        for defn in defns:
            text = " ".join((defn.text or "").split())
            print(f"  [{defn.code}] {defn.name} L{defn.level} :: {text[:90]}")

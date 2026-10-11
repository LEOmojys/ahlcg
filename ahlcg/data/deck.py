"""Deck lists, deckbuilding rules and starter decks.

Rules Reference, "Deckbuilding":

  * the deck must contain exactly the printed Deck Size of standard player cards
  * weaknesses, investigator-specific cards and scenario cards do NOT count towards it
  * no more than 2 copies of a card by title
  * every standard card must come from the investigator's Deckbuilding Options
  * level 0 only at the start of a campaign
  * one required random basic weakness is added at the end
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from ..core.cards import CardDef
from ..core.enums import CardType
from ..core.errors import CardDataError
from ..core.rng import Rng

#: A core-set campaign builds its decks out of the core set only.
CORE_PACKS: tuple[str, ...] = ("core", "rcore")


@dataclass(frozen=True)
class DeckRules:
    """The Deckbuilding Options and Requirements printed on an investigator."""

    size: int = 30
    required_cards: tuple[str, ...] = ()
    random_basic_weakness: int = 1
    options: tuple[dict[str, Any], ...] = ()
    investigator_code: str = ""

    def option_for(self, defn: CardDef) -> dict[str, Any] | None:
        for option in self.options:
            factions = option.get("faction") or option.get("factions") or ()
            level = option.get("level") or {}
            low = int(level.get("min", 0))
            high = int(level.get("max", 5))
            if defn.card_class.value in factions and low <= defn.xp <= high:
                return option
        return None

    def allows(self, defn: CardDef) -> bool:
        return self.option_for(defn) is not None

    def primary_factions(self) -> tuple[str, ...]:
        if not self.options:
            return ()
        first = self.options[0]
        return tuple(first.get("faction") or first.get("factions") or ())


def _as_json(value: Any) -> Any:
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def rules_for(defn: CardDef) -> DeckRules:
    """Parse the deckbuilding data carried by an investigator CardDef."""
    requirements = _as_json(defn.meta.get("deck_requirements")) or {}
    options = _as_json(defn.meta.get("deck_options")) or []
    required: list[str] = []
    for code, alternatives in (requirements.get("card") or {}).items():
        required.append(str(code))
        if isinstance(alternatives, dict) and alternatives:
            required[-1] = str(next(iter(alternatives)))
    random_weakness = 0
    for entry in requirements.get("random") or []:
        if str(entry.get("value", "")).lower().replace(" ", "") == "basicweakness":
            random_weakness += 1
    return DeckRules(
        size=int(requirements.get("size") or 30),
        required_cards=tuple(required),
        random_basic_weakness=random_weakness,
        options=tuple(options) if isinstance(options, list) else (),
        investigator_code=defn.code,
    )


def is_investigator_specific(defn: CardDef) -> bool:
    """Cards printed for one investigator only (they never count towards deck size)."""
    return "deck only" in (defn.text or "").lower()


def is_weakness(defn: CardDef) -> bool:
    return defn.weakness or defn.basic_weakness or "weakness" in str(defn.meta.get("subtype", "")).lower()


def basic_weakness_codes(pool, *, packs: tuple[str, ...] | None = CORE_PACKS) -> list[str]:
    """Random basic weaknesses.  A core-set campaign draws them from the core set."""
    out: list[str] = []
    seen: set[str] = set()
    for card in pool.all():  # code-sorted, so the original printing wins
        if not card.basic_weakness or card.name in seen:
            continue  # core and revised-core printings are the same card
        pack = (card.meta.get("arkhamdb") or {}).get("pack_code")
        if packs is not None and pack not in packs:
            continue
        seen.add(card.name)
        out.append(card.code)
    return sorted(out)


@dataclass(frozen=True)
class DeckList:
    investigator: str
    cards: tuple[str, ...]
    name: str = ""
    notes: tuple[str, ...] = ()

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for code in self.cards:
            out[code] = out.get(code, 0) + 1
        return out

    def __len__(self) -> int:
        return len(self.cards)


def standard_count(pool, deck: DeckList) -> int:
    """How many cards of the deck count towards the printed Deck Size."""
    total = 0
    for code in deck.cards:
        defn = pool.get(code)
        if is_weakness(defn) or is_investigator_specific(defn):
            continue
        total += 1
    return total


def validate_deck(pool, deck: DeckList, *, level_limit: int = 0) -> list[str]:
    """Return a list of human readable problems (empty means the deck is legal)."""
    problems: list[str] = []
    investigator = pool.get(deck.investigator)
    if investigator.card_type is not CardType.INVESTIGATOR:
        return [f"{deck.investigator} 不是调查员卡"]
    rules = rules_for(investigator)

    by_title: dict[str, int] = {}
    for code in deck.cards:
        if not pool.has(code):
            problems.append(f"未知卡牌 {code}")
            continue
        defn = pool.get(code)
        by_title[defn.name] = by_title.get(defn.name, 0) + 1
    for title, count in by_title.items():
        if count > 2:
            problems.append(f"「{title}」有 {count} 张，超过同名 2 张上限")

    standard = standard_count(pool, deck)
    if standard != rules.size:
        problems.append(f"标准卡 {standard} 张，应为 {rules.size} 张（弱点与专属卡不计入）")

    for code in rules.required_cards:
        if code not in deck.cards:
            problems.append(f"缺少调查员专属卡 {pool.get(code).name if pool.has(code) else code}")

    weaknesses = sum(1 for code in deck.cards if pool.has(code) and pool.get(code).basic_weakness)
    if weaknesses < rules.random_basic_weakness:
        problems.append(f"需要 {rules.random_basic_weakness} 张随机基础弱点，当前 {weaknesses} 张")

    for code in deck.cards:
        if not pool.has(code):
            continue
        defn = pool.get(code)
        if is_weakness(defn) or is_investigator_specific(defn):
            continue
        if defn.xp > level_limit:
            problems.append(f"「{defn.name}」等级 {defn.xp} 超过当前可用等级 {level_limit}")
        elif not rules.allows(defn):
            problems.append(f"「{defn.name}」（{defn.card_class.value} {defn.xp} 级）不在组卡许可范围内")
    return problems


def build_starter_deck(
    pool,
    investigator_code: str,
    *,
    rng: Rng | None = None,
    copies: int = 1,
    level_limit: int = 0,
    packs: tuple[str, ...] | None = CORE_PACKS,
) -> DeckList:
    """Build a legal starting deck for an investigator out of level 0 cards.

    The core set only prints one copy of most cards, so the deck is padded with
    legal second copies up to the printed Deck Size.
    """
    rng = rng or Rng(0)
    investigator = pool.get(investigator_code)
    rules = rules_for(investigator)

    chosen: list[str] = []
    for code in rules.required_cards:
        if pool.has(code):
            chosen.append(code)

    weaknesses = [c for c in basic_weakness_codes(pool)]
    if weaknesses:
        for _ in range(rules.random_basic_weakness):
            chosen.append(rng.choice(weaknesses))

    titles = {pool.get(code).name for code in chosen if pool.has(code)}
    standard: list[str] = []

    def candidates() -> list[str]:
        out: list[str] = []
        for option in rules.options:
            factions = set(option.get("faction") or option.get("factions") or ())
            level = option.get("level") or {}
            high = int(level.get("max", 5))
            for defn in sorted(pool.all(), key=lambda d: d.code):
                if defn.card_type not in (CardType.ASSET, CardType.EVENT, CardType.SKILL):
                    continue
                if defn.card_class.value not in factions:
                    continue
                if defn.xp > min(high, level_limit):
                    continue
                if is_weakness(defn) or is_investigator_specific(defn):
                    continue
                record = defn.meta.get("arkhamdb", {})
                if record.get("encounter_code"):
                    continue  # scenario cards never belong in a player deck
                if packs is not None and record.get("pack_code") not in packs:
                    continue  # core-set campaign: no cards from later cycles
                if defn.code in chosen or defn.code in standard:
                    continue
                out.append(defn.code)
        return out

    first_pass = candidates()
    for code in first_pass:
        if len(standard) >= rules.size:
            break
        if pool.get(code).name in titles:
            continue
        standard.append(code)
        titles.add(pool.get(code).name)

    # pad with second copies of legal cards (same title, at most 2 by title)
    for _ in range(copies):
        if len(standard) >= rules.size:
            break
        for code in first_pass:
            if len(standard) >= rules.size:
                break
            standard.append(code)

    deck = DeckList(
        investigator=investigator_code,
        cards=tuple(chosen + standard),
        name=f"{investigator.display_name} 起始牌组",
        notes=(f"标准卡 {len(standard)} 张 + 专属卡/弱点 {len(chosen)} 张",),
    )
    return deck


#: The five core-set investigators.
CORE_INVESTIGATORS: tuple[str, ...] = ("01001", "01002", "01003", "01004", "01005")


def starter_decks(pool, *, seed: int = 0) -> dict[str, DeckList]:
    rng = Rng(seed)
    return {code: build_starter_deck(pool, code, rng=rng) for code in CORE_INVESTIGATORS}


def default_deck(pool, investigator_code: str = "01001") -> DeckList:
    return build_starter_deck(pool, investigator_code, rng=Rng(0))


#: Roland Banks, the recommended core-set starter deck, spelled out.
#: 30 standard cards plus his investigator-specific cards and 1 basic weakness
#: (weaknesses and investigator-specific cards do not count towards Deck Size).
ROLAND_STARTER = DeckList(
    investigator="01001",
    name="Roland Banks 起始牌组",
    cards=(
        "01006", "01007",                                      # .38 Special, Cover Up (investigator specific)
        "01016", "01017", "01018", "01019", "01020", "01020",   # Machete twice
        "01021", "01022", "01023", "01024", "01025",
        "01030", "01031", "01032", "01033", "01034", "01035", "01036", "01037", "01038", "01039",
        "01086", "01087", "01088", "01088",                     # Emergency Cache twice
        "01089", "01090", "01091", "01092", "01093",
        "01096",                                               # Amnesia (basic weakness)
    ),
    notes=("标准卡 30 张", "含调查员专属卡与 1 张基础弱点（不计入 30）"),
)


def deck_from_codes(pool, investigator_code: str, codes) -> DeckList:
    """Build a player deck from an explicit card list, enforcing the deckbuilding rules.

    Signature cards are added automatically, and a random basic weakness joins
    the deck, exactly like the starter decks.
    """
    rules = rules_for(pool.get(investigator_code))
    cards = list(codes)
    for code in rules.required_cards:
        if code not in cards:
            cards.append(code)
    if not any(pool.has(c) and pool.get(c).basic_weakness for c in cards):
        weaknesses = basic_weakness_codes(pool)
        if weaknesses:
            cards.append(weaknesses[Rng().randrange(len(weaknesses))])
    deck = DeckList(investigator=investigator_code, cards=tuple(cards), name=f"{investigator_code} 自由组卡")
    problems = validate_deck(pool, deck)
    if problems:
        raise ValueError("；".join(problems[:4]))
    return deck


def ensure_codes_exist(deck: DeckList, registry) -> None:
    missing = [code for code in deck.cards if code not in registry]
    if missing:
        raise CardDataError(f"deck {deck.name!r} references unknown cards: {sorted(set(missing))}")

"""Starter decks for the web client.

The engine ships one hand tuned starter deck (Roland Banks, the deck the rules
tests use).  The web client also offers the other core set investigators, so it
builds them a level 0 core set deck: the investigator's own class plus neutral
cards, two copies each, respecting the printed deck limit.  Those decks are
legal and playable but deliberately not tuned - they are a convenience, not a
deck builder.
"""

from __future__ import annotations

from ..core.enums import CardClass, CardType
from ..data.deck import ROLAND_STARTER, DeckList, deck_from_codes  # noqa: F401
from ..data.pool import CardPool

#: the core set investigators offered by the web client (official codes)
CORE_INVESTIGATORS: tuple[str, ...] = ("01001", "01002", "01003", "01004", "01005")

INVESTIGATOR_NAMES_ZH: dict[str, str] = {
    "01001": "罗兰·班克斯",
    "01002": "黛西·沃克",
    "01003": "斯基兹·奥图尔",
    "01004": "阿格尼丝·贝克",
    "01005": "温迪·亚当斯",
}

#: investigator specific cards and weaknesses (01006 - 01015) plus the Lita
#: Chantler story asset; none of these belong in an auto built deck
EXCLUDED_CODES: frozenset[str] = frozenset(
    {f"010{number:02d}" for number in range(6, 16)} | {"01117"}
)

DECK_SIZE = 30


def eligible(defn) -> bool:
    """A core set level 0 player card that may be duplicated in a starter deck."""
    if defn.code in EXCLUDED_CODES:
        return False
    if defn.weakness or defn.basic_weakness:
        return False
    if defn.card_type not in (CardType.ASSET, CardType.EVENT, CardType.SKILL):
        return False
    if defn.level:
        return False
    pack = (defn.meta.get("arkhamdb") or {}).get("pack_code")
    return pack == "core"


def build_core_deck(pool: CardPool, investigator_code: str, size: int = DECK_SIZE) -> list[str]:
    """Build a level 0 deck from the core set for one investigator."""
    investigator = pool.get(investigator_code)
    primary = investigator.card_class
    own: list[str] = []
    neutral: list[str] = []
    for defn in sorted(pool.all(), key=lambda card: card.code):
        if not eligible(defn):
            continue
        copies = 2 if defn.deck_limit >= 2 else 1
        if defn.card_class is primary:
            own.extend([defn.code] * copies)
        elif defn.card_class is CardClass.NEUTRAL:
            neutral.extend([defn.code] * copies)

    cards = own + neutral
    if len(cards) < size:
        # extremely defensive: pad with anything else that is level 0 and legal
        for defn in sorted(pool.all(), key=lambda card: card.code):
            if len(cards) >= size:
                break
            if eligible(defn) and defn.code not in cards:
                cards.append(defn.code)
    return cards[:size]


def deck_for(pool: CardPool, investigator_code: str) -> DeckList:
    """The deck a web session starts with."""
    if investigator_code == ROLAND_STARTER.investigator:
        return ROLAND_STARTER
    if not pool.has(investigator_code):
        raise KeyError(f"unknown investigator code {investigator_code!r}")
    cards = build_core_deck(pool, investigator_code)
    name = INVESTIGATOR_NAMES_ZH.get(investigator_code, investigator_code)
    return DeckList(
        investigator=investigator_code,
        cards=tuple(cards),
        name=f"{name} 起始牌组（核心包自动组建）",
        notes=(
            "由 Web 层按职业自动组建的 0 级核心包牌组；未包含个人弱点与随机基础弱点。",
        ),
    )


def investigator_display_name(pool: CardPool, code: str) -> str:
    zh = INVESTIGATOR_NAMES_ZH.get(code)
    if zh:
        return zh
    if pool.has(code):
        return pool.get(code).display_name
    return code

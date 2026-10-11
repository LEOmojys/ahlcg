"""Card definitions (static data) and card instances (runtime state).

CardDef is pure data: JSON friendly, usable by a deck builder, and shared by
every copy of a card.  CardInstance is one physical card in one game - it
carries damage, horror, uses, tokens and its current zone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from .enums import (
    AbilityKind,
    CardClass,
    CardType,
    CostKind,
    Skill,
    Slot,
    Trigger,
    Zone,
)
from .errors import CardDataError, RuleError


# --------------------------------------------------------------------------
# costs and abilities
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Cost:
    kind: CostKind
    amount: int = 1
    detail: str | None = None

    def __str__(self) -> str:
        if self.kind is CostKind.ACTION:
            return "行动" if self.amount == 1 else f"{self.amount} 行动"
        if self.kind is CostKind.RESOURCE:
            return f"{self.amount} 资源"
        if self.kind is CostKind.EXHAUST:
            return "消耗"
        return self.detail or f"{self.kind.value} x{self.amount}"


@dataclass
class Ability:
    """A declarative card ability.

    The effect receives an effect context supplied by the engine (it exposes the
    game state, the source card and the event).  Keeping the effect as a plain
    callable means card files read like the card text while the engine keeps
    full control over when it fires.
    """

    kind: AbilityKind
    trigger: Trigger | None = None
    costs: tuple[Cost, ...] = ()
    effect: Callable[[Any], None] | None = None
    condition: Callable[[Any], bool] | None = None
    label: str | None = None
    limit: str | None = None
    key: str | None = None

    @property
    def is_activated(self) -> bool:
        return self.kind in (AbilityKind.ACTIVATED, AbilityKind.PARLEY)


@dataclass(frozen=True)
class DeckRequirement:
    """Deckbuilding constraints of an investigator."""

    size: int = 30
    primary_class: CardClass | None = None
    secondary_class: CardClass | None = None
    secondary_max_level: int = 0
    max_level: int = 5
    required_codes: tuple[str, ...] = ()
    random_basic_weakness: int = 1
    notes: tuple[str, ...] = ()


# --------------------------------------------------------------------------
# card definition
# --------------------------------------------------------------------------
@dataclass
class CardDef:
    code: str
    name: str
    card_type: CardType
    card_class: CardClass = CardClass.NEUTRAL
    text: str = ""
    name_zh: str | None = None
    text_zh: str | None = None
    subtitle: str | None = None
    traits: frozenset[str] = frozenset()
    unique: bool = False
    level: int = 0
    encounter_set: str | None = None
    quantity: int = 1

    # --- player cards
    cost: int | None = None
    slots: tuple[Slot, ...] = ()
    icons: Mapping[Skill, int] = field(default_factory=dict)
    wild_icons: int = 0
    deck_limit: int = 2
    xp: int = 0
    health: int | None = None
    sanity: int | None = None
    uses: Mapping[str, int] = field(default_factory=dict)
    weakness: bool = False
    basic_weakness: bool = False

    # --- investigator
    willpower: int | None = None
    intellect: int | None = None
    combat: int | None = None
    agility: int | None = None
    deck_requirement: DeckRequirement | None = None
    elder_sign: str | None = None

    # --- enemy
    fight: int | None = None
    evade: int | None = None
    enemy_damage: int = 0
    enemy_horror: int = 0
    hunter: bool = False
    prey: str | None = None
    spawn: str | None = None
    victory: int = 0
    vengeance: int = 0
    massive: bool = False
    elite: bool = False
    health_per_investigator: bool = False

    # --- location
    shroud: int | None = None
    clues: int = 0
    clues_per_investigator: bool = False
    unrevealed_name: str | None = None
    revealed: bool = False

    # --- act / agenda
    clues_required: int | None = None
    clues_per_investigator_required: bool = False
    doom_threshold: int | None = None
    act_number: int | None = None
    agenda_number: int | None = None

    # --- generic
    keywords: frozenset[str] = frozenset()
    abilities: tuple[Ability, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)

    # -- queries --------------------------------------------------------
    @property
    def is_asset(self) -> bool:
        return self.card_type is CardType.ASSET

    @property
    def is_player_card(self) -> bool:
        return self.card_type in (CardType.ASSET, CardType.EVENT, CardType.SKILL)

    @property
    def is_encounter_card(self) -> bool:
        return self.card_type in (CardType.TREACHERY, CardType.ENEMY)

    @property
    def display_name(self) -> str:
        return self.name_zh or self.name

    def stat(self, skill: Skill) -> int | None:
        return {
            Skill.WILLPOWER: self.willpower,
            Skill.INTELLECT: self.intellect,
            Skill.COMBAT: self.combat,
            Skill.AGILITY: self.agility,
        }[skill]

    def icon_count(self, skill: Skill) -> int:
        return int(self.icons.get(skill, 0))

    def total_icons(self) -> int:
        return sum(int(v) for v in self.icons.values()) + self.wild_icons

    def commit_bonus(self, skill: Skill) -> int:
        """Icons this card adds to a test of the given skill (wild icons count)."""
        return self.icon_count(skill) + self.wild_icons

    def abilities_of(self, kind: AbilityKind) -> tuple[Ability, ...]:
        return tuple(a for a in self.abilities if a.kind is kind)


def card(code: str, name: str, card_type: CardType, **kwargs: Any) -> CardDef:
    """Small factory so card-pool modules stay readable."""
    return CardDef(code=code, name=name, card_type=card_type, **kwargs)


# --------------------------------------------------------------------------
# runtime instance
# --------------------------------------------------------------------------
@dataclass
class CardInstance:
    id: str
    defn: CardDef
    owner_id: str | None = None
    controller_id: str | None = None
    zone: Zone = Zone.LIMBO
    exhausted: bool = False
    damage: int = 0
    horror: int = 0
    clues: int = 0
    doom: int = 0
    uses: dict[str, int] = field(default_factory=dict)
    tokens: dict[str, int] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    attachments: list[str] = field(default_factory=list)
    attached_to: str | None = None
    location_id: str | None = None
    engaged_with: list[str] = field(default_factory=list)
    in_play_since_round: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    # -- identity -------------------------------------------------------
    @property
    def code(self) -> str:
        return self.defn.code

    @property
    def name(self) -> str:
        return self.defn.display_name

    @property
    def card_type(self) -> CardType:
        return self.defn.card_type

    # -- condition ------------------------------------------------------
    @property
    def health_total(self) -> int | None:
        """Printed health plus any per-game bonus (e.g. +4 per investigator)."""
        if self.defn.health is None:
            return None
        return int(self.defn.health) + int(self.meta.get("health_bonus", 0))

    def health_remaining(self) -> int | None:
        total = self.health_total
        if total is None:
            return None
        return total - self.damage

    def sanity_remaining(self) -> int | None:
        if self.defn.sanity is None:
            return None
        return self.defn.sanity - self.horror

    def is_defeated(self) -> bool:
        hp = self.health_remaining()
        sp = self.sanity_remaining()
        return (hp is not None and hp <= 0) or (sp is not None and sp <= 0)

    # -- uses -----------------------------------------------------------
    def use(self, key: str, amount: int = 1) -> int:
        """Spend amount uses of key; returns the remaining count."""
        current = self.uses.get(key, 0)
        if current < amount:
            raise RuleError(f"{self.name} has only {current} use(s) of {key!r}")
        self.uses[key] = current - amount
        return self.uses[key]

    def add_uses(self, key: str, amount: int) -> None:
        self.uses[key] = self.uses.get(key, 0) + amount

    def token(self, name: str) -> int:
        return self.tokens.get(name, 0)

    def add_token(self, name: str, amount: int = 1) -> None:
        self.tokens[name] = self.tokens.get(name, 0) + amount

    def mark_used(self, key: str) -> None:
        """Record a once-per-scope limit marker."""
        self.meta[key] = True

    def was_used(self, key: str) -> bool:
        return bool(self.meta.get(key))


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------
class CardRegistry:
    def __init__(self) -> None:
        self._by_code: dict[str, CardDef] = {}

    def register(self, defn: CardDef) -> CardDef:
        if defn.code in self._by_code:
            existing = self._by_code[defn.code]
            raise CardDataError(f"duplicate card code {defn.code!r}: {existing.name!r} vs {defn.name!r}")
        self._by_code[defn.code] = defn
        return defn

    def extend(self, defns: Iterable[CardDef]) -> None:
        for defn in defns:
            self.register(defn)

    def get(self, code: str) -> CardDef:
        try:
            return self._by_code[code]
        except KeyError:
            raise CardDataError(f"unknown card code {code!r}") from None

    def has(self, code: str) -> bool:
        return code in self._by_code

    def codes(self) -> list[str]:
        return sorted(self._by_code)

    def all(self) -> list[CardDef]:
        return [self._by_code[c] for c in self.codes()]

    def find(self, *, card_type: CardType | None = None, card_class: CardClass | None = None) -> list[CardDef]:
        out = []
        for defn in self.all():
            if card_type is not None and defn.card_type is not card_type:
                continue
            if card_class is not None and defn.card_class is not card_class:
                continue
            out.append(defn)
        return out

    def __len__(self) -> int:
        return len(self._by_code)

    def __contains__(self, code: object) -> bool:
        return code in self._by_code


CARD_REGISTRY = CardRegistry()

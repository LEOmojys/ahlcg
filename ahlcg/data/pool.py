"""A loaded, behaviour-aware card pool."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator

from ..core.cards import CardDef
from ..core.enums import CardClass, CardType
from ..cards import apply_behaviours, load_all
from .loader import load_records, to_card_def

DEFAULT_DATA = Path(__file__).resolve().parents[2] / "reference" / "arkhamdb_core.json"


class CardPool:
    """Every card the engine knows, keyed by official code."""

    def __init__(self, cards: dict[str, CardDef] | None = None) -> None:
        self._cards: dict[str, CardDef] = dict(cards or {})

    @classmethod
    def load(cls, path: str | Path = DEFAULT_DATA) -> "CardPool":
        load_all()
        records = load_records(path)
        cards: dict[str, CardDef] = {}
        for code, record in records.items():
            try:
                defn = to_card_def(record)
            except Exception:
                continue
            cards[code] = apply_behaviours(defn)
        return cls(cards)

    # -- access ---------------------------------------------------------
    def get(self, code: str) -> CardDef:
        try:
            return self._cards[code]
        except KeyError:
            from ..core.errors import CardDataError

            raise CardDataError(f"card {code!r} is not in the pool") from None

    def has(self, code: str) -> bool:
        return code in self._cards

    def __len__(self) -> int:
        return len(self._cards)

    def __contains__(self, code: object) -> bool:
        return code in self._cards

    def all(self) -> list[CardDef]:
        return list(self._cards.values())

    def of_type(self, card_type: CardType) -> list[CardDef]:
        return [c for c in self._cards.values() if c.card_type is card_type]

    def of_class(self, card_class: CardClass) -> list[CardDef]:
        return [c for c in self._cards.values() if c.card_class is card_class]

    def encounter_set(self, encounter_code: str) -> list[CardDef]:
        return [c for c in self._cards.values() if c.encounter_set == encounter_code]

    def encounter_cards(self, encounter_code: str) -> list[CardDef]:
        """Only the cards of a set that get shuffled into the encounter deck."""
        return [
            c
            for c in self.encounter_set(encounter_code)
            if c.card_type in (CardType.ENEMY, CardType.TREACHERY)
        ]

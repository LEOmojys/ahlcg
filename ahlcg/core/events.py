"""Timing points, triggered abilities and numeric modifiers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from .enums import AbilityKind, Trigger


@dataclass
class GameEvent:
    """Something that just happened, emitted at a well defined timing point."""

    trigger: Trigger
    source: Any = None
    target: Any = None
    payload: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.payload.get(key, default)


@dataclass
class AbilityRef:
    """A concrete ability on a concrete card, matched to a concrete event."""

    source: Any
    ability: Any
    event: GameEvent

    @property
    def is_forced(self) -> bool:
        return self.ability.kind is AbilityKind.FORCED

    @property
    def is_optional(self) -> bool:
        return not self.is_forced


@dataclass(frozen=True)
class Modifier:
    """A numeric adjustment to a stat, skill test or value."""

    value: int
    source: Any = None
    reason: str = ""


def total_modifiers(modifiers: Iterable[Modifier]) -> int:
    return sum(m.value for m in modifiers)


def order_triggered(
    refs: Sequence[AbilityRef],
    active_player_id: str | None,
    owner_of: Callable[[Any], str | None] | None = None,
) -> list[AbilityRef]:
    """Order triggered abilities: forced first, then active player, then the rest.

    owner_of maps a source object to its controller id; by default the source is
    expected to expose a controller_id attribute.
    """

    def controller(ref: AbilityRef) -> str | None:
        if owner_of is not None:
            return owner_of(ref.source)
        return getattr(ref.source, "controller_id", None)

    def sort_key(ref: AbilityRef) -> tuple[int, int]:
        forced_rank = 0 if ref.is_forced else 1
        return (forced_rank, 0 if controller(ref) == active_player_id else 1)

    return sorted(refs, key=sort_key)

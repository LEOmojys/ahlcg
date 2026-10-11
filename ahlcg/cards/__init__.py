"""Card behaviour.

Card definitions are pure data (loaded from the public card database).  Anything
that needs code - triggered abilities, activated abilities, event effects,
weakness and treachery resolutions - lives in implementation modules that fill
the registries below.  apply_behaviours() is the single seam between the two.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from ..core.cards import Ability, CardDef

#: card code -> abilities printed on that card
CARD_ABILITIES: dict[str, tuple[Ability, ...]] = {}
#: card code -> effect resolved when the event is played
CARD_PLAY_EFFECTS: dict[str, Callable[[Any], Any]] = {}
#: card code -> extra static data the engine understands
#: ("attack" for weapons, "soak", custom scenario switches, ...)
CARD_META: dict[str, dict[str, Any]] = {}
#: treachery card code -> Revelation effect
CARD_REVELATION_EFFECTS: dict[str, Callable[[Any], Any]] = {}
#: weakness card code -> effect resolved when drawn
CARD_WEAKNESS_EFFECTS: dict[str, Callable[[Any], Any]] = {}


def register(
    code: str,
    *,
    abilities: Iterable[Ability] = (),
    play: Callable[[Any], Any] | None = None,
    revelation: Callable[[Any], Any] | None = None,
    weakness: Callable[[Any], Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Register the behaviour of one card."""
    abilities = tuple(abilities)
    if abilities:
        existing = CARD_ABILITIES.get(code, ())
        CARD_ABILITIES[code] = existing + abilities
    if play is not None:
        CARD_PLAY_EFFECTS[code] = play
    if revelation is not None:
        CARD_REVELATION_EFFECTS[code] = revelation
    if weakness is not None:
        CARD_WEAKNESS_EFFECTS[code] = weakness
    if meta:
        CARD_META.setdefault(code, {}).update(meta)


def apply_behaviours(defn: CardDef) -> CardDef:
    """Attach registered behaviour to a freshly loaded CardDef."""
    abilities = CARD_ABILITIES.get(defn.code)
    if abilities:
        defn.abilities = tuple(defn.abilities) + abilities
    if defn.code in CARD_PLAY_EFFECTS:
        defn.meta["play"] = CARD_PLAY_EFFECTS[defn.code]
    if defn.code in CARD_REVELATION_EFFECTS:
        defn.meta["resolve"] = CARD_REVELATION_EFFECTS[defn.code]
    if defn.code in CARD_WEAKNESS_EFFECTS:
        defn.meta["weakness"] = CARD_WEAKNESS_EFFECTS[defn.code]
    extra = CARD_META.get(defn.code)
    if extra:
        defn.meta.update(extra)
        declared_uses = extra.get("uses")
        if declared_uses:
            defn.uses = dict(declared_uses)
    return defn


def load_all() -> None:
    """Import every implementation module so the registries get filled."""
    from . import core_set_encounters  # noqa: F401
    from . import core_set_extra  # noqa: F401
    from . import core_set_player  # noqa: F401
    from . import encounters_devourer  # noqa: F401
    from . import encounters_midnight  # noqa: F401

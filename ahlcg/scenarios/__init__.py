"""Playable scenarios."""

from __future__ import annotations

from ..data.pool import CardPool
from .base import Scenario

_SCENARIO_CLASSES: dict[str, str] = {
    "torch": "ahlcg.scenarios.night_of_the_zealot.the_gathering:TheGathering",
    "arkham": "ahlcg.scenarios.night_of_the_zealot.the_midnight_masks:TheMidnightMasks",
    "tentacles": "ahlcg.scenarios.night_of_the_zealot.the_devourer_below:TheDevourerBelow",
}


def scenario_codes() -> list[str]:
    return sorted(_SCENARIO_CLASSES)


def load_scenario(code: str, pool: CardPool) -> Scenario:
    import importlib

    if code not in _SCENARIO_CLASSES:
        raise KeyError(f"unknown scenario {code!r}; known: {scenario_codes()}")
    module_name, _, class_name = _SCENARIO_CLASSES[code].partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, class_name)(pool)

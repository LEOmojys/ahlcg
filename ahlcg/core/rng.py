"""Deterministic randomness.

Every shuffle and every chaos token draw goes through this class, so a game is
fully reproducible from a seed plus the sequence of choices.  That is what makes
regression tests and balance simulations possible.
"""

from __future__ import annotations

import random
from typing import Any, Sequence, TypeVar

T = TypeVar("T")


class Rng:
    """Thin, serialisable wrapper around random.Random."""

    __slots__ = ("seed", "_random")

    def __init__(self, seed: int | None = None) -> None:
        self.seed = seed
        self._random = random.Random(seed)

    # -- basic draws ----------------------------------------------------
    def randint(self, low: int, high: int) -> int:
        """Inclusive on both ends."""
        return self._random.randint(low, high)

    def random(self) -> float:
        return self._random.random()

    def choice(self, seq: Sequence[T]) -> T:
        if not seq:
            raise ValueError("cannot choose from an empty sequence")
        return seq[self._random.randrange(len(seq))]

    def sample(self, population: Sequence[T], k: int) -> list[T]:
        return self._random.sample(list(population), k)

    def shuffle(self, seq: list[T]) -> list[T]:
        self._random.shuffle(seq)
        return seq

    def roll(self, probability: float) -> bool:
        return self._random.random() < probability

    # -- persistence ----------------------------------------------------
    def state(self) -> dict[str, Any]:
        version, internal, gauss = self._random.getstate()
        return {"seed": self.seed, "version": version, "internal": list(internal), "gauss": gauss}

    def set_state(self, state: dict[str, Any]) -> None:
        self.seed = state.get("seed", self.seed)
        self._random.setstate((state["version"], tuple(state["internal"]), state["gauss"]))

    def clone(self) -> "Rng":
        other = Rng(self.seed)
        other.set_state(self.state())
        return other

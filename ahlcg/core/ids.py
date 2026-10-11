"""Stable, human-readable ids for runtime objects."""

from __future__ import annotations


class IdGenerator:
    """Monotonic counter producing ids like asset-0007."""

    __slots__ = ("prefix", "counter")

    def __init__(self, prefix: str = "obj", start: int = 0) -> None:
        self.prefix = prefix
        self.counter = start

    def next(self) -> str:
        self.counter += 1
        return f"{self.prefix}-{self.counter:04d}"

    def state(self) -> dict[str, object]:
        return {"prefix": self.prefix, "counter": self.counter}

    def set_state(self, state: dict[str, object]) -> None:
        self.prefix = str(state.get("prefix", self.prefix))
        self.counter = int(state.get("counter", self.counter))  # type: ignore[arg-type]

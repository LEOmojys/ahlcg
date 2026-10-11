"""The engine's way of asking a question.

The engine never blocks.  When a player must decide something it appends a
PendingChoice to the pending stack and returns; a test script, an AI or the web
client then answers it with the selected option ids.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

from .errors import ChoiceError
from .enums import ChoiceKind


@dataclass(frozen=True)
class ChoiceOption:
    """A single selectable answer."""

    id: str
    label: str
    detail: str | None = None
    disabled: bool = False
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChoiceAnswer:
    choice_id: str
    selected: tuple[str, ...] = ()
    cancelled: bool = False


@dataclass
class PendingChoice:
    """A question waiting for an answer."""

    id: str
    kind: ChoiceKind
    player_id: str
    prompt: str
    options: list[ChoiceOption] = field(default_factory=list)
    min_selected: int = 1
    max_selected: int = 1
    optional: bool = False
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def is_multi(self) -> bool:
        return self.max_selected != 1 or self.min_selected != 1

    @property
    def must_answer(self) -> bool:
        """True when the player cannot decline the choice outright.

        min_selected governs how many options must be picked once the player
        decides to answer; optional governs whether declining is allowed at all.
        """
        return not self.optional

    def option(self, option_id: str) -> ChoiceOption:
        for opt in self.options:
            if opt.id == option_id:
                return opt
        raise ChoiceError(f"choice {self.id!r} has no option {option_id!r}")

    def validate(self, answer: ChoiceAnswer) -> tuple[str, ...]:
        """Check an answer against this question, returning the selected ids."""
        if answer.cancelled:
            if self.must_answer:
                raise ChoiceError(f"choice {self.id!r} cannot be cancelled")
            return ()
        if answer.choice_id != self.id:
            raise ChoiceError(f"answer for {answer.choice_id!r} does not match pending choice {self.id!r}")
        selected = answer.selected
        if len(set(selected)) != len(selected):
            raise ChoiceError(f"choice {self.id!r} received duplicate selections")
        if len(selected) < self.min_selected:
            raise ChoiceError(f"choice {self.id!r} needs at least {self.min_selected} selection(s)")
        if len(selected) > self.max_selected:
            raise ChoiceError(f"choice {self.id!r} accepts at most {self.max_selected} selection(s)")
        for option_id in selected:
            opt = self.option(option_id)
            if opt.disabled:
                raise ChoiceError(f"option {option_id!r} of choice {self.id!r} is not available")
        return selected


def choose_one(
    choice_id: str,
    player_id: str,
    prompt: str,
    options: list[ChoiceOption],
    **payload: Any,
) -> PendingChoice:
    return PendingChoice(
        id=choice_id,
        kind=ChoiceKind.OPTION,
        player_id=player_id,
        prompt=prompt,
        options=options,
        min_selected=1,
        max_selected=1,
        payload=payload,
    )


def confirm(choice_id: str, player_id: str, prompt: str, *, yes: str = "是", no: str = "否") -> PendingChoice:
    return PendingChoice(
        id=choice_id,
        kind=ChoiceKind.CONFIRM,
        player_id=player_id,
        prompt=prompt,
        options=[ChoiceOption("yes", yes), ChoiceOption("no", no)],
        min_selected=1,
        max_selected=1,
    )


def asdict(choice: PendingChoice) -> dict[str, Any]:
    return dataclasses.asdict(choice)

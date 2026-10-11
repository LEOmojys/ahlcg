"""The context handed to card abilities.

Card effects are ordinary generator functions: they may call the helper methods
here, each of which yields a PendingChoice and receives the player's answer.
That keeps card text readable while the engine keeps control of timing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generator, Iterable, Sequence

from ..core.cards import CardInstance
from ..core.choices import ChoiceOption, PendingChoice
from ..core.enums import ChoiceKind, Skill, TokenType
from ..core.events import GameEvent

if TYPE_CHECKING:  # pragma: no cover
    from .game import Game
    from .state import Player


@dataclass
class EffectContext:
    """What an ability knows about the world when it resolves."""

    game: "Game"
    source: CardInstance | None = None
    controller: "Player | None" = None
    event: GameEvent | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    # -- shortcuts ------------------------------------------------------
    @property
    def state(self):
        return self.game.state

    def card(self, card_id: str) -> CardInstance:
        return self.state.cards[card_id]

    @property
    def investigator(self) -> CardInstance | None:
        if self.controller is not None:
            return self.state.maybe_card(self.controller.investigator_id)
        return None

    def get(self, key: str, default: Any = None) -> Any:
        return self.payload.get(key, default)

    # -- interaction ----------------------------------------------------
    def ask(self, choice: PendingChoice) -> Generator[PendingChoice, tuple[str, ...], tuple[str, ...]]:
        return (yield choice)

    def ask_yes_no(self, prompt: str, *, optional: bool = True) -> Generator[PendingChoice, tuple[str, ...], bool]:
        choice = PendingChoice(
            id=self.game.next_choice_id(),
            kind=ChoiceKind.CONFIRM,
            player_id=self.controller.id if self.controller else "0",
            prompt=prompt,
            options=[ChoiceOption("yes", "是"), ChoiceOption("no", "否")],
            optional=optional,
        )
        picked = yield from self.ask(choice)
        return "yes" in picked

    def ask_option(self, prompt: str, options: Sequence[tuple[str, str]]) -> Generator[PendingChoice, tuple[str, ...], str]:
        choice = PendingChoice(
            id=self.game.next_choice_id(),
            kind=ChoiceKind.OPTION,
            player_id=self.controller.id if self.controller else "0",
            prompt=prompt,
            options=[ChoiceOption(value, label) for value, label in options],
        )
        picked = yield from self.ask(choice)
        return picked[0] if picked else ""

    def log(self, text: str, kind: str = "info") -> None:
        self.state.log(text, kind=kind)

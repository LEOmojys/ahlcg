"""A simple, deterministic policy.

It is not a good Arkham player - it exists so the whole engine can be exercised
without a human: seeded games, regression runs and the "auto play" button.
"""

from __future__ import annotations

from ..core.choices import ChoiceAnswer
from ..core.enums import CardType, ChoiceKind, Zone

PRIORITY = (
    ("advance_act", 100),
    ("parley:", 95),
    ("investigate", 80),
    ("fight:", 70),
    ("evade:", 60),
    ("play:", 50),
    ("activate:", 40),
    ("engage:", 35),
    ("move:", 30),
    ("draw", 20),
    ("resource", 15),
    ("resign", 5),
)


def score(option_id: str) -> int:
    for prefix, value in PRIORITY:
        if option_id == prefix or option_id.startswith(prefix):
            return value
    if option_id == "pass":
        return 0
    return 10


def choose(game) -> ChoiceAnswer:
    """Pick an answer for whatever the engine is currently asking."""
    choice = game.awaiting
    if choice is None:
        raise RuntimeError("the game is not waiting for anything")

    if choice.kind is ChoiceKind.COMMIT:
        # never commit cards: keeps the robot fast and deterministic
        return ChoiceAnswer(choice.id, ())

    if choice.kind is ChoiceKind.CARDS and choice.min_selected == 0 and choice.optional:
        # optional multi-selects (mulligan, "you may discard ...") are declined
        return ChoiceAnswer(choice.id, ())

    usable = [o for o in choice.options if not o.disabled]
    if not usable:
        if choice.optional:
            return ChoiceAnswer(choice.id, cancelled=True)
        raise RuntimeError(f"no legal option for {choice.prompt!r}")

    if choice.kind is ChoiceKind.CONFIRM:
        # decline optional triggered abilities, accept mandatory confirmations
        for option in usable:
            if option.id == "no" and choice.optional:
                return ChoiceAnswer(choice.id, ("no",))
        return ChoiceAnswer(choice.id, (usable[0].id,))

    best = max(usable, key=lambda o: score(o.id))
    return ChoiceAnswer(choice.id, (best.id,))


def play(game, max_steps: int = 20000) -> dict:
    """Run the game to its end.  Returns a small report."""
    game.start()
    steps = 0
    while game.awaiting is not None and steps < max_steps and not game.state.finished:
        game.resolve(choose(game))
        steps += 1
    return {
        "steps": steps,
        "finished": game.state.finished,
        "resolution": game.state.resolution,
        "rounds": game.state.round,
        "pending": game.awaiting.prompt if game.awaiting else None,
    }

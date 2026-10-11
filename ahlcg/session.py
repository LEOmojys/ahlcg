"""Assemble a playable game: cards, deck, chaos bag, scenario."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .core.enums import Zone
from .core.rng import Rng
from .data.deck import DeckList, build_starter_deck, ensure_codes_exist
from .data.pool import CardPool
from .engine.chaos import AUTOFAIL, CULTIST, ELDER_SIGN, SKULL, TABLET, ChaosBag, numeric
from .engine.game import Game
from .engine.state import GameState, Player
from .scenarios import load_scenario

#: Chaos bag composition per difficulty, from the Night of the Zealot campaign guide.
CHAOS_BAGS: dict[str, tuple] = {
    "easy": (
        numeric(1), numeric(1), numeric(0), numeric(0), numeric(0),
        numeric(-1), numeric(-1), numeric(-1), numeric(-2), numeric(-2),
        SKULL, SKULL, CULTIST, TABLET, AUTOFAIL, ELDER_SIGN,
    ),
    "standard": (
        numeric(1), numeric(0), numeric(0), numeric(-1), numeric(-1), numeric(-1),
        numeric(-2), numeric(-2), numeric(-3), numeric(-4),
        SKULL, SKULL, CULTIST, TABLET, AUTOFAIL, ELDER_SIGN,
    ),
    "hard": (
        numeric(0), numeric(0), numeric(0), numeric(-1), numeric(-1), numeric(-2),
        numeric(-2), numeric(-3), numeric(-3), numeric(-4), numeric(-5),
        SKULL, SKULL, CULTIST, TABLET, AUTOFAIL, ELDER_SIGN,
    ),
    "expert": (
        numeric(0), numeric(-1), numeric(-1), numeric(-2), numeric(-2), numeric(-3),
        numeric(-3), numeric(-4), numeric(-4), numeric(-5), numeric(-6), numeric(-8),
        SKULL, SKULL, CULTIST, TABLET, AUTOFAIL, ELDER_SIGN,
    ),
}

DIFFICULTIES: tuple[str, ...] = ("easy", "standard", "hard", "expert")


def build_chaos_bag(difficulty: str = "standard") -> ChaosBag:
    if difficulty not in CHAOS_BAGS:
        raise KeyError(f"unknown difficulty {difficulty!r}; known: {sorted(CHAOS_BAGS)}")
    return ChaosBag(tokens=list(CHAOS_BAGS[difficulty]))


@dataclass
class GameSetup:
    """Everything needed to start one scenario."""

    pool: CardPool
    #: an explicit deck; when omitted a legal starter deck is built for the investigator
    deck: DeckList | None = None
    investigator: str = "01001"
    scenario: str = "torch"
    difficulty: str = "standard"
    seed: int | None = 0
    player_name: str = "调查员"
    opening_hand: int = 5
    starting_resources: int = 5
    #: scenario switches handed down by the campaign layer (see SPEC.md)
    flags: dict[str, Any] = field(default_factory=dict)
    #: offer the opening-hand mulligan.  Off by default so headless drivers and
    #: tests see the first investigation prompt straight after start().
    mulligan: bool = False
    #: enforce support slot limits when playing assets (same rationale as above)
    slot_limits: bool = False
    #: permanent trauma becomes starting damage / horror
    trauma: tuple[int, int] = (0, 0)
    #: story assets granted by earlier scenarios
    extra_cards: tuple[str, ...] = ()


def create_game(setup: GameSetup) -> Game:
    pool = setup.pool
    deck = setup.deck or build_starter_deck(pool, setup.investigator, rng=Rng(setup.seed or 0))
    ensure_codes_exist(deck, pool)
    if not pool.has(deck.investigator):
        raise KeyError(f"unknown investigator code {deck.investigator!r}")

    state = GameState(
        seed=setup.seed,
        rng=Rng(setup.seed),
        difficulty=setup.difficulty,
        chaos_bag=build_chaos_bag(setup.difficulty),
    )
    state.flags.update(dict(setup.flags))
    state.flags["mulligan"] = bool(setup.mulligan)
    state.flags["slot_limits"] = bool(setup.slot_limits)

    player = Player(id="p1", name=setup.player_name)
    state.players.append(player)

    investigator = state.add_card(
        pool.get(deck.investigator), owner_id=player.id, controller_id=player.id, zone=Zone.PLAY
    )
    player.investigator_id = investigator.id
    investigator.damage = max(0, int(setup.trauma[0]))
    investigator.horror = max(0, int(setup.trauma[1]))
    player.resources = setup.starting_resources

    for code in deck.cards:
        state.add_card(pool.get(code), owner_id=player.id, zone=Zone.DECK)
    for code in setup.extra_cards:
        card = state.add_card(pool.get(code), owner_id=player.id, zone=Zone.SET_ASIDE)
        player.set_aside.append(card.id)
    deck_ids = [c.id for c in state.cards.values() if c.owner_id == player.id and c.zone is Zone.DECK]
    state.rng.shuffle(deck_ids)
    player.deck = deck_ids

    scenario = load_scenario(setup.scenario, pool)
    game = Game(state, scenario)
    for _ in range(setup.opening_hand):
        if not player.deck:
            break
        card_id = player.deck.pop(0)
        state.cards[card_id].zone = Zone.HAND
        player.hand.append(card_id)
    return game


def deal_opening_hand(game: Game, player: Player, count: int = 5) -> None:
    state = game.state
    for _ in range(count):
        if not player.deck:
            break
        card_id = player.deck.pop(0)
        state.cards[card_id].zone = Zone.HAND
        player.hand.append(card_id)

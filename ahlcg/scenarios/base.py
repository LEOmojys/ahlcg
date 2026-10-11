"""Scenario framework.

A scenario is data (which cards, which locations, how they connect) plus a few
generator methods for its special rules.  The helpers here cover the repetitive
parts: laying out locations, building the encounter deck from encounter sets,
and installing scenario level abilities at the right timing points.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from ..core.cards import Ability, CardInstance
from ..core.enums import CardType, Phase, Trigger, Zone
from ..core.errors import CardDataError
from ..data.pool import CardPool


class Scenario:
    """Base class for playable scenarios."""

    code: str = ""
    name: str = ""
    campaign: str = ""

    def __init__(self, pool: CardPool) -> None:
        self.pool = pool

    # -- to implement ---------------------------------------------------
    def setup(self, game):  # pragma: no cover - abstract
        raise NotImplementedError
        yield  # make this a generator

    # -- layout helpers -------------------------------------------------
    def clues_for(self, defn, players: int) -> int:
        if defn.clues_per_investigator:
            return int(defn.clues) * max(1, players)
        return int(defn.clues)

    def add_location(
        self,
        game,
        code: str,
        *,
        revealed: bool = False,
        connections: Sequence[str] = (),
        blocked: bool = False,
    ) -> CardInstance:
        state = game.state
        defn = self.pool.get(code)
        inst = state.add_card(defn, zone=Zone.PLAY)
        inst.meta["revealed"] = bool(revealed) or bool(defn.revealed)
        inst.meta["blocked"] = blocked
        inst.clues = self.clues_for(defn, len(state.players))
        if inst.id not in state.location_ids:
            state.location_ids.append(inst.id)
        state.connections.setdefault(inst.id, [])
        for connection in connections:
            state.connections[inst.id].append(connection)
        return inst

    def connect(self, game, a: str, b: str) -> None:
        state = game.state
        state.connections.setdefault(a, [])
        state.connections.setdefault(b, [])
        if b not in state.connections[a]:
            state.connections[a].append(b)
        if a not in state.connections[b]:
            state.connections[b].append(a)

    def add_act(self, game, code: str) -> CardInstance:
        state = game.state
        inst = state.add_card(self.pool.get(code), zone=Zone.PLAY)
        state.act_deck.append(inst.id)
        return inst

    def add_agenda(self, game, code: str) -> CardInstance:
        state = game.state
        inst = state.add_card(self.pool.get(code), zone=Zone.PLAY)
        state.agenda_deck.append(inst.id)
        return inst

    def set_aside(self, game, code: str) -> CardInstance:
        state = game.state
        inst = state.add_card(self.pool.get(code), zone=Zone.SET_ASIDE)
        state.set_aside.append(inst.id)
        return inst

    def find_card(self, game, code: str) -> CardInstance | None:
        for card in game.state.cards.values():
            if card.code == code:
                return card
        return None

    def bring_into_play(self, game, code: str, location_id: str | None = None) -> CardInstance:
        """Move a set-aside card into play (used by act/agenda advancement)."""
        card = self.find_card(game, code)
        if card is None:
            card = self.set_aside(game, code)
        card.zone = Zone.PLAY
        card.exhausted = False
        if location_id is not None:
            card.location_id = location_id
        return card

    # -- encounter deck -------------------------------------------------
    def build_encounter_deck(
        self,
        game,
        encounter_sets: Iterable[str],
        *,
        exclude: Iterable[str] = (),
        include: Iterable[str] = (),
        shuffle: bool = True,
    ) -> list[str]:
        state = game.state
        excluded = set(exclude)
        ids: list[str] = []
        for set_code in encounter_sets:
            for defn in self.pool.encounter_cards(set_code):
                if defn.code in excluded:
                    continue
                count = int(getattr(defn, "quantity", 1) or 1)
                for _ in range(count):
                    ids.append(state.add_card(defn, zone=Zone.ENCOUNTER_DECK).id)
        for code in include:
            defn = self.pool.get(code)
            ids.append(state.add_card(defn, zone=Zone.ENCOUNTER_DECK).id)
        if shuffle:
            state.rng.shuffle(ids)
        state.encounter_deck = ids
        return ids

    # -- scenario level abilities ---------------------------------------
    def install_abilities(self, game, abilities: Iterable[Ability]) -> None:
        for ability in abilities:
            trigger = ability.trigger
            if trigger is None:
                continue
            game.state.global_abilities.setdefault(trigger.value, []).append(ability)

    def install_token_modifier(self, game, modifier) -> None:
        game.state.chaos_bag.modifiers.append(modifier)

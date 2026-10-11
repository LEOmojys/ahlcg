"""The complete state of one game in progress.

Everything the engine needs to resume a game lives here.  Zones hold card ids
and the cards themselves live in one registry, so a card exists exactly once no
matter how many zone lists reference it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator, Sequence

from ..core.cards import CardDef, CardInstance
from ..core.choices import PendingChoice
from ..core.enums import CardType, Phase, Zone
from ..core.ids import IdGenerator
from ..core.rng import Rng
from .chaos import ChaosBag


@dataclass
class LogEntry:
    """One line of the game log."""

    text: str
    round: int = 0
    phase: str = ""
    kind: str = "info"
    cards: list[str] = field(default_factory=list)


@dataclass
class Player:
    """A player seat, owning one investigator."""

    id: str
    name: str
    investigator_id: str | None = None
    deck: list[str] = field(default_factory=list)
    hand: list[str] = field(default_factory=list)
    discard: list[str] = field(default_factory=list)
    play_area: list[str] = field(default_factory=list)
    threat_area: list[str] = field(default_factory=list)
    set_aside: list[str] = field(default_factory=list)
    resources: int = 0
    actions_left: int = 3
    defeated: bool = False
    resigned: bool = False
    killed: bool = False
    insane: bool = False
    trauma_physical: int = 0
    trauma_mental: int = 0
    xp_earned: int = 0
    victory_points: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return not self.defeated and not self.resigned


@dataclass
class GameState:
    """Mutable state of a single scenario run."""

    seed: int | None = None
    rng: Rng = field(default_factory=Rng)
    scenario_code: str = ""
    scenario_name: str = ""
    difficulty: str = "standard"
    players: list[Player] = field(default_factory=list)
    cards: dict[str, CardInstance] = field(default_factory=dict)
    ids: IdGenerator = field(default_factory=lambda: IdGenerator("c"))
    choice_ids: IdGenerator = field(default_factory=lambda: IdGenerator("choice"))

    # --- scenario layout
    location_ids: list[str] = field(default_factory=list)
    connections: dict[str, list[str]] = field(default_factory=dict)
    encounter_deck: list[str] = field(default_factory=list)
    encounter_discard: list[str] = field(default_factory=list)
    victory_display: list[str] = field(default_factory=list)
    act_deck: list[str] = field(default_factory=list)
    act_index: int = 0
    act_progress: int = 0
    agenda_deck: list[str] = field(default_factory=list)
    agenda_index: int = 0
    set_aside: list[str] = field(default_factory=list)

    # --- flow
    round: int = 0
    phase: Phase = Phase.MYTHOS
    active_index: int = 0
    pending: list[PendingChoice] = field(default_factory=list)
    #: the game log.  Named log_entries because a dataclass field cannot share a
    #: name with the log() method below (the field default would shadow it).
    log_entries: list[LogEntry] = field(default_factory=list)
    chaos_bag: ChaosBag = field(default_factory=ChaosBag)
    resolution: str | None = None
    finished: bool = False
    flags: dict[str, Any] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    #: scenario supplied abilities, keyed by trigger value, for the whole board
    global_abilities: dict[str, list[Any]] = field(default_factory=dict)
    skill_test: Any = None

    # -- construction helpers -------------------------------------------
    def add_card(
        self,
        defn: CardDef,
        *,
        owner_id: str | None = None,
        controller_id: str | None = None,
        zone: Zone = Zone.LIMBO,
        **kwargs: Any,
    ) -> CardInstance:
        inst = CardInstance(id=self.ids.next(), defn=defn, owner_id=owner_id, controller_id=controller_id, zone=zone)
        for key, value in kwargs.items():
            setattr(inst, key, value)
        if defn.uses and not inst.uses:
            inst.uses = dict(defn.uses)
        self.cards[inst.id] = inst
        return inst

    def add_cards(self, defn: CardDef, count: int, **kwargs: Any) -> list[CardInstance]:
        return [self.add_card(defn, **kwargs) for _ in range(count)]

    # -- lookup ---------------------------------------------------------
    def card(self, card_id: str) -> CardInstance:
        return self.cards[card_id]

    def maybe_card(self, card_id: str | None) -> CardInstance | None:
        return self.cards.get(card_id) if card_id else None

    def player(self, player_id: str) -> Player:
        for player in self.players:
            if player.id == player_id:
                return player
        raise KeyError(f"unknown player {player_id!r}")

    def player_of(self, card_or_id: CardInstance | str | None) -> Player | None:
        inst = self.maybe_card(card_or_id if isinstance(card_or_id, str) else None) if card_or_id else None
        if inst is None and isinstance(card_or_id, CardInstance):
            inst = card_or_id
        if inst is None:
            return None
        for player in self.players:
            if player.investigator_id == inst.id or inst.controller_id == player.id or inst.owner_id == player.id:
                return player
        return None

    @property
    def active_player(self) -> Player | None:
        if not self.players:
            return None
        return self.players[self.active_index % len(self.players)]

    def active_players_in_order(self) -> list[Player]:
        if not self.players:
            return []
        n = len(self.players)
        return [self.players[(self.active_index + i) % n] for i in range(n)]

    def set_active(self, player_id: str) -> None:
        for index, player in enumerate(self.players):
            if player.id == player_id:
                self.active_index = index
                return
        raise KeyError(f"unknown player {player_id!r}")

    def investigators(self) -> list[CardInstance]:
        out = []
        for player in self.players:
            inst = self.maybe_card(player.investigator_id)
            if inst is not None:
                out.append(inst)
        return out

    def investigator_of(self, player: Player) -> CardInstance:
        inst = self.maybe_card(player.investigator_id)
        if inst is None:
            raise KeyError(f"player {player.id!r} has no investigator")
        return inst

    # -- board ----------------------------------------------------------
    def locations(self) -> list[CardInstance]:
        return [self.cards[i] for i in self.location_ids if i in self.cards]

    def revealed_locations(self) -> list[CardInstance]:
        return [loc for loc in self.locations() if loc.meta.get("revealed")]

    def location_of(self, card_id: str) -> CardInstance | None:
        return self.maybe_card(card_id)

    def connections_of(self, location_id: str) -> list[str]:
        return list(self.connections.get(location_id, []))

    def enemies(self) -> list[CardInstance]:
        return [c for c in self.cards.values() if c.card_type is CardType.ENEMY and c.zone is Zone.PLAY]

    def enemies_at(self, location_id: str) -> list[CardInstance]:
        return [e for e in self.enemies() if e.location_id == location_id and not e.engaged_with]

    def engaged_enemies(self, player_id: str) -> list[CardInstance]:
        return [e for e in self.enemies() if player_id in e.engaged_with]

    def unengaged_enemies(self) -> list[CardInstance]:
        return [e for e in self.enemies() if not e.engaged_with]

    def assets_of(self, player_id: str) -> list[CardInstance]:
        player = self.player(player_id)
        return [self.cards[i] for i in player.play_area if i in self.cards]

    def threat_area_of(self, player_id: str) -> list[CardInstance]:
        player = self.player(player_id)
        return [self.cards[i] for i in player.threat_area if i in self.cards]

    def cards_in_play(self) -> list[CardInstance]:
        out = [c for c in self.cards.values() if c.zone is Zone.PLAY]
        return out

    def current_act(self) -> CardInstance | None:
        if 0 <= self.act_index < len(self.act_deck):
            return self.cards[self.act_deck[self.act_index]]
        return None

    def current_agenda(self) -> CardInstance | None:
        if 0 <= self.agenda_index < len(self.agenda_deck):
            return self.cards[self.agenda_deck[self.agenda_index]]
        return None

    def total_doom(self) -> int:
        total = 0
        for card in self.cards_in_play():
            total += card.doom
        agenda = self.current_agenda()
        if agenda is not None:
            total += agenda.doom
        return total

    # -- zones ----------------------------------------------------------
    def move_card(self, card_id: str, zone: Zone, controller_id: str | None = None) -> CardInstance:
        inst = self.cards[card_id]
        inst.zone = zone
        if controller_id is not None:
            inst.controller_id = controller_id
        return inst

    # -- logging --------------------------------------------------------
    def log(self, text: str, kind: str = "info", cards: Iterable[str] = ()) -> LogEntry:
        entry = LogEntry(text=text, round=self.round, phase=self.phase.value, kind=kind, cards=list(cards))
        self.log_entries.append(entry)
        return entry


def serialize_state(state: GameState) -> dict[str, Any]:
    """A trimmed, JSON-ready view of the state for the web client."""
    from ..core.serialization import to_jsonable

    return {
        "round": state.round,
        "phase": state.phase.value,
        "scenario": state.scenario_code,
        "scenario_name": state.scenario_name,
        "difficulty": state.difficulty,
        "resolution": state.resolution,
        "finished": state.finished,
        "active_player": state.active_player.id if state.active_player else None,
        "players": to_jsonable(state.players),
        "locations": [to_jsonable(state.cards[i]) for i in state.location_ids if i in state.cards],
        "connections": to_jsonable(state.connections),
        "enemies": to_jsonable(state.enemies()),
        "act": to_jsonable(state.current_act()),
        "agenda": to_jsonable(state.current_agenda()),
        "act_progress": state.act_progress,
        "total_doom": state.total_doom(),
        "encounter_deck": len(state.encounter_deck),
        "encounter_discard": len(state.encounter_discard),
        "chaos_bag": to_jsonable(state.chaos_bag.tokens),
        "log": to_jsonable(state.log_entries[-200:]),
    }

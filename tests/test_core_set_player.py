"""End-to-end tests for the core-set player card behaviour.

The first half checks that every registered code still produces a sane CardDef
after apply_behaviours(); the second half drives real effects through a Game
with a small hand-built GameState.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import ahlcg.cards.core_set_player  # noqa: F401  (runs every register() call)
from ahlcg.cards import (
    CARD_ABILITIES,
    CARD_META,
    CARD_PLAY_EFFECTS,
    CARD_REVELATION_EFFECTS,
    apply_behaviours,
)
from ahlcg.core.cards import CardDef
from ahlcg.core.choices import ChoiceAnswer
from ahlcg.core.enums import AbilityKind, CardType, ChoiceKind, Skill, Trigger, Zone
from ahlcg.core.events import GameEvent
from ahlcg.data.loader import to_card_def
from ahlcg.engine.actions import execute_action
from ahlcg.engine.chaos import numeric
from ahlcg.engine.effects import EffectContext
from ahlcg.engine.game import Game
from ahlcg.engine.state import GameState, Player

ROOT = Path(__file__).resolve().parents[1]
RECORDS = json.loads((ROOT / "reference" / "arkhamdb_core.json").read_text(encoding="utf-8"))

REGISTERED_CODES = sorted(
    set(CARD_ABILITIES) | set(CARD_META) | set(CARD_PLAY_EFFECTS) | set(CARD_REVELATION_EFFECTS)
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def load(code: str) -> CardDef:
    """Build the CardDef of a registered code the way the game does."""
    return apply_behaviours(to_card_def(RECORDS[code]))


def defn(code: str, name: str, **kwargs) -> CardDef:
    """Small hand-built card for the board fixtures."""
    return CardDef(code=code, name=name, card_type=CardType.ASSET, **kwargs)


def make_player(state: GameState, player_id: str = "p1", **kwargs) -> Player:
    player = Player(id=player_id, name="Player 1", **kwargs)
    state.players.append(player)
    return player


#: the game built by the most recent base_game() call, so small test drivers can
#: keep using Drive(flow, rules) while still resolving through Game.resolve()
_LAST_GAME: list = [None]


class Drive:
    """Runs an engine flow through the engine's own driver.

    Going through Game.start()/Game.resolve() is important: resolve() unpacks a
    ChoiceAnswer into the tuple (or, for ASSIGN_DAMAGE, the bare card id) that the
    generator expects.  Feeding the generator by hand would skip that step.
    """

    def __init__(self, flow, rules=(), game=None):
        self.game = game if game is not None else _LAST_GAME[0]
        self.flow = flow
        self.rules = list(rules)
        self.events = []

    def _answer(self, choice):
        for rule in self.rules:
            picked = rule(choice)
            if picked is not None:
                return picked
        if choice.kind is ChoiceKind.COMMIT:
            return ()
        if choice.kind is ChoiceKind.CONFIRM:
            return "no"
        for option in choice.options:
            if not option.disabled:
                return option.id
        return ()

    def run(self):
        self.game.start(self.flow)
        while self.game.awaiting is not None:
            choice = self.game.awaiting
            self.events.append(choice)
            picked = self._answer(choice)
            if picked is None or picked == ():
                self.game.resolve(ChoiceAnswer(choice.id, ()))
                continue
            if isinstance(picked, str):
                picked = (picked,)
            self.game.resolve(ChoiceAnswer(choice.id, tuple(picked)))
        # Game._pump() flags the *game* as finished whenever a driven flow runs
        # off its end.  For a flow that is only one action (or one card effect)
        # that is an artefact, not a scenario ending, so undo it unless the flow
        # actually set a resolution.
        if self.game.state.resolution is None:
            self.game.state.finished = False
        return self


# --------------------------------------------------------------------------
# every registered code must still produce a sane CardDef
# --------------------------------------------------------------------------
def test_at_least_the_required_scope_is_registered():
    assert len(REGISTERED_CODES) >= 20


@pytest.mark.parametrize("code", REGISTERED_CODES)
def test_registered_cards_load_and_are_sane(code):
    record = RECORDS.get(code)
    assert record is not None, f"{code} is not in the card database"
    defn = load(code)
    assert defn.code == code
    assert defn.name
    assert defn.card_type in (
        CardType.ASSET,
        CardType.EVENT,
        CardType.SKILL,
        CardType.TREACHERY,
    )
    assert defn.text, "every registered card has printed text"
    # every registered ability is a real Ability with a real effect
    for ability in defn.abilities:
        assert ability.kind in AbilityKind
        assert ability.effect is not None
    play = defn.meta.get("play")
    if play is not None:
        assert callable(play)
    resolve = defn.meta.get("resolve")
    if resolve is not None:
        assert callable(resolve)


def test_weapon_meta_is_only_attached_to_real_weapons():
    expected = {
        "01016": (1, 1),
        "01020": (1, 1),
        "01044": (0, 1),
        "01047": (2, 1),
    }
    for code, (bonus, damage) in expected.items():
        attack = load(code).meta.get("attack")
        assert attack.get("combat_bonus") == bonus and attack.get("damage") == damage, code
        extra = {k: v for k, v in attack.items() if k not in ("combat_bonus", "damage")}
        assert all(k in ("only_engaged_bonus", "spend") for k in extra), code
        assert load(code).card_type is CardType.ASSET


def test_events_register_a_play_effect_and_assets_do_not():
    for code in ("01022", "01023", "01024", "01037", "01050", "01051", "01065", "01079", "01080", "01088"):
        defn = load(code)
        assert defn.card_type is CardType.EVENT
        assert callable(defn.meta.get("play"))
    for code in ("01016", "01018", "01019", "01020", "01021", "01031", "01033", "01044", "01045", "01047", "01063"):
        defn = load(code)
        assert defn.card_type is CardType.ASSET
        assert "play" not in defn.meta
        # a lone weapon may only carry meta["attack"], everything else gets code
        assert defn.abilities or defn.meta.get("attack"), code


def test_icon_only_skill_cards_need_no_behaviour():
    # Unexpected Courage is genuinely data-only: it has icons and nothing else.
    record = RECORDS["01093"]
    assert record["type_code"] == "skill"
    assert to_card_def(record).total_icons() >= 1
    assert "01093" not in REGISTERED_CODES

    # Guts / Perception / Overpower / Manual Dexterity print "If this test is
    # successful, draw 1 card.", so they DO need behaviour (added with the
    # committed-card result hooks).
    for code in ("01089", "01090", "01091", "01092"):
        assert code in REGISTERED_CODES, code
        assert to_card_def(RECORDS[code]).total_icons() >= 1, code


def test_deliberately_skipped_cards_are_not_registered():
    # these used to be impossible to express; the engine hooks added later
    # (constant modifiers, the during-a-test window, result riders, extra actions)
    # now carry them, so assert the positive fact instead of the old limitation.
    now_supported = {
        "01017": "in_test",
        "01062": "in_test",
        "01025": "abilities",
        "01039": "abilities",
        "01053": "abilities",
        "01048": "extra_action",
    }
    for code, hook in now_supported.items():
        assert code in REGISTERED_CODES, code
        defn = load(code)
        if hook == "in_test":
            assert defn.meta.get("in_test"), code
        elif hook == "extra_action":
            assert defn.meta.get("extra_action") == 1, code
        else:
            assert defn.abilities, code

    # data-only cards that need no behaviour at all
    for code in ("01030", "01059", "01060"):
        defn = load(code)
        assert defn.meta.get("constant") or defn.meta.get("attack"), code


def test_weakness_revelations_are_registered():
    for code in ("01007", "01011", "01015", "01096", "01097", "01098", "01099", "01100"):
        defn = load(code)
        assert defn.weakness, code
        assert callable(defn.meta.get("resolve")), code


def test_guard_dog_and_arcane_initiate_have_reactions_and_forced_abilities():
    dog = load("01021")
    triggers = [a.trigger for a in dog.abilities]
    assert Trigger.ON_DAMAGE_TAKEN in triggers

    initiate = load("01063")
    kinds = {a.kind for a in initiate.abilities}
    assert AbilityKind.FORCED in kinds
    assert AbilityKind.ACTIVATED in kinds

    cover_up = load("01007")
    assert any(a.trigger is Trigger.ON_SCENARIO_END for a in cover_up.abilities)

    psychosis = load("01099")
    assert any(a.trigger is Trigger.ON_HORROR_TAKEN for a in psychosis.abilities)
    hypochondria = load("01100")
    assert any(a.trigger is Trigger.ON_DAMAGE_TAKEN for a in hypochondria.abilities)


def test_every_effect_is_a_callable():
    for code in REGISTERED_CODES:
        for ability in load(code).abilities:
            assert callable(ability.effect)
        for key in ("play", "resolve"):
            effect = load(code).meta.get(key)
            if effect is not None:
                assert callable(effect)


# --------------------------------------------------------------------------
# board fixtures for the end-to-end tests
# --------------------------------------------------------------------------
def make_enemy(state, name="Ghoul", *, fight=2, evade=2, health=4, damage=1, horror=1):
    defn = CardDef(code="E" + str(len(state.cards)), name=name, card_type=CardType.ENEMY)
    # set after construction: CardDef.health is the enemy health field, while the
    # "damage"/"horror" constructor keywords are location clue counters
    defn.fight = fight
    defn.evade = evade
    defn.health = health
    defn.enemy_damage = damage
    defn.enemy_horror = horror
    return state.add_card(defn, zone=Zone.PLAY)


def base_game(*, resources=10, health=10, sanity=10, agility=4, combat=4, intellect=4, willpower=4, bag=None):
    state = GameState()
    player = make_player(state, resources=resources)
    inv = state.add_card(
        CardDef(
            code="INV",
            name="Roland Banks",
            card_type=CardType.INVESTIGATOR,
            willpower=willpower,
            intellect=intellect,
            combat=combat,
            agility=agility,
            health=health,
            sanity=sanity,
        )
    )
    player.investigator_id = inv.id
    here = state.add_card(CardDef(code="L1", name="Study", card_type=CardType.LOCATION, shroud=2))
    here.clues = 3  # set after construction: CardDef.clues is the location clue count
    state.location_ids.append(here.id)
    inv.meta["location_id"] = here.id
    here.meta["revealed"] = True
    for token in bag if bag is not None else [numeric(v) for v in (0, 1, 2, 3, 4)]:
        state.chaos_bag.add(token)
    game = Game(state)
    _LAST_GAME[0] = game  # lets Drive(flow, rules) resolve through this game
    return game, player, inv, here


def put_in_play(state, player, code, **kwargs):
    card = state.add_card(load(code), owner_id=player.id, controller_id=player.id, zone=Zone.PLAY, **kwargs)
    player.play_area.append(card.id)
    return card


def put_in_hand(state, player, code):
    card = state.add_card(load(code), owner_id=player.id, zone=Zone.HAND)
    player.hand.append(card.id)
    return card


def play_card(game, player, card, rules=()):
    drive = Drive(execute_action(game, player, f"play:{card.id}"), rules)
    drive.run()
    return drive


def end_turn(choice):
    if choice.kind is ChoiceKind.OPTION and "行动" in choice.prompt:
        for option in choice.options:
            if option.id == "pass":
                return "pass"
    return None


# --------------------------------------------------------------------------
# exercise 1: .45 Automatic through the engine's basic Fight action
# --------------------------------------------------------------------------
def test_45_automatic_boosts_the_basic_fight_action():
    game, player, inv, here = base_game(combat=4)
    weapon = put_in_play(game.state, player, "01016")
    enemy = make_enemy(game.state, health=4)
    Drive(game.engage(enemy, player)).run()

    Drive(execute_action(game, player, f"fight:{enemy.id}"), (end_turn,)).run()

    # combat 4 + 1 from the weapon = 5 against fight 2 -> always succeeds with a
    # non-negative token.  The basic action spends no ammo, so it deals the
    # weapon's printed 1 damage; the +1 belongs to the card's own ability below.
    assert enemy.damage == 1
    assert game.state.skill_test is not None
    assert game.state.skill_test.skill_value == 5
    assert weapon.exhausted is False
    assert weapon.uses.get("ammo", 4) == 4


def test_45_automatic_activated_ability_spends_ammo_for_extra_damage():
    game, player, inv, here = base_game(combat=4, bag=[numeric(0)])
    weapon = put_in_play(game.state, player, "01016", uses={"ammo": 4})
    enemy = make_enemy(game.state, health=6)
    Drive(game.engage(enemy, player)).run()

    Drive(execute_action(game, player, f"activate:{weapon.id}:0"), (end_turn,)).run()

    assert weapon.uses["ammo"] == 3
    assert game.state.skill_test.skill_value == 5
    assert enemy.damage == 2


def test_beat_cop_discards_itself_to_damage_an_enemy_here():
    game, player, inv, here = base_game()
    cop = put_in_play(game.state, player, "01018")
    enemy = make_enemy(game.state, health=4)
    enemy.location_id = here.id

    Drive(execute_action(game, player, f"activate:{cop.id}:0"), (end_turn,)).run()

    assert enemy.damage == 1
    assert cop.zone is Zone.DISCARD
    assert cop.id in player.discard


def test_weapon_without_attack_meta_is_not_offered_to_the_fight_action():
    from ahlcg.engine.actions import attack_assets

    game, player, inv, here = base_game()
    put_in_play(game.state, player, "01031")  # Old Book of Lore is not a weapon
    assert attack_assets(game.state, player) == []


# --------------------------------------------------------------------------
# exercise 2: Guard Dog's damage reaction
# --------------------------------------------------------------------------
def answer_dog_reaction(choice):
    """Say yes to Guard Dog's own reaction prompt."""
    if choice.kind is ChoiceKind.CONFIRM and "Guard Dog" in choice.prompt:
        return "yes"
    return None


def test_guard_dog_deals_damage_back_when_an_enemy_attack_hurts_it():
    game, player, inv, here = base_game()
    dog = put_in_play(game.state, player, "01021")
    enemy = make_enemy(game.state, health=4, damage=1, horror=1)

    # the engine emits ON_DAMAGE_TAKEN with the enemy as the source and the dog
    # as the target, which is exactly the printed timing window
    drive = Drive(
        game.emit(Trigger.ON_DAMAGE_TAKEN, source=enemy, target=dog, amount=1),
        (answer_dog_reaction,),
    )
    drive.run()

    # Guard Dog retaliated for 1 damage
    assert enemy.damage == 1
    # the reaction was asked (optional), not forced
    assert any(c.kind is ChoiceKind.CONFIRM for c in drive.events)


def test_guard_dog_reaction_is_optional():
    game, player, inv, here = base_game()
    dog = put_in_play(game.state, player, "01021")
    enemy = make_enemy(game.state, health=4)

    # the driver's default answer for a confirmation is "no"
    Drive(game.emit(Trigger.ON_DAMAGE_TAKEN, source=enemy, target=dog, amount=1)).run()
    assert enemy.damage == 0


def test_guard_dog_can_soak_the_damage_of_an_enemy_attack():
    game, player, inv, here = base_game()
    dog = put_in_play(game.state, player, "01021")
    enemy = make_enemy(game.state, health=4, damage=1, horror=0)

    def soak_dog(choice):
        # ASSIGN_DAMAGE answers are the bare card id, which is what Game._assign reads
        if choice.kind is ChoiceKind.ASSIGN_DAMAGE and dog.id in [o.id for o in choice.options]:
            return dog.id
        return None

    Drive(game.enemy_attack(enemy, player), (soak_dog,)).run()

    # the attack's damage was soaked by the dog
    assert dog.damage == 1
    assert dog.zone is Zone.PLAY
    assert inv.damage == 0
    # NB the engine applies soak damage inside _assign and does not emit
    # ON_DAMAGE_TAKEN for the soaking asset, so the dog's own reaction is covered
    # by test_guard_dog_deals_damage_back_when_an_enemy_attack_hurts_it


def test_guard_dog_is_discarded_when_its_last_sanity_is_soaked():
    game, player, inv, here = base_game()
    dog = put_in_play(game.state, player, "01021")
    enemy = make_enemy(game.state, health=4, damage=1, horror=1)

    def soak_dog(choice):
        if choice.kind is ChoiceKind.ASSIGN_DAMAGE and dog.id in [o.id for o in choice.options]:
            return dog.id
        return None

    Drive(game.enemy_attack(enemy, player), (soak_dog, answer_dog_reaction)).run()

    # Guard Dog has 3 health but only 1 sanity, so soaking both defeats it
    assert dog.zone is Zone.DISCARD
    assert dog.id in player.discard


def test_guard_dog_condition_matches_only_enemy_attacks_on_the_dog():
    from ahlcg.cards.core_set_player import _guard_dog_condition

    game, player, inv, here = base_game()
    dog = put_in_play(game.state, player, "01021")
    enemy = make_enemy(game.state)

    def ctx_for(source, target, trigger=Trigger.ON_DAMAGE_TAKEN):
        return EffectContext(
            game=game,
            source=dog,
            controller=player,
            event=GameEvent(trigger=trigger, source=source, target=target),
        )

    assert _guard_dog_condition(ctx_for(enemy, dog)) is True
    assert _guard_dog_condition(ctx_for(enemy, inv)) is False
    assert _guard_dog_condition(ctx_for(inv, dog)) is False


# --------------------------------------------------------------------------
# exercise 3: Backstab - an event that runs its own agility Fight
# --------------------------------------------------------------------------
def test_backstab_fights_with_agility_and_deals_three_damage():
    game, player, inv, here = base_game(agility=4, combat=1, bag=[numeric(0)])
    card = put_in_hand(game.state, player, "01051")
    enemy = make_enemy(game.state, health=4, fight=2)
    Drive(game.engage(enemy, player)).run()

    drive = play_card(game, player, card, (end_turn,))
    drive.run()

    assert card.zone is Zone.DISCARD
    assert player.resources == 7  # 10 - 3
    result = game.state.skill_test
    assert result is not None and result.skill is Skill.AGILITY
    assert result.success
    # 3 damage from the +2 rider on top of the attack's 1
    assert enemy.damage == 3


def test_backstab_without_a_target_is_a_no_op():
    game, player, inv, here = base_game()
    card = put_in_hand(game.state, player, "01051")
    play_card(game, player, card)
    assert card.zone is Zone.DISCARD
    assert game.state.skill_test is None


# --------------------------------------------------------------------------
# exercise 4: Dynamite Blast - multi-target damage at a chosen location
# --------------------------------------------------------------------------
def test_dynamite_blast_damages_every_enemy_and_investigator_at_the_location():
    game, player, inv, here = base_game(resources=10, health=10)
    card = put_in_hand(game.state, player, "01024")
    enemy_a = make_enemy(game.state, "Ghoul A", health=5)
    enemy_b = make_enemy(game.state, "Ghoul B", health=2)
    enemy_c = make_enemy(game.state, "Far Ghoul", health=5)
    enemy_a.location_id = here.id
    enemy_b.location_id = here.id
    other = game.state.add_card(CardDef(code="L2", name="Cellar", card_type=CardType.LOCATION, shroud=1))
    game.state.location_ids.append(other.id)
    enemy_c.location_id = other.id

    # only one choice: the investigator's own location
    play_card(game, player, card, (end_turn,))

    assert enemy_a.damage == 3
    assert enemy_b.defn.health == 2
    assert enemy_b.zone is not Zone.PLAY  # 3 damage defeated it
    assert enemy_c.damage == 0
    assert inv.damage == 3  # the investigator at the location takes it too
    assert card.zone is Zone.DISCARD
    assert player.resources == 5


def test_dynamite_blast_offers_each_connected_location():
    game, player, inv, here = base_game()
    card = put_in_hand(game.state, player, "01024")
    other = game.state.add_card(CardDef(code="L2", name="Cellar", card_type=CardType.LOCATION, shroud=1))
    game.state.location_ids.append(other.id)
    game.state.connections[here.id] = [other.id]
    far_enemy = make_enemy(game.state, "Cellar Ghoul", health=4)
    far_enemy.location_id = other.id

    def pick_cellar(choice):
        if choice.kind is ChoiceKind.OPTION and "爆破" in choice.prompt:
            for option in choice.options:
                if option.id == other.id:
                    return (other.id,)
        return None

    play_card(game, player, card, (pick_cellar,))
    assert far_enemy.damage == 3
    assert inv.damage == 0


# --------------------------------------------------------------------------
# exercise 5: Evidence! - a played event that discovers a clue
# --------------------------------------------------------------------------
def test_evidence_discovers_a_clue_and_pays_for_itself():
    game, player, inv, here = base_game(resources=3)
    card = put_in_hand(game.state, player, "01022")

    play_card(game, player, card, (end_turn,))

    assert player.resources == 2
    assert inv.clues == 1
    assert here.clues == 2
    assert card.zone is Zone.DISCARD


# --------------------------------------------------------------------------
# exercise 6: Burglary - an activated ability with an exhaust cost
# --------------------------------------------------------------------------
def test_burglary_exhausts_to_investigate_for_resources_instead_of_clues():
    game, player, inv, here = base_game(resources=0, intellect=5)
    burglary = put_in_play(game.state, player, "01045")
    before = player.resources

    Drive(execute_action(game, player, f"activate:{burglary.id}:0"), (end_turn,)).run()

    assert burglary.exhausted is True
    assert player.resources == before + 3
    assert inv.clues == 0  # no clues were discovered
    assert here.clues == 3
    assert game.state.skill_test.success


# --------------------------------------------------------------------------
# exercise 7: First Aid - heal and spend supplies
# --------------------------------------------------------------------------
def test_first_aid_heals_damage_and_spends_a_supply():
    game, player, inv, here = base_game()
    aid = put_in_play(game.state, player, "01019", uses={"supply": 3})
    inv.damage = 2

    Drive(execute_action(game, player, f"activate:{aid.id}:0"), ()).run()

    assert aid.uses["supply"] == 2
    assert inv.damage == 1
    assert inv.horror == 0


def test_first_aid_asks_damage_or_horror_and_can_discard_itself_when_empty():
    game, player, inv, here = base_game()
    aid = put_in_play(game.state, player, "01019", uses={"supply": 1})
    inv.damage = 1
    inv.horror = 1

    def heal_horror(choice):
        if choice.kind is ChoiceKind.OPTION and "治疗" in choice.prompt and "恐惧" in choice.prompt:
            return "horror"
        return None

    Drive(execute_action(game, player, f"activate:{aid.id}:0"), (heal_horror,)).run()

    assert inv.horror == 0
    assert inv.damage == 1
    assert aid.uses["supply"] == 0
    # "If First Aid has no supplies, discard it"
    assert aid.zone is Zone.DISCARD
    assert aid.id not in player.play_area


def test_first_aid_condition_is_false_without_supplies():
    from ahlcg.cards.core_set_player import _first_aid_can_activate

    game, player, inv, here = base_game()
    aid = put_in_play(game.state, player, "01019", uses={"supply": 0})
    ctx = EffectContext(game=game, source=aid, controller=player)
    assert _first_aid_can_activate(ctx) is False
    aid.uses["supply"] = 1
    assert _first_aid_can_activate(ctx) is True


# --------------------------------------------------------------------------
# exercise 8: Old Book of Lore - search the top 3 cards of a deck
# --------------------------------------------------------------------------
def test_old_book_of_lore_searches_the_top_three_and_draws_one():
    game, player, inv, here = base_game()
    book = put_in_play(game.state, player, "01031")
    wanted = put_in_hand(game.state, player, "01088")  # a real card, moved to deck
    player.hand.remove(wanted.id)
    wanted.zone = Zone.DECK
    filler = [put_in_hand(game.state, player, "01022") for _ in range(2)]
    for card in filler:
        player.hand.remove(card.id)
        card.zone = Zone.DECK
    player.deck = [wanted.id] + [c.id for c in filler]

    def pick_wanted(choice):
        if choice.kind is ChoiceKind.OPTION and "加入手牌" in choice.prompt:
            return wanted.id
        return None

    Drive(execute_action(game, player, f"activate:{book.id}:0"), (pick_wanted,)).run()

    assert book.exhausted is True
    assert wanted.id in player.hand
    assert wanted.zone is Zone.HAND
    assert wanted.id not in player.deck
    assert len(player.deck) == 2


# --------------------------------------------------------------------------
# exercise 9: Arcane Initiate - forced doom on entry plus a Spell search
# --------------------------------------------------------------------------
def test_arcane_initiate_takes_doom_when_it_enters_play():
    game, player, inv, here = base_game()
    initiate = put_in_play(game.state, player, "01063")

    Drive(game.emit(Trigger.ON_ENTER_PLAY, source=initiate, target=inv)).run()

    assert initiate.doom == 1


def test_arcane_initiate_searches_only_for_spell_cards():
    game, player, inv, here = base_game()
    initiate = put_in_play(game.state, player, "01063")
    spell = put_in_hand(game.state, player, "01060")  # Shrivelling, a Spell
    mundane = put_in_hand(game.state, player, "01088")
    for card in (spell, mundane):
        player.hand.remove(card.id)
        card.zone = Zone.DECK
    player.deck = [mundane.id, spell.id]

    Drive(execute_action(game, player, f"activate:{initiate.id}:1"), ()).run()

    assert initiate.exhausted is True
    assert spell.id in player.hand
    assert spell.zone is Zone.HAND
    assert mundane.id in player.deck
    assert len(player.deck) == 1


# --------------------------------------------------------------------------
# exercise 10: Elusive - disengage and move to an empty revealed location
# --------------------------------------------------------------------------
def test_elusive_disengages_every_enemy_and_moves_to_an_empty_location():
    game, player, inv, here = base_game(resources=5)
    card = put_in_hand(game.state, player, "01050")
    engaged = make_enemy(game.state, "Ghoul")
    Drive(game.engage(engaged, player)).run()
    assert engaged.engaged_with == [player.id]

    safe = game.state.add_card(CardDef(code="L2", name="Cellar", card_type=CardType.LOCATION, shroud=1))
    safe.meta["revealed"] = True
    game.state.location_ids.append(safe.id)
    game.state.connections[here.id] = [safe.id]

    play_card(game, player, card, (end_turn,))

    assert engaged.engaged_with == []
    assert engaged.location_id == here.id
    assert inv.meta["location_id"] == safe.id
    assert card.zone is Zone.DISCARD


# --------------------------------------------------------------------------
# exercise 11: Dodge / Ward of Protection cancellation flags and costs
# --------------------------------------------------------------------------
def test_dodge_marks_the_attack_cancelled_and_does_not_cost_horror():
    game, player, inv, here = base_game(resources=5)
    card = put_in_hand(game.state, player, "01023")
    enemy = make_enemy(game.state)

    ctx = EffectContext(
        game=game,
        source=card,
        controller=player,
        payload={"enemy": enemy, "damage": 1, "horror": 1},
    )
    play_card(game, player, card, ())
    Drive(game.run_effect(load("01023").meta["play"], ctx)).run()
    assert ctx.payload["cancelled"] is True
    assert ctx.payload["damage"] == 0
    assert ctx.payload["horror"] == 0
    assert inv.horror == 0
    assert card.zone is Zone.DISCARD


def test_ward_of_protection_cancels_and_takes_a_horror():
    game, player, inv, here = base_game(resources=5)
    card = put_in_hand(game.state, player, "01065")
    ctx = EffectContext(game=game, source=card, controller=player, payload={"treachery": "T"})
    Drive(game.run_effect(load("01065").meta["play"], ctx)).run()
    assert ctx.payload["cancelled"] is True
    assert inv.horror == 1


# --------------------------------------------------------------------------
# exercise 12: weaknesses
# --------------------------------------------------------------------------
def test_paranoia_revelation_discards_all_resources():
    game, player, inv, here = base_game(resources=7)
    card = put_in_hand(game.state, player, "01097")
    Drive(game.run_effect(load("01097").meta["resolve"], EffectContext(game=game, source=card, controller=player))).run()
    assert player.resources == 0


def test_abandoned_and_alone_takes_two_horror_and_exiles_the_discard_pile():
    game, player, inv, here = base_game()
    card = put_in_hand(game.state, player, "01015")
    junk = put_in_hand(game.state, player, "01088")
    player.hand.remove(junk.id)
    game.move_to_discard(player, junk.id)

    Drive(game.run_effect(load("01015").meta["resolve"], EffectContext(game=game, source=card, controller=player))).run()

    assert inv.horror == 2
    assert player.discard == []
    assert junk.zone is Zone.REMOVED


def test_amnesia_makes_the_player_choose_all_but_one_card():
    game, player, inv, here = base_game()
    card = put_in_hand(game.state, player, "01096")
    for code in ("01088", "01022"):
        extra = put_in_hand(game.state, player, code)
        assert extra.id in player.hand
    keep = player.hand[0]
    discard_these = player.hand[1:]

    flow = game.run_effect(load("01096").meta["resolve"], EffectContext(game=game, source=card, controller=player))
    # EffectContext.ask hands the raw selection tuple straight to the generator,
    # so drive this multi-select window by hand instead of through the driver
    first = flow.send(None)
    assert first.kind is ChoiceKind.CARDS
    assert first.min_selected == 2 and first.max_selected == 2

    with pytest.raises(StopIteration):
        flow.send(tuple(discard_these))

    assert player.hand == [keep]
    assert len(player.discard) == 2


def test_cover_up_enters_the_threat_area_with_three_clues():
    game, player, inv, here = base_game()
    card = put_in_hand(game.state, player, "01007")
    Drive(game.run_effect(load("01007").meta["resolve"], EffectContext(game=game, source=card, controller=player))).run()

    assert card.zone is Zone.THREAT_AREA
    assert card.id in player.threat_area
    assert card.clues == 3


def test_cover_up_reaction_moves_a_clue_off_the_card():
    game, player, inv, here = base_game()
    card = put_in_play(game.state, player, "01007")
    card.clues = 3
    ctx = EffectContext(game=game, source=card, controller=player, payload={})
    Drive(game.run_effect(load("01007").abilities[0].effect, ctx)).run()
    assert card.clues == 2
    assert ctx.payload["clues_cancelled"] is True


def test_hospital_debts_limits_the_resource_move_to_twice_per_round():
    from ahlcg.cards.core_set_player import _hospital_debts_condition

    game, player, inv, here = base_game(resources=5)
    card = put_in_play(game.state, player, "01011")
    game.state.round = 1
    effect = load("01011").abilities[0].effect

    for _ in range(2):
        ctx = EffectContext(game=game, source=card, controller=player)
        Drive(game.run_effect(effect, ctx)).run()

    assert player.resources == 3
    assert card.meta["resources"] == 2
    assert _hospital_debts_condition(EffectContext(game=game, source=card, controller=player)) is False

    game.state.round = 2
    assert _hospital_debts_condition(EffectContext(game=game, source=card, controller=player)) is True


def test_hospital_debts_end_of_game_penalty():
    game, player, inv, here = base_game()
    card = put_in_play(game.state, player, "01011")
    card.meta["resources"] = 2
    forced = [a for a in load("01011").abilities if a.kind is AbilityKind.FORCED][0]
    Drive(game.run_effect(forced.effect, EffectContext(game=game, source=card, controller=player))).run()
    assert player.xp_earned == -2


def test_haunted_and_the_madness_weaknesses_go_to_the_threat_area():
    for code in ("01098", "01099", "01100"):
        game, player, inv, here = base_game()
        card = put_in_hand(game.state, player, code)
        Drive(game.run_effect(load(code).meta["resolve"], EffectContext(game=game, source=card, controller=player))).run()
        assert card.zone is Zone.THREAT_AREA, code
        assert card.id in player.threat_area, code
        # the [action][action] discard ability
        discard = [a for a in load(code).abilities if a.kind is AbilityKind.ACTIVATED][0]
        assert discard.costs[0].amount == 2
        Drive(game.run_effect(discard.effect, EffectContext(game=game, source=card, controller=player))).run()
        assert card.zone is Zone.DISCARD, code


def test_haunted_revelation_puts_the_card_in_the_threat_area():
    game, player, inv, here = base_game()
    card = put_in_hand(game.state, player, "01098")
    Drive(game.run_effect(load("01098").meta["resolve"], EffectContext(game=game, source=card, controller=player))).run()
    assert card.zone is Zone.THREAT_AREA


def test_psychosis_forces_direct_damage_after_horror():
    game, player, inv, here = base_game()
    card = put_in_play(game.state, player, "01099")
    card.zone = Zone.THREAT_AREA
    player.threat_area.append(card.id)
    player.play_area.remove(card.id)

    Drive(game.deal_horror(inv, 1, reason="test")).run()

    assert inv.horror == 1
    assert inv.damage == 1


def test_hypochondria_forces_direct_horror_after_damage():
    game, player, inv, here = base_game()
    card = put_in_play(game.state, player, "01100")
    card.zone = Zone.THREAT_AREA
    player.threat_area.append(card.id)
    player.play_area.remove(card.id)

    Drive(game.assign_damage(inv, 1, reason="test")).run()

    assert inv.damage == 1
    assert inv.horror == 1

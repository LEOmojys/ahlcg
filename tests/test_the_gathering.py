"""The Gathering: setup, the scenario reference, and a full robot playthrough."""

import pytest

from ahlcg.ai import robot
from ahlcg.core.cards import CardInstance
from ahlcg.core.enums import CardType, Phase, TokenType, Zone
from ahlcg.data.pool import CardPool
from ahlcg.engine.chaos import CULTIST, SKULL, TABLET, ChaosToken, numeric
from ahlcg.engine.skill_test import SkillTest
from ahlcg.session import GameSetup, CHAOS_BAGS, build_chaos_bag, create_game


@pytest.fixture(scope="module")
def pool():
    return CardPool.load()


@pytest.fixture
def game(pool):
    return create_game(GameSetup(pool=pool, seed=7))


def test_setup_lays_out_the_gathering(game):
    game.start()
    state = game.state
    locations = state.locations()
    assert [loc.code for loc in locations] == ["01111"]
    assert locations[0].defn.name == "Study"
    assert locations[0].name == "书房"  # 卡面已本地化
    assert locations[0].clues == 2
    assert locations[0].meta["revealed"] is True

    assert [state.cards[i].code for i in state.act_deck] == ["01108", "01109", "01110"]
    assert [state.cards[i].code for i in state.agenda_deck] == ["01105", "01106", "01107"]

    # Ghoul Priest and Lita Chantler start set aside
    set_aside = {state.cards[i].code for i in state.set_aside}
    assert {"01116", "01117"} <= set_aside

    # encounter deck: 2 ghoul enemies from the scenario set + 3+7+7+3+4 from the encounter sets
    assert len(state.encounter_deck) == 26
    codes = [state.cards[i].code for i in state.encounter_deck]
    assert "01116" not in codes and "01117" not in codes
    for treachery in ("01162", "01163", "01164", "01165", "01166", "01167", "01168"):
        assert treachery in codes

    investigator = state.investigator_of(state.players[0])
    study = locations[0]
    assert investigator.meta["location_id"] == study.id
    assert state.flags["move_locked_at"] == study.id
    assert state.flags["act_advance"]["01108"]["clues"] == 2
    assert len(state.players[0].hand) == 5


def test_first_round_skips_the_mythos_phase(game):
    game.start()
    # the opening hand mulligan comes first; decline it
    choice = game.awaiting
    if choice is not None and "重抽" in (choice.prompt or ""):
        from ahlcg.core.choices import ChoiceAnswer

        game.resolve(ChoiceAnswer(choice.id, ()))
    assert game.state.round == 1
    assert game.state.phase is Phase.INVESTIGATION
    assert any("第一轮跳过神话阶段" in entry.text for entry in game.state.log_entries)
    agenda = game.state.current_agenda()
    assert agenda is not None and agenda.doom == 0


@pytest.mark.parametrize(
    "difficulty,size",
    [("easy", 16), ("standard", 16), ("hard", 17), ("expert", 18)],
)
def test_chaos_bag_matches_the_campaign_guide(difficulty, size):
    bag = build_chaos_bag(difficulty)
    assert bag.size == size
    assert bag.count_type(TokenType.AUTOFAIL) == 1
    assert bag.count_type(TokenType.ELDER_SIGN) == 1


def test_standard_bag_composition():
    bag = build_chaos_bag("standard")
    for value, count in ((1, 1), (0, 2), (-1, 3), (-2, 2), (-3, 1), (-4, 1)):
        assert bag.count(numeric(value)) == count, value


def test_scenario_reference_token_modifiers(game):
    game.start()
    state = game.state
    investigator = state.investigator_of(state.players[0])
    test = SkillTest(skill=__import__("ahlcg.core.enums", fromlist=["Skill"]).Skill.INTELLECT, difficulty=2, investigator_id=investigator.id)
    bag = state.chaos_bag

    # no ghouls at the location yet: the skull token is worth 0
    assert bag.value_of(SKULL, test) == 0
    assert bag.value_of(CULTIST, test) == -1
    assert bag.value_of(TABLET, test) == -2

    # a ghoul minion in the Study makes the skull token worse (X = ghouls at your location)
    pool: CardPool = game.scenario.pool
    ghoul = state.add_card(pool.get("01160"), zone=Zone.PLAY, location_id=investigator.meta["location_id"])
    assert bag.value_of(SKULL, test) == -1
    ghoul2 = state.add_card(pool.get("01161"), zone=Zone.PLAY, location_id=investigator.meta["location_id"])
    assert bag.value_of(SKULL, test) == -2
    assert bag.success_probability(2, 2, test) < 1.0


def test_full_robot_playthrough_reaches_a_resolution(pool):
    game = create_game(GameSetup(pool=pool, seed=11))
    report = robot.play(game, max_steps=30000)
    assert report["finished"] is True, report
    assert game.state.resolution in {"R1", "R2", "R3", "defeated", "agenda_exhausted"}
    assert game.state.round >= 1
    assert game.awaiting is None


def test_robot_can_advance_the_acts(pool):
    """With the clue actions prioritised the robot should get past Act 1."""
    game = create_game(GameSetup(pool=pool, seed=3))
    game.start()
    steps = 0
    while game.awaiting is not None and steps < 30000 and not game.state.finished:
        if game.state.act_index >= 1:
            break
        game.resolve(robot.choose(game))
        steps += 1
    assert game.state.act_index >= 1, [e.text for e in game.state.log_entries[-25:]]

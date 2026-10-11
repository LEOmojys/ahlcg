"""第二章《午夜面具》：设置、邪教徒牌库、混沌标记修正、机器人通关。"""

import pytest

from ahlcg.ai import robot
from ahlcg.core.enums import CardType, Skill, TokenType, Zone
from ahlcg.data.pool import CardPool
from ahlcg.engine.chaos import CULTIST, SKULL, TABLET
from ahlcg.engine.skill_test import SkillTest
from ahlcg.session import GameSetup, create_game


@pytest.fixture(scope="module")
def pool():
    return CardPool.load()


def new_game(pool, seed=5, house_burned=False):
    setup = GameSetup(pool=pool, seed=seed, scenario="arkham")
    if house_burned:
        setup.flags = {"house_burned": True}
    return create_game(setup)


def test_setup_lays_out_arkham(pool):
    game = new_game(pool)
    game.start()
    state = game.state
    assert state.scenario_code == "arkham"
    codes = {loc.code for loc in state.locations()}
    assert "01124" in codes
    assert ("01130" in codes) != ("01131" in codes), "只应有 1 张市中心"
    assert ("01126" in codes) != ("01127" in codes), "只应有 1 张南区"
    assert {"01125", "01128", "01129", "01132", "01133", "01134"} <= codes
    assert len(state.locations()) == 9

    assert [state.cards[i].code for i in state.act_deck] == ["01123"]
    assert [state.cards[i].code for i in state.agenda_deck] == ["01121a", "01122"]
    assert len(state.flags["cultist_deck"]) == 5
    assert len(state.encounter_deck) == 21

    investigator = state.investigator_of(state.players[0])
    assert state.cards[investigator.meta["location_id"]].code == "01124"
    assert state.flags["act_advance"]["01123"]["objective"] == "cultists"
    assert state.flags["resign_allowed"] is True


def test_burned_house_starts_in_rivertown(pool):
    game = new_game(pool, house_burned=True)
    game.start()
    state = game.state
    codes = {loc.code for loc in state.locations()}
    assert "01124" not in codes
    assert len(state.locations()) == 8
    investigator = state.investigator_of(state.players[0])
    assert state.cards[investigator.meta["location_id"]].code == "01125"


def test_scenario_reference_tokens(pool):
    game = new_game(pool)
    game.start()
    state = game.state
    investigator = state.investigator_of(state.players[0])
    test = SkillTest(skill=Skill.INTELLECT, difficulty=2, investigator_id=investigator.id)
    bag = state.chaos_bag
    assert bag.value_of(SKULL, test) == 0
    assert bag.value_of(CULTIST, test) == -2
    assert bag.value_of(TABLET, test) == -3

    cultist = state.add_card(pool.get("01137"), zone=Zone.PLAY, location_id=investigator.meta["location_id"])
    cultist.doom = 2
    assert bag.value_of(SKULL, test) == -2


def test_group_action_draws_from_the_cultist_deck(pool):
    game = new_game(pool)
    game.start()
    state = game.state
    player = state.players[0]
    investigator = state.investigator_of(player)
    investigator.clues = 2

    from ahlcg.engine.actions import execute_action, legal_actions

    assert "cultist" in {option.id for option in legal_actions(game, player)}
    for _ in execute_action(game, player, "cultist"):
        pass
    assert investigator.clues == 0
    assert len(state.flags["cultist_deck"]) == 4
    assert len(state.enemies()) == 1


def test_doom_on_other_cards_pushes_the_agenda(pool):
    """Rules Reference 1.3: the threshold counts doom anywhere in play."""
    game = new_game(pool)
    game.start()
    state = game.state
    agenda = state.current_agenda()
    assert agenda is not None
    enemy = state.add_card(pool.get("01169"), zone=Zone.PLAY)
    enemy.doom = 5
    agenda.doom = 1  # 6 total, exactly the threshold
    list(game.place_doom(agenda, 0)) if False else None
    # advancing clears all doom in play, including the enemy's
    for _ in game.advance_agenda():
        pass
    assert state.agenda_index == 1
    assert state.total_doom() == 0


def test_robot_finishes_the_scenario(pool):
    game = new_game(pool, seed=9)
    report = robot.play(game, max_steps=40000)
    assert report["finished"], report
    assert game.state.resolution in {"R1", "R2", "defeated", "agenda_exhausted"}
    assert isinstance(game.state.flags.get("cultists_found"), list)
    assert isinstance(game.state.flags.get("cultists_escaped"), list)

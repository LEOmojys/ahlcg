"""第三章《深渊吞噬者》：设置、战役日志影响、阿布霍斯、机器人通关。"""

import pytest

from ahlcg.ai import robot
from ahlcg.core.enums import CardType, TokenType, Zone
from ahlcg.data.pool import CardPool
from ahlcg.engine.chaos import ELDER_THING
from ahlcg.session import GameSetup, create_game


@pytest.fixture(scope="module")
def pool():
    return CardPool.load()


def new_game(pool, seed=4, **flags):
    setup = GameSetup(pool=pool, seed=seed, scenario="tentacles")
    setup.flags = dict(flags)
    return create_game(setup)


def test_setup_lays_out_the_woods(pool):
    game = new_game(pool)
    game.start()
    state = game.state
    assert state.scenario_code == "tentacles"
    codes = [loc.code for loc in state.locations()]
    assert codes.count("01149") == 1, "主干道必须在场"
    woods = [c for c in codes if c in ("01150", "01151", "01152", "01153", "01154", "01155")]
    assert len(woods) == 4, "6 张阿卡姆树林随机 4 张进场"
    assert len(state.locations()) == 5

    assert [state.cards[i].code for i in state.act_deck] == ["01146", "01147", "01148"]
    assert [state.cards[i].code for i in state.agenda_deck] == ["01143", "01144", "01145"]

    # Umôrdhoth and the Ritual Site start set aside
    set_aside = {state.cards[i].code for i in state.set_aside}
    assert {"01156", "01157"} <= set_aside

    # exactly one agent set is used
    assert state.flags["devourer_agent_set"] in {
        "agents_of_yog", "agents_of_cthulhu", "agents_of_shub", "agents_of_hastur"
    }
    assert len(state.encounter_deck) == 29

    # the campaign guide adds one extra chaos token
    assert state.chaos_bag.count_type(TokenType.ELDER_THING) == 1

    investigator = state.investigator_of(state.players[0])
    assert state.cards[investigator.meta["location_id"]].code == "01149"


def test_escaped_cultists_put_doom_on_the_first_agenda(pool):
    game = new_game(pool, cultists_escaped=["Herman Collins", "Peter Warren", "Victoria Devereux"])
    game.start()
    agenda = game.state.current_agenda()
    assert agenda is not None and agenda.doom == 2

    game2 = new_game(pool, seed=6, cultists_escaped=["Ruth Turner"])
    game2.start()
    agenda2 = game2.state.current_agenda()
    assert agenda2 is not None and agenda2.doom == 1


def test_midnight_passed_discards_two_cards(pool):
    game = new_game(pool)
    game.start()
    assert len(game.state.players[0].hand) == 5

    game2 = new_game(pool, seed=6, midnight_passed=True)
    game2.start()
    assert len(game2.state.players[0].hand) == 3


def test_ghoul_priest_is_shuffled_back_in(pool):
    game = new_game(pool, ghoul_priest_alive=True)
    game.start()
    codes = [game.state.cards[i].code for i in game.state.encounter_deck]
    assert "01116" in codes
    assert len(game.state.encounter_deck) == 30


def test_umordhoth_arrives_with_health_per_investigator(pool):
    game = new_game(pool)
    game.start()
    state = game.state
    state.agenda_index = 2  # jump to "Vengeance Awaits"; its advance summons Umôrdhoth
    for _ in game.advance_agenda():
        pass
    umordhoth = next((e for e in state.enemies() if e.code == "01157"), None)
    assert umordhoth is not None, "复仇降临时阿布霍斯必须现身"
    assert umordhoth.health_total == 6 + 4  # 6 printed + 4 per investigator
    ritual = [loc for loc in state.locations() if loc.code == "01156"]
    assert ritual and umordhoth.location_id == ritual[0].id


def test_robot_finishes_the_devourer_below(pool):
    game = new_game(pool, seed=13)
    report = robot.play(game, max_steps=60000)
    assert report["finished"], report
    assert game.state.resolution in {"R1", "R2", "R3", "defeated", "agenda_exhausted"}

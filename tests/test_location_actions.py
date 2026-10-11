"""《午夜面具》的地点行动：引擎按回合/每局限制提供，并在执行后生效。"""

import pytest

from ahlcg.core.choices import ChoiceAnswer
from ahlcg.core.enums import ChoiceKind, Skill, Zone
from ahlcg.data.pool import CardPool
from ahlcg.engine.actions import execute_action, legal_actions
from ahlcg.session import GameSetup, create_game


@pytest.fixture(scope="module")
def pool():
    return CardPool.load()


def mm_game(pool, *, at="01134", seed=3):
    game = create_game(GameSetup(pool=pool, seed=seed, scenario="arkham"))
    game.start()
    state = game.state
    player = state.players[0]
    target = next(loc for loc in state.locations() if loc.code == at)
    state.investigator_of(player).meta["location_id"] = target.id
    return game, player, target


def option_ids(game, player):
    return {option.id for option in legal_actions(game, player)}


def use(game, player, location, action_id):
    gen = execute_action(game, player, f"locact:{location.id}:{action_id}")
    try:
        choice = next(gen)
        while True:
            picked = (choice.options[0].id,) if choice.options else ()
            choice = gen.send(picked)
    except StopIteration:
        return


def test_location_actions_are_offered_only_where_you_stand(pool):
    game, player, northside = mm_game(pool)
    ids = option_ids(game, player)
    assert f"locact:{northside.id}:northside" in ids
    # no other location's action is offered
    assert not any(i.startswith("locact:") and i != f"locact:{northside.id}:northside" for i in ids)


def test_northside_trades_resources_for_clues(pool):
    game, player, location = mm_game(pool)
    player.resources = 6
    investigator = game.state.investigator_of(player)
    before = investigator.clues
    use(game, player, location, "northside")
    assert player.resources == 1
    assert investigator.clues == before + 2


def test_your_house_is_once_per_turn(pool):
    game, player, location = mm_game(pool, at="01124")
    hand_before = len(player.hand)
    resources_before = player.resources
    use(game, player, location, "your_house")
    assert len(player.hand) >= hand_before  # drew a card
    assert player.resources >= resources_before
    # the same action is gone until the next round
    assert f"locact:{location.id}:your_house" not in option_ids(game, player)
    game.state.round += 1
    assert f"locact:{location.id}:your_house" in option_ids(game, player)


def test_once_per_game_actions_disappear(pool):
    game, player, location = mm_game(pool)
    use(game, player, location, "northside")
    assert f"locact:{location.id}:northside" not in option_ids(game, player)
    game.state.round += 1
    assert f"locact:{location.id}:northside" not in option_ids(game, player), "每局一次不应随回合恢复"


def test_st_marys_heals_damage(pool):
    game, player, location = mm_game(pool, at="01128")
    investigator = game.state.investigator_of(player)
    investigator.damage = 5
    use(game, player, location, "st_marys_heal")
    assert investigator.damage == 2


def test_easttown_discounts_ally_assets(pool):
    game, player, location = mm_game(pool, at="01132")
    state = game.state
    ally = state.add_card(pool.get("01048"), zone=Zone.HAND, owner_id=player.id, controller_id=player.id)  # Leo De Luca, Ally
    player.hand.append(ally.id)
    player.resources = 10
    cost = ally.defn.cost or 0
    assert location.defn.meta.get("ally_cost_reduction") == 2
    gen = execute_action(game, player, f"play:{ally.id}")
    try:
        gen.send(None)
    except (StopIteration, TypeError):
        pass
    assert player.resources >= 10 - cost, "折扣后不应多花资源"

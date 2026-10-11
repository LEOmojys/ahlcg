"""伤害打断窗口：“I've had worse…”从手牌取消最多 5 点伤害/恐惧并换取资源。"""

import pytest

from ahlcg.core.choices import ChoiceAnswer
from ahlcg.core.enums import ChoiceKind, Zone
from ahlcg.data.pool import CardPool
from ahlcg.engine.chaos import ChaosBag, numeric
from ahlcg.session import GameSetup, create_game


@pytest.fixture(scope="module")
def pool():
    return CardPool.load()


def make_game(pool):
    game = create_game(GameSetup(pool=pool, seed=3))
    game.start()
    state = game.state
    player = state.players[0]
    player.hand.clear()
    player.deck.clear()
    player.resources = 0
    state.chaos_bag = ChaosBag.from_tokens([numeric(0)])
    return game, player, state.investigator_of(player)


def drive(gen, yes=True):
    try:
        choice = next(gen)
    except StopIteration:
        return
    while True:
        picked = ()
        if choice.kind is ChoiceKind.CONFIRM:
            picked = ("yes",) if yes else ("no",)
        elif choice.options:
            picked = (choice.options[0].id,)
        try:
            choice = gen.send(picked)
        except StopIteration:
            return


def put_in_hand(game, pool, player, code):
    card = game.state.add_card(pool.get(code), zone=Zone.HAND, owner_id=player.id, controller_id=player.id)
    player.hand.append(card.id)
    return card


def test_cancels_up_to_five_damage(pool):
    game, player, investigator = make_game(pool)
    card = put_in_hand(game, pool, player, "01684")

    drive(game.deal_damage(investigator, 4, reason="test"))
    assert investigator.damage == 0, "4 点伤害应当被全部取消"
    assert player.resources == 4, "取消多少点就换多少资源"
    assert card.id in player.discard


def test_leaves_the_excess_damage(pool):
    game, player, investigator = make_game(pool)
    card = put_in_hand(game, pool, player, "01684")

    drive(game.deal_damage(investigator, 7, reason="test"))
    assert investigator.damage == 2, "只取消 5 点，剩下 2 点照常承受"
    assert player.resources == 5
    assert card.id in player.discard


def test_horror_is_cancelled_too(pool):
    game, player, investigator = make_game(pool)
    card = put_in_hand(game, pool, player, "01684")

    drive(game.deal_horror(investigator, 3, reason="test"))
    assert investigator.horror == 0
    assert player.resources == 3
    assert card.id in player.discard


def test_declining_keeps_the_card_and_takes_the_damage(pool):
    game, player, investigator = make_game(pool)
    card = put_in_hand(game, pool, player, "01684")

    drive(game.deal_damage(investigator, 3, reason="test"), yes=False)
    assert investigator.damage == 3
    assert player.resources == 0
    assert card.id in player.hand

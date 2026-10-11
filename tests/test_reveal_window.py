"""混沌标记揭示窗口：Grotesque Statue / Sure Gamble / Eucatastrophe。"""

import pytest

from ahlcg.core.enums import ChoiceKind, Skill, Zone
from ahlcg.data.pool import CardPool
from ahlcg.engine.chaos import AUTOFAIL, ChaosBag, numeric
from ahlcg.session import GameSetup, create_game


@pytest.fixture(scope="module")
def pool():
    return CardPool.load()


def make_game(pool, bag):
    game = create_game(GameSetup(pool=pool, seed=3))
    game.start()
    state = game.state
    player = state.players[0]
    player.hand.clear()
    player.deck.clear()
    player.resources = 10
    state.chaos_bag = ChaosBag.from_tokens(bag)
    return game, player, state.investigator_of(player)


def drive(gen, *, yes=True):
    try:
        choice = next(gen)
    except StopIteration as stop:
        return stop.value
    while True:
        picked = ()
        if choice.kind is ChoiceKind.CONFIRM:
            picked = ("yes",) if yes else ("no",)
        elif choice.options:
            picked = (choice.options[0].id,)
        try:
            choice = gen.send(picked)
        except StopIteration as stop:
            return stop.value


def put_in_play(game, pool, code, **kwargs):
    state = game.state
    player = state.players[0]
    card = state.add_card(pool.get(code), zone=Zone.PLAY, controller_id=player.id, **kwargs)
    if card.defn.uses and not card.uses:
        card.uses = dict(card.defn.uses)
    player.play_area.append(card.id)
    return card


def test_grotesque_statue_reveals_two_and_spends_a_charge(pool):
    game, player, investigator = make_game(pool, [numeric(-4), numeric(0)])
    statue = put_in_play(game, pool, "01071")
    assert statue.uses == {"charge": 4}

    result = drive(game.skill_test(investigator=investigator, skill=Skill.INTELLECT, difficulty=2))
    assert statue.uses["charge"] == 3, "应当消耗 1 点充能"
    assert result is not None


def test_grotesque_statue_is_optional(pool):
    game, player, investigator = make_game(pool, [numeric(0)])
    statue = put_in_play(game, pool, "01071")
    result = drive(game.skill_test(investigator=investigator, skill=Skill.INTELLECT, difficulty=2), yes=False)
    assert statue.uses["charge"] == 4, "拒绝使用时不该消耗充能"
    assert result is not None


def test_sure_gamble_turns_a_negative_token_into_four(pool):
    game, player, investigator = make_game(pool, [numeric(-5)])
    card = game.state.add_card(pool.get("01056"), zone=Zone.HAND, owner_id=player.id, controller_id=player.id)
    player.hand.append(card.id)

    result = drive(game.skill_test(investigator=investigator, skill=Skill.INTELLECT, difficulty=3))
    assert result.token_value == 4, "标记的修正应当被改成 +4"
    assert result.success
    assert card.id in player.discard, "打出的卡要进弃牌堆"


def test_sure_gamble_ignores_positive_tokens(pool):
    game, player, investigator = make_game(pool, [numeric(2)])
    card = game.state.add_card(pool.get("01056"), zone=Zone.HAND, owner_id=player.id, controller_id=player.id)
    player.hand.append(card.id)
    result = drive(game.skill_test(investigator=investigator, skill=Skill.INTELLECT, difficulty=2))
    assert result.token_value == 2
    assert card.id in player.hand, "条件不满足时不该被打出"


def test_eucatastrophe_fires_when_a_token_would_zero_you(pool):
    game, player, investigator = make_game(pool, [numeric(-4)])
    card = game.state.add_card(pool.get("01692"), zone=Zone.HAND, owner_id=player.id, controller_id=player.id)
    player.hand.append(card.id)

    # intellect 3 with a -4 token would leave the investigator at 0 or less
    result = drive(game.skill_test(investigator=investigator, skill=Skill.INTELLECT, difficulty=2))
    assert result is not None
    assert card.id in player.discard, "条件满足时这张卡必须被打出"


def test_eucatastrophe_effect_swaps_the_token(pool):
    """直接调用效果，确认它真的把标记换掉了（不受抽袋顺序影响）。"""
    from ahlcg.cards.core_set_extra import _eucatastrophe
    from ahlcg.core.enums import Trigger
    from ahlcg.core.events import GameEvent
    from ahlcg.engine.effects import EffectContext
    from ahlcg.engine.skill_test import SkillTest

    game, player, investigator = make_game(pool, [numeric(5)])
    card = game.state.add_card(pool.get("01692"), zone=Zone.HAND, owner_id=player.id, controller_id=player.id)
    player.hand.append(card.id)
    test = SkillTest(skill=Skill.INTELLECT, difficulty=2, investigator_id=investigator.id)
    payload = {"token": AUTOFAIL, "test": test}
    ctx = EffectContext(game=game, source=card, controller=player, event=GameEvent(Trigger.ON_REVEAL_TOKEN, payload=payload))
    list(game.run_effect(_eucatastrophe, ctx))
    assert payload["token"].value == 5, "应当换成新抽到的标记"
    assert card.id in player.discard

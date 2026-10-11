"""最后两张：The Necronomicon 的空白化与 Wendy's Amulet 的弃牌堆出牌。"""

import pytest

from ahlcg.core.enums import CardType, ChoiceKind, Trigger, Zone
from ahlcg.data.pool import CardPool
from ahlcg.engine.actions import execute_action, legal_actions
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
    player.discard.clear()
    player.play_area.clear()
    player.threat_area.clear()
    player.resources = 20
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


def put(game, pool, code, zone, **kwargs):
    player = game.state.players[0]
    card = game.state.add_card(pool.get(code), zone=zone, owner_id=player.id, controller_id=player.id, **kwargs)
    return card


def test_necronomicon_revelation_goes_to_the_threat_area(pool):
    game, player, investigator = make_game(pool)
    card = put(game, pool, "01009", Zone.DECK)
    player.deck.append(card.id)

    drive(game.draw_cards(player, 1))
    assert card.id in player.threat_area, "启示应当把它放进威胁区"
    assert card.horror == 3
    assert card.id not in player.hand


def test_necronomicon_blanks_tome_assets(pool):
    game, player, investigator = make_game(pool)
    tomes = [
        defn
        for defn in pool.all()
        if "tome" in defn.traits and defn.card_type is CardType.ASSET and defn.abilities
    ]
    if not tomes:
        pytest.skip("基础包里没有带能力的典籍")
    tome = put(game, pool, tomes[0].code, Zone.PLAY)
    player.play_area.append(tome.id)

    def activated_ids():
        return {o.id for o in legal_actions(game, player) if o.id.startswith(f"activate:{tome.id}:")}

    assert activated_ids(), "未受影响时典籍的能力应当可用"

    book = put(game, pool, "01009", Zone.THREAT_AREA)
    book.horror = 3
    player.threat_area.append(book.id)
    assert game.tomes_blanked(tome)

    assert not activated_ids(), "典籍的文本应当被《死灵之书》视为空白"


def test_wendys_amulet_plays_the_top_event_from_discard(pool):
    game, player, investigator = make_game(pool)
    amulet = put(game, pool, "01014", Zone.PLAY)
    player.play_area.append(amulet.id)

    buried = put(game, pool, "01023", Zone.DISCARD)  # Dodge, buried under the top card
    player.discard.append(buried.id)
    top = put(game, pool, "01057", Zone.DISCARD)  # Hot Streak, the topmost event
    player.discard.append(top.id)
    filler = put(game, pool, "01016", Zone.DECK)
    player.deck.insert(0, filler.id)

    ids = {option.id for option in legal_actions(game, player)}
    assert f"playdiscard:{top.id}" in ids, "应当能从弃牌堆打出最上面的事件"
    assert f"playdiscard:{buried.id}" not in ids, "只能打出最上面那张"

    resources_before = player.resources
    drive(execute_action(game, player, f"playdiscard:{top.id}"))
    assert player.resources == resources_before - (top.defn.cost or 0) + 10, "事件效果应当结算"
    assert top.id in player.discard, "打完的事件回到弃牌堆"
    assert filler.id in player.discard, "护符的强制条款弃掉牌库顶"


def test_wendys_amulet_is_needed_to_play_from_discard(pool):
    game, player, investigator = make_game(pool)
    top = put(game, pool, "01057", Zone.DISCARD)
    player.discard.append(top.id)
    ids = {option.id for option in legal_actions(game, player)}
    assert not any(i.startswith("playdiscard:") for i in ids)

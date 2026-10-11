"""本轮补齐的规则条款：霰弹枪按超出幅度结算伤害、棒球棒损坏、每次检定限投入 1 张。"""

import pytest

from ahlcg.core.choices import ChoiceAnswer
from ahlcg.core.enums import ChoiceKind, Skill, TokenType, Zone
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
    player.resources = 20
    state.chaos_bag = ChaosBag.from_tokens(bag)
    investigator = state.investigator_of(player)
    investigator.meta["location_id"] = next(iter(state.cards)).id if False else investigator.meta.get("location_id")
    return game, player, investigator


def put_in_play(game, pool, code):
    player = game.state.players[0]
    card = game.state.add_card(pool.get(code), zone=Zone.PLAY, owner_id=player.id, controller_id=player.id)
    if card.defn.uses and not card.uses:
        card.uses = dict(card.defn.uses)
    player.play_area.append(card.id)
    return card


def answer_first(gen):
    try:
        choice = next(gen)
    except StopIteration:
        return None
    while True:
        picked = ()
        if choice.kind is ChoiceKind.COMMIT:
            picked = ()
        elif choice.options:
            picked = (choice.options[0].id,)
        try:
            choice = gen.send(picked)
        except StopIteration as stop:
            return stop.value


def find_enemy(game, pool):
    state = game.state
    player = state.players[0]
    # 没有现成敌人时，生成一只食尸鬼祭司并交战
    enemies = [e for e in state.enemies() if player.id in e.engaged_with]
    if not enemies:
        card = state.add_card(pool.get("01116"), zone=Zone.PLAY, owner_id=None, controller_id=None)
        game.spawn_enemy(card, player)
        enemies = [card]
    return enemies[0]


def test_shotgun_deals_damage_per_success_point(pool):
    # 战斗 4 + 霰弹枪 +3 + 标记 +1 = 8，对食尸鬼祭司（战斗 5）超出成功 3 点 → 3 点伤害
    game, player, investigator = make_game(pool, [numeric(1)])
    shotgun = put_in_play(game, pool, "01029")
    enemy = find_enemy(game, pool)
    answer_first(__import__("ahlcg.engine.actions", fromlist=["_fight"])._fight(game, player, investigator, enemy))
    assert enemy.damage == 4, "霰弹枪应按超出成功的点数结算伤害（超出 4 点 → 4 点伤害）"


def test_baseball_bat_breaks_on_a_bad_token(pool):
    game, player, investigator = make_game(pool, [AUTOFAIL])
    bat = put_in_play(game, pool, "01074")
    enemy = find_enemy(game, pool)
    answer_first(__import__("ahlcg.engine.actions", fromlist=["_fight"])._fight(game, player, investigator, enemy))
    assert bat.id not in player.play_area, "揭示自动失败后棒球棒应在攻击后弃掉"


def test_max_one_committed_is_enforced(pool):
    game, player, investigator = make_game(pool, [numeric(0)])
    guts1 = game.state.add_card(pool.get("01089"), zone=Zone.HAND, owner_id=player.id, controller_id=player.id)
    guts2 = game.state.add_card(pool.get("01089"), zone=Zone.HAND, owner_id=player.id, controller_id=player.id)
    player.hand.extend([guts1.id, guts2.id])
    from ahlcg.engine.skill_test import SkillTest

    test = SkillTest(skill=Skill.WILLPOWER, difficulty=2, investigator_id=investigator.id)
    game.commit_window(player, test)
    driven = game.drive_commit_window(player, test) if hasattr(game, "drive_commit_window") else None
    # drive the commit choice through the public ask path
    gen = game.commit_window(player, test)
    try:
        choice = next(gen)
        picked_ids = [o.id for o in choice.options if o.id in (guts1.id, guts2.id)][:2]
        list(gen.send(tuple(picked_ids)))
    except StopIteration:
        pass
    committed_names = [entry.label for entry in test.committed]
    assert committed_names.count(guts1.name if guts1.name == guts2.name else "胆识") <= 1, "同名限 1 张"

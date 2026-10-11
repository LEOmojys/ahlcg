
import pathlib

path = pathlib.Path(r"E:\pyproject\agent_project\ahlcg\ahlcg\campaign\game_builder.py")

body = '''"""按战役进度组装一局游戏。

SPEC.md 第二节：

    build_scenario_game(campaign, pool) -> Game

做的事：
1. 用调查员的持久牌组（code 列表）构造 DeckList 并调用 create_game；
2. 把战役难度、种子（seed + 幕序号，保证可复现）带上；
3. 把创伤转换成开场伤害/恐惧（创伤 1 点 = 起始 1 点伤害/恐惧，最小 0）；
4. 把战役日志换算成 game.state.flags，键名严格用 SPEC.md 第四节那一组；
5. 上一幕得到的叙事资产（丽塔·钱德勒 01117）加入场外区，故事弱点加入牌组；
6. 第二/三幕设置里与战役日志有关的额外规则（额外混沌指示物、午夜已过弃牌）。

调用方拿到 Game 后按普通流程 game.start() 继续；本函数默认已经帮你起局，
传 start=False 可以自己控制时机（例如还要先改 state.flags）。
"""

from __future__ import annotations

from typing import Any

from ..core.cards import CardDef
from ..core.enums import Zone
from ..data.deck import DeckList
from ..data.pool import CardPool
from ..engine.chaos import ELDER_THING
from ..engine.game import Game
from ..engine.state import Player
from ..scenarios import load_scenario, scenario_codes
from .night_of_the_zealot import (
    GHOUL_PRIEST_ALIVE_ENTRY,
    HOUSE_BURNED_ENTRY,
    INVESTIGATORS_SACRIFICED_LITA,
    LITA_CHANTLER,
    LITA_SACRIFICED_ENTRY,
    MIDNIGHT_PASSED_ENTRY,
    SCENARIO_ORDER,
    bug_fix_placeholder as _placeholder,
)

#: 本战役的幕 code -> ahlcg.scenarios 注册名（目前两套命名一致）。
SCENARIO_REGISTRY = {"torch": "torch", "arkham": "arkham", "tentacles": "tentacles"}

#: 第三章设置：第三幕开局每个人从起始手牌随机弃掉的张数。
MIDNIGHT_DISCARD = 2


class CampaignGameError(RuntimeError):
    """Raised when a scenario cannot be built from the current campaign."""


def build_scenario_game(
    campaign: Any,
    pool: CardPool,
    *,
    scenario: str | None = None,
    start: bool = True,
) -> Game:
    """Build the Game for campaign.scenario_code()."""
    code = scenario or campaign.scenario_code()
    if not code:
        raise CampaignGameError("战役已经结束，没有下一幕可以游玩")

    register_code = SCENARIO_REGISTRY.get(code, code)
    if register_code not in scenario_codes():
        raise CampaignGameError(
            "剧本 %r（%s）还没有实现；已注册的剧本：%s"
            % (code, campaign.scenario_name(code), ", ".join(scenario_codes()))
        )

    investigator = _lead_investigator(campaign)
    from ..session import GameSetup, create_game

    deck = DeckList(
        investigator=investigator.investigator_code,
        cards=tuple(investigator.deck),
        name="%s 的战役牌组" % investigator.name,
    )
    setup = GameSetup(
        pool=pool,
        deck=deck,
        scenario=register_code,
        difficulty=campaign.difficulty,
        seed=_seed_for(campaign, code),
        player_name=investigator.name,
    )
    game = create_game(setup)

    flags = flags_from_campaign(campaign, game)
    game.state.flags.update(flags)
    game.state.flags["campaign"] = game.state.flags.get("campaign") or campaign.to_dict()
    game.state.flags[INVESTIGATORS_SACRIFICED_LITA] = bool(flags.get(INVESTIGATORS_SACRIFICED_LITA))

    _apply_trauma(game, investigator)
    _add_story_cards(game, campaign)
    _scenario_adjustments(game, campaign, flags, code)

    if start:
        game.start()
        if flags.get("midnight_passed"):
            _apply_midnight_discard(game)
    return game


# ----------------------------------------------------------------------
# flags
# ----------------------------------------------------------------------
def flags_from_campaign(campaign: Any, game: Any | None = None) -> dict[str, Any]:
    """把战役日志换算成剧本层要读的那组开关（键名见 SPEC.md 第四节）。"""
    log = getattr(campaign, "log", {}) or {}
    def has(fragment: str) -> bool:
        return any(fragment in line for line in (log.get("战役记录") or []))

    defeated = _defeated_codes(game) if game is not None else set()
    return {
        "house_burned": has(HOUSE_BURNED_ENTRY),
        # 祭司只要还在游戏里（或被击败后放进了胜利点弃牌堆）就不算存活
        "ghoul_priest_alive": has(GHOUL_PRIEST_ALIVE_ENTRY) and "01116" not in defeated,
        "cultists_found": list(log.get("我们发现的邪教徒") or []),
        "cultists_escaped": list(log.get("逃跑的邪教徒") or []),
        "midnight_passed": has(MIDNIGHT_PASSED_ENTRY),
        "ritual_broken": has("召唤阿布霍斯的仪式已经被破坏"),
        INVESTIGATORS_SACRIFICED_LITA: has(LITA_SACRIFICED_ENTRY),
    }


def _defeated_codes(game: Any) -> set[str]:
    state = getattr(game, "state", None)
    if state is None:
        return set()
    out: set[str] = set()
    for card_id in getattr(state, "victory_display", []) or []:
        instance = state.maybe_card(card_id) if hasattr(state, "maybe_card") else None
        if instance is not None:
            out.add(instance.code)
    return out


# ----------------------------------------------------------------------
# 开局数值
# ----------------------------------------------------------------------
def _apply_trauma(game: Game, investigator: Any) -> None:
    """创伤 = 开场伤害/恐惧（最小值 0），伤害/恐惧不会超过生命/理智。"""
    player = game.state.players[0] if game.state.players else None
    if player is None or player.investigator_id is None:
        return
    card = game.state.card(player.investigator_id)
    physical = max(0, int(getattr(investigator, "trauma_physical", 0) or 0))
    mental = max(0, int(getattr(investigator, "trauma_mental", 0) or 0))
    health = int(card.defn.health or 0)
    sanity = int(card.defn.sanity or 0)
    card.damage = min(physical, health)
    card.horror = min(mental, sanity)
    if physical or mental:
        game.state.log(
            "%s 带着 %d 点身体创伤 / %d 点精神创伤进入本幕"
            % (card.name, physical, mental),
            kind="story",
        )


def _add_story_cards(game: Game, campaign: Any) -> None:
    """叙事资产进场外区；故事弱点（献祭丽塔的内疚）加入牌组。"""
    state = game.state
    player = state.players[0] if state.players else None
    investigator = _lead_investigator(campaign)

    deck_or_set_aside: list[str] = []
    for code in getattr(investigator, "story_assets", []) or []:
        if code == LITA_CHANTLER:
            continue
        if campaign.pool is not None and not campaign.pool.has(code):
            continue
        if code in investigator.deck:
            continue
        deck_or_set_aside.append(code)
    weaknesses = [code for code in (getattr(investigator, "story_weaknesses", []) or []) if code]

    if player is None:
        return
    for code in weaknesses:
        if not game.scenario.pool.has(code):
            continue
        instance = state.add_card(
            game.scenario.pool.get(code),
            owner_id=player.id,
            controller_id=player.id,
            zone=Zone.DECK,
        )
        player.deck.insert(0, instance.id)
        state.log("%s 的牌组加入故事弱点 %s" % (investigator.name, instance.name), kind="story")

    # 丽塔·钱德勒在剧本设置时会被放在一边；只在剧本设置没有自带这张卡时才补
    if LITA_CHANTLER in (getattr(investigator, "story_assets", []) or []):
        _grant_lita(game, campaign, player)


def _grant_lita(game: Game, campaign: Any, player: Player) -> None:
    """丽塔·钱德勒：起始时计入场外区（不计入牌组张数），玩家可以随时选择加入牌组。"""
    state = game.state
    if any(state.cards[i].code == LITA_CHANTLER for i in state.set_aside):
        return
    pool = game.scenario.pool
    if not pool.has(LITA_CHANTLER):
        return
    if any(card.code == LITA_CHANTLER and card.owner_id == player.id for card in state.cards.values()):
        return
    instance = state.add_card(pool.get(LITA_CHANTLER), owner_id=player.id, controller_id=player.id, zone=Zone.SET_ASIDE)
    state.set_aside.append(instance.id)
    state.log("丽塔·钱德勒（01117）加入 %s 的场外区（不计入牌组张数）" % player.name, kind="story")


# ----------------------------------------------------------------------
# 各幕设置里与战役日志有关的规则
# ----------------------------------------------------------------------
def _scenario_adjustments(game: Game, campaign: Any, flags: dict[str, Any], code: str) -> None:
    state = game.state
    if code in ("tentacles",):
        # 第三章设置：在剩余的战役中将 1 个远古之物混沌指示物加入混沌袋
        if state.chaos_bag.count_type(ELDER_THING.type) == 0:
            state.chaos_bag.add(ELDER_THING, 1)
            state.log("混沌袋加入 1 个远古之物指示物（第三章设置）", kind="story")
        escaped = flags.get("cultists_escaped") or []
        state.flags["escaped_cultist_doom"] = _doom_for_escaped(escaped)
    if code == "arkham":
        state.flags["cultists_found_count"] = len(flags.get("cultists_found") or [])
        state.flags["cultists_escaped_count"] = len(flags.get("cultists_escaped") or [])


def _doom_for_escaped(escaped: list[str]) -> int:
    """第三章设置：逃跑的邪教徒 0 个不加，1-2 个加 1，3-4 个加 2，5-6 个加 3。"""
    count = len(escaped)
    if count <= 0:
        return 0
    if count <= 2:
        return 1
    if count <= 4:
        return 2
    return 3


def _apply_midnight_discard(game: Game) -> None:
    """午夜已过：每个玩家从起始手牌中随机弃掉 2 张。"""
    state = game.state
    for player in state.players:
        for _ in range(MIDNIGHT_DISCARD):
            if not player.hand:
                break
            card_id = state.rng.choice(list(player.hand))
            state.log("%s 因为午夜已过随机弃掉 %s" % (player.name, state.cards[card_id].name), kind="discard")
            game.move_to_discard(player, card_id)


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _lead_investigator(campaign: Any) -> Any:
    active = campaign.active_investigators()
    if not active:
        raise CampaignGameError("没有存活的调查员，战役无法继续")
    return active[0]


def _seed_for(campaign: Any, code: str) -> int | None:
    """种子 + 幕序号：同一存档的每一幕仍然完全可复现。"""
    seed = getattr(campaign, "seed", None)
    if seed is None:
        return None
    order = getattr(campaign, "scenario_order", ()) or SCENARIO_ORDER
    index = order.index(code) if code in order else 0
    return int(seed) + index


__all__ = ["CampaignGameError", "SCENARIO_REGISTRY", "build_scenario_game", "flags_from_campaign"]
'''

path.write_text(body, encoding="utf-8")
print("written", len(body))

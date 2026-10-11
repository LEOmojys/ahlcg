
import pathlib

path = pathlib.Path(r"E:\pyproject\agent_project\ahlcg\ahlcg\campaign\night_of_the_zealot.py")

body = '''"""狂热者之夜（Night of the Zealot）三幕的结局数据。

数值与正文全部来自官方中文战役指南
reference/pdf/night_of_the_zealot_campaign_guide.txt；正文按页内文本范围抽取，
只做换行与页眉页脚的清理，不做任何改写（见 _clean 与 RESOLUTION_SOURCES）。

战役日志栏目（与指南最后一页的战役笔记一致）：
    剧本 / 战役记录 / 我们发现的邪教徒 / 逃跑的邪教徒 / 被杀和疯狂的调查员 /
    获得的故事资产/弱点

传给剧本层的开关（game.state.flags）键名与 SPEC.md 第四节一致：
    house_burned, ghoul_priest_alive, cultists_found, cultists_escaped,
    midnight_passed, ritual_broken, investigators_sacrificed_lita
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

CAMPAIGN = "night_of_the_zealot"
SCENARIO_ORDER = ("torch", "arkham", "tentacles")

SCENARIO_NAMES = {
    "torch": "第一章：集结",
    "arkham": "第二章：午夜面具",
    "tentacles": "第三章：深渊吞噬者",
}

#: 指南最后一页的战役日志栏目
LOG_SECTIONS = (
    "剧本",
    "战役记录",
    "我们发现的邪教徒",
    "逃跑的邪教徒",
    "被杀和疯狂的调查员",
    "获得的故事资产/弱点",
)

#: 丽塔·钱德勒
LITA_CHANTLER = "01117"
#: 食尸鬼祭司
GHOUL_PRIEST = "01116"

#: 战役记录中的固定条目（剧本层/存档都用这些字符串做判断）
HOUSE_BURNED_ENTRY = "你的屋子已经被焚毁"
HOUSE_STANDS_ENTRY = "你的屋子依然存在"
GHOUL_PRIEST_ALIVE_ENTRY = "食尸鬼祭司依然存活"
MIDNIGHT_PASSED_ENTRY = "午夜已过"
RITUAL_BROKEN_ENTRY = "召唤阿布霍斯的仪式已经被破坏"
LITA_SACRIFICED_ENTRY = "调查员们将丽塔钱德勒献祭给了阿布霍斯"
AKHAM_FELL_ENTRY = "阿卡姆屈服于阿布霍斯的可怕复仇之下"
DEVOURER_REPELLED_ENTRY = "调查员击退了阿布霍斯"
LITA_ABANDONED_ENTRY = "丽塔 被迫去寻找其他人来协助解决她的麻烦"

#: 摘要 dict 里表示「献祭丽塔」的键名
INVESTIGATORS_SACRIFICED_LITA = "investigators_sacrificed_lita"

#: 基础包中的「疯狂」基本弱点（献祭丽塔后每人随机获得一张）。
MADNESS_WEAKNESSES = (
    "01097",  # Amnesia 失忆
    "01098",  # Paranoia 偏执
    "01099",  # Haunted 闹鬼
    "01100",  # Psychosis 精神病
    "01101",  # Hypochondria 疑病症
)

_GUIDE = Path(__file__).resolve().parents[2] / "reference" / "pdf" / "night_of_the_zealot_campaign_guide.txt"

#: 结局正文在指南里的行号范围（含首尾；1 起算）
RESOLUTION_SOURCES: dict[tuple[str, str], tuple[tuple[int, int], ...]] = {
    ("torch", "no_resolution"): ((54, 63),),
    ("torch", "R1"): ((74, 80),),
    ("torch", "R2"): ((125, 132),),
    ("torch", "R3"): ((141, 144),),
    ("arkham", "no_resolution"): ((263, 264), (383, 390)),
    ("arkham", "R1"): ((265, 267), (395, 400)),
    ("arkham", "R2"): ((279, 282),),
    ("tentacles", "no_resolution"): ((450, 451), (383, 390)),
    ("tentacles", "R1"): ((457, 457),),
    ("tentacles", "R2"): ((478, 481),),
    ("tentacles", "R3"): ((493, 508),),
}

RESOLUTION_TITLES: dict[tuple[str, str], str] = {
    ("torch", "no_resolution"): "没有达成任何结局",
    ("torch", "R1"): "你烧掉了自己的房子",
    ("torch", "R2"): "你拒绝烧掉自己的房子",
    ("torch", "R3"): "你没能逃出屋子",
    ("arkham", "no_resolution"): "阿卡姆屈服于阿布霍斯",
    ("arkham", "R1"): "仪式被破坏",
    ("arkham", "R2"): "午夜已过",
    ("tentacles", "no_resolution"): "调查员们失败了",
    ("tentacles", "R1"): "阿布霍斯被驱逐",
    ("tentacles", "R2"): "阿布霍斯逃回它的维度",
    ("tentacles", "R3"): "丽塔被献祭",
}


# ----------------------------------------------------------------------
# 指南正文
# ----------------------------------------------------------------------
def _read_guide() -> list[str]:
    try:
        return _GUIDE.read_text(encoding="utf-8").splitlines()
    except OSError:  # pragma: no cover - the reference pdf may be absent
        return []


def _clean(fragment: str) -> str:
    """Turn hard wrapped guide text into one readable paragraph."""
    text = fragment.replace("\\n", "")
    # 页标记、页码、页眉页脚
    text = re.sub(r"\\s*={2,}\\s*page\\s+\\d+\\s*={2,}\\s*", "", text)
    text = re.sub(r"不要阅读\\s*直到你完成该章节", "", text)
    text = re.sub(r"\\d+\\s*©\\s*\\d{4}\\s*FFG.*", "", text)
    # 行首残留的编号（如「4 第二章：午夜面具」）
    text = re.sub(r"^\\s*\\d+\\s*", "", text.strip())
    return re.sub(r"\\s+", "", text)


def resolution_text(scenario: str, resolution: str) -> str:
    """结局正文（中文，忠实摘要/节选，取自官方指南）。"""
    ranges = RESOLUTION_SOURCES.get((scenario, resolution))
    if not ranges:
        return ""
    lines = _read_guide()
    parts = []
    for start, end in ranges:
        parts.append("".join(lines[start - 1 : end]))
    return _clean("".join(parts))


def resolution_title(scenario: str, resolution: str) -> str:
    return RESOLUTION_TITLES.get((scenario, resolution), resolution)


def scenario_name(code: str) -> str:
    return SCENARIO_NAMES.get(code, code)


# ----------------------------------------------------------------------
# 结局数值表
# ----------------------------------------------------------------------
def _xp_for_resolution(scenario: str, resolution: str) -> int:
    """奖励的经验值（不含胜利点数；胜利点由 game.state 提供）。"""
    table = {
        ("torch", "R1"): 2,
        ("torch", "R2"): 2,
        ("tentacles", "R1"): 5,
        ("tentacles", "R2"): 10,
    }
    return table.get((scenario, resolution), 0)


def _trauma_for_resolution(scenario: str, resolution: str) -> dict[str, int]:
    table = {
        ("torch", "R1"): {"physical": 0, "mental": 1},
        ("tentacles", "R1"): {"physical": 0, "mental": 2},
        ("tentacles", "R2"): {"physical": 2, "mental": 2},
        ("tentacles", "R3"): {"physical": 2, "mental": 2},
    }
    return dict(table.get((scenario, resolution), {"physical": 0, "mental": 0}))


def _log_changes(scenario: str, resolution: str, campaign: "CampaignState") -> list[dict[str, Any]]:
    """指南里「在你的战役日志中记录……」的那些条目。"""
    changes: list[dict[str, Any]] = []

    def add(section: str, entry: str) -> None:
        if not any(c["section"] == section and c["entry"] == entry for c in changes):
            changes.append({"section": section, "entry": entry})

    if scenario == "torch":
        if resolution == "R1":
            add("战役记录", HOUSE_BURNED_ENTRY)
        elif resolution == "R2":
            add("战役记录", HOUSE_STANDS_ENTRY)
        elif resolution == "R3":
            add("战役记录", LITA_ABANDONED_ENTRY)
            add("战役记录", HOUSE_STANDS_ENTRY)
            add("战役记录", GHOUL_PRIEST_ALIVE_ENTRY)
        else:
            add("战役记录", HOUSE_STANDS_ENTRY)
            add("战役记录", GHOUL_PRIEST_ALIVE_ENTRY)
    elif scenario == "arkham":
        if resolution == "R2":
            add("战役记录", MIDNIGHT_PASSED_ENTRY)
        elif resolution == "no_resolution":
            add("战役记录", AKHAM_FELL_ENTRY)
    elif scenario == "tentacles":
        if resolution == "R1":
            add("战役记录", RITUAL_BROKEN_ENTRY)
        elif resolution == "R2":
            add("战役记录", DEVOURER_REPELLED_ENTRY)
        elif resolution == "R3":
            add("战役记录", LITA_SACRIFICED_ENTRY)
    return changes


def _victory_xp(game: Any) -> int:
    """胜利点弃牌堆里的经验值（每个调查员各自结算）。"""
    state = getattr(game, "state", None)
    if state is None:
        return 0
    cards = getattr(state, "victory_display", []) or []
    total = 0
    for card_id in cards:
        instance = state.maybe_card(card_id) if hasattr(state, "maybe_card") else None
        if instance is None:
            continue
        total += int(getattr(instance.defn, "victory", 0) or 0)
    return total


def _per_investigator_victory(game: Any) -> int:
    """单选调查员时直接读玩家的胜利点数；多人时退回全桌计数。"""
    state = getattr(game, "state", None)
    if state is None:
        return 0
    players = list(getattr(state, "players", []) or [])
    totals = [int(getattr(p, "victory_points", 0) or 0) for p in players]
    if totals and any(totals):
        return max(totals)
    return _victory_xp(game)


def _ghoul_priest_escaped(game: Any) -> bool:
    """食尸鬼祭司是否已经进入胜利点弃牌堆（= 已经被击败）。"""
    state = getattr(game, "state", None)
    if state is None or not hasattr(state, "maybe_card"):
        return False
    for card_id in getattr(state, "victory_display", []) or []:
        instance = state.maybe_card(card_id)
        if instance is not None and instance.code == GHOUL_PRIEST:
            return True
    return False


def _card_name(game: Any, card_id: str) -> str:
    state = getattr(game, "state", None)
    instance = state.maybe_card(card_id) if state is not None and hasattr(state, "maybe_card") else None
    return instance.name if instance is not None else str(card_id)


def _enemy_names(game: Any, *, escaped: bool) -> list[str]:
    """邪教徒名单：没写进入胜利点弃牌堆 vs 还在邪教徒牌库/场上。"""
    state = getattr(game, "state", None)
    if state is None:
        return []
    names: list[str] = []
    if escaped:
        for card in state.cards.values():
            code = getattr(card, "code", "")
            if code in (GHOUL_PRIEST, LITA_CHANTLER):
                continue
            traits = getattr(card.defn, "traits", frozenset())
            if "cultist" not in traits:
                continue
            if card.zone.value in ("removed", "encounter_discard"):
                continue
            if card_id_in_victory(state, card.id):
                continue
            if card.name not in names:
                names.append(card.name)
    return names


def card_id_in_victory(state: Any, card_id: str) -> bool:
    return card_id in (getattr(state, "victory_display", []) or [])


# ----------------------------------------------------------------------
# 摘要
# ----------------------------------------------------------------------
def resolve_summary(campaign: "CampaignState", game: Any) -> dict[str, Any]:
    """Build the UI summary for whatever game.state.resolution says."""
    state = getattr(game, "state", None)
    scenario = str(getattr(state, "scenario_code", "") or campaign.scenario_code() or "")
    resolution = str(getattr(state, "resolution", "") or "no_resolution")
    victory = _per_investigator_victory(game)
    bonus = _xp_for_resolution(scenario, resolution)
    trauma = _trauma_for_resolution(scenario, resolution)
    changes = _log_changes(scenario, resolution, campaign)
    defeated: list[str] = []
    victim_names: list[str] = []
    if resolution == "no_resolution" and scenario in ("arkham", "tentacles"):
        for player in getattr(state, "players", []) or []:
            defeated.append(player.id)
            if state is not None and hasattr(state, "investigator_of"):
                victim_names.append(state.investigator_of(player).name)
    elif resolution == "R3" and scenario == "torch":
        for player in getattr(state, "players", []) or []:
            if not getattr(player, "resigned", False):
                defeated.append(player.id)
                if state is not None and hasattr(state, "investigator_of"):
                    victim_names.append(state.investigator_of(player).name)

    if resolution == "no_resolution":
        xp = 0
    elif scenario == "arkham":
        xp = victory
    else:
        xp = victory + bonus

    summary = {
        "scenario": scenario,
        "scenario_name": scenario_name(scenario),
        "resolution": resolution,
        "title": resolution_title(scenario, resolution),
        "text": resolution_text(scenario, resolution),
        "xp_gained": int(xp),
        "trauma": trauma,
        "log_changes": changes,
        "next_scenario": SCENARIO_ORDER[campaign.scenario_index + 1]
        if campaign.scenario_index + 1 < len(SCENARIO_ORDER)
        else None,
        "defeated_investigators": defeated,
        # --- 以下字段供 record_summary / 剧本层使用
        "story_assets": [LITA_CHANTLER] if (scenario, resolution) in (("torch", "R1"), ("torch", "R2"), ("torch", "R3")) else [],
        "story_weaknesses": [],
        "victory_points": victory,
        "defeated_names": victim_names,
    }

    if scenario == "arkham" and resolution in ("R1", "R2"):
        found = _enemy_names(game, escaped=False)
        escaped = _enemy_names(game, escaped=True)
        if resolution == "R1" and _agenda_is_first(state):
            if "面具猎手" not in escaped:
                escaped.append("面具猎手")
        for name in found:
            summary["log_changes"].append({"section": "我们发现的邪教徒", "entry": name})
        for name in escaped:
            summary["log_changes"].append({"section": "逃跑的邪教徒", "entry": name})
        if _ghoul_priest_escaped(game):
            summary["log_changes"].append(
                {"section": "战役记录", "entry": GHOUL_PRIEST_ALIVE_ENTRY, "remove": True}
            )

    if scenario == "torch" and _ghoul_priest_escaped(game):
        summary["log_changes"].append({"section": "战役记录", "entry": GHOUL_PRIEST_ALIVE_ENTRY, "remove": True})

    if (scenario, resolution) == ("tentacles", "R3"):
        picks = random_weaknesses(campaign, game)
        summary["story_weaknesses"] = picks
        summary[INVESTIGATORS_SACRIFICED_LITA] = True

    return summary


def _agenda_is_first(state: Any) -> bool:
    if state is None or not hasattr(state, "current_agenda"):
        return False
    try:
        return int(getattr(state, "agenda_index", 0) or 0) == 0
    except Exception:  # pragma: no cover
        return False


def random_weaknesses(campaign: "CampaignState", game: Any) -> list[str]:
    """每位调查员从随机基本弱点的「疯狂」子集中搜一张（指南第三章结局 3）。"""
    if not campaign.active_investigators():
        return []
    state = getattr(game, "state", None)
    rng = getattr(state, "rng", None)
    picks: list[str] = []
    used: set[str] = set()
    for _ in campaign.active_investigators():
        remaining = [code for code in MADNESS_WEAKNESSES if code not in used]
        if not remaining:
            remaining = list(MADNESS_WEAKNESSES)
        if rng is not None and hasattr(rng, "choice"):
            picked = rng.choice(remaining)
        else:  # pragma: no cover - 确定性兜底
            picked = remaining[0]
        used.add(picked)
        picks.append(picked)
    return picks
'''

path.write_text(body, encoding="utf-8")
print("written", len(body))

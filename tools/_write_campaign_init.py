
import pathlib

path = pathlib.Path(r"E:\pyproject\agent_project\ahlcg\ahlcg\campaign\__init__.py")
path.parent.mkdir(parents=True, exist_ok=True)

body = '''"""战役层（Campaign layer）: campaign log, XP, trauma and deck upgrades.

Night of the Zealot runs three scenarios in a row.  Everything that survives
from one scenario to the next lives here:

    CampaignState
        scenario_index      0 = 集结 (torch), 1 = 午夜面具 (arkham),
                            2 = 深渊吞噬者 (tentacles), 3 = 战役结束
        investigators       每人一份持久牌组 + 经验 + 创伤 + 故事资产/弱点
        log                 战役日志（中文栏目名 -> 中文条目）
        history             每一幕的结算摘要

Web 层按 SPEC.md 第二节调用本模块；情景相关的数值与文本全部来自
reference/pdf/night_of_the_zealot_campaign_guide.txt（见 night_of_the_zealot.py）。

存档：CampaignState.save(path) / CampaignState.load(path)，默认目录 campaign/saves/。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ..core.enums import CardClass, CardType, class_zh
from ..data.pool import CardPool

#: 所有战役存档的默认目录（相对仓库根目录）。
DEFAULT_SAVE_DIR = Path(__file__).resolve().parents[2] / "campaign" / "saves"

#: 调查员牌组的目标张数（规则：30 张）。
DECK_SIZE = 30

#: 升级后牌组允许的最大张数（允许少量超出，但升级时不能再无中生有地加牌）。
MAX_DECK_SIZE = 31

#: 卡牌等级上限（基础包规则）。
MAX_CARD_LEVEL = 5

CAMPAIGNS = ("night_of_the_zealot",)


class CampaignError(ValueError):
    """Raised when a campaign operation is impossible as requested."""


@dataclass
class CampaignInvestigator:
    """One investigator as they persist between scenarios."""

    player_id: str
    name: str
    investigator_code: str
    deck: list[str] = field(default_factory=list)
    xp_earned: int = 0
    xp_spent: int = 0
    trauma_physical: int = 0
    trauma_mental: int = 0
    story_assets: list[str] = field(default_factory=list)
    story_weaknesses: list[str] = field(default_factory=list)
    killed: bool = False
    insane: bool = False

    @property
    def xp_available(self) -> int:
        return max(0, int(self.xp_earned) - int(self.xp_spent))

    @property
    def is_active(self) -> bool:
        return not self.killed and not self.insane

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "investigator_code": self.investigator_code,
            "deck": list(self.deck),
            "deck_count": len(self.deck),
            "xp_earned": self.xp_earned,
            "xp_spent": self.xp_spent,
            "xp_available": self.xp_available,
            "trauma_physical": self.trauma_physical,
            "trauma_mental": self.trauma_mental,
            "story_assets": list(self.story_assets),
            "story_weaknesses": list(self.story_weaknesses),
            "killed": self.killed,
            "insane": self.insane,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CampaignInvestigator":
        return cls(
            player_id=str(data.get("player_id", "p1")),
            name=str(data.get("name", "调查员")),
            investigator_code=str(data.get("investigator_code", "")),
            deck=[str(c) for c in data.get("deck", [])],
            xp_earned=int(data.get("xp_earned", 0) or 0),
            xp_spent=int(data.get("xp_spent", 0) or 0),
            trauma_physical=int(data.get("trauma_physical", 0) or 0),
            trauma_mental=int(data.get("trauma_mental", 0) or 0),
            story_assets=[str(c) for c in data.get("story_assets", [])],
            story_weaknesses=[str(c) for c in data.get("story_weaknesses", [])],
            killed=bool(data.get("killed", False)),
            insane=bool(data.get("insane", False)),
        )


@dataclass
class CampaignState:
    """The whole campaign: who plays, what they own, and how far they got."""

    code: str = "night_of_the_zealot"
    difficulty: str = "standard"
    seed: int | None = None
    scenario_index: int = 0
    investigators: list[CampaignInvestigator] = field(default_factory=list)
    log: dict[str, list[str]] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    #: 卡池（不写进存档；spend_xp 需要它来判断等级/职业）
    pool: CardPool | None = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    @classmethod
    def new(
        cls,
        code: str = "night_of_the_zealot",
        investigator_codes: Iterable[str] = ("01001",),
        difficulty: str = "standard",
        decks: Iterable[Iterable[str]] | None = None,
        seed: int | None = None,
        *,
        pool: CardPool | None = None,
    ) -> "CampaignState":
        """Start a brand new campaign.

        investigator_codes / decks are parallel sequences; decks may be omitted
        when the caller only wants an empty shell (the UI fills decks in).
        """
        codes = [str(c) for c in investigator_codes]
        deck_lists = [list(d) for d in decks] if decks is not None else []
        resolved_pool = pool
        if resolved_pool is None:
            try:
                resolved_pool = CardPool.load()
            except Exception:  # pragma: no cover - a missing data file must not break new()
                resolved_pool = None

        investigators: list[CampaignInvestigator] = []
        for index, investigator_code in enumerate(codes):
            deck = deck_lists[index] if index < len(deck_lists) else []
            name = investigator_code
            if resolved_pool is not None and resolved_pool.has(investigator_code):
                name = resolved_pool.get(investigator_code).display_name
            investigators.append(
                CampaignInvestigator(
                    player_id="p%d" % (index + 1),
                    name=name,
                    investigator_code=investigator_code,
                    deck=list(deck),
                )
            )

        state = cls(
            code=code,
            difficulty=difficulty,
            seed=seed,
            scenario_index=0,
            investigators=investigators,
            log={section: [] for section in _log_sections(code)},
            history=[],
            pool=resolved_pool,
        )
        state.log.setdefault("战役记录", [])
        state.log.setdefault("我们发现的邪教徒", [])
        state.log.setdefault("逃跑的邪教徒", [])
        state.log_entry("战役记录", "战役开始：" + "、".join(i.name for i in investigators))
        return state

    # ------------------------------------------------------------------
    # accessors
    # ------------------------------------------------------------------
    @property
    def scenario_order(self) -> tuple[str, ...]:
        from .night_of_the_zealot import SCENARIO_ORDER

        return SCENARIO_ORDER if self.code == "night_of_the_zealot" else ()

    def scenario_code(self) -> str | None:
        """Which scenario should be played now, or None when the campaign is over."""
        order = self.scenario_order
        if 0 <= self.scenario_index < len(order):
            return order[self.scenario_index]
        return None

    def scenario_name(self, code: str | None = None) -> str:
        from .night_of_the_zealot import scenario_name

        return scenario_name(code or self.scenario_code() or "")

    def investigator(self, player_id: str) -> CampaignInvestigator:
        for investigator in self.investigators:
            if investigator.player_id == player_id:
                return investigator
        raise KeyError("unknown player %r" % (player_id,))

    def active_investigators(self) -> list[CampaignInvestigator]:
        return [i for i in self.investigators if i.is_active]

    def find_player_id(self, name_or_id: str) -> str | None:
        for investigator in self.investigators:
            if name_or_id in (investigator.player_id, investigator.name, investigator.investigator_code):
                return investigator.player_id
        return None

    # ------------------------------------------------------------------
    # campaign log
    # ------------------------------------------------------------------
    def log_entry(self, section: str, entry: str) -> bool:
        """Record one 战役记录 line.  Returns False when it was already there."""
        lines = self.log.setdefault(section, [])
        if entry in lines:
            return False
        lines.append(entry)
        return True

    def remove_log_entry(self, section: str, entry: str) -> bool:
        """划掉（删除）一条战役日志；规则要求被删除的记录以后要忽略。"""
        lines = self.log.get(section)
        if not lines or entry not in lines:
            return False
        lines.remove(entry)
        return True

    def log_text(self, section: str) -> str:
        return "\\n".join(self.log.get(section, []))

    def has_log_entry(self, section: str, fragment: str) -> bool:
        """True when any line of the section contains fragment."""
        return any(fragment in line for line in self.log.get(section, []))

    # ------------------------------------------------------------------
    # scenario transitions
    # ------------------------------------------------------------------
    def apply_resolution(self, game: Any) -> dict[str, Any]:
        """Read game.state.resolution, update the campaign, and summarise it.

        The returned dict is exactly the shape SPEC.md section 2 documents, so
        the UI can render it directly.  advance() is a separate call: the caller
        decides when the players have finished reading the outcome.
        """
        summary = resolve_summary(self, game)
        self.record_summary(summary)
        return summary

    def record_summary(self, summary: dict[str, Any]) -> None:
        """Apply a summary produced by apply_resolution / resolve_summary."""
        from .night_of_the_zealot import INVESTIGATORS_SACRIFICED_LITA

        for player_id in summary.get("defeated_investigators", []):
            try:
                self.investigator(player_id).killed = True
            except KeyError:
                continue
        for change in summary.get("log_changes") or []:
            section = str(change.get("section", "战役记录"))
            entry = str(change.get("entry", ""))
            if change.get("remove"):
                self.remove_log_entry(section, entry)
            elif entry:
                self.log_entry(section, entry)
            elif change.get("remove_section_entry"):
                self.remove_log_entry(section, str(change["remove_section_entry"]))

        xp = int(summary.get("xp_gained", 0) or 0)
        trauma = summary.get("trauma") or {}
        physical = int(trauma.get("physical", 0) or 0)
        mental = int(trauma.get("mental", 0) or 0)
        for investigator in self.investigators:
            if investigator.killed or investigator.insane:
                continue
            investigator.xp_earned += xp
            investigator.trauma_physical += physical
            investigator.trauma_mental += mental

        for asset in summary.get("story_assets") or []:
            _grant_to_leader(self, list(asset) if isinstance(asset, (list, tuple)) else [str(asset)])
        for weakness in summary.get("story_weaknesses") or []:
            for investigator in self.active_investigators():
                code = str(weakness)
                if code and code not in investigator.story_weaknesses:
                    investigator.story_weaknesses.append(code)

        record = {
            "scenario": summary.get("scenario", ""),
            "scenario_name": summary.get("scenario_name", ""),
            "resolution": summary.get("resolution", ""),
            "title": summary.get("title", ""),
            "xp_gained": xp,
            "trauma": {"physical": physical, "mental": mental},
            "log_changes": list(summary.get("log_changes") or []),
            "defeated_investigators": list(summary.get("defeated_investigators") or []),
            "investigators_sacrificed_lita": bool(summary.get(INVESTIGATORS_SACRIFICED_LITA, False)),
        }
        self.history.append(record)

    def advance(self) -> None:
        """Move on to the next scenario (call after apply_resolution)."""
        self.scenario_index += 1

    # ------------------------------------------------------------------
    # experience / deck upgrades
    # ------------------------------------------------------------------
    def spend_xp(
        self,
        player_id: str,
        purchases: list[dict[str, Any]],
        *,
        pool: CardPool | None = None,
    ) -> list[str]:
        """Spend experience on new cards and upgrades.

        Each purchase is {"code": "01025", "replace": "01016", "count": 1}:

        * a brand new card costs max(1, level) experience and needs a free deck
          slot (give replace when the deck is already at its size limit);
        * upgrading a card you own to a higher level version of the *same name*
          costs only the difference between the two levels and replaces a copy;
        * card level is capped at MAX_CARD_LEVEL and the card class must be one
          the investigator may take.

        Returns a list of Chinese error messages; an empty list means success
        and the deck/xp_spent have been updated.
        """
        errors: list[str] = []
        try:
            investigator = self.investigator(player_id)
        except KeyError:
            return ["未知的调查员：%s" % player_id]
        if investigator.killed or investigator.insane:
            return ["%s 已经被杀害或陷入疯狂，不能再花费经验" % investigator.name]
        if not purchases:
            return []

        card_pool = pool or self.pool
        if card_pool is None:
            try:
                card_pool = CardPool.load()
            except Exception:
                card_pool = None
            self.pool = card_pool
        if card_pool is None:
            return ["无法读取卡牌数据（CardPool），无法校验升级"]

        permissions = investigator_permissions(card_pool, investigator.investigator_code)
        deck = list(investigator.deck)
        spent = 0
        budget = investigator.xp_available

        for position, purchase in enumerate(purchases, start=1):
            where = "第 %d 项升级" % position
            if not isinstance(purchase, dict):
                errors.append(where + "：格式不对，应该是 {'code': 卡号}")
                continue
            code = str(purchase.get("code", ""))
            if not code:
                errors.append(where + "：缺少卡牌编号 code")
                continue
            if not card_pool.has(code):
                errors.append(where + "：卡池里没有卡牌 %s" % code)
                continue
            defn = card_pool.get(code)
            count = int(purchase.get("count", 1) or 1)
            if count < 1:
                errors.append(where + "：count 必须至少为 1")
                continue
            replace = purchase.get("replace")
            replace = str(replace) if replace else None
            if replace is not None and replace not in deck:
                errors.append(where + "：要替换的 %s 不在 %s 的牌组里" % (replace, investigator.name))
                continue
            if defn.level > MAX_CARD_LEVEL:
                errors.append(where + "：%s 的等级 %d 超过上限 %d" % (defn.display_name, defn.level, MAX_CARD_LEVEL))
                continue
            if not _class_allowed(defn, permissions):
                errors.append(
                    where + "：%s（%s）不在 %s 的职业准入范围内"
                    % (defn.display_name, class_zh(defn.card_class), investigator.name)
                )
                continue
            if defn.card_type not in (CardType.ASSET, CardType.EVENT, CardType.SKILL):
                errors.append(where + "：%s 不是玩家卡，无法加入牌组" % defn.display_name)
                continue

            upgrade_from = None
            for candidate in deck:
                if _same_name(card_pool, candidate, defn) and card_pool.get(candidate).level < defn.level:
                    upgrade_from = candidate
                    break
            if upgrade_from is not None:
                cost = max(0, defn.level - card_pool.get(upgrade_from).level)
            else:
                cost = max(1, defn.level)
                if not replace and len(deck) >= MAX_DECK_SIZE:
                    errors.append(
                        where + "：牌组已经有 %d 张卡，加入 %s 必须同时给出 replace（替换掉一张卡）"
                        % (len(deck), defn.display_name)
                    )
                    continue
            if cost > budget:
                errors.append(
                    where + "：需要 %d 点经验，但只剩 %d 点（可用 %d）" % (cost, budget, investigator.xp_available)
                )
                continue

            copies = deck.count(code)
            if copies + count > defn.deck_limit:
                errors.append(
                    where + "：%s 超过牌组上限 %d（已有 %d 张）" % (defn.display_name, defn.deck_limit, copies)
                )
                continue

            if upgrade_from is not None:
                deck[deck.index(upgrade_from)] = code
                for _ in range(count - 1):
                    if replace:
                        deck[deck.index(replace)] = code
                    else:
                        deck.append(code)
            elif replace:
                for _ in range(count):
                    deck[deck.index(replace)] = code
            else:
                deck.extend([code] * count)
            budget -= cost
            spent += cost

        if errors:
            return errors
        investigator.deck = deck
        investigator.xp_spent += spent
        return []

    # ------------------------------------------------------------------
    # serialisation
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "difficulty": self.difficulty,
            "seed": self.seed,
            "scenario_index": self.scenario_index,
            "scenario_code": self.scenario_code(),
            "scenario_name": self.scenario_name(),
            "investigators": [i.to_dict() for i in self.investigators],
            "log": {section: list(lines) for section, lines in self.log.items()},
            "history": [dict(entry) for entry in self.history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, pool: CardPool | None = None) -> "CampaignState":
        log = {str(section): [str(line) for line in lines] for section, lines in (data.get("log") or {}).items()}
        state = cls(
            code=str(data.get("code", "night_of_the_zealot")),
            difficulty=str(data.get("difficulty", "standard")),
            seed=data.get("seed"),
            scenario_index=int(data.get("scenario_index", 0) or 0),
            investigators=[CampaignInvestigator.from_dict(item) for item in (data.get("investigators") or [])],
            log=log,
            history=[dict(entry) for entry in (data.get("history") or [])],
            pool=pool,
        )
        for section in _log_sections(state.code):
            state.log.setdefault(section, [])
        state.log.setdefault("战役记录", [])
        return state

    # -- files ----------------------------------------------------------
    def save(self, path: str | Path | None = None) -> Path:
        """Write the campaign to JSON; returns the file that was written."""
        target = Path(path) if path is not None else DEFAULT_SAVE_DIR / (self.code + ".json")
        if target.suffix == "" and target.name:
            target = target.with_suffix(".json")
        if target.parent and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: str | Path, *, pool: CardPool | None = None) -> "CampaignState":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data, pool=pool)


# ----------------------------------------------------------------------
# deck building helpers
# ----------------------------------------------------------------------
def investigator_permissions(pool: CardPool, investigator_code: str) -> dict[str, Any]:
    """Read an investigator's deckbuilding allowance.

    ahlcg.data.loader does not currently fill CardDef.deck_requirement, so the
    raw card record is consulted (deck_options).  When nothing is available we
    fall back to the investigator's own class at level 0-5 plus neutral, which
    is the safe minimum.
    """
    permissions: dict[str, Any] = {
        "cards": {},
        "secondary_class": None,
        "secondary_max_level": 0,
        "max_level": MAX_CARD_LEVEL,
        "classes": [],
        "primary_class": None,
    }
    if not (pool is not None and pool.has(investigator_code)):
        return permissions
    defn = pool.get(investigator_code)
    requirement = getattr(defn, "deck_requirement", None)
    if requirement is not None:  # pragma: no cover - loader does not build it yet
        permissions["primary_class"] = requirement.primary_class
        permissions["secondary_class"] = requirement.secondary_class
        permissions["secondary_max_level"] = requirement.secondary_max_level
        permissions["max_level"] = requirement.max_level
        if requirement.primary_class is not None:
            permissions["classes"] = [requirement.primary_class]
        return permissions

    raw = _raw_record(investigator_code)
    options = (raw or {}).get("deck_options")
    classes: list[CardClass] = []
    cards: dict[str, int] = {}
    if options:
        for option in options:
            if not isinstance(option, dict):
                continue
            level = option.get("level") or {}
            max_level = int(level.get("max", MAX_CARD_LEVEL) or MAX_CARD_LEVEL)
            for faction in option.get("faction") or []:
                try:
                    card_class = CardClass(str(faction))
                except ValueError:
                    continue
                if card_class not in classes:
                    classes.append(card_class)
                cards[str(faction)] = max(cards.get(str(faction), 0), max_level)
    if not classes:
        classes = [defn.card_class]
        cards = {defn.card_class.value: MAX_CARD_LEVEL}
    permissions["classes"] = classes
    permissions["cards"] = cards
    permissions["primary_class"] = classes[0]
    if len(classes) > 1:
        permissions["secondary_class"] = classes[-1]
        permissions["secondary_max_level"] = cards.get(classes[-1].value, 0)
    return permissions


_RAW_RECORDS: dict[str, dict[str, Any]] | None = None


def _raw_record(code: str) -> dict[str, Any] | None:
    """Look a card up in the raw ArkhamDB json (deck_options live there)."""
    global _RAW_RECORDS
    if _RAW_RECORDS is None:
        try:
            _RAW_RECORDS = json.loads(Path(CardPool.DEFAULT_DATA).read_text(encoding="utf-8"))
        except Exception:
            _RAW_RECORDS = {}
    return _RAW_RECORDS.get(code)


def _class_allowed(defn: Any, permissions: dict[str, Any]) -> bool:
    """Neutral cards are always allowed; otherwise the class must be in scope."""
    allowed = permissions.get("cards") or {}
    if defn.card_class is CardClass.NEUTRAL:
        level_cap = max(allowed.values()) if allowed else int(permissions.get("max_level", MAX_CARD_LEVEL))
        return defn.level <= int(level_cap)
    if str(defn.card_class.value) not in allowed:
        return False
    return defn.level <= int(allowed[str(defn.card_class.value)])


def _same_name(pool: CardPool, code: str, defn: Any) -> bool:
    if not pool.has(code):
        return False
    return pool.get(code).name == defn.name


def _grant_to_leader(campaign: "CampaignState", codes: Iterable[str]) -> None:
    active = campaign.active_investigators()
    if not active:
        return
    leader = active[0]
    for code in codes:
        code = str(code)
        if code and code not in leader.story_assets:
            leader.story_assets.append(code)
            campaign.log_entry("获得的故事资产/弱点", "%s 获得故事资产 %s" % (leader.name, code))


def _log_sections(code: str) -> list[str]:
    if code == "night_of_the_zealot":
        from .night_of_the_zealot import LOG_SECTIONS

        return list(LOG_SECTIONS)
    return ["战役记录", "获得的故事资产/弱点"]


def resolve_summary(campaign: "CampaignState", game: Any) -> dict[str, Any]:
    """Dispatch to the campaign's resolution table (kept importable for tests)."""
    from .night_of_the_zealot import resolve_summary as _resolve

    return _resolve(campaign, game)


def load_campaign(path: str | Path, *, pool: CardPool | None = None) -> "CampaignState":
    """Convenience wrapper: CampaignState.load(path)."""
    return CampaignState.load(path, pool=pool)


__all__ = [
    "CAMPAIGNS",
    "CampaignError",
    "CampaignInvestigator",
    "CampaignState",
    "DECK_SIZE",
    "DEFAULT_SAVE_DIR",
    "MAX_CARD_LEVEL",
    "MAX_DECK_SIZE",
    "investigator_permissions",
    "load_campaign",
    "resolve_summary",
]
'''

path.write_text(body, encoding="utf-8")
print("written", path, len(body))

"""Skill tests: the beating heart of the game.

A SkillTest is a small mutable object assembled step by step (base value,
committed cards, modifiers, revealed token) so that the interactive flow -
commit cards, reveal, resolve - maps one to one onto the rules.  Resolution
itself is a pure function, which keeps it trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ..core.enums import Skill
from ..core.events import Modifier
from ..core.rng import Rng
from .chaos import ChaosBag, ChaosToken


@dataclass(frozen=True)
class Commit:
    """One card committed to a skill test."""

    card_id: str | None = None
    icons: Mapping[Skill, int] = field(default_factory=dict)
    wild: int = 0
    label: str = ""

    def bonus_for(self, skill: Skill) -> int:
        return int(self.icons.get(skill, 0)) + self.wild


@dataclass
class SkillTest:
    skill: Skill
    difficulty: int
    base_value: int = 0
    committed: list[Commit] = field(default_factory=list)
    modifiers: list[Modifier] = field(default_factory=list)
    kind: str = "skill"
    investigator_id: str | None = None
    source: Any = None
    target: Any = None
    automatic_success: bool = False
    automatic_fail: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    # -- value ----------------------------------------------------------
    def commit(
        self,
        icons: Mapping[Skill, int] | None = None,
        *,
        wild: int = 0,
        card_id: str | None = None,
        label: str = "",
    ) -> Commit:
        entry = Commit(card_id=card_id, icons=dict(icons or {}), wild=wild, label=label)
        self.committed.append(entry)
        return entry

    def commit_card(self, card_id: str, icons: Mapping[Skill, int], wild: int = 0, label: str = "") -> Commit:
        return self.commit(icons, wild=wild, card_id=card_id, label=label)

    def add_modifier(self, value: int, source: Any = None, reason: str = "") -> None:
        self.modifiers.append(Modifier(value=value, source=source, reason=reason))

    @property
    def icon_bonus(self) -> int:
        return sum(entry.bonus_for(self.skill) for entry in self.committed)

    @property
    def modifier_total(self) -> int:
        return sum(m.value for m in self.modifiers)

    def skill_value(self) -> int:
        """Current skill value.  Per the rules a skill value cannot go below 0."""
        return max(0, self.base_value + self.icon_bonus + self.modifier_total)

    def committed_count(self) -> int:
        return len(self.committed)

    def describe(self) -> str:
        return (
            f"{self.skill.zh}检定 难度{self.difficulty} "
            f"技能值{self.skill_value()} (基础{self.base_value}"
            f"{f' 投入+{self.icon_bonus}' if self.icon_bonus else ''}"
            f"{f' 修正{self.modifier_total:+d}' if self.modifier_total else ''})"
        )


@dataclass(frozen=True)
class SkillTestResult:
    skill: Skill
    difficulty: int
    skill_value: int
    token: ChaosToken
    token_value: int
    total: int
    success: bool
    margin: int
    auto_fail: bool = False
    #: shared with the SkillTest, so abilities triggered by the result can hand
    #: extra information back to whoever started the test (damage, clues, ...)
    meta: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        verdict = "成功" if self.success else "失败"
        return (
            f"{self.skill.zh}检定 {verdict}：技能值{self.skill_value} "
            f"{'+' if self.token_value >= 0 else ''}{self.token_value}({self.token.label}) "
            f"= {self.total} vs 难度{self.difficulty}"
        )


def resolve_skill_test(
    test: SkillTest,
    bag: ChaosBag,
    rng: Rng,
    context: Any = None,
) -> SkillTestResult:
    """Reveal a chaos token and resolve the test.

    Equality counts as success (the rules use 'equal to or greater than').
    The auto-fail token always fails; automatic_success / automatic_fail
    overrides come from card effects and are applied last.
    """
    skill_value = test.skill_value()
    token = bag.draw(rng)
    token_value = bag.value_of(token, context if context is not None else test)
    total = skill_value + token_value

    if test.automatic_fail or token.is_autofail:
        success = False
    elif test.automatic_success:
        success = True
    else:
        success = total >= test.difficulty

    return SkillTestResult(
        skill=test.skill,
        difficulty=test.difficulty,
        skill_value=skill_value,
        token=token,
        token_value=token_value,
        total=total,
        success=success,
        margin=total - test.difficulty,
        auto_fail=token.is_autofail or test.automatic_fail,
        meta=test.meta,
    )


def evaluate_skill_test(
    test: SkillTest,
    token: ChaosToken,
    bag: ChaosBag,
    context: Any = None,
) -> SkillTestResult:
    """Resolve a test with an already known token (for replays and previews)."""
    skill_value = test.skill_value()
    token_value = bag.value_of(token, context if context is not None else test)
    total = skill_value + token_value
    if test.automatic_fail or token.is_autofail:
        success = False
    elif test.automatic_success:
        success = True
    else:
        success = total >= test.difficulty
    return SkillTestResult(
        skill=test.skill,
        difficulty=test.difficulty,
        skill_value=skill_value,
        token=token,
        token_value=token_value,
        total=total,
        success=success,
        margin=total - test.difficulty,
        auto_fail=token.is_autofail or test.automatic_fail,
        meta=test.meta,
    )


def sum_icons(cards: Iterable[Mapping[Skill, int]], skill: Skill, wild: int = 0) -> int:
    return sum(int(c.get(skill, 0)) for c in cards) + wild

import pytest

from ahlcg.core.enums import Skill
from ahlcg.core.rng import Rng
from ahlcg.engine.chaos import AUTOFAIL, SKULL, ChaosBag, numeric
from ahlcg.engine.skill_test import SkillTest, evaluate_skill_test, resolve_skill_test


def test_equality_is_success():
    test = SkillTest(skill=Skill.INTELLECT, difficulty=3, base_value=3)
    bag = ChaosBag.from_tokens([numeric(0)])
    result = resolve_skill_test(test, bag, Rng(1))
    assert result.success
    assert result.margin == 0
    assert result.total == 3


def test_failure_when_below_difficulty():
    test = SkillTest(skill=Skill.COMBAT, difficulty=4, base_value=3)
    bag = ChaosBag.from_tokens([numeric(-1)])
    result = resolve_skill_test(test, bag, Rng(1))
    assert not result.success
    assert result.margin == -2


def test_committed_icons_only_count_matching_skill():
    test = SkillTest(skill=Skill.INTELLECT, difficulty=4, base_value=2)
    test.commit({Skill.INTELLECT: 1, Skill.COMBAT: 2})
    assert test.icon_bonus == 1
    assert test.skill_value() == 3

    test.commit({Skill.INTELLECT: 2})
    assert test.skill_value() == 5
    assert test.committed_count() == 2


def test_skill_value_never_below_zero():
    test = SkillTest(skill=Skill.AGILITY, difficulty=2, base_value=2)
    test.add_modifier(-5, reason="test penalty")
    assert test.skill_value() == 0


def test_autofail_always_fails_even_with_big_skill():
    test = SkillTest(skill=Skill.WILLPOWER, difficulty=1, base_value=10)
    bag = ChaosBag.from_tokens([AUTOFAIL])
    result = resolve_skill_test(test, bag, Rng(1))
    assert not result.success
    assert result.auto_fail


def test_automatic_success_and_failure_flags():
    test = SkillTest(skill=Skill.WILLPOWER, difficulty=10, base_value=0, automatic_success=True)
    bag = ChaosBag.from_tokens([numeric(-8)])
    assert resolve_skill_test(test, bag, Rng(1)).success

    test = SkillTest(skill=Skill.WILLPOWER, difficulty=1, base_value=10, automatic_fail=True)
    bag = ChaosBag.from_tokens([numeric(5)])
    assert not resolve_skill_test(test, bag, Rng(1)).success


def test_symbol_modifier_applies_through_the_bag():
    test = SkillTest(skill=Skill.COMBAT, difficulty=5, base_value=5)
    bag = ChaosBag.from_tokens([SKULL])
    bag.modifiers.append(lambda token, ctx: -2 if token.is_symbol else 0)
    result = resolve_skill_test(test, bag, Rng(1))
    assert not result.success
    assert result.token_value == -2


def test_evaluate_with_known_token_is_pure():
    test = SkillTest(skill=Skill.INTELLECT, difficulty=3, base_value=2)
    bag = ChaosBag.from_tokens([numeric(0)])
    result = evaluate_skill_test(test, numeric(1), bag)
    assert result.total == 3
    assert result.success
    # evaluating does not touch the bag
    assert bag.size == 1


def test_describe_mentions_the_verdict():
    test = SkillTest(skill=Skill.INTELLECT, difficulty=2, base_value=4)
    bag = ChaosBag.from_tokens([numeric(0)])
    result = resolve_skill_test(test, bag, Rng(1))
    assert "成功" in result.describe()
    assert "智力" in result.describe()

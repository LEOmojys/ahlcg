import pytest

from ahlcg.core.enums import TokenType
from ahlcg.core.rng import Rng
from ahlcg.engine.chaos import (
    AUTOFAIL,
    SKULL,
    ChaosBag,
    ChaosToken,
    numeric,
)


def test_core_set_composition():
    bag = ChaosBag.core_set()
    assert bag.size == 16
    assert bag.count(numeric(-1)) == 3
    assert bag.count(numeric(-2)) == 2
    assert bag.count(numeric(0)) == 2
    assert bag.count(SKULL) == 2
    assert bag.count_type(TokenType.CULTIST) == 1
    assert bag.count_type(TokenType.TABLET) == 1
    assert bag.count_type(TokenType.AUTOFAIL) == 1
    assert bag.count_type(TokenType.ELDER_SIGN) == 1


def test_draw_is_deterministic_for_a_seed():
    bag = ChaosBag.core_set()
    first = [bag.draw(Rng(1234)) for _ in range(8)]
    second = [bag.draw(Rng(1234)) for _ in range(8)]
    assert first == second


def test_draw_does_not_remove_tokens():
    bag = ChaosBag.core_set()
    before = bag.size
    for _ in range(20):
        bag.draw(Rng(3))
    assert bag.size == before


def test_value_of_tokens():
    bag = ChaosBag.core_set()
    assert bag.value_of(numeric(-4)) == -4
    assert bag.value_of(numeric(1)) == 1
    assert bag.value_of(SKULL) == 0
    assert bag.value_of(AUTOFAIL) == 0


def test_symbol_modifiers_are_scenario_hooks():
    bag = ChaosBag.from_tokens([SKULL, numeric(0)])
    assert bag.value_of(SKULL) == 0

    bag.modifiers.append(lambda token, ctx: -4 if token.is_symbol else 0)
    assert bag.value_of(SKULL) == -4
    assert bag.value_of(numeric(0)) == 0


def test_success_probability_excludes_autofail():
    bag = ChaosBag.from_tokens([numeric(0), numeric(-1), AUTOFAIL])
    # token 0 -> 3 >= 3 success, token -1 -> 2 fail, autofail -> fail
    assert bag.success_probability(3, 3) == pytest.approx(1 / 3)


def test_success_probability_reacts_to_modifiers():
    bag = ChaosBag.from_tokens([SKULL, numeric(0)])
    # a bare skull token is worth 0, so both tokens pass a 4 vs 4 test
    assert bag.success_probability(4, 4) == pytest.approx(1.0)

    bag.modifiers.append(lambda token, ctx: -4 if token.is_symbol else 0)
    assert bag.value_of(SKULL) == -4
    assert bag.success_probability(4, 4) == pytest.approx(0.5)
    assert bag.success_probability(1, 1) == pytest.approx(0.5)


def test_sealing_removes_and_restores_tokens():
    bag = ChaosBag.core_set()
    bag.seal(SKULL)
    assert bag.size == 15
    assert bag.count_type(TokenType.SKULL) == 1
    assert bag.sealed == [SKULL]
    bag.unseal_all()
    assert bag.size == 16
    assert bag.sealed == []


def test_distribution_sums_to_one():
    bag = ChaosBag.core_set()
    dist = bag.distribution(4)
    assert sum(dist.values()) == pytest.approx(1.0)
    assert set(dist).issubset({4 + v for v in range(-8, 3)} | {4})


def test_remove_missing_token_raises():
    from ahlcg.core.errors import RuleError

    bag = ChaosBag.from_tokens([numeric(0)])
    with pytest.raises(RuleError):
        bag.remove(numeric(-5))


def test_token_labels():
    assert numeric(-3).label == "-3"
    assert numeric(2).label == "+2"
    assert SKULL.label == "骷髅"
    assert ChaosToken(TokenType.BLESS).base_value == 2
    assert ChaosToken(TokenType.CURSE).base_value == -2

"""战役连贯性：三幕的顺序、结算、跨场景延续，以及调查员死亡时的规则行为。

机器人并不聪明（不会换武器、不会治疗、也几乎不放弃），所以它有可能在第一幕就被食尸鬼困死——
那是**规则的合法结果**（R3：所有未放弃的调查员被杀害）。因此这里区分两类断言：
  * 场景/结算/推进的机制是否正确（与存活无关）
  * 调查员死亡时战役层是否正确拒绝继续
"""

import pytest

from ahlcg.ai import robot
from ahlcg.campaign import CampaignState
from ahlcg.campaign.game_builder import CampaignGameError, build_scenario_game
from ahlcg.data.pool import CardPool


@pytest.fixture(scope="module")
def pool():
    return CardPool.load()


def play(campaign, pool, seed_game=None):
    game = build_scenario_game(campaign, pool)
    report = robot.play(game, max_steps=80000)
    assert report["finished"], report
    return game, report


def test_each_scenario_runs_in_campaign_context(pool):
    """三幕都能在战役层里建立、打完并结算。"""
    expected = {0: "torch", 1: "arkham", 2: "tentacles"}
    for index, code in expected.items():
        campaign = CampaignState.new("night_of_the_zealot", ("01001",), "standard", seed=11, pool=pool)
        campaign.scenario_index = index
        assert campaign.scenario_code() == code

        game, _ = play(campaign, pool)
        assert game.state.scenario_code == code
        summary = campaign.apply_resolution(game)
        assert summary["scenario"] == code
        assert summary["resolution"]
        assert campaign.history, "结算必须写入战役历史"


def test_resolution_writes_the_campaign_log(pool):
    campaign = CampaignState.new("night_of_the_zealot", ("01001",), "standard", seed=11, pool=pool)
    game, _ = play(campaign, pool)
    campaign.apply_resolution(game)
    assert campaign.log, "战役日志不应为空"
    assert any(entry for entries in campaign.log.values() for entry in entries)


def test_advance_keeps_the_scenario_order(pool):
    campaign = CampaignState.new("night_of_the_zealot", ("01001",), "standard", seed=11, pool=pool)
    order = []
    while campaign.scenario_code() is not None:
        order.append(campaign.scenario_code())
        campaign.advance()
        if len(order) > 3:
            break
    assert order == ["torch", "arkham", "tentacles"]


def test_killed_investigator_stops_the_campaign(pool):
    """规则：调查员被杀害且无人可用时，战役无法继续——战役层必须明确拒绝，而不是崩掉。"""
    campaign = CampaignState.new("night_of_the_zealot", ("01001",), "standard", seed=11, pool=pool)
    game, _ = play(campaign, pool)
    summary = campaign.apply_resolution(game)
    killed = campaign.investigators[0].killed or campaign.investigators[0].insane
    if not killed:
        pytest.skip(f"这一局调查员活了下来（{summary['resolution']}），死亡路径未被触发")

    assert campaign.active_investigators() == []
    campaign.advance()
    with pytest.raises(CampaignGameError):
        build_scenario_game(campaign, pool)


def test_trauma_carries_into_the_next_scenario(pool):
    campaign = CampaignState.new("night_of_the_zealot", ("01001",), "standard", seed=11, pool=pool)
    game, _ = play(campaign, pool)
    campaign.apply_resolution(game)
    investigator = campaign.investigators[0]
    if investigator.killed or investigator.insane:
        pytest.skip("调查员已阵亡，无法验证创伤延续")

    before = (investigator.trauma_physical, investigator.trauma_mental)
    campaign.advance()
    second = build_scenario_game(campaign, pool)
    card = second.state.investigator_of(second.state.players[0])
    assert (card.damage, card.horror) == before


def test_campaign_round_trips_through_json(pool):
    campaign = CampaignState.new("night_of_the_zealot", ("01002",), "easy", seed=3, pool=pool)
    data = campaign.to_dict()
    restored = CampaignState.from_dict(data, pool=pool)
    assert restored.scenario_code() == campaign.scenario_code()
    assert restored.difficulty == campaign.difficulty
    assert restored.to_dict() == data

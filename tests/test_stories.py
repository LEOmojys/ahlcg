"""故事文本：结局正文与开场剧情都能读到，第二幕引序按战役日志分支。"""

import pytest

from ahlcg.campaign.night_of_the_zealot import (
    RESOLUTION_SOURCES,
    SCENARIO_ORDER,
    resolution_story,
    resolution_text,
    scenario_intro,
)


def test_every_ending_has_a_readable_story():
    for code, res in RESOLUTION_SOURCES:
        text = resolution_text(code, res)
        assert len(text) >= 20, f"{code}/{res} 的结局正文太短：{text!r}"
        assert resolution_story(code, res), f"{code}/{res} 的备用读取为空"


def test_intro_exists_for_every_scenario():
    for code in SCENARIO_ORDER:
        assert len(scenario_intro(code)) >= 40, code


def test_second_act_intro_branches_on_the_log():
    class FakeCampaign:
        def __init__(self, found):
            self.found = found

        def has_log_entry(self, section, entry):
            return self.found

    a = scenario_intro("arkham", FakeCampaign(True))
    b = scenario_intro("arkham", FakeCampaign(False))
    assert a != b, "第二幕引序应按日志选择不同引序"
    assert "一个惊恐的女人" in a
    assert "紧随着你屋子灾难而来" in b

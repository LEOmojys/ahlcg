"""引擎钩子：常量修正、检定中能力、投入卡的结果时机、额外行动。"""

import pytest

from ahlcg.core.enums import ChoiceKind, Skill, Trigger, Zone
from ahlcg.data.pool import CardPool
from ahlcg.engine.chaos import ChaosBag, numeric
from ahlcg.engine.skill_test import SkillTest, SkillTestResult
from ahlcg.session import GameSetup, create_game


@pytest.fixture(scope="module")
def pool():
    return CardPool.load()


def make_game(pool, seed=1):
    game = create_game(GameSetup(pool=pool, seed=seed))
    game.start()
    game.state.chaos_bag = ChaosBag.from_tokens([numeric(0)])
    player = game.state.players[0]
    player.hand.clear()
    player.deck.clear()
    player.resources = 5
    return game


def put_in_play(game, pool, code):
    state = game.state
    player = state.players[0]
    card = state.add_card(pool.get(code), zone=Zone.PLAY, controller_id=player.id)
    player.play_area.append(card.id)
    return card


def drive(gen, answer_in_test=True, confirm=True, in_test_times=1):
    """Drive an engine generator, answering prompts the way a cooperative player would.

    The during-a-test window is repeatable by design (物理训练 can be used as often
    as you can pay), so it is answered exactly in_test_times times.
    """
    used_in_test = 0
    try:
        choice = next(gen)
    except StopIteration as stop:
        return stop.value
    while True:
        picked: tuple = ()
        if choice.kind is ChoiceKind.CONFIRM:
            picked = ("yes",) if confirm else ("no",)
        elif choice.options:
            prompt = choice.prompt or ""
            if "检定中的能力" in prompt:
                if answer_in_test and used_in_test < in_test_times:
                    picked = (choice.options[0].id,)
                    used_in_test += 1
                else:
                    picked = ()
            elif choice.min_selected and choice.min_selected > 0:
                picked = tuple(o.id for o in choice.options[: choice.min_selected])
        try:
            choice = gen.send(picked)
        except StopIteration as stop:
            return stop.value


def investigator_of(game):
    return game.state.investigator_of(game.state.players[0])


def test_magnifying_glass_helps_investigation_only(pool):
    game = make_game(pool)
    put_in_play(game, pool, "01030")  # Magnifying Glass: +1 intellect while investigating
    investigator = investigator_of(game)

    result = drive(game.skill_test(investigator=investigator, skill=Skill.INTELLECT, difficulty=2, kind="investigate"))
    assert result.skill_value == 3 + 1

    fight = drive(game.skill_test(investigator=investigator, skill=Skill.COMBAT, difficulty=2, kind="fight"))
    assert fight.skill_value == 4, "放大镜不该影响战斗"


def test_holy_rosary_and_beat_cop_constants(pool):
    game = make_game(pool)
    put_in_play(game, pool, "01059")  # Holy Rosary: +1 willpower
    put_in_play(game, pool, "01018")  # Beat Cop: +1 combat
    investigator = investigator_of(game)
    assert drive(game.skill_test(investigator=investigator, skill=Skill.WILLPOWER, difficulty=2)).skill_value == 3 + 1
    assert drive(game.skill_test(investigator=investigator, skill=Skill.COMBAT, difficulty=2)).skill_value == 4 + 1


def test_physical_training_window_spends_resources(pool):
    game = make_game(pool)
    put_in_play(game, pool, "01017")  # Physical Training: [free] 1 resource -> +1 willpower/combat
    investigator = investigator_of(game)

    result = drive(
        game.skill_test(investigator=investigator, skill=Skill.COMBAT, difficulty=3, kind="fight"), answer_in_test=True
    )
    assert result.skill_value == 4 + 1
    assert game.state.players[0].resources == 4, "应当花掉 1 点资源"

    declined = drive(
        game.skill_test(investigator=investigator, skill=Skill.COMBAT, difficulty=3, kind="fight"), answer_in_test=False
    )
    assert declined.skill_value == 4
    assert game.state.players[0].resources == 4, "拒绝后不应再花资源"


def test_arcane_studies_only_offered_for_its_skills(pool):
    game = make_game(pool)
    put_in_play(game, pool, "01062")  # Arcane Studies: willpower/intellect only
    investigator = investigator_of(game)
    result = drive(game.skill_test(investigator=investigator, skill=Skill.AGILITY, difficulty=2), answer_in_test=True)
    assert result.skill_value == 2, "敏捷检定不该给出奥术研究的选项"
    assert game.state.players[0].resources == 5


def _emit_result(game, pool, code, *, kind, success=True, margin=2, skill=Skill.COMBAT):
    state = game.state
    player = state.players[0]
    card = state.add_card(pool.get(code), zone=Zone.HAND, owner_id=player.id, controller_id=player.id)
    player.hand.append(card.id)
    test = SkillTest(skill=skill, difficulty=2, kind=kind, investigator_id=state.investigator_of(player).id)
    test.commit_card(card.id, card.defn.icons, card.defn.wild_icons, card.name)
    result = SkillTestResult(
        skill=skill,
        difficulty=2,
        skill_value=4,
        token=numeric(0),
        token_value=0,
        total=4,
        success=success,
        margin=margin,
        meta=test.meta,
    )
    trigger = Trigger.ON_SUCCESS if success else Trigger.ON_FAIL
    drive(game.emit(trigger, source=card, target=None, extra_sources=[card], test=test, result=result))
    return card, test


def test_vicious_blow_adds_damage_to_a_fight(pool):
    game = make_game(pool)
    card, test = _emit_result(game, pool, "01025", kind="fight")
    assert test.meta.get("damage_bonus") == 1


def test_vicious_blow_ignores_non_fights(pool):
    game = make_game(pool)
    card, test = _emit_result(game, pool, "01025", kind="investigate")
    assert "damage_bonus" not in test.meta


def test_deduction_discovers_an_extra_clue(pool):
    game = make_game(pool)
    card, test = _emit_result(game, pool, "01039", kind="investigate", skill=Skill.INTELLECT)
    assert test.meta.get("extra_clues") == 1


def test_opportunist_returns_to_hand_when_succeeding_by_three(pool):
    game = make_game(pool)
    card, test = _emit_result(game, pool, "01053", kind="fight", margin=3)
    assert card.id in test.meta.get("keep_cards", [])

    game2 = make_game(pool, seed=2)
    card2, test2 = _emit_result(game2, pool, "01053", kind="fight", margin=1)
    assert not test2.meta.get("keep_cards")


def test_leo_de_luca_grants_an_extra_action(pool):
    game = make_game(pool)
    player = game.state.players[0]
    assert game.extra_actions(player) == 0
    put_in_play(game, pool, "01048")
    assert game.extra_actions(player) == 1


def test_shrivelling_attacks_with_willpower_and_charges(pool):
    defn = pool.get("01060")
    assert defn.meta["attack"]["skill"] == "willpower"
    assert defn.meta["attack"]["damage"] == 2
    assert defn.uses == {"charge": 4}

def test_mulligan_replaces_the_cards_you_choose(pool):
    from ahlcg.core.choices import ChoiceAnswer

    game = create_game(GameSetup(pool=pool, seed=7, mulligan=True))
    game.start()
    choice = game.awaiting
    assert choice is not None and "重抽" in choice.prompt

    hand_before = list(game.state.players[0].hand)
    discarded = hand_before[0]
    game.resolve(ChoiceAnswer(choice.id, (discarded,)))

    hand_after = game.state.players[0].hand
    assert len(hand_after) == len(hand_before)
    assert discarded not in hand_after, "被换掉的牌不应还在手里"
    assert discarded in game.state.players[0].deck, "换掉的牌要洗回牌库"


def test_mulligan_can_be_declined(pool):
    from ahlcg.core.choices import ChoiceAnswer

    game = create_game(GameSetup(pool=pool, seed=7, mulligan=True))
    game.start()
    choice = game.awaiting
    assert choice is not None
    hand_before = list(game.state.players[0].hand)
    game.resolve(ChoiceAnswer(choice.id, ()))
    assert game.state.players[0].hand == hand_before


def test_slot_limit_makes_you_discard_something(pool):
    from ahlcg.engine.actions import execute_action

    game = make_game(pool)
    game.state.flags["slot_limits"] = True
    player = game.state.players[0]
    machete = put_in_play(game, pool, "01020")     # Hand
    switchblade = put_in_play(game, pool, "01044")  # Hand
    third = game.state.add_card(pool.get("01016"), zone=Zone.HAND, owner_id=player.id, controller_id=player.id)
    player.hand.append(third.id)
    player.resources = 10

    gen = execute_action(game, player, f"play:{third.id}")
    choice = next(gen)
    assert choice.kind is ChoiceKind.CARD
    assert "槽位" in choice.prompt
    try:
        gen.send((machete.id,))
    except StopIteration:
        pass
    assert machete.id in player.discard, "槽位满时必须弃掉一张手部件"
    assert third.id in player.play_area
    assert switchblade.id in player.play_area


def test_two_handed_slot_takes_two_slots(pool):
    from ahlcg.core.enums import Slot

    defn = load_card(pool, "01029")  # Shotgun, level 4, "Hand x2"
    assert defn.slots.count(Slot.HAND) == 2


def load_card(pool, code):
    return pool.get(code)

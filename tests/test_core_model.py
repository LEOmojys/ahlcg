import pytest

from ahlcg.core.cards import CardDef, CardInstance, CardRegistry, card
from ahlcg.core.choices import ChoiceAnswer, ChoiceOption, PendingChoice
from ahlcg.core.enums import CardClass, CardType, ChoiceKind, Skill, Slot, Zone
from ahlcg.core.errors import CardDataError, ChoiceError, RuleError
from ahlcg.core.rng import Rng
from ahlcg.core.serialization import to_jsonable


def test_card_instance_tracks_damage_and_defeat():
    defn = card("01001", "Roland Banks", CardType.INVESTIGATOR, health=9, sanity=5)
    inst = CardInstance(id="inv-1", defn=defn)
    assert inst.health_remaining() == 9
    inst.damage = 9
    assert inst.is_defeated()
    assert inst.sanity_remaining() == 5


def test_asset_without_health_is_never_defeated_by_damage():
    defn = card("01020", "Machete", CardType.ASSET, cost=3, slots=(Slot.HAND,))
    inst = CardInstance(id="asset-1", defn=defn)
    inst.damage = 99
    assert inst.health_remaining() is None
    assert not inst.is_defeated()


def test_uses_are_spent_and_guarded():
    defn = card("01030", "Flashlight", CardType.ASSET, uses={"supply": 3})
    inst = CardInstance(id="asset-2", defn=defn, uses={"supply": 3})
    assert inst.use("supply") == 2
    inst.use("supply", 2)
    assert inst.uses["supply"] == 0
    with pytest.raises(RuleError):
        inst.use("supply")


def test_card_def_helpers():
    defn = CardDef(
        code="01021",
        name="Magnifying Glass",
        card_type=CardType.ASSET,
        card_class=CardClass.SEEKER,
        icons={Skill.INTELLECT: 1},
        traits=frozenset({"item", "tool"}),
    )
    assert defn.is_player_card
    assert not defn.is_encounter_card
    assert defn.icon_count(Skill.INTELLECT) == 1
    assert defn.total_icons() == 1
    assert defn.display_name == "Magnifying Glass"


def test_registry_rejects_duplicates_and_unknown_codes():
    reg = CardRegistry()
    reg.register(card("X1", "Thing", CardType.ASSET))
    with pytest.raises(CardDataError):
        reg.register(card("X1", "Other thing", CardType.ASSET))
    with pytest.raises(CardDataError):
        reg.get("NOPE")
    assert "X1" in reg
    assert len(reg) == 1


def test_pending_choice_validation():
    choice = PendingChoice(
        id="c1",
        kind=ChoiceKind.OPTION,
        player_id="p1",
        prompt="pick",
        options=[ChoiceOption("a", "A"), ChoiceOption("b", "B", disabled=True)],
        min_selected=1,
        max_selected=1,
    )
    assert choice.validate(ChoiceAnswer("c1", ("a",))) == ("a",)
    with pytest.raises(ChoiceError):
        choice.validate(ChoiceAnswer("c1", ("a", "a")))
    with pytest.raises(ChoiceError):
        choice.validate(ChoiceAnswer("c1", ("b",)))
    with pytest.raises(ChoiceError):
        choice.validate(ChoiceAnswer("nope", ("a",)))
    with pytest.raises(ChoiceError):
        choice.validate(ChoiceAnswer("c1", ()))


def test_optional_choice_can_be_cancelled():
    choice = PendingChoice(
        id="c2",
        kind=ChoiceKind.CONFIRM,
        player_id="p1",
        prompt="optional",
        options=[ChoiceOption("yes", "Yes"), ChoiceOption("no", "No")],
        optional=True,
    )
    assert choice.validate(ChoiceAnswer("c2", cancelled=True)) == ()


def test_multi_select_bounds():
    choice = PendingChoice(
        id="c3",
        kind=ChoiceKind.CARDS,
        player_id="p1",
        prompt="commit",
        options=[ChoiceOption(str(i), str(i)) for i in range(4)],
        min_selected=0,
        max_selected=3,
    )
    assert len(choice.validate(ChoiceAnswer("c3", ("0", "1")))) == 2
    with pytest.raises(ChoiceError):
        choice.validate(ChoiceAnswer("c3", ("0", "1", "2", "3")))


def test_to_jsonable_handles_dataclasses_enums_and_sets():
    defn = card(
        "01039",
        "Daisy Walker",
        CardType.INVESTIGATOR,
        card_class=CardClass.SEEKER,
        traits=frozenset({"scholar"}),
        slots=(Slot.ALLY,),
    )
    data = to_jsonable(defn)
    assert data["_type"] == "CardDef"
    assert data["card_type"] == "asset" or data["card_type"] == "investigator"
    assert data["card_class"] == "seeker"
    assert data["traits"] == ["scholar"]
    assert data["slots"] == ["ally"]


def test_rng_state_round_trip_reproduces_draws():
    rng = Rng(99)
    rng.shuffle(list(range(20)))
    snapshot = rng.state()

    expected = [rng.randint(1, 100) for _ in range(5)]

    replay = Rng(0)
    replay.set_state(snapshot)
    assert [replay.randint(1, 100) for _ in range(5)] == expected

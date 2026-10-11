"""Encounter card behaviour for the core set / Night of the Zealot.

Text is quoted from the printed cards; every effect below is a direct
transcription.  Interactive effects are generators so they can ask questions.
"""

from __future__ import annotations

from ..core.enums import AbilityKind, CardType, Skill, Trigger, Zone
from . import register


def _investigator(ctx):
    return ctx.payload.get("investigator")


# --------------------------------------------------------------------------
# treacheries
# --------------------------------------------------------------------------
def grasping_hands(ctx):
    """Grasping Hands: Revelation - Test agility (3). For each point you fail by, take 1 damage."""
    investigator = _investigator(ctx)
    result = yield from ctx.game.skill_test(
        investigator=investigator, skill=Skill.AGILITY, difficulty=3, source=ctx.source, kind="revelation"
    )
    if not result.success:
        yield from ctx.game.deal_damage(investigator, -result.margin, source=ctx.source, reason="Grasping Hands")


def rotting_remains(ctx):
    """Rotting Remains: Revelation - Test willpower (3). For each point you fail by, take 1 horror."""
    investigator = _investigator(ctx)
    result = yield from ctx.game.skill_test(
        investigator=investigator, skill=Skill.WILLPOWER, difficulty=3, source=ctx.source, kind="revelation"
    )
    if not result.success:
        yield from ctx.game.deal_horror(investigator, -result.margin, source=ctx.source, reason="Rotting Remains")


def frozen_in_fear(ctx):
    """Frozen in Fear: Revelation - Put into play in your threat area."""
    ctx.game.move_to_threat_area(ctx.controller, ctx.source)


def frozen_end_of_turn(ctx):
    """Forced - At the end of your turn: Test willpower (3). If you succeed, discard Frozen in Fear."""
    card = ctx.source
    player = ctx.state.player_of(card)
    if player is None or player.id != ctx.event.get("player"):
        return
    investigator = ctx.state.investigator_of(player)
    result = yield from ctx.game.skill_test(
        investigator=investigator, skill=Skill.WILLPOWER, difficulty=3, source=card, kind="revelation"
    )
    if result.success:
        ctx.game.discard_from_play(card)


def dissonant_voices(ctx):
    """Dissonant Voices: Revelation - Put into play in your threat area. You cannot play assets or events."""
    ctx.game.move_to_threat_area(ctx.controller, ctx.source)


def dissonant_end_of_round(ctx):
    """Forced - At the end of the round: Discard Dissonant Voices."""
    ctx.game.discard_from_play(ctx.source)


def ancient_evils(ctx):
    """Ancient Evils: Revelation - Place 1 doom on the current agenda."""
    agenda = ctx.state.current_agenda()
    if agenda is not None:
        yield from ctx.game.place_doom(agenda, 1)


def crypt_chill(ctx):
    """Crypt Chill: Revelation - Test willpower (4). If you fail, discard 1 asset (or take 2 damage)."""
    investigator = _investigator(ctx)
    player = ctx.controller
    result = yield from ctx.game.skill_test(
        investigator=investigator, skill=Skill.WILLPOWER, difficulty=4, source=ctx.source, kind="revelation"
    )
    if result.success:
        return
    assets = ctx.state.assets_of(player.id)
    if not assets:
        yield from ctx.game.deal_damage(investigator, 2, source=ctx.source, reason="Crypt Chill")
        return
    from ..core.choices import ChoiceOption, PendingChoice
    from ..core.enums import ChoiceKind

    choice = PendingChoice(
        id=ctx.game.next_choice_id(),
        kind=ChoiceKind.CARD,
        player_id=player.id,
        prompt="Crypt Chill：选择并弃掉 1 张你控制的支援卡",
        options=[ChoiceOption(a.id, a.name) for a in assets],
    )
    picked = yield from ctx.game.ask(choice)
    ctx.game.move_to_discard(player, picked[0])


def obscuring_fog(ctx):
    """Obscuring Fog: Revelation - Attach to your location. Attached location gets +2 shroud."""
    investigator = _investigator(ctx)
    location = ctx.state.maybe_card(investigator.meta.get("location_id"))
    if location is not None:
        ctx.game.attach_to_location(ctx.source, location)


def obscuring_fog_clears(ctx):
    """Forced - After attached location is successfully investigated: Discard Obscuring Fog."""
    card = ctx.source
    if card.attached_to != getattr(ctx.event.target, "id", None):
        return
    result = ctx.event.get("result")
    if result is not None and result.success:
        ctx.game.discard_from_play(card)


register("01162", revelation=grasping_hands)
register("01163", revelation=rotting_remains)
register(
    "01164",
    revelation=frozen_in_fear,
    meta={"extra_action_verbs": ("move", "fight", "evade"), "extra_action_amount": 1},
    abilities=(
        __import__("ahlcg.core.cards", fromlist=["Ability"]).Ability(
            kind=AbilityKind.FORCED, trigger=Trigger.ON_TURN_END, effect=frozen_end_of_turn, label="Frozen in Fear"
        ),
    ),
)
register(
    "01165",
    revelation=dissonant_voices,
    meta={"no_play": True},
    abilities=(
        __import__("ahlcg.core.cards", fromlist=["Ability"]).Ability(
            kind=AbilityKind.FORCED, trigger=Trigger.ON_ROUND_END, effect=dissonant_end_of_round, label="Dissonant Voices"
        ),
    ),
)
register("01166", revelation=ancient_evils)
register("01167", revelation=crypt_chill)
register(
    "01168",
    revelation=obscuring_fog,
    meta={"shroud_bonus": 2},
    abilities=(
        __import__("ahlcg.core.cards", fromlist=["Ability"]).Ability(
            kind=AbilityKind.FORCED, trigger=Trigger.ON_INVESTIGATE, effect=obscuring_fog_clears, label="Obscuring Fog"
        ),
    ),
)

# --------------------------------------------------------------------------
# locations of The Gathering
# --------------------------------------------------------------------------
def attic_enter(ctx):
    """Forced - After you enter the Attic: Take 1 horror."""
    investigator = ctx.event.target
    if investigator is None or investigator.card_type is not CardType.INVESTIGATOR:
        return
    yield from ctx.game.deal_horror(investigator, 1, source=ctx.source, reason="Attic")


def cellar_enter(ctx):
    """Forced - After you enter the Cellar: Take 1 damage."""
    investigator = ctx.event.target
    if investigator is None or investigator.card_type is not CardType.INVESTIGATOR:
        return
    yield from ctx.game.deal_damage(investigator, 1, source=ctx.source, reason="Cellar")


from ..core.cards import Ability as _Ability  # noqa: E402  (after the registrations above)

register(
    "01113",
    abilities=(_Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ENTER_LOCATION, effect=attic_enter, label="Attic"),),
)
register(
    "01114",
    abilities=(_Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ENTER_LOCATION, effect=cellar_enter, label="Cellar"),),
)
# The Parlor offers Resign; Lita Chantler can be taken with a Parley while uncontrolled.
register("01115", meta={"resign": True})
register("01117", meta={"parley": {"skill": "intellect", "difficulty": 4}})

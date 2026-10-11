"""Encounter card behaviour for 第三章《深渊吞噬者》(The Devourer Below).

Text quoted from the printed cards.  Registered from ahlcg/cards/__init__.py.
"""

from __future__ import annotations

from ..core.cards import Ability
from ..core.choices import ChoiceOption, PendingChoice
from ..core.enums import AbilityKind, CardType, ChoiceKind, Skill, TokenType, Trigger, Zone
from ..engine.actions import register_location_action
from . import register


def _investigator(ctx):
    return ctx.payload.get("investigator")


def _madness_weakness(state):
    pool = getattr(state, "pool", None)
    for card_id in state.cards:
        card = state.cards[card_id]
        if card.defn.basic_weakness and "madness" in card.defn.traits:
            return card
    return None


# --------------------------------------------------------------------------
# treacheries
# --------------------------------------------------------------------------
def umordhoths_wrath(ctx):
    """Umördhoth's Wrath: test willpower (5). For each point you fail by, discard a card or take 1 damage and 1 horror."""
    investigator = _investigator(ctx)
    result = yield from ctx.game.skill_test(
        investigator=investigator, skill=Skill.WILLPOWER, difficulty=5, source=ctx.source, kind="revelation"
    )
    if result.success:
        return
    for _ in range(-result.margin):
        player = ctx.controller
        options = []
        if player.hand:
            options.append(ChoiceOption("discard", "随机弃掉 1 张手牌"))
        options.append(ChoiceOption("suffer", "承受 1 点伤害与 1 点恐惧"))
        choice = PendingChoice(
            id=ctx.game.next_choice_id(),
            kind=ChoiceKind.OPTION,
            player_id=player.id,
            prompt="阿布霍斯的愤怒：选择一项",
            options=options,
        )
        picked = yield from ctx.game.ask(choice)
        if picked[0] == "discard":
            card_id = ctx.state.rng.choice(list(player.hand))
            ctx.state.log(f"弃掉 {ctx.state.cards[card_id].name}", kind="discard")
            ctx.game.move_to_discard(player, card_id)
        else:
            yield from ctx.game.deal_damage(investigator, 1, source=ctx.source, reason="Umôrdhoth's Wrath")
            yield from ctx.game.deal_horror(investigator, 1, source=ctx.source, reason="Umôrdhoth's Wrath")


def the_yellow_sign(ctx):
    """The Yellow Sign: test willpower (4). On failure take 2 horror and draw a Madness weakness."""
    investigator = _investigator(ctx)
    result = yield from ctx.game.skill_test(
        investigator=investigator, skill=Skill.WILLPOWER, difficulty=4, source=ctx.source, kind="revelation"
    )
    if result.success:
        return
    yield from ctx.game.deal_horror(investigator, 2, source=ctx.source, reason="The Yellow Sign")
    madness = _madness_weakness(ctx.state)
    if madness is not None:
        ctx.game.remove_from_zones(ctx.controller, madness.id)
        madness.zone = Zone.HAND
        ctx.controller.hand.append(madness.id)
        ctx.state.log(f"{madness.name} 被塞进了 {investigator.name} 的手中", kind="story")


def offer_of_power(ctx):
    """Offer of Power: Peril. Either draw 2 cards and place 2 doom on the agenda, or take 2 horror."""
    investigator = _investigator(ctx)
    choice = PendingChoice(
        id=ctx.game.next_choice_id(),
        kind=ChoiceKind.OPTION,
        player_id=ctx.controller.id,
        prompt="力量的诱惑：选择一项",
        options=[
            ChoiceOption("deal", "抽 2 张牌，并在当前阴谋卡上放置 2 个毁灭标记"),
            ChoiceOption("horror", "承受 2 点恐惧"),
        ],
    )
    picked = yield from ctx.game.ask(choice)
    if picked[0] == "deal":
        yield from ctx.game.draw_cards(ctx.controller, 2)
        agenda = ctx.state.current_agenda()
        if agenda is not None:
            yield from ctx.game.place_doom(agenda, 2)
    else:
        yield from ctx.game.deal_horror(investigator, 2, source=ctx.source, reason="Offer of Power")


def dreams_of_rlyeh(ctx):
    """Dreams of R'lyeh: put into your threat area. You get -1 willpower and -1 sanity."""
    ctx.game.move_to_threat_area(ctx.controller, ctx.source)
    ctx.source.meta["willpower_penalty"] = 1
    ctx.source.meta["sanity_penalty"] = 1


def dreams_of_rlyeh_escape(ctx):
    """[action]: Test willpower (3). If you succeed, discard Dreams of R'lyeh."""
    investigator = _investigator(ctx) or ctx.investigator
    result = yield from ctx.game.skill_test(
        investigator=investigator, skill=Skill.WILLPOWER, difficulty=3, source=ctx.source, kind="activate"
    )
    if result.success:
        ctx.game.discard_from_play(ctx.source)


# --------------------------------------------------------------------------
# enemies
# --------------------------------------------------------------------------
def umordhoth_readies(ctx):
    """Umördhoth: Forced - At the end of each investigator's turn: ready Umördhoth."""
    ctx.source.exhausted = False


def ritual_site_refills(ctx):
    """Ritual Site: Forced - At the end of the round, add clues until it holds 2 per investigator."""
    state = ctx.state
    location = ctx.source
    wanted = 2 * max(1, len([p for p in state.players if p.is_active]))
    if location.clues < wanted:
        location.clues = wanted
        state.log(f"{location.name} 的线索被补满到 {wanted} 条", kind="clue")


def byakhee_engage(ctx):
    """Screeching Byakhee: while engaged with an investigator with 4 or fewer sanity, +1 fight and +1 evade."""
    investigator = ctx.event.target
    if investigator is None or investigator.card_type is not CardType.INVESTIGATOR:
        return
    remaining = investigator.sanity_remaining()
    if remaining is not None and remaining <= 4:
        ctx.source.meta["fight_bonus"] = 1
        ctx.source.meta["evade_bonus"] = 1
        ctx.state.log("尖啸的拜亚基因为你的虚弱而更加凶暴（+1 战力/+1 闪避）", kind="encounter")


def yithian_attack(ctx):
    """Yithian Observer: Forced - When it attacks you: discard a random card, else it deals +1 damage and +1 horror."""
    enemy = ctx.source
    player = ctx.state.player_of(ctx.event.target)
    if player is None:
        return
    if player.hand:
        card_id = ctx.state.rng.choice(list(player.hand))
        ctx.state.log(f"伊斯观察者夺走了 {ctx.state.cards[card_id].name}", kind="discard")
        ctx.game.move_to_discard(player, card_id)
        return
    enemy.meta["attack_damage_bonus"] = 1
    enemy.meta["attack_horror_bonus"] = 1


def dark_young_recovers(ctx):
    """Relentless Dark Young: Forced - At the end of the round: heal 2 damage from it."""
    ctx.source.damage = max(0, ctx.source.damage - 2)


def goat_spawn_death(ctx):
    """Goat Spawn: Forced - When it is defeated: each investigator at this location takes 1 horror."""
    state = ctx.state
    enemy = ctx.source
    where = enemy.location_id
    if where is None and enemy.engaged_with:
        for player in state.players:
            if player.id in enemy.engaged_with:
                where = state.investigator_of(player).meta.get("location_id")
    for player in state.players:
        if not player.is_active:
            continue
        investigator = state.investigator_of(player)
        if investigator.meta.get("location_id") == where:
            yield from ctx.game.deal_horror(investigator, 1, source=enemy, reason="Goat Spawn")


def deep_one_engages(ctx):
    """Young Deep One: Forced - After it engages you: take 1 horror."""
    investigator = ctx.event.target
    if investigator is None or investigator.card_type is not CardType.INVESTIGATOR:
        return
    yield from ctx.game.deal_horror(investigator, 1, source=ctx.source, reason="Young Deep One")


def woods_entry_test(ctx):
    """Arkham Woods 01150: Forced - After you enter: test willpower (4); on failure take 1 horror and 1 damage."""
    investigator = ctx.event.target
    if investigator is None or investigator.card_type is not CardType.INVESTIGATOR:
        return
    result = yield from ctx.game.skill_test(
        investigator=investigator, skill=Skill.WILLPOWER, difficulty=4, source=ctx.source, kind="revelation"
    )
    if not result.success:
        yield from ctx.game.deal_horror(investigator, 1, source=ctx.source, reason="Arkham Woods")
        yield from ctx.game.deal_damage(investigator, 1, source=ctx.source, reason="Arkham Woods")


# --------------------------------------------------------------------------
# location actions
# --------------------------------------------------------------------------
def woods_heal(game, player, location):
    """01155 Arkham Woods: [action] Heal 1 damage or heal 1 horror. (Limit once per turn.)"""
    investigator = game.state.investigator_of(player)
    choice = PendingChoice(
        id=game.next_choice_id(),
        kind=ChoiceKind.OPTION,
        player_id=player.id,
        prompt="林间空地：治疗什么？",
        options=[ChoiceOption("damage", "治疗 1 点伤害"), ChoiceOption("horror", "治疗 1 点恐惧")],
    )
    picked = yield from game.ask(choice)
    if picked[0] == "damage":
        game.heal(investigator, damage=1)
    else:
        game.heal(investigator, horror=1)


register_location_action("woods_heal", woods_heal)

register("01150", abilities=(Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ENTER_LOCATION, effect=woods_entry_test, label="Arkham Woods"),))
register("01151", meta={"move_test": {"skill": "intellect", "difficulty": 3}})
register("01152", meta={"investigate_skill": "willpower"})
register("01153", meta={"investigate_skill": "agility"})
register("01154", meta={"investigate_skill": "combat"})
register("01155", meta={"location_actions": [{"id": "woods_heal", "label": "治疗 1 点伤害或恐惧", "limit": "turn"}]})
register(
    "01156",
    abilities=(Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ROUND_END, effect=ritual_site_refills, label="Ritual Site"),),
)
register(
    "01157",
    abilities=(
        Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_TURN_END, effect=umordhoth_readies, label="Umôrdhoth"),
    ),
)
register("01158", revelation=umordhoths_wrath)
register(
    "01175",
    abilities=(Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ENEMY_ENGAGED, effect=byakhee_engage, label="Screeching Byakhee"),),
)
register("01176", revelation=the_yellow_sign)
register(
    "01177",
    abilities=(Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ENEMY_ATTACK, effect=yithian_attack, label="Yithian Observer"),),
)
register("01178", revelation=offer_of_power)
register(
    "01179",
    abilities=(Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ROUND_END, effect=dark_young_recovers, label="Relentless Dark Young"),),
)
register(
    "01180",
    abilities=(Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ENEMY_DEFEATED, effect=goat_spawn_death, label="Goat Spawn"),),
)
register(
    "01181",
    abilities=(Ability(kind=AbilityKind.FORCED, trigger=Trigger.ON_ENEMY_ENGAGED, effect=deep_one_engages, label="Young Deep One"),),
)
register(
    "01182",
    meta={"penalty": [{"skill": "willpower", "amount": 1}]},
    revelation=dreams_of_rlyeh,
    abilities=(
        Ability(kind=AbilityKind.ACTIVATED, label="挣脱梦境", effect=dreams_of_rlyeh_escape),
    ),
)

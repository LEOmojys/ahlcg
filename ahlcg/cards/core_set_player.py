"""Behaviour of the core-set *player* cards.

The card definitions themselves are data (see ahlcg/data/loader.py).  This module
registers the code that data cannot express: weapons the basic Fight action can
use, activated abilities, reactions, event resolutions and weaknesses.

Every card below carries its printed English text as a comment above the
implementation, and every implementation was written from that text only.

NOT IMPLEMENTED
---------------
Cards with no registration at all, and why:

* 01017 Physical Training - a [fast] ability usable *during* a skill test; the
  engine only offers hand cards in the commit window, so the ability cannot be
  activated at the printed timing.
* 01030 Magnifying Glass - "You get +1 [intellect] while investigating" is a
  constant stat bonus; the engine has no constant skill-modifier hook and never
  reads such a meta key, so registering one would be dead code.
* 01048 Leo De Luca - "You may take an additional action during your turn": the
  engine does not model action-pool changes (no turn-start action hook).
* 01059 Holy Rosary - constant +1 [willpower]; same reason as Magnifying Glass.
* 01060 Shrivelling - "This attack uses [willpower] instead of [combat]" plus a
  symbol-token horror trigger; the engine's Fight action fixes the skill to
  [combat] and gives card code no post-reveal hook.
* 01062 Arcane Studies - same timing problem as Physical Training.
* 01025 Vicious Blow / 01039 Deduction - "If this skill test is successful ...";
  the engine discards committed cards before any success reaction could resolve
  and exposes no per-test result hook to a committed card, so the extra damage
  or clue cannot be applied at the right time.
* 01053 Opportunist - "If you succeed by 3 or more, return Opportunist to your
  hand"; the same missing committed-card result hook.
* 01093 Unexpected Courage - "Max 1 committed per skill test" is a commit
  restriction the engine keeps outside card behaviour; its icon is data.

Cards that ARE registered but lose one printed clause, because the engine cannot
express it:

* 01018 Beat Cop - the constant "+1 [combat]" is not modelled (no constant stat
  hook); its [fast] discard ability is registered.
* 01031 Old Book of Lore - the "shuffles the remaining cards into his or her
  deck" wording is approximated: the deck is shuffled and the remaining cards
  stay in the deck, but the searched cards are not reordered first.
* 01033 Dr. Milan Christopher - the constant "+1 [intellect]" is not modelled
  (see Magnifying Glass); the reaction after a successful investigation is.
* 01065 Ward of Protection - the engine emits ON_TREACHERY_REVEALED but never
  reads a cancellation flag from the event, so the card sets
  payload["cancelled"] for the caller and takes the horror cost.  The
  cancellation itself only takes effect once the engine honours that flag.
* 01007 Cover Up - same shape: clue discovery is lead by the engine
  (actions._investigate) and the card can only set payload["clues_cancelled"]
  from an ON_DISCOVER_CLUE reaction; the engine does not consult it yet.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from ..core.cards import Ability, Cost, CardInstance
from ..core.choices import ChoiceOption, PendingChoice
from ..core.enums import AbilityKind, CardType, ChoiceKind, CostKind, Skill, Trigger, Zone
from ..engine.effects import EffectContext

from . import register


# ==========================================================================
# small generic helpers
# ==========================================================================
def _effect_of(ctx: EffectContext) -> Callable[[EffectContext], Any] | None:
    """The ability currently resolving, if the caller supplied it."""
    return ctx.get("effect")


def _run_effect(ctx: EffectContext):
    """Continue a nested effect (generator or plain callable) inside a card effect."""
    effect = _effect_of(ctx)
    if effect is None:
        return
    result = effect(ctx)
    if inspect.isgenerator(result):
        yield from result


def _ask_option(ctx: EffectContext, prompt: str, options: list[tuple[str, str]]):
    """ctx.ask_option as a generator, usable even when a test drives an effect bare."""
    asker = getattr(ctx, "ask_option", None)
    if asker is None:
        return (yield from _run_effect(ctx))
    return (yield from asker(prompt, options))


def _ask_selection(ctx: EffectContext, choice: PendingChoice) -> tuple[str, ...]:
    """Ask a raw PendingChoice (multi-select windows are not covered by the helpers)."""
    asker = getattr(ctx, "ask", None)
    if asker is None:
        yield from _run_effect(ctx)
        return ()
    return (yield from asker(choice))


def _current_location(ctx: EffectContext) -> CardInstance | None:
    inv = ctx.investigator
    if inv is None:
        return None
    return ctx.state.maybe_card(inv.meta.get("location_id"))


def _players_at(ctx: EffectContext, location: CardInstance | None) -> list[Any]:
    """Every player whose investigator is at the given location (including mine)."""
    if location is None:
        return []
    out = []
    for player in ctx.state.players:
        inv = ctx.state.maybe_card(player.investigator_id)
        if inv is not None and inv.meta.get("location_id") == location.id:
            out.append(player)
    return out


def _candidates_at(ctx: EffectContext, location: CardInstance | None) -> list[Any]:
    """My seat first, then any other investigator at the same location."""
    out = [ctx.controller] if ctx.controller is not None else []
    for player in _players_at(ctx, location):
        if player not in out:
            out.append(player)
    return out


def _damage_enemy(ctx: EffectContext, enemy: CardInstance, amount: int, source: Any):
    """Deal amount damage to an enemy through the engine, so its triggers fire."""
    deal = getattr(ctx.game, "deal_damage", None)
    if deal is None:  # pragma: no cover - only for foreign Game stand-ins
        enemy.damage += amount
        ctx.log(f"{enemy.name} 受到 {amount} 点伤害（{enemy.damage}/{enemy.defn.health}）")
        if enemy.is_defeated():
            yield from ctx.game.defeat_card(enemy, source=source)
        return
    yield from deal(enemy, amount, source=source, reason="卡牌效果")


def _put_in_threat_area(ctx: EffectContext) -> CardInstance | None:
    card = ctx.source
    if card is None:
        return None
    card.zone = Zone.THREAT_AREA
    if ctx.controller is not None:
        card.controller_id = ctx.controller.id
        if card.id not in ctx.controller.threat_area:
            ctx.controller.threat_area.append(card.id)
    who = ctx.investigator.name if ctx.investigator is not None else ""
    ctx.log(f"{card.name} 进入{who}的威胁区")
    return card


def _pick_location(ctx: EffectContext, prompt: str):
    """Pick the investigator's location or one connected to it."""
    state = ctx.state
    current = _current_location(ctx)
    if current is None:
        return None
    choices: list[CardInstance] = [current]
    for other in state.connections_of(current.id):
        loc = state.maybe_card(other)
        if loc is not None:
            choices.append(loc)
    if len(choices) == 1:
        return choices[0]
    options = [(loc.id, loc.name) for loc in choices]
    picked = yield from _ask_option(ctx, prompt, options)
    return state.maybe_card(picked) or choices[0]


def _search_top_of_deck(ctx: EffectContext, player: Any, predicate: Callable[[CardInstance], bool] | None, label: str):
    """Look at the top 3 cards of the deck, draw one match, shuffle the deck."""
    seen = list(player.deck[:3])
    if not seen:
        ctx.log(f"{label}：牌库已空，没有可搜寻的牌")
        return
    matches = [cid for cid in seen if predicate is None or predicate(ctx.state.cards[cid])]
    if not matches:
        ctx.log(f"{label}：牌库顶 3 张中没有符合条件的牌")
        ctx.state.rng.shuffle(player.deck)
        return
    if len(matches) == 1:
        picked = matches[0]
    else:
        options = [(cid, ctx.state.cards[cid].name) for cid in matches]
        picked = yield from _ask_option(ctx, "选择要加入手牌的牌", options)
        if picked not in player.deck:
            picked = matches[0]
    player.deck.remove(picked)
    card = ctx.state.cards[picked]
    player.hand.append(picked)
    card.zone = Zone.HAND
    ctx.log(f"{label}：{card.name} 加入手牌")
    ctx.state.rng.shuffle(player.deck)


def _discard_source(ctx: EffectContext):
    source = ctx.source
    if source is None or ctx.controller is None:
        return
    if source.card_type is CardType.ASSET:
        ctx.log(f"{source.name} 被弃置")
        ctx.game.move_to_discard(ctx.controller, source.id)


def _uses_left(ctx: EffectContext, name: str) -> bool:
    return ctx.source is not None and ctx.source.uses.get(name, 0) > 0


def _spend_ammo(ctx: EffectContext) -> bool:
    """Spend 1 ammo; discard the weapon when its last ammo is gone."""
    source = ctx.source
    if source is None:
        return False
    source.use("ammo")
    if source.uses.get("ammo", 0) <= 0:
        ctx.log(f"{source.name} 的弹药耗尽")
        _discard_source(ctx)
    return True


def _weapon_attack(ctx: EffectContext, enemy: CardInstance, *, multiplier: int = 1, label: str = "攻击"):
    """Run a Fight test with this weapon's combat bonus and deal its damage."""
    inv = ctx.investigator
    if inv is None:
        return
    bonus = int((ctx.source.defn.meta.get("attack") or {}).get("combat_bonus", 0)) if ctx.source else 0
    result = yield from ctx.game.skill_test(
        investigator=inv,
        skill=Skill.COMBAT,
        difficulty=enemy.defn.fight or 0,
        source=ctx.source or inv,
        target=enemy,
        kind="fight",
        bonus=bonus,
    )
    if result.success:
        yield from _damage_enemy(ctx, enemy, multiplier, inv)
        ctx.log(f"{label}：对 {enemy.name} 造成 {multiplier} 点伤害")


def _pick_engaged_enemy(ctx: EffectContext):
    inv = ctx.investigator
    player = ctx.controller
    if inv is None or player is None:
        return None
    enemies = list(ctx.state.engaged_enemies(player.id))
    if not enemies:
        location = _current_location(ctx)
        if location is not None:
            enemies = list(ctx.state.enemies_at(location.id))
    if not enemies:
        return None
    if len(enemies) == 1:
        return enemies[0]
    options = [(e.id, e.name) for e in enemies]
    picked = yield from _ask_option(ctx, "攻击哪个敌人？", options)
    return ctx.state.maybe_card(picked) or enemies[0]


def _ammo_attack_effect(ctx: EffectContext):
    """[action] Spend 1 ammo: Fight. - the ammo is this card's own cost."""
    source = ctx.source
    if source is None:
        return
    if not _spend_ammo(ctx):
        return
    enemy = yield from _pick_engaged_enemy(ctx)
    if enemy is None:
        ctx.log(f"{source.name}：没有可攻击的敌人")
        return
    multiplier = int((source.defn.meta.get("attack") or {}).get("damage", 1)) + 1
    yield from _weapon_attack(ctx, enemy, multiplier=multiplier, label=source.name)


# ==========================================================================
# 01016 .45 Automatic
#
# Uses (4 ammo).
# [action] Spend 1 ammo: Fight. You get +1 [combat] for this attack.
# This attack deals +1 damage.
# ==========================================================================
# The basic Fight action reads meta["attack"].  Its own cost is "spend 1 ammo",
# which the engine's cost list does not model, so the ability checks and spends
# the ammo itself and the printed damage (1 + 1) lives in the effect.
register(
    "01016",
    meta={"attack": {"combat_bonus": 1, "damage": 1}},
    abilities=(
        Ability(
            kind=AbilityKind.ACTIVATED,
            costs=(Cost(CostKind.ACTION),),
            condition=lambda ctx: _uses_left(ctx, "ammo"),
            effect=_ammo_attack_effect,
            label="[action] 消耗 1 弹药：战斗，+1 战斗力且造成 +1 伤害",
        ),
    ),
)


# ==========================================================================
# 01018 Beat Cop
#
# You get +1 [combat].
# [fast] Discard Beat Cop: Deal 1 damage to an enemy at your location.
# ==========================================================================
def _beat_cop_effect(ctx: EffectContext):
    location = _current_location(ctx)
    if location is None:
        return
    enemies = ctx.state.enemies_at(location.id)
    if not enemies:
        return
    if len(enemies) == 1:
        enemy = enemies[0]
    else:
        options = [(e.id, e.name) for e in enemies]
        picked = yield from _ask_option(ctx, "对哪个敌人造成 1 点伤害？", options)
        enemy = ctx.state.maybe_card(picked) or enemies[0]
    if enemy is not None:
        yield from _damage_enemy(ctx, enemy, 1, ctx.source)
        ctx.log(f"Beat Cop 对 {enemy.name} 造成 1 点伤害")
    # "Discard Beat Cop" is part of the cost; the engine has no DISCARD cost kind
    # it can pay, so the effect discards the card itself.
    _discard_source(ctx)


register(
    "01018",
    abilities=(
        Ability(
            kind=AbilityKind.ACTIVATED,
            costs=(),
            effect=_beat_cop_effect,
            label="[fast] 弃置 Beat Cop：对同地点的敌人造成 1 点伤害并弃置它（+1 战斗力常驻效果未实现）",
        ),
    ),
)


# ==========================================================================
# 01019 First Aid
#
# Uses (3 supplies). If First Aid has no supplies, discard it.
# [action] Spend 1 supply: Heal 1 damage or horror from an investigator at your
# location.
# ==========================================================================
def _first_aid_can_activate(ctx: EffectContext) -> bool:
    return ctx.source is not None and ctx.source.uses.get("supply", 0) > 0


def _first_aid_effect(ctx: EffectContext):
    source = ctx.source
    if source is None:
        return
    # supplies are a card-defined counter, not a CostKind the engine knows
    if source.uses.get("supply", 0) <= 0:
        ctx.log("First Aid 没有补给，弃置")
        _discard_source(ctx)
        return
    source.use("supply")
    location = _current_location(ctx)
    candidates = _candidates_at(ctx, location)
    if not candidates:
        return
    if len(candidates) == 1:
        target_player = candidates[0]
    else:
        options = [(p.id, ctx.state.investigator_of(p).name) for p in candidates]
        picked = yield from _ask_option(ctx, "治疗哪位调查员？", options)
        target_player = ctx.state.player(picked) if picked else candidates[0]
    target = ctx.state.maybe_card(target_player.investigator_id)
    if target is None:
        return
    if target.damage > 0 and target.horror > 0:
        picked = yield from _ask_option(ctx, "治疗 1 点伤害还是 1 点恐惧？", [("damage", "伤害"), ("horror", "恐惧")])
    elif target.damage > 0:
        picked = "damage"
    elif target.horror > 0:
        picked = "horror"
    else:
        return
    if picked == "damage":
        ctx.game.heal(target, damage=1)
    else:
        ctx.game.heal(target, horror=1)
    if source.uses.get("supply", 0) <= 0:
        ctx.log("First Aid 的补给耗尽，弃置")
        _discard_source(ctx)


register(
    "01019",
    abilities=(
        Ability(
            kind=AbilityKind.ACTIVATED,
            costs=(Cost(CostKind.ACTION),),
            condition=_first_aid_can_activate,
            effect=_first_aid_effect,
            label="[action] 消耗 1 补给：治疗同地点调查员 1 点伤害或恐惧",
        ),
    ),
)


# ==========================================================================
# 01020 Machete
#
# [action]: Fight. You get +1 [combat] for this attack. If the attacked enemy is
# the only enemy engaged with you, this attack deals +1 damage.
# ==========================================================================
# The unconditional part is +1 combat; the +1 damage applies while the attacked
# enemy is the only one engaged with you (modelled by only_engaged_bonus).
register(
    "01020",
    meta={"attack": {"combat_bonus": 1, "damage": 1, "only_engaged_bonus": 1}},
)


# ==========================================================================
# 01021 Guard Dog
#
# [reaction] When an enemy attack deals damage to Guard Dog: Deal 1 damage to
# the attacking enemy.
# ==========================================================================
def _guard_dog_condition(ctx: EffectContext) -> bool:
    source = ctx.source
    if source is None or ctx.event is None:
        return False
    if ctx.event.target is not source:
        return False
    attacker = ctx.event.source
    return attacker is not None and attacker.card_type is CardType.ENEMY


def _guard_dog_effect(ctx: EffectContext):
    attacker = ctx.event.source if ctx.event is not None else None
    if attacker is not None:
        yield from _damage_enemy(ctx, attacker, 1, ctx.source)
        ctx.log(f"Guard Dog 反击 {attacker.name}，造成 1 点伤害")


register(
    "01021",
    abilities=(
        Ability(
            kind=AbilityKind.TRIGGERED,
            trigger=Trigger.ON_DAMAGE_TAKEN,
            condition=_guard_dog_condition,
            effect=_guard_dog_effect,
            label="[reaction] 敌方攻击对 Guard Dog 造成伤害时：对攻击者造成 1 点伤害",
        ),
    ),
)


# ==========================================================================
# 01031 Old Book of Lore
#
# [action] Exhaust Old Book of Lore: Choose an investigator at your location.
# That investigator searches the top 3 cards of his or her deck for a card,
# draws it, and shuffles the remaining cards into his or her deck.
# ==========================================================================
def _old_book_effect(ctx: EffectContext):
    location = _current_location(ctx)
    candidates = _candidates_at(ctx, location)
    if not candidates:
        return
    if len(candidates) == 1:
        target_player = candidates[0]
    else:
        options = [(p.id, ctx.state.investigator_of(p).name) for p in candidates]
        picked = yield from _ask_option(ctx, "选择要搜寻牌库的调查员", options)
        target_player = ctx.state.player(picked) if picked else candidates[0]
    yield from _search_top_of_deck(ctx, target_player, None, "Old Book of Lore")


register(
    "01031",
    abilities=(
        Ability(
            kind=AbilityKind.ACTIVATED,
            costs=(Cost(CostKind.ACTION), Cost(CostKind.EXHAUST)),
            effect=_old_book_effect,
            label="[action] 消耗 Old Book of Lore：同地点调查员搜寻牌库顶 3 张，抽 1 张并洗牌",
        ),
    ),
)


# ==========================================================================
# 01033 Dr. Milan Christopher
#
# You get +1 [intellect].
# [reaction] After you successfully investigate: Gain 1 resource.
# ==========================================================================
def _milan_condition(ctx: EffectContext) -> bool:
    if ctx.controller is None:
        return False
    return ctx.get("kind", "investigate") == "investigate"


def _milan_effect(ctx: EffectContext):
    result = ctx.get("result")
    if result is not None and getattr(result, "success", False) and ctx.controller is not None:
        ctx.controller.resources += 1
        ctx.log(f"Dr. Milan Christopher：{ctx.investigator.name} 获得 1 资源")


register(
    "01033",
    abilities=(
        Ability(
            kind=AbilityKind.TRIGGERED,
            trigger=Trigger.ON_INVESTIGATE,
            condition=_milan_condition,
            effect=_milan_effect,
            label="[reaction] 成功调查后：获得 1 资源（+1 智力常驻效果未实现）",
        ),
    ),
)


# ==========================================================================
# 01044 Switchblade
#
# Fast.
# [action]: Fight. If you succeed by 2 or more, this attack deals +1 damage.
# ==========================================================================
# No unconditional combat bonus; the basic Fight action can still use it.
register(
    "01044",
    meta={"attack": {"combat_bonus": 0, "damage": 1}},
)


# ==========================================================================
# 01045 Burglary
#
# [action] Exhaust Burglary: Investigate. If you succeed, instead of discovering
# clues, gain 3 resources.
# ==========================================================================
def _burglary_effect(ctx: EffectContext):
    location = _current_location(ctx)
    inv = ctx.investigator
    if location is None or inv is None:
        return
    result = yield from ctx.game.skill_test(
        investigator=inv,
        skill=Skill.INTELLECT,
        difficulty=location.defn.shroud or 0,
        source=location,
        kind="investigate",
    )
    if result.success and ctx.controller is not None:
        ctx.controller.resources += 3
        ctx.log(f"Burglary：{inv.name} 获得 3 资源（不发现线索）")


register(
    "01045",
    abilities=(
        Ability(
            kind=AbilityKind.ACTIVATED,
            costs=(Cost(CostKind.ACTION), Cost(CostKind.EXHAUST)),
            effect=_burglary_effect,
            label="[action] 消耗 Burglary：调查；成功则改为获得 3 资源",
        ),
    ),
)


# ==========================================================================
# 01047 .41 Derringer
#
# Uses (3 ammo).
# [action] Spend 1 ammo: Fight. You get +2 [combat] for this attack. If you
# succeed by 2 or more, this attack deals +1 damage.
# ==========================================================================
# Ammo and the succeed-by-2 rider belong to the action layer; the unconditional
# +2 combat is what the basic Fight action reads.
register(
    "01047",
    meta={"attack": {"combat_bonus": 2, "damage": 1}},
)


# ==========================================================================
# 01063 Arcane Initiate
#
# Forced - After Arcane Initiate enters play: Place 1 doom on it.
# [fast] Exhaust Arcane Initiate: Search the top 3 cards of your deck for a
# [[Spell]] card and draw it. Shuffle your deck.
# ==========================================================================
def _arcane_initiate_enter(ctx: EffectContext):
    source = ctx.source
    if source is None:
        return
    place = getattr(ctx.game, "place_doom", None)
    if place is not None:
        yield from place(source, 1)
    else:  # pragma: no cover - only for foreign Game stand-ins
        source.doom += 1
        ctx.log(f"{source.name} 上放置 1 个毁灭标记（{source.doom}）")


def _is_spell(card: CardInstance) -> bool:
    return "spell" in card.defn.traits


def _arcane_initiate_search(ctx: EffectContext):
    if ctx.controller is None:
        return
    yield from _search_top_of_deck(ctx, ctx.controller, _is_spell, "Arcane Initiate")


register(
    "01063",
    abilities=(
        Ability(
            kind=AbilityKind.FORCED,
            trigger=Trigger.ON_ENTER_PLAY,
            effect=_arcane_initiate_enter,
            label="Forced - Arcane Initiate 进场后：在其上放置 1 个毁灭标记",
        ),
        Ability(
            kind=AbilityKind.ACTIVATED,
            costs=(Cost(CostKind.EXHAUST),),
            effect=_arcane_initiate_search,
            label="[fast] 消耗 Arcane Initiate：搜寻牌库顶 3 张中的 Spell 牌并抽到手中",
        ),
    ),
)


# ==========================================================================
# events
# ==========================================================================
# 01088 Emergency Cache
#
# Gain 3 resources.
# ==========================================================================
def _emergency_cache(ctx: EffectContext):
    if ctx.controller is not None:
        ctx.controller.resources += 3
        ctx.log(f"Emergency Cache：{ctx.investigator.name} 获得 3 资源")


register("01088", play=_emergency_cache)


# 01022 Evidence!
#
# Fast. Play after you defeat an enemy.
# Discover 1 clue at your location.
# ==========================================================================
def _evidence(ctx: EffectContext):
    inv = ctx.investigator
    if inv is not None:
        ctx.game.discover_clue(inv, None, 1)


register("01022", play=_evidence)


# 01023 Dodge
#
# Fast. Play when an enemy attacks an investigator at your location.
# Cancel that attack.
# ==========================================================================
def _dodge(ctx: EffectContext):
    # The engine emits ON_ENEMY_ATTACK with damage/horror in the payload but has
    # no interception hook; setting these flags is what a future engine reads.
    ctx.payload["cancelled"] = True
    ctx.payload["damage"] = 0
    ctx.payload["horror"] = 0
    ctx.log("Dodge：取消这次敌人攻击")


register("01023", play=_dodge)


# 01024 Dynamite Blast
#
# Choose either your location or a connecting location. Deal 3 damage to each
# enemy and to each investigator at the chosen location.
# ==========================================================================
def _dynamite_blast(ctx: EffectContext):
    location = yield from _pick_location(ctx, "选择要爆破的地点")
    if location is None:
        return
    ctx.log(f"Dynamite Blast：{location.name} 遭到爆破")
    for enemy in list(ctx.state.enemies_at(location.id)):
        yield from _damage_enemy(ctx, enemy, 3, ctx.source)
    for player in ctx.state.players:
        inv = ctx.state.maybe_card(player.investigator_id)
        if inv is None or inv.meta.get("location_id") != location.id:
            continue
        yield from ctx.game.assign_damage(inv, 3, source=ctx.source, reason="Dynamite Blast")


register("01024", play=_dynamite_blast)


# 01037 Working a Hunch
#
# Fast. Play only during your turn.
# Discover 1 clue at your location.
# ==========================================================================
def _working_a_hunch(ctx: EffectContext):
    inv = ctx.investigator
    if inv is not None:
        ctx.game.discover_clue(inv, None, 1)


register("01037", play=_working_a_hunch)


# 01050 Elusive
#
# Fast. Play only during your turn.
# Disengage from each enemy engaged with you and move to a revealed location
# with no enemies.
# ==========================================================================
def _elusive(ctx: EffectContext):
    if ctx.controller is None:
        return
    inv = ctx.investigator
    player = ctx.controller
    for enemy in list(ctx.state.engaged_enemies(player.id)):
        ctx.game.disengage(enemy, player)
    candidates = [loc for loc in ctx.state.revealed_locations() if not ctx.state.enemies_at(loc.id)]
    if not candidates or inv is None:
        return
    if len(candidates) == 1:
        destination = candidates[0]
    else:
        options = [(loc.id, loc.name) for loc in candidates]
        picked = yield from _ask_option(ctx, "移动到哪个地点？", options)
        destination = ctx.state.maybe_card(picked) or candidates[0]
    yield from ctx.game.move_investigator(inv, destination.id)


register("01050", play=_elusive)


# 01051 Backstab
#
# Fight. This attack uses [agility] instead of [combat]. This attack deals
# +2 damage.
# ==========================================================================
def _backstab(ctx: EffectContext):
    inv = ctx.investigator
    player = ctx.controller
    if inv is None or player is None:
        return
    enemies = list(ctx.state.engaged_enemies(player.id))
    if not enemies:
        location = _current_location(ctx)
        if location is not None:
            enemies = list(ctx.state.enemies_at(location.id))
    if not enemies:
        ctx.log("Backstab：没有可攻击的敌人")
        return
    if len(enemies) == 1:
        enemy = enemies[0]
    else:
        options = [(e.id, e.name) for e in enemies]
        picked = yield from _ask_option(ctx, "背刺哪个敌人？", options)
        enemy = ctx.state.maybe_card(picked) or enemies[0]
    result = yield from ctx.game.skill_test(
        investigator=inv,
        skill=Skill.AGILITY,
        difficulty=enemy.defn.fight or 0,
        source=ctx.source,
        target=enemy,
        kind="fight",
    )
    if result.success:
        yield from _damage_enemy(ctx, enemy, 3, inv)
        ctx.log(f"Backstab：对 {enemy.name} 造成 3 点伤害")


register("01051", play=_backstab)


# 01065 Ward of Protection
#
# Fast. Play when you draw a non-weakness treachery card.
# Cancel that card's revelation effect. Then, take 1 horror.
# ==========================================================================
def _ward_of_protection(ctx: EffectContext):
    ctx.payload["cancelled"] = True
    ctx.log("Ward of Protection：取消该卡牌的启示效果")
    inv = ctx.investigator
    if inv is not None:
        yield from ctx.game.deal_horror(inv, 1, source=ctx.source, reason="Ward of Protection")


register("01065", play=_ward_of_protection)


# 01079 "Look what I found!"
#
# Fast. Play after you fail a skill test by 2 or less while investigating.
# Discover 2 clues in your location.
# ==========================================================================
def _look_what_i_found(ctx: EffectContext):
    inv = ctx.investigator
    if inv is not None:
        ctx.game.discover_clue(inv, None, 2)


register("01079", play=_look_what_i_found)


# 01080 Lucky!
#
# Fast. Play when you would fail a skill test.
# Get +2 to your skill value for that test.
# ==========================================================================
def _lucky(ctx: EffectContext):
    test = ctx.get("test") or ctx.get("skill_test")
    if test is None:
        test = ctx.state.skill_test
    if test is not None and hasattr(test, "add_modifier"):
        test.add_modifier(2, source=ctx.source, reason="Lucky!")
    ctx.log("Lucky!：该技能检定 +2 技能值")


register("01080", play=_lucky)


# ==========================================================================
# investigator weaknesses
# ==========================================================================
# 01007 Cover Up
#
# Revelation - Put Cover Up into play in your threat area, with 3 clues on it.
# [reaction] When you would discover 1 or more clues at your location: Discard
# that many clues from Cover Up instead.
# Forced - When the game ends, if there are any clues on Cover Up: You suffer 1
# mental trauma.
# ==========================================================================
def _cover_up_revelation(ctx: EffectContext):
    card = _put_in_threat_area(ctx)
    if card is None:
        return
    card.clues = 3
    ctx.log("Cover Up 上放置 3 条线索")


def _cover_up_condition(ctx: EffectContext) -> bool:
    source = ctx.source
    return source is not None and source.clues > 0


def _cover_up_effect(ctx: EffectContext):
    # The card text replaces discovering clues with discarding from Cover Up,
    # one clue per trigger (the reaction fires on a clue discovery).
    source = ctx.source
    if source is None or source.clues <= 0:
        return
    source.clues -= 1
    ctx.payload["clues_cancelled"] = True
    ctx.log(f"Cover Up：改为从其上弃置 1 条线索（剩余 {source.clues}）")


def _cover_up_end_of_game(ctx: EffectContext):
    source = ctx.source
    if source is None or source.clues <= 0:
        return
    player = ctx.controller
    if player is None:
        return
    player.trauma_mental += 1
    ctx.log(f"Cover Up：{ctx.investigator.name} 承受 1 点精神创伤")


register(
    "01007",
    revelation=_cover_up_revelation,
    abilities=(
        Ability(
            kind=AbilityKind.TRIGGERED,
            trigger=Trigger.ON_DISCOVER_CLUE,
            condition=_cover_up_condition,
            effect=_cover_up_effect,
            label="[reaction] 你将要发现线索时：改为从 Cover Up 上弃置等量线索",
        ),
        Ability(
            kind=AbilityKind.FORCED,
            trigger=Trigger.ON_SCENARIO_END,
            condition=_cover_up_condition,
            effect=_cover_up_end_of_game,
            label="Forced - 游戏结束时若 Cover Up 上仍有线索：承受 1 点精神创伤",
        ),
    ),
)


# 01011 Hospital Debts
#
# Revelation - Put Hospital Debts into play in your threat area.
# [fast]: Move 1 resource from your resource pool to Hospital Debts.
# (Limit twice per round.)
# Forced - When the game ends, if Hospital Debts has fewer than 6 resources on
# it: You earn 2 fewer experience for this scenario.
# ==========================================================================
def _hospital_debts_revelation(ctx: EffectContext):
    _put_in_threat_area(ctx)


def _hospital_debts_condition(ctx: EffectContext) -> bool:
    source = ctx.source
    if source is None or ctx.controller is None:
        return False
    if ctx.controller.resources < 1:
        return False
    if source.meta.get("resources_this_round") == ctx.state.round:
        return False
    return source.meta.get("resources", 0) < 6


def _hospital_debts_effect(ctx: EffectContext):
    source = ctx.source
    if source is None or ctx.controller is None:
        return
    ctx.controller.resources -= 1
    source.meta["resources"] = source.meta.get("resources", 0) + 1
    source.meta["resources_this_round"] = ctx.state.round
    ctx.log(f"Hospital Debts：移动 1 资源（共 {source.meta['resources']}）")


def _hospital_debts_end_of_game(ctx: EffectContext):
    source = ctx.source
    if source is None or source.meta.get("resources", 0) >= 6:
        return
    if ctx.controller is not None:
        ctx.controller.xp_earned -= 2
        ctx.log("Hospital Debts：本场景少获得 2 点经验")


register(
    "01011",
    revelation=_hospital_debts_revelation,
    abilities=(
        Ability(
            kind=AbilityKind.ACTIVATED,
            costs=(),
            condition=_hospital_debts_condition,
            effect=_hospital_debts_effect,
            label="[fast]：将 1 资源移到 Hospital Debts 上（每轮限两次）",
        ),
        Ability(
            kind=AbilityKind.FORCED,
            trigger=Trigger.ON_SCENARIO_END,
            effect=_hospital_debts_end_of_game,
            label="Forced - 游戏结束时若 Hospital Debts 上少于 6 资源：本场景少获得 2 点经验",
        ),
    ),
)


# 01015 Abandoned and Alone
#
# Revelation - Take 2 direct horror and remove all cards in your discard pile
# from the game.
# ==========================================================================
def _abandoned_and_alone(ctx: EffectContext):
    inv = ctx.investigator
    player = ctx.controller
    if inv is not None:
        yield from ctx.game.deal_horror(inv, 2, source=ctx.source, reason="Abandoned and Alone")
    if player is not None:
        removed = list(player.discard)
        for card_id in removed:
            card = ctx.state.maybe_card(card_id)
            if card is not None:
                card.zone = Zone.REMOVED
        player.discard.clear()
        ctx.log(f"Abandoned and Alone：{len(removed)} 张弃牌被移出游戏")


register("01015", revelation=_abandoned_and_alone)


# ==========================================================================
# basic weaknesses
# ==========================================================================
# 01096 Amnesia
#
# Revelation - Choose and discard all but 1 card from your hand.
# ==========================================================================
def _amnesia(ctx: EffectContext):
    player = ctx.controller
    if player is None or len(player.hand) <= 1:
        return
    options = [ChoiceOption(cid, ctx.state.cards[cid].name) for cid in list(player.hand)]
    choice = PendingChoice(
        id=ctx.game.next_choice_id(),
        kind=ChoiceKind.CARDS,
        player_id=player.id,
        prompt=f"选择要弃掉的 {len(options) - 1} 张手牌",
        options=options,
        min_selected=len(options) - 1,
        max_selected=len(options) - 1,
    )
    picked = yield from _ask_selection(ctx, choice)
    for card_id in picked:
        ctx.game.move_to_discard(player, card_id)
    ctx.log(f"Amnesia：{ctx.investigator.name} 弃掉了 {len(picked)} 张手牌")


register("01096", revelation=_amnesia)


# 01097 Paranoia
#
# Revelation - Discard all your resources.
# ==========================================================================
def _paranoia(ctx: EffectContext):
    player = ctx.controller
    if player is None:
        return
    lost = player.resources
    player.resources = 0
    ctx.log(f"Paranoia：{ctx.investigator.name} 丢弃全部 {lost} 资源")


register("01097", revelation=_paranoia)


# 01098 Haunted
#
# Revelation - Add Haunted to your threat area.
# You get -1 to each of your skills.
# [action] [action]: Discard Haunted.
# ==========================================================================
def _haunted_revelation(ctx: EffectContext):
    _put_in_threat_area(ctx)


def _discard_self(ctx: EffectContext):
    source = ctx.source
    if source is None or ctx.controller is None:
        return
    ctx.log(f"{source.name} 被弃置")
    ctx.game.move_to_discard(ctx.controller, source.id)


register(
    "01098",
    revelation=_haunted_revelation,
    abilities=(
        # The constant "-1 to each of your skills" is not modelled: the engine
        # has no constant stat hook (see the module docstring).
        Ability(
            kind=AbilityKind.ACTIVATED,
            costs=(Cost(CostKind.ACTION, 2),),
            effect=_discard_self,
            label="[action][action]：弃置 Haunted（-1 全技能常驻效果未实现）",
        ),
    ),
)


# 01099 Psychosis
#
# Revelation - Add Psychosis to your threat area.
# Forced - After you take 1 or more horror: Take 1 direct damage.
# [action] [action]: Discard Psychosis.
# ==========================================================================
def _psychosis_revelation(ctx: EffectContext):
    _put_in_threat_area(ctx)


def _psychosis_condition(ctx: EffectContext) -> bool:
    return ctx.investigator is not None and ctx.event is not None and ctx.event.target is ctx.investigator


def _psychosis_effect(ctx: EffectContext):
    inv = ctx.investigator
    if inv is not None:
        yield from ctx.game.deal_damage(inv, 1, source=ctx.source, reason="Psychosis")
        ctx.log("Psychosis：受到 1 点直接伤害")


register(
    "01099",
    revelation=_psychosis_revelation,
    abilities=(
        Ability(
            kind=AbilityKind.FORCED,
            trigger=Trigger.ON_HORROR_TAKEN,
            condition=_psychosis_condition,
            effect=_psychosis_effect,
            label="Forced - 你受到恐惧后：受到 1 点直接伤害",
        ),
        Ability(
            kind=AbilityKind.ACTIVATED,
            costs=(Cost(CostKind.ACTION, 2),),
            effect=_discard_self,
            label="[action][action]：弃置 Psychosis",
        ),
    ),
)


# 01100 Hypochondria
#
# Revelation - Add Hypochondria to your threat area.
# Forced - After you take 1 or more damage: Take 1 direct horror.
# [action] [action]: Discard Hypochondria.
# ==========================================================================
def _hypochondria_revelation(ctx: EffectContext):
    _put_in_threat_area(ctx)


def _hypochondria_condition(ctx: EffectContext) -> bool:
    return ctx.investigator is not None and ctx.event is not None and ctx.event.target is ctx.investigator


def _hypochondria_effect(ctx: EffectContext):
    inv = ctx.investigator
    if inv is not None:
        yield from ctx.game.deal_horror(inv, 1, source=ctx.source, reason="Hypochondria")
        ctx.log("Hypochondria：受到 1 点直接恐惧")


register(
    "01100",
    revelation=_hypochondria_revelation,
    abilities=(
        Ability(
            kind=AbilityKind.FORCED,
            trigger=Trigger.ON_DAMAGE_TAKEN,
            condition=_hypochondria_condition,
            effect=_hypochondria_effect,
            label="Forced - 你受到伤害后：受到 1 点直接恐惧",
        ),
        Ability(
            kind=AbilityKind.ACTIVATED,
            costs=(Cost(CostKind.ACTION, 2),),
            effect=_discard_self,
            label="[action][action]：弃置 Hypochondria",
        ),
    ),
)

# --------------------------------------------------------------------------
# Cards that needed engine hooks: constant modifiers, the during-a-test
# window, and abilities that react to the result of the test they were
# committed to.
# --------------------------------------------------------------------------
from ..core.cards import Ability as _HookAbility  # noqa: E402
from ..core.enums import AbilityKind as _HookKind, Trigger as _HookTrigger  # noqa: E402
from ..core.cards import Cost as _HookCost  # noqa: E402
from ..core.enums import CostKind as _HookCostKind  # noqa: E402


def _vicious_blow(ctx):
    """Vicious Blow: "If this skill test is successful, this attack deals +1 damage." """
    test = ctx.event.get("test")
    if test is None or test.kind != "fight":
        return
    test.meta["damage_bonus"] = int(test.meta.get("damage_bonus", 0)) + 1
    ctx.log("Vicious Blow：这次攻击额外造成 1 点伤害")


def _deduction(ctx):
    """Deduction: "If this skill test is successful while investigating a location, discover 1 additional clue." """
    test = ctx.event.get("test")
    if test is None or test.kind != "investigate":
        return
    test.meta["extra_clues"] = int(test.meta.get("extra_clues", 0)) + 1
    ctx.log("Deduction：多发现 1 条线索")


def _opportunist(ctx):
    """Opportunist: "If this skill test is successful by 3 or more, return Opportunist to your hand." """
    result = ctx.event.get("result")
    if result is None or result.margin < 3:
        return
    test = ctx.event.get("test")
    if test is not None:
        test.meta.setdefault("keep_cards", []).append(ctx.source.id)
        ctx.log("Opportunist：这张卡退回手牌")


# These three are printed as straight effects ("this attack deals +1 damage",
# "discover 1 additional clue", "return ... to your hand"), not as optional
# abilities, so they are FORCED: no prompt, and they never disturb a driver.
register(
    "01025",
    abilities=(_HookAbility(kind=_HookKind.FORCED, trigger=_HookTrigger.ON_SUCCESS, effect=_vicious_blow, label="Vicious Blow"),),
)
register(
    "01039",
    abilities=(_HookAbility(kind=_HookKind.FORCED, trigger=_HookTrigger.ON_SUCCESS, effect=_deduction, label="Deduction"),),
)
register(
    "01053",
    abilities=(_HookAbility(kind=_HookKind.FORCED, trigger=_HookTrigger.ON_SUCCESS, effect=_opportunist, label="Opportunist"),),
)

# Magnifying Glass: "You get +1 [intellect] while investigating."
register("01030", meta={"constant": [{"skill": "intellect", "amount": 1, "kind": ["investigate"]}]})
# Holy Rosary: "You get +1 [willpower]."
register("01059", meta={"constant": [{"skill": "willpower", "amount": 1}]})
# Beat Cop / Dr. Milan Christopher flat bonuses
register("01018", meta={"constant": [{"skill": "combat", "amount": 1}]})
register("01033", meta={"constant": [{"skill": "intellect", "amount": 1}]})

# Physical Training / Arcane Studies: "[free] Spend 1 resource: +1 skill for this test."
register("01017", meta={"in_test": {"skills": ["willpower", "combat"], "cost": 1, "bonus": 1, "label": "体能训练"}})
register("01062", meta={"in_test": {"skills": ["willpower", "intellect"], "cost": 1, "bonus": 1, "label": "奥术研究"}})

# Shrivelling: "Uses (4 charges). [action] Spend 1 charge: Fight. Use [willpower] instead of [combat].
#              You get +1 [willpower] and deal +1 damage for this attack."
register(
    "01060",
    meta={
        "attack": {"skill": "willpower", "combat_bonus": 1, "damage": 2, "spend": "charge"},
        "uses": {"charge": 4},
    },
)

# Leo De Luca: "You may take an additional action during your turn."
register("01048", meta={"extra_action": 1})

# --------------------------------------------------------------------------
# More core-set cards, implemented on the existing hooks.
# --------------------------------------------------------------------------
from ..core.enums import Skill as _Skill, Zone as _Zone  # noqa: E402


def _test_investigator(ctx):
    test = ctx.event.get("test")
    if test is None:
        return None
    return ctx.state.maybe_card(getattr(test, "investigator_id", None))


def _draw_if_successful(ctx):
    """"If this skill test is successful, draw 1 card." (Guts / Perception / Overpower / Manual Dexterity)"""
    investigator = _test_investigator(ctx)
    player = ctx.state.player_of(investigator) if investigator is not None else None
    if player is None:
        return
    yield from ctx.game.draw_cards(player, 1)


def _fearless(ctx):
    """"If this skill test is successful, heal 1 horror." (Fearless)"""
    investigator = _test_investigator(ctx)
    if investigator is not None:
        ctx.game.heal(investigator, horror=1)


for _code in ("01089", "01090", "01091", "01092"):
    register(
        _code,
        abilities=(_HookAbility(kind=_HookKind.FORCED, trigger=_HookTrigger.ON_SUCCESS, effect=_draw_if_successful, label="成功时抽牌"),),
    )
register(
    "01067",
    abilities=(_HookAbility(kind=_HookKind.FORCED, trigger=_HookTrigger.ON_SUCCESS, effect=_fearless, label="Fearless"),),
)

# [fast] spend 1 resource for +1 to two skills
register("01049", meta={"in_test": {"skills": ["combat", "agility"], "cost": 1, "bonus": 1, "label": "Hard Knocks"}})
register("01034", meta={"in_test": {"skills": ["intellect", "agility"], "cost": 1, "bonus": 1, "label": "Hyperawareness"}})
register("01077", meta={"in_test": {"skills": ["willpower", "agility"], "cost": 1, "bonus": 1, "label": "Dig Deep"}})

# weapons that plug into the basic Fight action
register("01086", meta={"attack": {"combat_bonus": 1, "damage": 1}})            # Knife
register("01074", meta={"attack": {"combat_bonus": 2, "damage": 2, "breaks_on_bad_token": True}})  # Baseball Bat
register(
    "01006",
    meta={"attack": {"combat_bonus": 1, "damage": 1, "spend": "ammo"}, "uses": {"ammo": 4}},
)  # Roland's .38 Special
register("01008", meta={"extra_slots": {"hand": 2}})                            # Daisy's Tote Bag


def _flashlight(ctx):
    """Flashlight: Uses (3 supplies). [action] Spend 1 supply: Investigate with -2 shroud."""
    card = ctx.source
    player = ctx.controller
    investigator = ctx.investigator
    if card.uses.get("supply", 0) <= 0 or investigator is None:
        return
    location = ctx.state.maybe_card(investigator.meta.get("location_id"))
    if location is None:
        return
    card.use("supply")
    ctx.log(f"手电筒照亮了{location.name}（遮蔽 -2，剩余 {card.uses['supply']}）")
    result = yield from ctx.game.skill_test(
        investigator=investigator,
        skill=_Skill.INTELLECT,
        difficulty=max(0, ctx.game.shroud_of(location) - 2),
        source=card,
        kind="investigate",
    )
    if result.success:
        ctx.game.discover_clue(investigator, location, 1)


register(
    "01087",
    meta={"uses": {"supply": 3}},
    abilities=(_HookAbility(kind=_HookKind.ACTIVATED, costs=(_HookCost(_HookCostKind.ACTION),), effect=_flashlight, label="Spend 1 supply: Investigate (-2 shroud)"),),
)


def _forbidden_knowledge(ctx):
    """Forbidden Knowledge: [fast] Exhaust and take 1 horror: move 1 secret to your resource pool."""
    card = ctx.source
    player = ctx.controller
    if card.exhausted or card.uses.get("secret", 0) <= 0:
        return
    card.exhausted = True
    card.use("secret")
    player.resources += 1
    yield from ctx.game.deal_horror(ctx.investigator, 1, source=card, reason="Forbidden Knowledge")
    if card.uses.get("secret", 0) <= 0:
        ctx.game.move_to_discard(player, card.id)


register(
    "01058",
    meta={"uses": {"secret": 4}},
    abilities=(_HookAbility(kind=_HookKind.ACTIVATED, limit="fast", effect=_forbidden_knowledge, label="[fast] 1 秘密换 1 资源，承受 1 恐惧"),),
)


def _pickpocketing(ctx):
    """Pickpocketing: [reaction] After you evade an enemy, exhaust: draw 1 card."""
    card = ctx.source
    result = ctx.event.get("result")
    if card.exhausted or result is None or not result.success:
        return
    card.exhausted = True
    player = ctx.state.player_of(card)
    if player is not None:
        yield from ctx.game.draw_cards(player, 1)


register(
    "01046",
    abilities=(_HookAbility(kind=_HookKind.TRIGGERED, trigger=_HookTrigger.ON_EVADE, effect=_pickpocketing, label="Pickpocketing"),),
)


def _rabbits_foot(ctx):
    """Rabbit's Foot: [reaction] After you fail a skill test, exhaust: draw 1 card."""
    card = ctx.source
    if card.exhausted:
        return
    card.exhausted = True
    player = ctx.state.player_of(card)
    if player is not None:
        yield from ctx.game.draw_cards(player, 1)


register(
    "01075",
    abilities=(_HookAbility(kind=_HookKind.TRIGGERED, trigger=_HookTrigger.ON_FAIL, effect=_rabbits_foot, label="Rabbit's Foot"),),
)


def _research_librarian(ctx):
    """Research Librarian: [reaction] After it enters play: search your deck for a Tome."""
    player = ctx.state.player_of(ctx.source)
    if player is None:
        return
    candidates = [cid for cid in player.deck if "tome" in ctx.state.cards[cid].defn.traits]
    if not candidates:
        return
    choice = PendingChoice(
        id=ctx.game.next_choice_id(),
        kind=ChoiceKind.CARD,
        player_id=player.id,
        prompt="研究馆员：从牌库找出一张典籍",
        options=[ChoiceOption(cid, ctx.state.cards[cid].name) for cid in candidates],
    )
    picked = yield from ctx.game.ask(choice)
    card_id = picked[0]
    player.deck.remove(card_id)
    ctx.state.cards[card_id].zone = _Zone.HAND
    player.hand.append(card_id)
    ctx.state.rng.shuffle(player.deck)


register(
    "01032",
    abilities=(_HookAbility(kind=_HookKind.TRIGGERED, trigger=_HookTrigger.ON_ENTER_PLAY, effect=_research_librarian, label="Research Librarian"),),
)


def _heirloom(ctx):
    """"Heirloom of Hyperborea: [reaction] After you play a Spell card: draw 1 card." """
    played = ctx.event.source
    if played is None or played is ctx.source or "spell" not in (played.defn.traits or frozenset()):
        return
    player = ctx.state.player_of(ctx.source)
    if player is not None:
        yield from ctx.game.draw_cards(player, 1)


register("01012", abilities=(_HookAbility(kind=_HookKind.TRIGGERED, trigger=_HookTrigger.ON_ENTER_PLAY, effect=_heirloom, label="Heirloom of Hyperborea"),))


def _scavenging(ctx):
    """Scavenging: [reaction] After you successfully investigate by 2 or more, exhaust: return an Item from your discard."""
    card = ctx.source
    result = ctx.event.get("result")
    if card.exhausted or result is None or not result.success or result.margin < 2:
        return
    card.exhausted = True
    player = ctx.state.player_of(card)


def _sneak_attack(ctx):
    """Sneak Attack: Deal 2 damage to an exhausted enemy at your location."""
    investigator = ctx.investigator
    if investigator is None:
        return
    targets = [e for e in ctx.state.enemies_at(investigator.meta.get("location_id")) if e.exhausted]
    targets += [e for e in ctx.state.engaged_enemies(ctx.controller.id) if e.exhausted]
    if not targets:
        ctx.log("潜行攻击：这里没有已消耗的敌人")
        return
    choice = PendingChoice(
        id=ctx.game.next_choice_id(),
        kind=ChoiceKind.ENEMY,
        player_id=ctx.controller.id,
        prompt="潜行攻击：选择一名已消耗的敌人",
        options=[ChoiceOption(e.id, e.name) for e in targets],
    )
    picked = yield from ctx.game.ask(choice)
    yield from ctx.game.deal_damage(ctx.state.cards[picked[0]], 2, source=ctx.source, reason="Sneak Attack")


register("01052", play=_sneak_attack)


def _cunning_distraction(ctx):
    """Cunning Distraction: Evade. Automatically evade all enemies at your location."""
    investigator = ctx.investigator
    if investigator is None:
        return
    player = ctx.controller
    here = investigator.meta.get("location_id")
    for enemy in list(ctx.state.enemies_at(here)) + list(ctx.state.engaged_enemies(player.id)):
        enemy.exhausted = True
        if player.id in enemy.engaged_with:
            ctx.game.disengage(enemy, player)
    ctx.log("Cunning Distraction：此地的敌人全部被闪避")


register("01078", play=_cunning_distraction)


def _drawn_to_the_flame(ctx):
    """Drawn to the Flame: Draw the top card of the encounter deck. Then discover 2 clues here."""
    player = ctx.controller
    investigator = ctx.investigator
    card = ctx.game.draw_encounter(player)
    if card is not None:
        yield from ctx.game.resolve_encounter(player, card)
    if investigator is not None:
        location = ctx.state.maybe_card(investigator.meta.get("location_id"))
        if location is not None:
            ctx.game.discover_clue(investigator, location, 2)


register("01064", play=_drawn_to_the_flame)


def _dark_memory(ctx):
    """Dark Memory: Place 1 doom on the current agenda."""
    agenda = ctx.state.current_agenda()
    if agenda is not None:
        yield from ctx.game.place_doom(agenda, 1)


register("01013", play=_dark_memory)


def _stray_cat(ctx):
    """Stray Cat: [fast] Discard Stray Cat: automatically evade a non-Elite enemy at your location."""
    investigator = ctx.investigator
    player = ctx.controller
    if investigator is None:
        return
    targets = [e for e in ctx.state.enemies_at(investigator.meta.get("location_id")) if not e.defn.elite]
    targets += [e for e in ctx.state.engaged_enemies(player.id) if not e.defn.elite]
    if not targets:
        return
    choice = PendingChoice(
        id=ctx.game.next_choice_id(),
        kind=ChoiceKind.ENEMY,
        player_id=player.id,
        prompt="野猫：选择一名非精英敌人自动闪避",
        options=[ChoiceOption(e.id, e.name) for e in targets],
    )
    picked = yield from ctx.game.ask(choice)
    enemy = ctx.state.cards[picked[0]]
    enemy.exhausted = True
    if player.id in enemy.engaged_with:
        ctx.game.disengage(enemy, player)
    ctx.game.move_to_discard(player, ctx.source.id)


register(
    "01076",
    abilities=(_HookAbility(kind=_HookKind.ACTIVATED, limit="fast", effect=_stray_cat, label="[fast] 弃掉野猫：自动闪避一名非精英敌人"),),
)

"""Build the JSON view the browser renders.

The engine already ships serialize_state(); this module adds the fields the
board needs (hand, play area, threat area, locations with their connections,
the current choice, the last skill test) without changing any key that
serialize_state owns.
"""

from __future__ import annotations

from typing import Any

from ..core.cards import CardDef, CardInstance
from ..core.choices import PendingChoice
from ..core.enums import PHASE_ZH, CardType, Skill, Zone

CARD_TYPE_ZH: dict[CardType, str] = {
    CardType.INVESTIGATOR: "调查员",
    CardType.ASSET: "支援",
    CardType.EVENT: "事件",
    CardType.SKILL: "技能",
    CardType.TREACHERY: "诡计",
    CardType.ENEMY: "敌人",
    CardType.LOCATION: "地点",
    CardType.ACT: "幕",
    CardType.AGENDA: "阴谋",
    CardType.STORY: "故事",
    CardType.SCENARIO: "剧本",
}

LOG_LIMIT = 200


def card_type_label(card_type: CardType) -> str:
    return CARD_TYPE_ZH.get(card_type, card_type.value)


def icons_view(defn: CardDef) -> dict[str, int]:
    icons = {skill.value: int(count) for skill, count in defn.icons.items() if count}
    if defn.wild_icons:
        icons["wild"] = int(defn.wild_icons)
    return icons


#: The language the view strings resolve to ("zh" by default, "en" for originals).
LANG = {"cur": "zh"}


def _name(defn) -> str:
    return defn.name if LANG["cur"] == "en" else defn.display_name


def _text(defn) -> str:
    if LANG["cur"] == "en":
        return defn.text or ""
    return defn.text_zh or defn.text or ""


def _flavor(defn) -> str:
    if LANG["cur"] == "en":
        return (defn.meta.get("arkhamdb") or {}).get("flavor") or ""
    return defn.meta.get("flavor_zh") or ""


def card_view(card: CardInstance) -> dict[str, Any]:
    """One card on the board, with everything the front end draws."""
    defn = card.defn
    return {
        "id": card.id,
        "code": defn.code,
        "name": _name(defn),
        "text": _text(defn),
        "type": defn.card_type.value,
        "type_label": card_type_label(defn.card_type),
        "cost": defn.cost,
        "icons": icons_view(defn),
        "traits": sorted(defn.traits),
        "subtitle": defn.subtitle,
        "unique": bool(defn.unique),
        "exhausted": bool(card.exhausted),
        "damage": card.damage,
        "horror": card.horror,
        "clues": card.clues,
        "doom": card.doom,
        "health": defn.health,
        "sanity": defn.sanity,
        "uses": dict(card.uses),
        "tokens": dict(card.tokens),
        "attached_to": card.attached_to,
        "slots": [slot.value for slot in defn.slots],
    }


def chaos_bag_view(state) -> list[dict[str, Any]]:
    return [
        {"type": token.type.value, "value": token.value, "label": token.label}
        for token in state.chaos_bag.tokens
    ]


def choice_view(choice: PendingChoice | None) -> dict[str, Any] | None:
    if choice is None:
        return None
    return {
        "id": choice.id,
        "kind": choice.kind.value,
        "player_id": choice.player_id,
        "prompt": choice.prompt,
        "min_selected": choice.min_selected,
        "max_selected": choice.max_selected,
        "optional": bool(choice.optional),
        "options": [
            {
                "id": option.id,
                "label": option.label,
                "detail": option.detail or "",
                "disabled": bool(option.disabled),
            }
            for option in choice.options
        ],
    }


def enemy_view(enemy: CardInstance) -> dict[str, Any]:
    defn = enemy.defn
    return {
        "id": enemy.id,
        "code": defn.code,
        "name": _name(defn),
        "text": _text(defn),
        "fight": defn.fight,
        "evade": defn.evade,
        "damage": defn.enemy_damage,
        "horror": defn.enemy_horror,
        "health_remaining": defn.health - enemy.damage if defn.health is not None else 0,
        "health": defn.health,
        "exhausted": bool(enemy.exhausted),
        "engaged_with": list(enemy.engaged_with),
        "location_id": enemy.location_id,
        "traits": sorted(defn.traits),
        "victory": defn.victory,
        "hunter": bool(defn.hunter),
        "retaliate": "retaliate" in defn.keywords,
        "damage_taken": enemy.damage,
    }


def location_view(state) -> list[dict[str, Any]]:
    enemies_at: dict[str, list[str]] = {}
    for enemy in state.enemies():
        if enemy.location_id:
            enemies_at.setdefault(enemy.location_id, []).append(enemy.id)
    investigators_at: dict[str, list[str]] = {}
    for player in state.players:
        investigator = state.maybe_card(player.investigator_id)
        if investigator is None:
            continue
        location_id = investigator.meta.get("location_id")
        if location_id:
            investigators_at.setdefault(location_id, []).append(player.id)

    playable = set(state.location_ids)
    out = []
    for location in state.locations():
        connections = [
            other
            for other in state.connections_of(location.id)
            if other in playable and state.maybe_card(other) is not None
        ]
        out.append(
            {
                "id": location.id,
                "code": location.code,
                "name": _name(location.defn),
                "text": _text(location.defn),
                "shroud": location.defn.shroud,
                "clues": location.clues,
                "revealed": bool(location.meta.get("revealed")),
                "blocked": bool(location.meta.get("blocked")),
                "victory": location.defn.victory,
                "connections": connections,
                "enemies": enemies_at.get(location.id, []),
                "investigators": investigators_at.get(location.id, []),
            }
        )
    return out


def investigator_view(state, player) -> dict[str, Any]:
    investigator = state.investigator_of(player)
    defn = investigator.defn
    return {
        "player_id": player.id,
        "name": investigator.name,
        "code": defn.code,
        "text": _text(defn),
        "traits": sorted(defn.traits),
        "damage": investigator.damage,
        "horror": investigator.horror,
        "health": defn.health,
        "sanity": defn.sanity,
        "resources": player.resources,
        "clues": investigator.clues,
        "actions_left": player.actions_left,
        "location_id": investigator.meta.get("location_id"),
        "skills": {skill.value: int(defn.stat(skill) or 0) for skill in Skill},
        "skill_labels": {skill.value: skill.zh for skill in Skill},
        "exhausted": bool(investigator.exhausted),
        "defeated": bool(player.defeated),
        "resigned": bool(player.resigned),
        "killed": bool(player.killed),
        "insane": bool(player.insane),
        "trauma_physical": player.trauma_physical,
        "trauma_mental": player.trauma_mental,
        "xp_earned": player.xp_earned,
        "victory_points": player.victory_points,
        "elder_sign": defn.elder_sign,
    }


def act_view(game) -> dict[str, Any] | None:
    state = game.state
    act = state.current_act()
    if act is None:
        return None
    rule = game.act_advance_rule(act)
    required = rule.get("clues")
    if required is None:
        required = act.defn.clues_required
    objective = rule.get("objective")
    progress = 0
    if required is not None:
        required = int(required)
        if rule.get("per_investigator") or act.defn.clues_per_investigator_required:
            required *= max(1, len([p for p in state.players if p.is_active]))
        progress = sum(state.investigator_of(p).clues for p in state.players if p.is_active)
    else:
        objective = objective or "enemy_defeated"
    return {
        "id": act.id,
        "code": act.code,
        "name": _name(act.defn),
        "text": _text(act.defn),
        "flavor": _flavor(act.defn),
        "progress": progress,
        "required": required,
        "objective": objective or "clues",
        "label": rule.get("label") or "",
        "index": state.act_index,
        "total": len(state.act_deck),
    }


def agenda_view(state) -> dict[str, Any] | None:
    agenda = state.current_agenda()
    if agenda is None:
        return None
    return {
        "id": agenda.id,
        "code": agenda.code,
        "name": _name(agenda.defn),
        "text": _text(agenda.defn),
        "flavor": _flavor(agenda.defn),
        "doom": agenda.doom,
        "threshold": agenda.defn.doom_threshold,
        "total_doom": state.total_doom(),
        "index": state.agenda_index,
        "total": len(state.agenda_deck),
    }


def last_skill_test_view(state) -> dict[str, Any] | None:
    result = state.skill_test
    if result is None:
        return None
    try:
        skill = result.skill
        token = result.token
        return {
            "skill": skill.zh,
            "skill_code": skill.value,
            "difficulty": result.difficulty,
            "skill_value": result.skill_value,
            "token": token.label,
            "token_type": token.type.value,
            "token_value": result.token_value,
            "total": result.total,
            "success": bool(result.success),
            "margin": result.margin,
            "auto_fail": bool(result.auto_fail),
            "text": result.describe(),
        }
    except AttributeError:
        return None


def log_view(state, limit: int = LOG_LIMIT) -> list[dict[str, Any]]:
    entries = state.log_entries[-limit:]
    return [
        {
            "round": entry.round,
            "phase": entry.phase,
            "kind": entry.kind,
            "text": entry.text,
        }
        for entry in reversed(entries)
    ]


def hand_view(state, player) -> list[dict[str, Any]]:
    return [card_view(state.cards[card_id]) for card_id in player.hand if card_id in state.cards]


def _scenario_story(state, session) -> str:
    """The opening narrative of the running scenario (act 2 branches on the campaign log)."""
    try:
        from ..campaign.night_of_the_zealot import scenario_intro

        return scenario_intro(state.scenario_code, getattr(session, "campaign", None))
    except Exception:
        return ""


def build_view(session) -> dict[str, Any]:
    """The complete view for one browser session."""
    from .campaign_bridge import campaign_name

    game = session.game
    state = game.state
    player = state.players[0] if state.players else None
    campaign = session.campaign_dict()

    view: dict[str, Any] = {
        "session_id": session.id,
        "campaign": campaign,
        "scenario": {
            "code": state.scenario_code,
            "name": state.scenario_name,
            "round": state.round,
            "phase": PHASE_ZH.get(state.phase, state.phase.value),
            "phase_code": state.phase.value,
            "story": _scenario_story(state, session),
            "resolution": state.resolution,
            "finished": bool(state.finished),
        },
        "difficulty": state.difficulty,
        "notice": session.notice,
        "last_summary": session.last_summary,
        "investigator": investigator_view(state, player) if player is not None else None,
        "locations": location_view(state),
        "act": act_view(game),
        "agenda": agenda_view(state),
        "enemies": [enemy_view(enemy) for enemy in state.enemies()],
        "play_area": [card_view(card) for card in (state.assets_of(player.id) if player else [])],
        "threat_area": [
            card_view(card) for card in (state.threat_area_of(player.id) if player else [])
        ],
        "hand": hand_view(state, player) if player is not None else [],
        "discard": [
            card_view(state.cards[card_id])
            for card_id in (player.discard if player else [])
            if card_id in state.cards
        ],
        "deck_count": len(player.deck) if player else 0,
        "encounter_deck_count": len(state.encounter_deck),
        "encounter_discard_count": len(state.encounter_discard),
        "victory_display": len(state.victory_display),
        "chaos_bag": chaos_bag_view(state),
        "last_skill_test": last_skill_test_view(state),
        "choice": choice_view(game.awaiting),
        "log": log_view(state),
        "campaign_name": campaign_name(campaign.get("code")),
    }
    if player is not None:
        view["first_player"] = {
            "player_id": player.id,
            "name": player.name,
            "investigator": view["investigator"]["name"],
        }
    return view

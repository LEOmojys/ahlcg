"""Enumerations shared across the whole engine."""

from __future__ import annotations

from enum import Enum


class Skill(str, Enum):
    """The four investigator skills."""

    WILLPOWER = "willpower"
    INTELLECT = "intellect"
    COMBAT = "combat"
    AGILITY = "agility"

    @property
    def zh(self) -> str:
        return _SKILL_ZH[self]


_SKILL_ZH = {
    Skill.WILLPOWER: "意志",
    Skill.INTELLECT: "智力",
    Skill.COMBAT: "战斗力",
    Skill.AGILITY: "敏捷",
}


class CardClass(str, Enum):
    GUARDIAN = "guardian"
    SEEKER = "seeker"
    ROGUE = "rogue"
    MYSTIC = "mystic"
    SURVIVOR = "survivor"
    NEUTRAL = "neutral"
    MYTHOS = "mythos"


_CLASS_ZH = {
    CardClass.GUARDIAN: "守护者",
    CardClass.SEEKER: "探求者",
    CardClass.ROGUE: "流浪者",
    CardClass.MYSTIC: "秘术师",
    CardClass.SURVIVOR: "幸存者",
    CardClass.NEUTRAL: "中立",
    CardClass.MYTHOS: "神话",
}


def class_zh(card_class: CardClass) -> str:
    return _CLASS_ZH[card_class]


class CardType(str, Enum):
    INVESTIGATOR = "investigator"
    ASSET = "asset"
    EVENT = "event"
    SKILL = "skill"
    TREACHERY = "treachery"
    ENEMY = "enemy"
    LOCATION = "location"
    ACT = "act"
    AGENDA = "agenda"
    STORY = "story"
    SCENARIO = "scenario"


class Slot(str, Enum):
    HAND = "hand"
    ARCANE = "arcane"
    ALLY = "ally"
    ACCESSORY = "accessory"
    BODY = "body"
    TAROT = "tarot"


SLOT_CAPACITY: dict[Slot, int] = {
    Slot.HAND: 2,
    Slot.ARCANE: 2,
    Slot.ALLY: 1,
    Slot.ACCESSORY: 1,
    Slot.BODY: 1,
    Slot.TAROT: 1,
}

SLOT_ZH = {
    Slot.HAND: "手部",
    Slot.ARCANE: "奥术",
    Slot.ALLY: "盟友",
    Slot.ACCESSORY: "饰品",
    Slot.BODY: "身体",
    Slot.TAROT: "塔罗",
}


class Zone(str, Enum):
    """Where a card currently lives."""

    DECK = "deck"
    HAND = "hand"
    PLAY = "play"
    DISCARD = "discard"
    EXILE = "exile"
    PLAY_AREA = "play_area"      # attached / controlled but not slotted
    THREAT_AREA = "threat_area"  # investigator's threat area (weaknesses, treacheries)
    ENCOUNTER_DECK = "encounter_deck"
    ENCOUNTER_DISCARD = "encounter_discard"
    LOCATION = "location"
    ACT_DECK = "act_deck"
    ACT = "act"
    AGENDA_DECK = "agenda_deck"
    AGENDA = "agenda"
    SET_ASIDE = "set_aside"
    REMOVED = "removed"
    LIMBO = "limbo"


class Phase(str, Enum):
    MYTHOS = "mythos"
    INVESTIGATION = "investigation"
    ENEMY = "enemy"
    UPKEEP = "upkeep"


PHASE_ZH = {
    Phase.MYTHOS: "神话阶段",
    Phase.INVESTIGATION: "调查阶段",
    Phase.ENEMY: "敌人阶段",
    Phase.UPKEEP: "维持阶段",
}

PHASE_ORDER = (Phase.MYTHOS, Phase.INVESTIGATION, Phase.ENEMY, Phase.UPKEEP)


class TokenType(str, Enum):
    NUMERIC = "numeric"
    SKULL = "skull"
    CULTIST = "cultist"
    TABLET = "tablet"
    ELDER_THING = "elder_thing"
    AUTOFAIL = "autofail"
    ELDER_SIGN = "elder_sign"
    BLESS = "bless"
    CURSE = "curse"
    FROST = "frost"


SYMBOL_TOKEN_TYPES = (
    TokenType.SKULL,
    TokenType.CULTIST,
    TokenType.TABLET,
    TokenType.ELDER_THING,
)

TOKEN_ZH = {
    TokenType.SKULL: "骷髅",
    TokenType.CULTIST: "邪教徒",
    TokenType.TABLET: "石板",
    TokenType.ELDER_THING: "远古之物",
    TokenType.AUTOFAIL: "自动失败",
    TokenType.ELDER_SIGN: "古神印记",
    TokenType.BLESS: "祝福",
    TokenType.CURSE: "诅咒",
    TokenType.FROST: "寒霜",
}


class AbilityKind(str, Enum):
    CONSTANT = "constant"      # always-on static effect
    TRIGGERED = "triggered"    # "After X, do Y"
    ACTIVATED = "activated"    # "Action/Free trigger: do Y"
    FORCED = "forced"          # "Forced - when X, do Y"
    PARLEY = "parley"


class CostKind(str, Enum):
    ACTION = "action"
    RESOURCE = "resource"
    EXHAUST = "exhaust"
    DAMAGE = "damage"
    HORROR = "horror"
    CLUE = "clue"
    DISCARD = "discard"
    DOOM = "doom"
    CUSTOM = "custom"


class Trigger(str, Enum):
    """Timing points the engine emits."""

    # --- setup / scenario flow
    ON_SETUP = "on_setup"
    ON_SCENARIO_START = "on_scenario_start"
    ON_SCENARIO_END = "on_scenario_end"
    ON_ROUND_START = "on_round_start"
    ON_ROUND_END = "on_round_end"
    ON_PHASE_START = "on_phase_start"
    ON_PHASE_END = "on_phase_end"

    # --- investigator
    ON_TURN_START = "on_turn_start"
    ON_TURN_END = "on_turn_end"
    ON_ACTION_START = "on_action_start"
    ON_ACTION_END = "on_action_end"
    ON_ENTER_PLAY = "on_enter_play"
    ON_LEAVE_PLAY = "on_leave_play"
    ON_MOVE = "on_move"
    ON_ENTER_LOCATION = "on_enter_location"
    ON_LEAVE_LOCATION = "on_leave_location"
    ON_DAMAGE_TAKEN = "on_damage_taken"
    ON_HORROR_TAKEN = "on_horror_taken"
    ON_ASSET_DEFEATED = "on_asset_defeated"
    ON_DEFEATED = "on_defeated"

    # --- skill tests
    ON_TEST_START = "on_test_start"
    ON_BEFORE_REVEAL = "on_before_reveal"
    ON_REVEAL_TOKEN = "on_reveal_token"
    ON_TEST_RESULT = "on_test_result"
    ON_SUCCESS = "on_success"
    ON_FAIL = "on_fail"
    ON_TEST_END = "on_test_end"

    # --- investigation / combat
    ON_INVESTIGATE = "on_investigate"
    ON_DISCOVER_CLUE = "on_discover_clue"
    ON_ATTACK = "on_attack"
    ON_DAMAGE_DEALT = "on_damage_dealt"
    ON_ENEMY_ENGAGED = "on_enemy_engaged"
    ON_ENEMY_DEFEATED = "on_enemy_defeated"
    ON_EVADE = "on_evade"
    ON_ENEMY_ATTACK = "on_enemy_attack"

    # --- mythos / encounter
    ON_ENCOUNTER_DRAW = "on_encounter_draw"
    ON_ENCOUNTER_RESOLVE = "on_encounter_resolve"
    ON_TREACHERY_REVEALED = "on_treachery_revealed"
    ON_ENEMY_SPAWN = "on_enemy_spawn"

    # --- scenario progression
    ON_PLACE_DOOM = "on_place_doom"
    ON_AGENDA_ADVANCE = "on_agenda_advance"
    ON_ACT_ADVANCE = "on_act_advance"
    ON_LOCATION_REVEAL = "on_location_reveal"
    ON_RESOLUTION = "on_resolution"


class ChoiceKind(str, Enum):
    """What shape of answer a PendingChoice expects."""

    OPTION = "option"
    CARD = "card"
    CARDS = "cards"
    ENEMY = "enemy"
    LOCATION = "location"
    INVESTIGATOR = "investigator"
    COMMIT = "commit"
    ASSIGN_DAMAGE = "assign_damage"
    ORDER = "order"
    CONFIRM = "confirm"


class Resolution(str, Enum):
    """Standard scenario outcomes."""

    NO_RESOLUTION = "no_resolution"
    RESIGN = "resign"
    DEFEATED = "defeated"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"
    R5 = "R5"

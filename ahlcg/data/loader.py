"""Turn the public ArkhamDB card records into engine CardDef objects.

ArkhamDB carries what the Tabletop Simulator save does not: enemy fight/evade,
location shroud, investigator skills, skill icons and the actual rules text.
Keywords that only exist in the text (Hunter, Retaliate, Prey, Spawn, ...) are
parsed out here so the engine can reason about them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from ..core.cards import CardDef, DeckRequirement
from ..core.enums import CardClass, CardType, Skill, Slot
from ..core.errors import CardDataError
from ..core.serialization import to_jsonable

TYPE_MAP = {
    "investigator": CardType.INVESTIGATOR,
    "asset": CardType.ASSET,
    "event": CardType.EVENT,
    "skill": CardType.SKILL,
    "treachery": CardType.TREACHERY,
    "enemy": CardType.ENEMY,
    "location": CardType.LOCATION,
    "act": CardType.ACT,
    "agenda": CardType.AGENDA,
    "story": CardType.STORY,
    "scenario": CardType.SCENARIO,
}

CLASS_MAP = {
    "guardian": CardClass.GUARDIAN,
    "seeker": CardClass.SEEKER,
    "rogue": CardClass.ROGUE,
    "mystic": CardClass.MYSTIC,
    "survivor": CardClass.SURVIVOR,
    "neutral": CardClass.NEUTRAL,
    "mythos": CardClass.MYTHOS,
    "multiclass": CardClass.NEUTRAL,
}

SLOT_MAP = {
    "hand": Slot.HAND,
    "hand x2": Slot.HAND,
    "arcane": Slot.ARCANE,
    "arcane x2": Slot.ARCANE,
    "ally": Slot.ALLY,
    "accessory": Slot.ACCESSORY,
    "body": Slot.BODY,
    "tarot": Slot.TAROT,
}

KEYWORDS = (
    "hunter",
    "retaliate",
    "alert",
    "aloof",
    "massive",
    "elite",
    "surge",
    "peril",
    "hidden",
    "swarming",
    "teeming",
    "vengeance",
    "patrol",
)

#: Prey/Spawn instructions may contain periods ("St. Mary's Hospital"), so only
#: stop at a newline or a tag marker, then trim the trailing sentence period.
PREY_RE = re.compile(r"prey\s*[-–]\s*([^\n|]+)", re.IGNORECASE)
SPAWN_RE = re.compile(r"spawn\s*[-–]\s*([^\n|]+)", re.IGNORECASE)


def strip_markup(text: str) -> str:
    """ArkhamDB wraps keywords in tags; keep a readable plain text version."""
    text = re.sub(r"<b>(.*?)</b>", r"\1", text or "", flags=re.S)
    text = re.sub(r"<i>(.*?)</i>", r"\1", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def parse_keywords(text: str) -> frozenset[str]:
    lowered = (text or "").lower()
    return frozenset(word for word in KEYWORDS if re.search(rf"\b{word}\b", lowered))


def parse_traits(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(t.strip().lower().rstrip(".") for t in re.split(r"[.,]", raw) if t.strip())


def parse_slots(raw: str | None) -> tuple[Slot, ...]:
    if not raw:
        return ()
    out: list[Slot] = []
    for part in raw.split("."):
        key = part.strip().lower()
        if not key:
            continue
        double = key.endswith("x2")  # "Hand x2" occupies two slots
        if double:
            key = key[:-2].strip()
        if key in SLOT_MAP:
            out.append(SLOT_MAP[key])
            if double:
                out.append(SLOT_MAP[key])
    return tuple(out)


def icons_of(record: dict[str, Any], *, investigator: bool) -> dict[Skill, int]:
    if investigator:
        return {}
    icons: dict[Skill, int] = {}
    for key, skill in (
        ("skill_willpower", Skill.WILLPOWER),
        ("skill_intellect", Skill.INTELLECT),
        ("skill_combat", Skill.COMBAT),
        ("skill_agility", Skill.AGILITY),
    ):
        value = record.get(key) or 0
        if value:
            icons[skill] = int(value)
    return icons


def to_card_def(record: dict[str, Any]) -> CardDef:
    type_code = record.get("type_code")
    if type_code not in TYPE_MAP:
        raise CardDataError(f"unknown card type {type_code!r} for {record.get('code')!r}")
    card_type = TYPE_MAP[type_code]
    card_class = CLASS_MAP.get(str(record.get("faction_code")), CardClass.NEUTRAL)
    text = strip_markup(record.get("real_text") or record.get("text") or "")
    investigator = card_type is CardType.INVESTIGATOR

    defn = CardDef(
        code=str(record.get("code")),
        name=str(record.get("name") or ""),
        card_type=card_type,
        card_class=card_class,
        text=text,
        subtitle=record.get("subname"),
        traits=parse_traits(record.get("real_traits") or record.get("traits")),
        unique=bool(record.get("is_unique")),
        level=int(record.get("xp") or 0),
        encounter_set=record.get("encounter_code"),
        cost=record.get("cost"),
        slots=parse_slots(record.get("real_slot")),
        icons=icons_of(record, investigator=investigator),
        deck_limit=int(record.get("deck_limit") or 2),
        xp=int(record.get("xp") or 0),
        weakness="weakness" in str(record.get("subtype_code") or "").lower()
        or bool(record.get("weakness"))
        or "weakness" in (record.get("real_subtype") or "").lower(),
        keywords=parse_keywords(text),
    )
    subtype = str(record.get("real_subtype") or record.get("subtype_code") or "").lower()
    defn.basic_weakness = "basicweakness" in subtype.replace(" ", "")
    defn.meta["subtype"] = record.get("real_subtype") or record.get("subtype_code") or ""
    defn.meta["deck_requirements"] = record.get("deck_requirements")
    defn.meta["deck_options"] = record.get("deck_options")
    defn.meta["arkhamdb"] = {
        "pack_code": record.get("pack_code"),
        "pack_name": record.get("pack_name"),
        "encounter_code": record.get("encounter_code"),
        "encounter_name": record.get("encounter_name"),
        "position": record.get("position"),
        "flavor": record.get("flavor"),
        "illustrator": record.get("illustrator"),
        "imagesrc": record.get("imagesrc"),
        "back_text": strip_markup(record.get("back_text") or ""),
        "quantity": int(record.get("quantity") or 1),
        "encounter_position": record.get("encounter_position"),
    }
    defn.quantity = int(record.get("quantity") or 1)

    from .zh import attach as _attach_zh

    _attach_zh(defn)

    if investigator:
        defn.willpower = record.get("skill_willpower")
        defn.intellect = record.get("skill_intellect")
        defn.combat = record.get("skill_combat")
        defn.agility = record.get("skill_agility")
        defn.health = record.get("health")
        defn.sanity = record.get("sanity")
        defn.deck_limit = 1
    elif card_type in (CardType.ASSET, CardType.EVENT, CardType.SKILL):
        defn.xp = int(record.get("xp") or 0)

    if card_type is CardType.ASSET:
        defn.health = record.get("health")
        defn.sanity = record.get("sanity")

    if card_type is CardType.ENEMY:
        defn.fight = record.get("enemy_fight")
        defn.evade = record.get("enemy_evade")
        defn.enemy_damage = int(record.get("enemy_damage") or 0)
        defn.enemy_horror = int(record.get("enemy_horror") or 0)
        defn.health = record.get("health")
        defn.health_per_investigator = bool(record.get("health_per_investigator"))
        defn.hunter = "hunter" in defn.keywords
        defn.elite = "elite" in defn.keywords
        defn.massive = "massive" in defn.keywords
        prey = PREY_RE.search(text)
        if prey:
            defn.prey = prey.group(1).strip().rstrip(".")
        spawn = SPAWN_RE.search(text)
        if spawn:
            defn.spawn = spawn.group(1).strip().rstrip(".")

    if card_type is CardType.LOCATION:
        defn.shroud = record.get("shroud")
        defn.clues = int(record.get("clues") or 0)
        defn.clues_per_investigator = not bool(record.get("clues_fixed"))
        defn.victory = int(record.get("victory") or 0)

    if card_type is CardType.ACT:
        defn.clues_required = int(record.get("clues") or 0)
        defn.clues_per_investigator_required = not bool(record.get("clues_fixed"))
        defn.victory = int(record.get("victory") or 0)

    if card_type is CardType.AGENDA:
        defn.doom_threshold = int(record.get("doom") or 0)

    if card_type in (CardType.TREACHERY, CardType.ENEMY):
        defn.victory = int(record.get("victory") or 0)
        defn.vengeance = int(record.get("vengeance") or 0)

    if card_type is CardType.SKILL and not defn.icons:
        defn.wild_icons = 2  # skill cards with no printed skill icon are wild

    return defn


def load_records(path: str | Path) -> dict[str, dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_from_records(records: Iterable[dict[str, Any]]) -> list[CardDef]:
    return [to_card_def(record) for record in records]

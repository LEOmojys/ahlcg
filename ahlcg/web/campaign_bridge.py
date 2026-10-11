"""Optional bridge to the campaign layer (ahlcg.campaign).

The campaign package is owned by another agent and may not exist yet.  Every
call goes through this module so the web layer keeps working without it: when
the import fails the game degrades to a single scenario run, but the delegation
code below is complete and switches on automatically as soon as the package
appears (see SPEC.md section 2 for the contract).

Nothing here caches a negative result, so dropping ahlcg/campaign into the tree
while the server is running is enough to enable the full campaign flow.
"""

from __future__ import annotations

from typing import Any

CAMPAIGN_CODE = "night_of_the_zealot"
FIRST_SCENARIO = "torch"

CAMPAIGN_NAMES_ZH: dict[str, str] = {
    "night_of_the_zealot": "狂热者之夜",
}

SCENARIO_NAMES_ZH: dict[str, str] = {
    "torch": "第一章：集结",
    "arkham": "第二章：午夜面具",
    "tentacles": "第三章：深渊吞噬者",
}

#: tests inject a stand-in campaign package here
_override: Any = None
_override_set = False


def set_backend(backend: Any) -> None:
    """Inject a campaign package (used by tests); None restores the real one."""
    global _override, _override_set
    _override = backend
    _override_set = True


def load_backend() -> Any | None:
    """Return the campaign module, or None when it is not implemented yet."""
    if _override_set:
        return _override
    try:
        from .. import campaign
    except ImportError:
        return None
    except Exception:
        return None
    if campaign is None:
        return None
    if not hasattr(campaign, "CampaignState"):
        return None
    try:
        from ..campaign import game_builder  # noqa: F401
    except Exception:
        return None
    return campaign


def is_available() -> bool:
    return load_backend() is not None


def campaign_name(code: str | None) -> str:
    if not code:
        return CAMPAIGN_NAMES_ZH[CAMPAIGN_CODE]
    return CAMPAIGN_NAMES_ZH.get(code, code)


def scenario_name(code: str | None) -> str:
    if not code:
        return ""
    return SCENARIO_NAMES_ZH.get(code, code)


def new_campaign_state(
    backend: Any,
    investigator_codes: list[str],
    difficulty: str,
    decks: list[list[str]],
    seed: int | None,
) -> Any:
    """CampaignState.new(code, investigator_codes, difficulty, decks, seed)."""
    return backend.CampaignState.new(
        CAMPAIGN_CODE, list(investigator_codes), difficulty, [list(deck) for deck in decks], seed
    )


def build_scenario_game(backend: Any, campaign_state: Any, pool: Any) -> Any:
    from ..campaign.game_builder import build_scenario_game as builder

    return builder(campaign_state, pool)


def apply_resolution(campaign_state: Any, game: Any) -> dict:
    summary = campaign_state.apply_resolution(game)
    if not isinstance(summary, dict):
        summary = {"text": str(summary)}
    summary.setdefault("campaign_available", True)
    return summary


def advance(campaign_state: Any) -> None:
    campaign_state.advance()


def current_scenario_code(campaign_state: Any) -> str | None:
    code = campaign_state.scenario_code()
    return str(code) if code else None


def spend_xp(campaign_state: Any, player_id: str, purchases: list[dict]) -> list[str]:
    result = campaign_state.spend_xp(player_id, list(purchases))
    return list(result or [])


def campaign_dict(campaign_state: Any) -> dict:
    data = campaign_state.to_dict()
    if not isinstance(data, dict):
        return {}
    return dict(data)

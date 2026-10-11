"""Live browser sessions.

One session is one Game (plus the campaign state when the campaign layer
exists).  The engine is choice driven, so the store is thin: create a game,
hand out views, resolve ChoiceAnswers.
"""

from __future__ import annotations

import json
import random
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.choices import ChoiceAnswer
from ..core.errors import ChoiceError
from ..data.deck import DeckList
from ..data.pool import CardPool
from ..engine.game import Game
from ..session import CHAOS_BAGS, GameSetup, create_game
from . import campaign_bridge, decks


class SessionNotFound(KeyError):
    """The requested session id is unknown (expired or from another server)."""


class SessionBusy(RuntimeError):
    """The submitted answer does not match the pending choice."""


@dataclass
class Session:
    id: str
    difficulty: str
    seed: int | None
    investigator_code: str
    deck: list[str]
    game: Game
    campaign: Any = None
    notice: str | None = None
    last_summary: dict | None = None
    campaign_finished: bool = False
    created_at: float = field(default_factory=time.time)

    # -- campaign display ----------------------------------------------
    def campaign_dict(self) -> dict[str, Any]:
        """CampaignState.to_dict() when available, a matching stand-in when not."""
        if self.campaign is not None:
            try:
                data = campaign_bridge.campaign_dict(self.campaign)
            except Exception:
                data = {}
            if data:
                data.setdefault("name", campaign_bridge.campaign_name(data.get("code")))
                data.setdefault("difficulty", self.difficulty)
                data.setdefault("seed", self.seed)
                data["campaign_available"] = True
                return data
        return self.synthetic_campaign()

    def synthetic_campaign(self) -> dict[str, Any]:
        """Same keys as CampaignState.to_dict(), filled in by the web layer."""
        state = self.game.state
        player = state.players[0] if state.players else None
        investigator = state.investigator_of(player) if player is not None else None
        log: dict[str, list[str]] = {"战役记录": []}
        if self.notice:
            log["战役记录"].append(self.notice)
        return {
            "code": campaign_bridge.CAMPAIGN_CODE,
            "name": campaign_bridge.campaign_name(campaign_bridge.CAMPAIGN_CODE),
            "difficulty": self.difficulty,
            "seed": self.seed,
            "scenario_index": 0,
            "scenario_code": state.scenario_code,
            "scenario_name": state.scenario_name,
            "investigators": [
                {
                    "player_id": player.id,
                    "name": investigator.name if investigator else "调查员",
                    "investigator_code": self.investigator_code,
                    "deck": list(self.deck),
                    "xp_earned": player.xp_earned,
                    "xp_spent": 0,
                    "xp_available": player.xp_earned,
                    "trauma_physical": player.trauma_physical,
                    "trauma_mental": player.trauma_mental,
                    "story_assets": [],
                    "story_weaknesses": [],
                    "killed": bool(player.killed),
                    "insane": bool(player.insane),
                }
            ]
            if player is not None
            else [],
            "log": log,
            "history": list(state.counters.get("history") or []),
            "campaign_available": False,
            "single_scenario": True,
        }


class SessionStore:
    """In-memory registry of live games."""

    def __init__(
        self,
        pool: CardPool,
        *,
        image_store: Any = None,
        campaign_loader: Any = None,
        journal_dir: Any = None,
    ) -> None:
        self.pool = pool
        self.image_store = image_store
        self._loader = campaign_loader or campaign_bridge.load_backend
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        # Deterministic replay: the engine reproduces a game from its seed plus
        # the exact sequence of answers, so a journal of those answers is all a
        # restart needs to restore a game mid-scenario.
        self._journal_dir = Path(journal_dir) if journal_dir is not None else Path("assets/sessions")
        self._journals: dict[str, dict[str, Any]] = {}
        self._replaying = False

    # -- persistence ------------------------------------------------------
    def _journal_path(self, session_id: str) -> Path:
        return self._journal_dir / (session_id + ".json")

    def _save_journal(self, session_id: str) -> None:
        journal = self._journals.get(session_id)
        if journal is None:
            return
        try:
            self._journal_dir.mkdir(parents=True, exist_ok=True)
            self._journal_path(session_id).write_text(
                json.dumps(journal, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass  # persistence is best-effort; the live game is unaffected

    def _record(self, session: Session, entry: dict[str, Any]) -> None:
        if self._replaying:
            return
        journal = self._journals.setdefault(
            session.id,
            {
                "investigator_code": session.investigator_code,
                "difficulty": session.difficulty,
                "seed": session.seed,
                "deck": list(session.deck),
                "entries": [],
            },
        )
        journal["entries"].append(entry)
        self._save_journal(session.id)

    def _rebuild(self, session_id: str) -> Session:
        path = self._journal_path(session_id)
        journal = json.loads(path.read_text(encoding="utf-8"))
        self._journals[session_id] = journal
        self._replaying = True
        try:
            session = self.create(
                journal["investigator_code"],
                journal["difficulty"],
                journal["seed"],
                deck_codes=journal.get("deck"),
            )
            for entry in journal.get("entries", []):
                kind = entry.get("t")
                if kind == "answer":
                    self._apply_answer(session, entry.get("selected") or [], bool(entry.get("cancelled")))
                elif kind == "spend":
                    self.spend_xp(session.id, entry.get("purchases") or [])
                elif kind == "next":
                    self.next_scenario(session.id)
        finally:
            self._replaying = False
        # 关键：把恢复出的会话登记在"客户端所持的旧会话号"下。
        # 否则每次请求都会重放一遍日志，而新的记录会写进另一个文件，
        # 游戏状态就会永远弹回日志的末尾（看起来像"回到开局"）。
        session.id = session_id
        with self._lock:
            self._sessions[session_id] = session
        return session

    # -- lifecycle ------------------------------------------------------
    def create(
        self,
        investigator_code: str = "01001",
        difficulty: str = "standard",
        seed: int | None = None,
        deck_codes: list[str] | None = None,
    ) -> Session:
        if not self.pool.has(investigator_code):
            raise ValueError(f"未知调查员编号：{investigator_code}")
        if difficulty not in CHAOS_BAGS:
            raise ValueError(f"未知难度：{difficulty}")
        if seed is None:
            seed = random.randrange(1, 2 ** 31)  # a concrete seed keeps replay deterministic
        if deck_codes:
            deck = decks.deck_from_codes(self.pool, investigator_code, deck_codes)
        else:
            deck = decks.deck_for(self.pool, investigator_code)
        backend = self._loader()
        campaign = None
        game = None
        notice = None

        if backend is not None:
            try:
                campaign = campaign_bridge.new_campaign_state(
                    backend, [investigator_code], difficulty, [list(deck.cards)], seed
                )
                scenario_code = campaign_bridge.current_scenario_code(campaign)
                if scenario_code is None:
                    notice = "战役已经结束，改为单场景模式重玩第一章。"
                    campaign = None
                else:
                    game = campaign_bridge.build_scenario_game(backend, campaign, self.pool)
            except Exception as exc:  # campaign layer present but not usable
                campaign = None
                game = None
                notice = f"战役层调用失败（{exc}），已退回单场景模式。"
        if backend is None:
            notice = "战役层 ahlcg.campaign 尚未实现，当前为单场景模式：只玩第一章「集结」。"

        if game is None:
            game = self._single_scenario_game(deck, difficulty, seed)

        session = Session(
            id=secrets.token_hex(8),
            difficulty=difficulty,
            seed=seed,
            investigator_code=investigator_code,
            deck=list(deck.cards),
            game=game,
            campaign=campaign,
            notice=notice,
        )
        with self._lock:
            self._sessions[session.id] = session
        self._record(
            session,
            {"t": "new", "investigator_code": investigator_code, "difficulty": difficulty, "seed": seed},
        )
        return session

    def _single_scenario_game(self, deck: DeckList, difficulty: str, seed: int | None) -> Game:
        game = create_game(
            GameSetup(
                pool=self.pool,
                deck=deck,
                mulligan=True,
                slot_limits=True,
                scenario=campaign_bridge.FIRST_SCENARIO,
                difficulty=difficulty,
                seed=seed,
                player_name=decks.investigator_display_name(self.pool, deck.investigator),
            )
        )
        game.start()
        return game

    def get(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None and not self._replaying and self._journal_path(session_id).exists():
            session = self._rebuild(session_id)  # restore a game after a server restart
        if session is None:
            raise SessionNotFound(session_id)
        return session

    def drop(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def ids(self) -> list[str]:
        return list(self._sessions)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()

    # -- play -----------------------------------------------------------
    def answer(self, session_id: str, choice_id: str, selected: list[str], cancelled: bool = False) -> Session:
        session = self.get(session_id)
        choice = session.game.awaiting
        if choice is None:
            raise SessionBusy("当前没有等待中的选择（可能已经结算或结束）")
        if choice_id and choice_id != choice.id:
            raise SessionBusy("这个选择已经过期了，请刷新后重试")
        self._apply_answer(session, selected, cancelled)
        self._record(session, {"t": "answer", "selected": list(selected), "cancelled": bool(cancelled)})
        return session

    def _apply_answer(self, session: Session, selected: list[str], cancelled: bool) -> None:
        """Apply an answer to whatever the game is waiting for (replay relies on order, not ids)."""
        choice = session.game.awaiting
        if choice is None:
            raise SessionBusy("当前没有等待中的选择（可能已经结算或结束）")
        try:
            session.game.resolve(ChoiceAnswer(choice.id, tuple(selected), bool(cancelled)))
        except ChoiceError as exc:
            raise ValueError(str(exc)) from None

    # -- campaign -------------------------------------------------------
    def next_scenario(self, session_id: str) -> tuple[dict, Session]:
        session = self.get(session_id)
        if session.campaign is not None:
            backend = self._loader()
            if backend is not None:
                try:
                    summary = campaign_bridge.apply_resolution(session.campaign, session.game)
                    campaign_bridge.advance(session.campaign)
                    code = campaign_bridge.current_scenario_code(session.campaign)
                    if code is None:
                        session.campaign_finished = True
                        session.notice = "战役结束：三幕已经全部结束。"
                    else:
                        session.game = campaign_bridge.build_scenario_game(
                            backend, session.campaign, self.pool
                        )
                        session.game.start()
                        session.notice = None
                    session.last_summary = summary
                    self._record(session, {"t": "next"})
                    return summary, session
                except Exception as exc:
                    session.campaign = None
                    session.notice = f"战役层结算失败（{exc}），改为单场景模式重玩本章。"
            else:
                session.campaign = None
                session.notice = "战役层不可用，改为单场景模式重玩本章。"
        summary = self._local_summary(session)
        session.last_summary = summary
        deck = DeckList(
            investigator=session.investigator_code,
            cards=tuple(session.deck),
            name=f"{session.investigator_code} 牌组",
        )
        session.game = self._single_scenario_game(deck, session.difficulty, session.seed)
        if not session.notice:
            session.notice = "战役层尚未实现：本章已重新开始（单场景模式）。"
        return summary, session

    def _local_summary(self, session: Session) -> dict:
        """Resolution summary computed without the campaign layer."""
        state = session.game.state
        story = [entry.text for entry in state.log_entries if entry.kind == "story"][-4:]
        return {
            "scenario": state.scenario_code,
            "scenario_name": state.scenario_name,
            "resolution": state.resolution,
            "title": f"{state.scenario_name or state.scenario_code}：{state.resolution or '未结束'}",
            "text": "\n".join(story) or "本局尚未结束。",
            "xp_gained": 0,
            "trauma": {"physical": 0, "mental": 0},
            "log_changes": [],
            "next_scenario": None,
            "defeated_investigators": [],
            "campaign_available": False,
            "note": "战役层（ahlcg.campaign）尚未实现，经验、创伤与战役日志无法结算。",
        }

    def spend_xp(self, session_id: str, purchases: list[dict]) -> tuple[list[str] | None, Session]:
        session = self.get(session_id)
        if session.campaign is None:
            return None, session
        try:
            result = campaign_bridge.spend_xp(session.campaign, "p1", purchases)
        except Exception as exc:
            session.notice = f"升级失败：{exc}"
            return None, session
        if not result:
            self._record(session, {"t": "spend", "purchases": list(purchases)})
        return result, session

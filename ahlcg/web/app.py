"""FastAPI application for the AHLCG web client.

Run it with:

    python -m ahlcg.web.app

and open http://127.0.0.1:8765 .  The client is a single static page; the API
is the contract documented in SPEC.md section 3.
"""

from __future__ import annotations

import argparse
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..core.enums import CardType, Skill
from ..data.deck import is_investigator_specific, is_weakness, rules_for
from ..data.pool import CardPool
from ..session import CHAOS_BAGS
from . import campaign_bridge, decks
from .cardimages import CardImageStore, store_from_environment
from .sessions import SessionBusy, SessionNotFound, SessionStore
from .view import build_view

STATIC_DIR = Path(__file__).resolve().parent / "static"
HOST = "127.0.0.1"
PORT = 8765

DIFFICULTY_ORDER = ("easy", "standard", "hard", "expert")
DIFFICULTY_LABELS = {
    "easy": "简单",
    "standard": "标准",
    "hard": "困难",
    "expert": "专家",
}


# --------------------------------------------------------------------------
# request bodies
# --------------------------------------------------------------------------
class NewCampaignRequest(BaseModel):
    investigator_code: str = "01001"
    difficulty: str = "standard"
    seed: int | None = None
    deck_codes: list[str] | None = None


class ChoiceRequest(BaseModel):
    session_id: str
    choice_id: str = ""
    selected: list[str] = Field(default_factory=list)
    cancelled: bool = False


class NextRequest(BaseModel):
    session_id: str = ""


class Purchase(BaseModel):
    code: str
    replace: str | None = None


class SpendRequest(BaseModel):
    session_id: str
    purchases: list[Purchase] = Field(default_factory=list)


# --------------------------------------------------------------------------
# pool listing
# --------------------------------------------------------------------------
def deck_requirement_view(pool: CardPool, code: str) -> dict[str, Any]:
    defn = pool.get(code)
    primary = defn.card_class.value
    return {
        "size": decks.DECK_SIZE,
        "primary_class": primary,
        "max_level": 5,
        "notes": [
            f"30 张牌：{primary} 与中立卡",
            "本客户端提供的是自动组建的 0 级起始牌组",
        ],
    }


def pool_view(pool: CardPool) -> dict[str, Any]:
    investigators = []
    for code in decks.CORE_INVESTIGATORS:
        if not pool.has(code):
            continue
        defn = pool.get(code)
        investigators.append(
            {
                "code": code,
                "name": defn.display_name,
                "name_zh": decks.INVESTIGATOR_NAMES_ZH.get(code),
                "classes": [defn.card_class.value],
                "health": defn.health,
                "sanity": defn.sanity,
                "stats": {skill.value: int(defn.stat(skill) or 0) for skill in Skill},
                "stat_labels": {skill.value: skill.zh for skill in Skill},
                "deck_requirement": deck_requirement_view(pool, code),
                "starter": code == "01001",
            }
        )
    scenario_codes = _scenario_codes()
    return {
        "investigators": investigators,
        "difficulties": [code for code in DIFFICULTY_ORDER if code in CHAOS_BAGS],
        "difficulty_labels": dict(DIFFICULTY_LABELS),
        "scenarios": scenario_codes,
        "scenario_labels": {
            code: campaign_bridge.scenario_name(code) for code in scenario_codes
        },
        "campaigns": [campaign_bridge.CAMPAIGN_CODE],
        "campaign_labels": {campaign_bridge.CAMPAIGN_CODE: campaign_bridge.campaign_name(None)},
        "campaign_available": campaign_bridge.is_available(),
    }


def _scenario_codes() -> list[str]:
    try:
        from ..scenarios import scenario_codes

        codes = list(scenario_codes())
    except Exception:
        codes = []
    if campaign_bridge.FIRST_SCENARIO not in codes:
        codes.insert(0, campaign_bridge.FIRST_SCENARIO)
    return codes


# --------------------------------------------------------------------------
# application factory
# --------------------------------------------------------------------------
#: How long a reloading page has to re-register before the idle check may fire.
RELOAD_GRACE = 8.0


def presence_should_exit(last_seen: float | None, timeout: float, now: float) -> bool:
    """True once nobody has pinged for longer than timeout (0 disables auto-close)."""
    if last_seen is None or timeout <= 0:
        return False
    return (now - last_seen) > timeout


async def _json_body(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def create_app(
    pool: CardPool | None = None,
    *,
    image_store: CardImageStore | None = None,
    campaign_loader: Any = None,
    auto_close: float = 0.0,
    presence: dict[str, Any] | None = None,
) -> FastAPI:
    """Build the application.  Dependencies are injectable for the tests.

    auto_close (seconds) makes the process exit once the browser page has been
    gone for that long: the page pings /api/ping while it is open and beacons
    /api/bye when it closes.  0 (the default) disables it, so tests and embedded
    uses never shut themselves down.
    """
    pool = pool if pool is not None else CardPool.load()
    store = image_store if image_store is not None else store_from_environment()
    sessions = SessionStore(pool, image_store=store, campaign_loader=campaign_loader)
    seen: dict[str, Any] = presence if presence is not None else {}
    seen.setdefault("clients", {})
    seen.setdefault("last", None)

    application = FastAPI(title="诡镇奇谈 规则引擎", version="0.1")
    application.state.pool = pool
    application.state.sessions = sessions
    application.state.images = store
    application.state.pool_cache = None

    # -- errors ---------------------------------------------------------
    @application.exception_handler(SessionNotFound)
    async def _missing_session(request: Request, exc: SessionNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "会话不存在或已过期，请重新开始战役。"})

    @application.exception_handler(SessionBusy)
    async def _busy(request: Request, exc: SessionBusy) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    # -- pages ----------------------------------------------------------
    @application.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    if STATIC_DIR.is_dir():
        application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # -- api ------------------------------------------------------------
    @application.get("/api/pool")
    async def api_pool() -> dict:
        if application.state.pool_cache is None:
            application.state.pool_cache = pool_view(pool)
        return application.state.pool_cache

    @application.post("/api/campaign/new")
    async def api_campaign_new(payload: NewCampaignRequest) -> dict:
        try:
            session = sessions.create(
            payload.investigator_code,
            payload.difficulty,
            payload.seed,
            deck_codes=payload.deck_codes,
        )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return {"session_id": session.id, "view": build_view(session)}

    @application.get("/api/state")
    async def api_state(session: str = Query(...), lang: str = Query(default="")) -> dict:
        from . import view as view_module

        if lang in ("zh", "en"):
            view_module.LANG["cur"] = lang
        return {"view": build_view(sessions.get(session))}

    @application.post("/api/choice")
    async def api_choice(payload: ChoiceRequest) -> dict:
        try:
            session = sessions.answer(
                payload.session_id, payload.choice_id, payload.selected, payload.cancelled
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return {"view": build_view(session)}

    @application.post("/api/campaign/next")
    async def api_campaign_next(
        payload: NextRequest | None = None,
        session: str | None = Query(default=None),
    ) -> dict:
        session_id = (payload.session_id if payload else "") or (session or "")
        if not session_id:
            raise HTTPException(status_code=400, detail="缺少 session_id")
        summary, live = sessions.next_scenario(session_id)
        return {"summary": summary, "view": build_view(live)}

    @application.post("/api/campaign/spend")
    async def api_campaign_spend(payload: SpendRequest) -> dict:
        purchases = [purchase.model_dump() for purchase in payload.purchases]
        result, live = sessions.spend_xp(payload.session_id, purchases)
        body = {"view": build_view(live), "spent": result}
        if result is None:
            body["notice"] = "战役层尚未实现或不接受本次升级，牌组未改变。"
        return body

    @application.get("/api/deck-options")
    async def api_deck_options(investigator: str = Query(...)) -> dict:
        """自由组卡：列出这名调查员可以放进起始牌组的所有卡（等级 0）。"""
        if not pool.has(investigator):
            raise HTTPException(status_code=404, detail="未知调查员编号")
        rules = rules_for(pool.get(investigator))
        cards = []
        for defn in pool.all():
            record = defn.meta.get("arkhamdb") or {}
            if record.get("pack_code") not in ("core", "rcore") or record.get("encounter_code"):
                continue
            if defn.card_type not in (CardType.ASSET, CardType.EVENT, CardType.SKILL):
                continue
            if defn.level != 0 or defn.weakness or is_weakness(defn):
                continue
            if is_investigator_specific(defn):
                continue  # signature cards join the deck automatically
            if not rules.allows(defn):
                continue
            cards.append(
                {
                    "code": defn.code,
                    "name": defn.display_name,
                    "text": defn.text_zh or defn.text or "",
                    "cost": defn.cost,
                    "type": defn.card_type.value,
                    "class": defn.card_class.value,
                    "traits": sorted(defn.traits),
                }
            )
        return {"cards": cards, "size": rules.size}

    @application.get("/api/campaign/upgrades")
    async def api_campaign_upgrades(session: str = Query(default="")) -> dict:
        """经验升级：列出这名调查员在两张幕之间可以购买的卡牌。"""
        if not session:
            raise HTTPException(status_code=400, detail="缺少 session")
        live = sessions.get(session)
        campaign = getattr(live, "campaign", None)
        if campaign is None:
            return {
                "available": False,
                "notice": "当前是单场景模式：打完这一幕才有经验可以花。",
                "xp": 0,
                "deck_size": 0,
                "candidates": [],
            }
        investigator = campaign.investigators[0]
        rules = rules_for(pool.get(investigator.investigator_code))
        counts = Counter(investigator.deck)
        candidates = []
        seen_names: set[str] = set()
        for defn in pool.all():  # pool.all() is code-sorted, so the original printing wins
            if defn.name in seen_names:
                continue  # core and revised-core printings are the same card
            seen_names.add(defn.name)
            if defn.card_type not in (CardType.ASSET, CardType.EVENT, CardType.SKILL):
                continue
            record = defn.meta.get("arkhamdb") or {}
            if record.get("encounter_code"):
                continue
            # a core-set campaign may only upgrade with core-set player cards
            if record.get("pack_code") not in ("core", "rcore"):
                continue
            # weaknesses and other investigators' signature cards cannot be bought
            if is_weakness(defn) or is_investigator_specific(defn):
                continue
            if defn.level > 5 or not rules.allows(defn):
                continue
            if counts.get(defn.code, 0) >= 2:
                continue
            candidates.append(
                {
                    "code": defn.code,
                    "name": defn.name,
                    "name_zh": defn.display_name,
                    "class": defn.card_class.value,
                    "level": defn.level,
                    "cost": max(1, defn.level),
                    "text": defn.text,
                    "in_deck": counts.get(defn.code, 0),
                }
            )
        candidates.sort(key=lambda c: (c["cost"], c["level"], c["name"]))
        return {
            "available": True,
            "player_id": investigator.player_id,
            "name": investigator.name,
            "xp": investigator.xp_available,
            "deck_size": len(investigator.deck),
            "candidates": candidates,
        }

    @application.post("/api/ping")
    async def api_ping(request: Request) -> dict:
        """The open page tells us it is still there."""
        payload = await _json_body(request)
        client = str(payload.get("client") or "default")
        seen["clients"][client] = time.time()
        seen["last"] = seen["clients"][client]
        return {"ok": True, "auto_close": auto_close, "clients": len(seen["clients"])}

    @application.post("/api/bye")
    async def api_bye(request: Request) -> dict:
        """The page is closing.  Leave a short grace period so a reload survives."""
        payload = await _json_body(request)
        client = str(payload.get("client") or "")
        if client:
            seen["clients"].pop(client, None)
        elif len(seen["clients"]) <= 1:
            # sendBeacon body could not be parsed: treat it as the only tab leaving
            seen["clients"].clear()
        if not seen["clients"] and auto_close > 0:
            seen["last"] = time.time() - auto_close + RELOAD_GRACE
        return {"ok": True, "clients": len(seen["clients"])}

    @application.get("/api/card-image/{code}")
    async def api_card_image(code: str) -> FileResponse:
        if not pool.has(code):
            raise HTTPException(status_code=404, detail="未知卡牌编号")
        record = pool.get(code).meta.get("arkhamdb") or {}
        imagesrc = record.get("imagesrc")
        path = store.ensure(code, imagesrc)
        if path is None:
            raise HTTPException(status_code=404, detail="卡图不可用（未缓存且无法下载）")
        return FileResponse(
            path,
            media_type=store.media_type(path),
            headers={"Cache-Control": "public, max-age=86400"},
        )

    return application


def main() -> None:
    parser = argparse.ArgumentParser(description="诡镇奇谈（AHLCG）网页客户端")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--no-images", action="store_true", help="禁用卡图下载，只用文字卡面")
    parser.add_argument(
        "--auto-close",
        type=float,
        default=120.0,
        metavar="SECONDS",
        help="浏览器页面关闭后多少秒自动退出；留足余量以容忍后台标签页的定时器节流（0 = 一直运行）",
    )
    arguments = parser.parse_args()

    print("正在载入卡池……")
    pool = CardPool.load()
    store = store_from_environment()
    if arguments.no_images:
        store.enabled = False
    presence: dict[str, Any] = {}
    application = create_app(
        pool,
        image_store=store,
        auto_close=arguments.auto_close,
        presence=presence,
    )

    import socket
    import urllib.request

    host = arguments.host

    def already_running(port: int) -> bool:
        try:
            with urllib.request.urlopen(f"http://{host}:{port}/api/pool", timeout=3) as response:
                return response.status == 200
        except Exception:
            return False

    # Another instance may already be serving this port (easy to do by accident):
    # point the player at it instead of crashing with "address already in use".
    if already_running(arguments.port):
        print(f"检测到 http://{host}:{arguments.port} 上已经有一个实例在运行。")
        print(f"直接打开浏览器访问：http://{host}:{arguments.port}")
        print(f"（想同时再开一个，请加 --port {arguments.port + 1}）")
        return

    port = None
    for candidate in range(arguments.port, arguments.port + 12):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, candidate))
            except OSError:
                continue
        port = candidate
        break
    if port is None:
        print(f"错误：从 {arguments.port} 起的连续 12 个端口都被占用，请用 --port 指定其它端口。")
        raise SystemExit(1)
    if port != arguments.port:
        print(f"提示：端口 {arguments.port} 已被占用，改用 {port}。")

    print(f"诡镇奇谈网页客户端：http://{host}:{port}")
    if store.enabled:
        print(f"卡图缓存目录：{store.directory}")
    if arguments.auto_close > 0:
        print(f"关闭浏览器页面后约 {arguments.auto_close:.0f} 秒会自动退出（--auto-close 0 可关掉此行为）。")
    print("也可以随时按 Ctrl+C 停止。")

    import uvicorn

    config = uvicorn.Config(application, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    if arguments.auto_close > 0:

        def watch_presence() -> None:
            while not server.should_exit:
                time.sleep(2.0)
                if presence_should_exit(presence.get("last"), arguments.auto_close, time.time()):
                    print(
                        f"\n浏览器页面已关闭（{arguments.auto_close:.0f} 秒没有收到心跳），自动退出。",
                        flush=True,
                    )
                    server.should_exit = True
                    return

        threading.Thread(target=watch_presence, daemon=True).start()

    server.run()


if __name__ == "__main__":
    main()

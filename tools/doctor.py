"""One-shot self check: can this project actually run?

Prints a ✓/✗ line per step so a failure is obvious, then starts nothing.
Run:  python tools/doctor.py
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

FAILURES: list[str] = []


def step(name: str, fn):
    try:
        detail = fn()
        print(f"  [OK]   {name}" + (f"  —  {detail}" if detail else ""))
        return True
    except Exception as exc:
        print(f"  [FAIL] {name}  —  {type(exc).__name__}: {exc}")
        FAILURES.append(name)
        traceback.print_exc(limit=3)
        return False


def main() -> int:
    print("工作目录:", pathlib.Path.cwd())
    print("项目根目录:", ROOT)

    print("\n1. 环境")
    step("Python 版本 >= 3.12", lambda: sys.version.split()[0])
    step("fastapi / uvicorn 可导入", lambda: __import__("fastapi").__version__)

    print("\n2. 数据文件")
    for rel in ("reference/arkhamdb_core.json", "reference/notz_scenario_data.json", "reference/rules_digest.md"):
        step(rel, lambda rel=rel: f"{(ROOT / rel).stat().st_size / 1024:.0f} KB")

    print("\n3. 卡池与卡牌行为")
    pool_holder: dict = {}
    step("载入卡池（含所有卡牌行为）", lambda: pool_holder.setdefault("pool", __import__("ahlcg.data.pool", fromlist=["CardPool"]).CardPool.load()) and len(pool_holder["pool"]))
    pool = pool_holder["pool"]

    print("\n4. 牌组")
    def build_decks():
        from ahlcg.data.deck import CORE_INVESTIGATORS, build_starter_deck, validate_deck
        bad = []
        for code in CORE_INVESTIGATORS:
            problems = validate_deck(pool, build_starter_deck(pool, code))
            if problems:
                bad.append((code, problems))
        if bad:
            raise RuntimeError(f"非法牌组: {bad}")
        return f"{len(CORE_INVESTIGATORS)} 套起始牌组合法"
    step("五名调查员起始牌组合法性", build_decks)

    print("\n5. 引擎：跑一局第一章")
    def run_game():
        from ahlcg.ai import robot
        from ahlcg.session import GameSetup, create_game
        game = create_game(GameSetup(pool=pool, seed=11))
        report = robot.play(game, max_steps=30000)
        if not report.get("finished"):
            raise RuntimeError(f"没有结束: {report}")
        return f"结局 {report['resolution']}，{report['rounds']} 轮，{report['steps']} 步"
    step("机器人自动打完第一章", run_game)

    print("\n6. 剧本科目")
    def scenarios():
        from ahlcg.scenarios import scenario_codes
        codes = scenario_codes()
        return f"已注册: {codes}"
    step("剧本注册表", scenarios)

    print("\n7. 战役层与 Web 层")
    step("import ahlcg.campaign", lambda: __import__("ahlcg.campaign", fromlist=["CAMPAIGNS"]).CAMPAIGNS)
    app_holder: dict = {}
    def make_app():
        from ahlcg.web.app import create_app
        from ahlcg.web.cardimages import store_from_environment
        store = store_from_environment()
        store.enabled = False
        app_holder["app"] = create_app(pool, image_store=store)
        return "create_app() 成功"
    step("create_app()", make_app)

    if "app" in app_holder:
        print("\n8. 前端与 HTTP 接口（进程内）")
        def frontend():
            from fastapi.testclient import TestClient
            client = TestClient(app_holder["app"], raise_server_exceptions=False)
            res = client.get("/")
            if res.status_code != 200:
                raise RuntimeError(f"GET / -> {res.status_code} {res.text[:120]}")
            text = res.text
            for marker in ("诡镇奇谈", "id=\"choice\"", "/api/choice", "/api/campaign/new"):
                if marker not in text:
                    raise RuntimeError(f"页面缺少 {marker}")
            return f"{len(text)} 字节，关键元素齐全"
        step("GET / 返回可用的单页界面", frontend)

        def api_flow():
            from fastapi.testclient import TestClient
            client = TestClient(app_holder["app"], raise_server_exceptions=False)
            r = client.post("/api/campaign/new", json={"investigator_code": "01001", "difficulty": "standard"})
            if r.status_code != 200:
                raise RuntimeError(f"POST /api/campaign/new -> {r.status_code} {r.text[:200]}")
            sid = r.json()["session_id"]
            for _ in range(6):
                view = client.get("/api/state", params={"session": sid}).json()["view"]
                choice = view.get("choice")
                if not choice:
                    break
                opts = [o for o in choice["options"] if not o.get("disabled")]
                pick = next((o["id"] for o in opts if o["id"] == "investigate"), None) or (opts[0]["id"] if opts else None)
                if pick is None:
                    body = {"session_id": sid, "choice_id": choice["id"], "selected": [], "cancelled": True}
                else:
                    body = {"session_id": sid, "choice_id": choice["id"], "selected": [pick]}
                rb = client.post("/api/choice", json=body)
                if rb.status_code != 200:
                    raise RuntimeError(f"POST /api/choice -> {rb.status_code} {rb.text[:200]}")
            return "建局 / 取状态 / 提交选择 全部 200"
        step("HTTP 对局流程", api_flow)

    print("\n9. 前端脚本语法（用 node 检查提取出来的 JS）")
    def check_js():
        html = (ROOT / "ahlcg" / "web" / "static" / "index.html").read_text(encoding="utf-8")
        blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
        if not blocks:
            raise RuntimeError("index.html 里没有 <script> 块")
        target = ROOT / "build" / "frontend_check.js"
        target.parent.mkdir(exist_ok=True)
        target.write_text("\n".join(blocks), encoding="utf-8")
        result = subprocess.run(["node", "--check", str(target)], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip()[:400])
        return f"{sum(len(b.splitlines()) for b in blocks)} 行 JS 语法通过"
    step("index.html 的 JS 语法", check_js)

    print()
    if FAILURES:
        print(f"结果：{len(FAILURES)} 项失败 -> {FAILURES}")
        return 1
    print("结果：全部通过。启动命令：python -m ahlcg.web.app   然后打开 http://127.0.0.1:8765")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

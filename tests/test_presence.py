"""页面关闭后自动退出：心跳接口与空闲判定。"""

import time

import pytest
from fastapi.testclient import TestClient

from ahlcg.data.pool import CardPool
from ahlcg.web.app import RELOAD_GRACE, create_app, presence_should_exit


@pytest.fixture(scope="module")
def pool():
    return CardPool.load()


def test_presence_exit_logic():
    now = 1000.0
    assert presence_should_exit(None, 40, now) is False, "还没人连过就不该退出"
    assert presence_should_exit(now - 5, 40, now) is False
    assert presence_should_exit(now - 41, 40, now) is True
    assert presence_should_exit(now - 999, 0, now) is False, "0 表示禁用自动退出"


def test_ping_keeps_the_server_alive(pool):
    presence = {}
    app = create_app(pool, auto_close=40.0, presence=presence)
    client = TestClient(app, raise_server_exceptions=False)

    assert client.post("/api/ping", json={"client": "abc"}).status_code == 200
    assert presence["clients"]["abc"]
    assert presence_should_exit(presence["last"], 40.0, time.time()) is False


def test_bye_schedules_a_shutdown_but_tolerates_a_reload(pool):
    presence = {}
    app = create_app(pool, auto_close=40.0, presence=presence)
    client = TestClient(app, raise_server_exceptions=False)

    client.post("/api/ping", json={"client": "abc"})
    assert client.post("/api/bye", json={"client": "abc"}).status_code == 200
    assert not presence["clients"]
    # 刷新页面会在宽限期内重新注册，此时不该退出
    assert presence_should_exit(presence["last"], 40.0, time.time()) is False
    assert presence_should_exit(presence["last"], 40.0, time.time() + RELOAD_GRACE + 0.5) is True
    client.post("/api/ping", json={"client": "abc"})
    assert presence_should_exit(presence["last"], 40.0, time.time()) is False


def test_one_closed_tab_does_not_stop_the_others(pool):
    presence = {}
    app = create_app(pool, auto_close=40.0, presence=presence)
    client = TestClient(app, raise_server_exceptions=False)

    client.post("/api/ping", json={"client": "tab1"})
    client.post("/api/ping", json={"client": "tab2"})
    client.post("/api/bye", json={"client": "tab1"})
    assert presence["clients"] == {"tab2": presence["clients"]["tab2"]}
    assert presence_should_exit(presence["last"], 40.0, time.time()) is False


def test_auto_close_is_off_by_default(pool):
    presence = {}
    app = create_app(pool, presence=presence)
    client = TestClient(app, raise_server_exceptions=False)
    client.post("/api/bye", json={"client": "abc"})
    assert presence_should_exit(presence["last"], 0.0, time.time() + 10_000) is False

"""断点恢复：会话日志落盘，服务重启后按操作序列重放。"""

import pytest

from ahlcg.data.pool import CardPool
from ahlcg.web.app import create_app
from ahlcg.web.sessions import SessionStore


@pytest.fixture(scope="module")
def pool():
    return CardPool.load()


def test_session_survives_a_restart(pool, tmp_path):
    store = SessionStore(pool, journal_dir=tmp_path)
    session = store.create("01001", "standard", 1234)
    assert session.game.awaiting is not None

    # play a few choices (accept whatever the game offers, first option / cancel)
    for _ in range(6):
        choice = session.game.awaiting
        if choice is None:
            break
        selected = [o.id for o in choice.options[:1]]
        store.answer(session.id, choice.id, selected, False)

    # a brand new store = the server restarted; the journal brings the game back
    store2 = SessionStore(pool, journal_dir=tmp_path)
    restored = store2.get(session.id)
    assert restored.game.awaiting is not None
    assert restored.game.state.round == session.game.state.round
    assert len(restored.game.state.players[0].hand) == len(session.game.state.players[0].hand)
    assert restored.game.state.players[0].resources == session.game.state.players[0].resources


def test_unknown_session_still_fails(pool, tmp_path):
    store = SessionStore(pool, journal_dir=tmp_path)
    from ahlcg.web.sessions import SessionNotFound

    with pytest.raises(SessionNotFound):
        store.get("deadbeef")


def test_restored_session_keeps_its_id_and_progresses(pool, tmp_path):
    """重启后：会话号必须保持不变，且继续提交选择要正常推进（不能弹回开局）。"""
    store = SessionStore(pool, journal_dir=tmp_path)
    session = store.create("01001", "standard", 99)

    for _ in range(4):
        choice = session.game.awaiting
        if choice is None:
            break
        store.answer(session.id, choice.id, [o.id for o in choice.options[:1]], False)
    progress_after_live = session.game.state.round

    store2 = SessionStore(pool, journal_dir=tmp_path)
    restored = store2.get(session.id)
    assert restored.id == session.id, "恢复出的会话必须沿用客户端所持的会话号"

    # 恢复后的会话继续游玩：再提交一个选择，状态必须前进而不是重放回起点
    choice = restored.game.awaiting
    if choice is not None:
        store2.answer(session.id, choice.id, [o.id for o in choice.options[:1]], False)
    again = store2.get(session.id)
    assert again.game is restored.game, "第二次访问必须命中缓存的会话，而不是再重放一遍"
    assert again.game.state.round >= progress_after_live

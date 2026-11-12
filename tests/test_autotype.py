"""打ち込みのキュー(sc61box.autotype.Typer)。本体を動かさずに試す"""

from sc61box.autotype import Typer
from sc61box.machine import new_machine


def _typer():
    return Typer(new_machine("1251", rom=False))


def test_each_call_runs_once():
    """同じ関数を何度入れても、入れた回数だけ呼ぶ(途中で呼んでから入れ直しても)"""
    t = _typer()
    ran: list[int] = []

    def f():
        ran.append(1)

    t.add_call(f)
    t.add_call(f)
    t.step()
    t.add_call(f)
    for _ in range(10):
        t.step()
    assert len(ran) == 3 and not t.busy


def test_writes_in_order():
    """ダンプは入れた順に書く(同じ中身のダンプも別々に)"""
    t = _typer()
    seen: list[list[tuple[int, bytes]]] = []
    t.on_write = seen.append
    blocks = [(0xC000, b"\x37")]
    t.add_write(blocks)
    t.add_write(blocks)
    t.add_write([(0xC001, b"\x00")])
    for _ in range(10):
        t.step()
        t.until = 0  # 書いたあとの間を待たずに次へ
    assert seen == [blocks, blocks, [(0xC001, b"\x00")]]


def test_clear_drops_calls_and_writes():
    """clearで捨てた関数とダンプは、キューと一緒になくなる(あとで呼ばない、持ち続けない)"""
    t = _typer()
    ran: list[int] = []
    for _ in range(10):
        t.add_write([(0xC000, b"\x37")])
        t.add_call(lambda: ran.append(1))
        t.clear()
    assert t.queue == [] and not t.busy
    assert not hasattr(t, "calls") and not hasattr(t, "writes")
    t.add_call(lambda: ran.append(2))
    for _ in range(3):
        t.step()
    assert ran == [2]


def test_short_mouse_taps_reach_basic():
    """マウスや指で軽く叩いたキーは、押して離すのが同じフレームの中でも、本体に届く"""
    from helpers import make_app

    from sc61box.lcdtext import lcd_text

    app = make_app(norom=True)
    for name in ("1", "+", "1", "ENTER"):
        app.typer.press_mouse(name)
        app.typer.release_mouse(name)
        for _ in range(6):
            app.frame()
    for _ in range(20):
        app.frame()
    assert lcd_text(app.m).strip().startswith("2")
    assert not app.m.held
    app.close()


def test_short_tap_then_restore_releases_key(tmp_path, monkeypatch):
    """短く叩いたキーを押しておくあいだに、前に保存した状態へ戻しても、そのキーは離す(押して
    おく時刻は戻す前のサイクルで数えたものなので、戻したあとには使わない)"""
    from helpers import make_app

    app = make_app(norom=True)
    monkeypatch.setattr(app, "state_file", str(tmp_path / "state.json"))
    app.save_state()
    for _ in range(150):  # 5秒
        app.frame()
    app.typer.press_mouse("1")
    app.typer.release_mouse("1")
    app.load_state()
    app.typer.add_text("2")
    for _ in range(30):
        app.frame()
    assert "1" not in app.m.held and not app.typer.mouse_off
    app.close()

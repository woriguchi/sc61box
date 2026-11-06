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

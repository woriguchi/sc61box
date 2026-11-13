"""ROMなしのBASICの状態の保存と復元: CALLの最中に保存して戻しても、保存しなかったときと同じに
終わる(4機種、打った行とプログラムの中、マシン語の戻り方)。壊れた状態は、本体に手を付けずに断る"""

import base64
import copy
import json
from typing import Any, cast

import pytest
from basic_diff import basic_machine
from helpers import finish

from sc61box.autotype import Typer
from sc61box.basic.pc1261.system import Basic as Basic1261
from sc61box.machine import CLOCK

# マシン語を置く番地と、待つあいだ見る番地
SPOTS = {
    "1251": (0xC200, 0xC300),
    "1245": (0xC200, 0xC300),
    "1261": (0x4800, 0x4900),
    "1350": (0x6800, 0x6900),
}

# 待ったあとの戻り方
ENDS = {
    "rtn": [0x37],
    # 14h番地を3にして、キャリーを1にして戻り番地の次へ戻る: エラー3(PC-1251系)
    "error": [0x02, 0x03, 0x94, 0xDB, 0x5B, 0x42, 0x34, 0xD0, 0x37],
    # 15h番地を30hにしてRTN: BREAK(PC-1251系)
    "break": [0x02, 0x30, 0x95, 0xDB, 0x37],
    # 15h番地を20hにしてRTN: プログラムの中なら>を出さずに止まる(PC-1251系)
    "quiet": [0x02, 0x20, 0x95, 0xDB, 0x37],
    # 15h番地を10hにしてRTN: 打った行なら、CONTが何もしなくなる(PC-1251系)
    "dead": [0x02, 0x10, 0x95, 0xDB, 0x37],
    # 戻り番地を捨て、Xを2つ進めてキャリー0で命令の続きへ(PC-1350)
    "go-on": [0x04, 0x04, 0xD1, 0x5B, 0x5B, 0x37],
    # 戻り番地を捨て、34h番地を3、キャリー1で命令の続きへ: エラー3(PC-1350)
    "fail": [0x02, 0x03, 0xB4, 0xDB, 0xD0, 0x5B, 0x5B, 0x37],
}
# 打つ行(atはマシン語の番地)。programはプログラムの中のCALL
LINES = {"typed": "CALL &{at:04X}", "typed-rest": "CALL &{at:04X}:A=1", "program": "RUN"}
MODEL_ENDS = {
    "1251": ("rtn", "error", "break", "quiet", "dead"),
    "1245": ("rtn", "error", "break", "quiet", "dead"),
    "1261": ("rtn",),
    "1350": ("rtn", "go-on", "fail"),
}


def _waiting(model: str, end: str, line: str):
    """マシン語がフラグを待っているCALLの最中の本体。lineはLINESの名前"""
    at, flag = SPOTS[model]
    code = bytes([0x10, flag >> 8, flag & 0xFF, 0x57, 0x67, 0x00, 0x39, 0x07] + ENDS[end])
    m = basic_machine(model)
    m.mem[at : at + len(code)] = code
    m.mem[flag] = 0
    t = Typer(m)
    if line == "program":
        t.add_mode("PRO")
        finish(m, t)
        m.run(CLOCK)
        for text in ("NEW", f"10 A=1:CALL &{at:04X}:A=7", "20 END"):
            t.add_text(text + "\n")
            finish(m, t)
        t.add_mode("RUN")
        finish(m, t)
        m.run(CLOCK)
    t.add_text(LINES[line].format(at=at) + "\n")
    finish(m, t)
    m.run(CLOCK // 2)
    assert at <= m.cpu.pc < at + len(code)  # 待っているところ
    return m


def _ended(m) -> tuple:
    """フラグを立ててマシン語を戻し、BASICが落ち着いたあとの様子"""
    m.mem[SPOTS[m.model.name][1]] = 1
    m.run(CLOCK)
    b = m.basic
    lo, hi = m.model.ram
    r = b.runner
    return (b.state, b.where, b.stopped_at, b.error_pos, m.columns(), bytes(m.mem[lo:hi]),
            r.resume, r.dead_cont, m.pc_out & 1)  # fmt: skip


CASES = [(model, end, line) for model, ends in MODEL_ENDS.items() for end in ends for line in LINES]


@pytest.mark.parametrize(("model", "end", "line"), CASES)
def test_call_ends_same_after_restore(model, end, line):
    """CALLの最中に保存した状態を別の本体に戻してから(戻したものをもう一度保存して戻しても)
    マシン語が戻ると、保存しなかったときと同じに終わる"""
    plain = _ended(_waiting(model, end, line))
    for times in (1, 2):
        m = _waiting(model, end, line)
        for _ in range(times):
            again = basic_machine(model)
            again.restore(json.loads(json.dumps(m.snapshot())))
            m = again
        got = _ended(m)
        assert got == plain, (times, got[:4], plain[:4])


SPOILS = {
    "call_code": lambda b: b.__setitem__("call_code", "zz"),
    "at": lambda b: b.__setitem__("at", [1]),
    "runner": lambda b: b["runner"].__setitem__("loops", [[1]]),
    "printout": lambda b: b.__setitem__("printout", [1]),
    "units": lambda b: b.__setitem__("units", ["x"]),
}


@pytest.mark.parametrize("model", list(SPOTS))
def test_broken_basic_state_leaves_machine_alone(model):
    """BASICの状態が壊れた状態のファイルは、RAM・CPU・BASICのどれにも手を付けずにValueErrorで断る"""
    state = json.loads(json.dumps(_waiting(model, "rtn", "typed").snapshot()))
    assert state["basic"]["where"] == "call-direct"
    for name, spoil in SPOILS.items():
        bad = copy.deepcopy(state)
        spoil(bad["basic"])
        m = basic_machine(model)
        t = Typer(m)
        t.add_text("A=5\n")
        finish(m, t)
        m.mem[m.model.ram[0]] ^= 0xFF
        before = json.dumps(m.snapshot())
        with pytest.raises(ValueError, match="BASICの状態"):
            m.restore(bad)
        assert json.dumps(m.snapshot()) == before, name
    basic_machine(model).restore(state)  # 壊さなければ戻せる


def test_state_without_basic_starts_at_prompt():
    """BASICの状態のない状態のファイルも読め、BASICは入力待ちから始める"""
    state = json.loads(json.dumps(_waiting("1251", "rtn", "typed").snapshot()))
    del state["basic"]
    m = basic_machine("1251")
    m.restore(state)
    assert m.basic is not None and m.basic.state == "prompt" and m.basic.where == "idle"


# # ram: で広げたRAMの終わりの80h前に置くマシン語。終わり−10hの番地が0でなくなるまで待ち、
# LIA 7Fをして、Aを終わり−0Fhに書いてRTN
def _wide_code(top: int) -> tuple[int, bytes]:
    at, flag, out = top - 0x80, top - 0x10, top - 0x0F
    return at, bytes([0x10, flag >> 8, flag & 0xFF, 0x57, 0x67, 0x00, 0x39, 0x07,
                      0x02, 0x7F, 0x10, out >> 8, out & 0xFF, 0x52, 0x37])  # fmt: skip


WIDE = {"1251": 0xC900, "1245": 0xC900, "1261": 0x6900}


def _wide_waiting(model: str):
    """RAMを広げ、広げた所のマシン語が待っているCALLの最中の本体"""
    top = WIDE[model]
    at, code = _wide_code(top)
    m = basic_machine(model)
    m.set_ram_top(top)
    m.mem[at : at + len(code)] = code
    m.mem[top - 0x10] = m.mem[top - 0x0F] = 0
    t = Typer(m)
    t.add_text(f"CALL &{at:04X}\n")
    finish(m, t)
    m.run(CLOCK // 2)
    assert at <= m.cpu.pc < at + 8
    return m


@pytest.mark.parametrize("model", list(WIDE))
@pytest.mark.parametrize("restored", [False, True])
def test_call_in_widened_ram_after_restore(model, restored):
    """# ram: で広げたRAMのマシン語をCALLしている最中に保存して別の本体に戻しても、続けて
    実行すると最後まで動き、作業欄の1命令ずつの実行でも命令を実行する(広げたRAMをROMの番地と
    みなしてCALLをやめない)"""
    from sc61box import workbench

    top = WIDE[model]
    at = top - 0x80
    for how in ("run", "step"):
        m = _wide_waiting(model)
        if restored:
            again = basic_machine(model)
            again.restore(json.loads(json.dumps(m.snapshot())))
            m = again
        basic = m.basic
        assert basic is not None
        m.mem[top - 0x10] = 1
        if how == "run":
            m.run(CLOCK)
        else:
            b = workbench.Bench(m)
            b.state = "pause"
            for _ in range(20):
                if m.cpu.pc == at + 8:
                    break
                b.step()
            b.step()  # LIA 7F
            assert m.cpu.pc == at + 10 and m.cpu.ram[2] == 0x7F, (how, hex(m.cpu.pc))
            assert b.state == "pause" and not basic.active
            for _ in range(3):
                b.step()
        assert m.mem[top - 0x0F] == 0x7F and basic.notice is None, how


@pytest.mark.parametrize("bad", [None, [], "x", 1])
def test_broken_runner_state_is_refused(bad):
    """BASICの状態のrunnerが辞書でなければ、本体に手を付けずにValueErrorで断る"""
    state = json.loads(json.dumps(basic_machine("1251").snapshot()))
    state["basic"]["runner"] = bad
    m = basic_machine("1251")
    before = json.dumps(m.snapshot())
    with pytest.raises(ValueError, match="BASICの状態"):
        m.restore(state)
    assert json.dumps(m.snapshot()) == before


@pytest.mark.parametrize("model", ["1251", "1261", "1350"])
@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("at", [2**40, 0]),
        ("at", [0xFFFF, 0]),
        ("at", [-1, 0]),
        ("at", [0, 999]),
        ("at", [1]),
        ("stopped_at", [2**40, 3]),
    ],
)
def test_broken_program_place_is_refused(model, key, bad):
    """BASICの状態の、プログラムの中の位置に行が入らない(メモリの外にかかる)なら、本体に手を
    付けずにValueErrorで断る(続けたときに、メモリの外を読んで落ちないように)"""
    state = json.loads(json.dumps(basic_machine(model).snapshot()))
    state["basic"][key] = bad
    m = basic_machine(model)
    before = json.dumps(m.snapshot())
    with pytest.raises(ValueError, match="BASICの状態"):
        m.restore(state)
    assert json.dumps(m.snapshot()) == before


@pytest.mark.parametrize(
    ("name", "bad"), [("t2", 2**40), ("t512cnt", 256), ("t2ms", 2), ("t512", 7)]
)
def test_broken_timer_is_refused(name, bad):
    """状態のタイマの値が範囲の外なら、ValueErrorで断る(続けたときに、タイマを進めるのに
    いつまでもかからないように)"""
    state = json.loads(json.dumps(basic_machine("1350").snapshot()))
    state["machine"][name] = bad
    m = basic_machine("1350")
    before = json.dumps(m.snapshot())
    with pytest.raises(ValueError, match=name):
        m.restore(state)
    assert json.dumps(m.snapshot()) == before


@pytest.mark.parametrize(("key", "index", "bad"), [("console", 1, 2**40), ("console", 6, -5),
                                                   ("graphics", 2, 2**40)])  # fmt: skip
def test_broken_pc1350_screen_state_is_not_used(key, index, bad):
    """PC-1350の表示の行と桁や、LINEの始めの点が範囲の外なら、そこは読まずに初めの値にする
    (表示を送るのやLINEに、いつまでもかからないように)"""
    m = basic_machine("1350")
    state = json.loads(json.dumps(m.snapshot()))
    state["basic"][key][index] = bad
    m.restore(state)
    b: Any = m.basic  # PC-1350のBASIC(表示とグラフィックの属性を見る)
    assert 0 <= b.console.row <= 4 and b.print_pos is None
    assert b.graphics.last == (0, 0)
    m.run(CLOCK // 10)


@pytest.mark.parametrize("bad", [[], {}, 1])
def test_broken_rom_digest_is_refused(bad):
    """状態のファイルのROMのハッシュが文字列でなければ、ValueErrorで断る"""
    state = json.loads(json.dumps(basic_machine("1251").snapshot()))
    state["rom"] = bad
    with pytest.raises(ValueError):
        basic_machine("1251").restore(state)


def _typed(m, t, lines):
    for text in lines:
        t.add_text(text + "\n")
        finish(m, t)


@pytest.mark.parametrize("model", list(SPOTS))
def test_restore_drops_unfinished_work_area(model):
    """計算の途中(作業領域の書き戻しの途中)で、実行する前に保存した状態に戻すと、RAMは保存した
    ときのまま(戻す前の計算の残りを、戻したRAMに書かない)"""
    m = basic_machine(model)
    t = Typer(m)
    t.add_mode("PRO")
    finish(m, t)
    m.run(CLOCK)
    _typed(m, t, ["NEW", "10 A=(123+456)*(789+234)", "20 GOTO 10"])
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK)
    before = json.loads(json.dumps(m.snapshot()))
    _typed(m, t, ["RUN"])
    assert m.basic is not None
    for _ in range(1000):
        m.run(CLOCK // 997)
        tl = m.basic.runner.timeline
        if tl is not None and tl.pending:
            break
    else:
        pytest.fail("作業領域を書き戻しているところに来ない")
    m.restore(before)
    lo, hi = m.model.ram
    assert bytes(m.mem[lo:hi]) == base64.b64decode(before["mem"])[lo:hi]


@pytest.mark.parametrize("model", ["1261", "1350"])
def test_error_line_notice_after_restore(model):
    """PROモードの↓でエラーで止まった行を出し、2行目にエラーメッセージを出しているところで保存して
    別の本体に戻しても、カーソルを描き直したときにメッセージが消えない"""
    m = basic_machine(model)
    t = Typer(m)
    t.add_mode("PRO")
    finish(m, t)
    m.run(CLOCK)
    _typed(m, t, ["NEW", "10 A=1/0", "20 END"])
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK)
    _typed(m, t, ["RUN"])
    m.run(CLOCK)
    if model == "1350":  # エラーの知らせを出しているあいだは、MODEキーが効かない
        t.add_keys([["CLS"]])
    t.add_mode("PRO")
    finish(m, t)
    m.run(2 * CLOCK)
    t.add_keys([["DOWN"]])
    finish(m, t)
    m.run(CLOCK // 2)
    b = m.basic
    assert b is not None and b.state == "error-line" and getattr(b, "notice_row", None) is not None
    state = json.loads(json.dumps(m.snapshot()))
    m.run(CLOCK)
    again = basic_machine(model)
    again.restore(state)
    again.run(CLOCK)
    shown = cast(Basic1261, again.basic).lcd.text
    assert shown == cast(Basic1261, b).lcd.text  # 点滅するカーソルの位相は比べない

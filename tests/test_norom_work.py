"""ROMなしのBASICが、計算に使うRAM(作業領域)をROMのある本体と同じ形で使うか"""

from decimal import Decimal

import helpers
import pytest
from basic_diff import basic_machine
from conftest import HAVE_ROM, HAVE_ROM_1245, HAVE_ROM_1260, HAVE_ROM_1350
from helpers import boot, finish

from sc61box.autotype import Typer
from sc61box.basic import workarea
from sc61box.basic.pc1251.evaluate import Evaluator as Evaluator1251
from sc61box.basic.pc1261.evaluate import Evaluator as Evaluator1261
from sc61box.basic.pc1261.pc1350 import Evaluator as Evaluator1350
from sc61box.machine import CLOCK

HAVE = {"1251": HAVE_ROM, "1245": HAVE_ROM_1245, "1261": HAVE_ROM_1260, "1350": HAVE_ROM_1350}
LAYOUT: dict[str, workarea.Layout] = {}
for _models, _evaluator in ((("1251", "1245"), Evaluator1251), (("1261",), Evaluator1261),
                            (("1350",), Evaluator1350)):  # fmt: skip
    assert _evaluator.WORK is not None
    LAYOUT |= dict.fromkeys(_models, _evaluator.WORK)
BASE = {"1251": 0xC200, "1245": 0xC200, "1261": 0x5800, "1350": 0x6800}  # マシン語を置く番地


def _ranges(w: workarea.Layout) -> list[tuple[int, int]]:
    """比べる作業領域で、前もって埋めてもROMのある本体が読まない所"""
    out = [(w.ops, w.ops + w.ops_size), (w.values, w.values + 8 * w.values_size),
           (w.strings, w.strings_end), (w.copy, w.copy + 8), (w.target, w.target + 3),
           (w.call, w.call + 2), (w.number_work + w.number_first, w.number_work + 28),
           (w.number_text, w.number_text + 24)]  # fmt: skip
    if w.array_kinds:
        out.append((w.ops + 0x10, w.ops + 0x10 + w.ops_size))
    for a in (w.ops_count, w.values_top, w.strings_next, w.copy_number):
        if a is not None:
            out.append((a, a + (8 if a == w.copy_number else 1)))
    fs, gs = workarea.record_size(w)
    out += [(w.for_at, w.for_at + 5 * fs), (w.gosub_at, w.gosub_at + 10 * gs)]
    return out


def _states(w: workarea.Layout) -> list[tuple[int, int]]:
    """比べるだけで埋めない所(ROMのある本体が読む値)"""
    out = [(w.for_top, w.for_top + 1), (w.gosub_top, w.gosub_top + 1),
           (w.last, w.last + (4 if w.line_numbers else 2)), (w.data, w.data + 2),
           (w.flags, w.flags + 1), (w.print_end, w.print_end + 1),
           (w.using, w.using + 3)]  # fmt: skip
    for a, n in ((w.print_item, 1), (w.program_head, 2)):
        if a is not None:
            out.append((a, a + n))
    return out


def _until(m, pc: int) -> None:
    for _ in range(800):
        if pc <= m.cpu.pc < pc + 3:
            return
        m.run(CLOCK // 100)
    raise AssertionError(f"{pc:04X}番地に来ない")


def at_call(m, model: str, stmt: str) -> dict[int, int]:
    """「10 CALL &b:stmt:CALL &b+10h」を走らせ、2つ目のCALLの入口での作業領域を返す。1つ目の
    CALLの入口で、作業領域を番地の下位バイトで埋めておく"""
    b, w, t = BASE[model], LAYOUT[model], Typer(m)
    t.add_mode("PRO")
    finish(m, t)
    m.run(CLOCK)
    stmt = stmt.replace("%X", f"{b + 0x10:04X}")
    t.add_text(f"NEW\n10 CALL &{b:04X}:{stmt}:CALL &{b + 0x10:04X}\n")
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK)
    for a in (b, b + 0x10):
        m.mem[a : a + 3] = bytes([0x79, a >> 8, a & 0xFF])  # JP a
    t.add_text("RUN\n")
    finish(m, t)
    _until(m, b)
    ranges = _ranges(w)
    for lo, hi in ranges:
        m.mem[lo:hi] = bytes(a & 0xFF for a in range(lo, hi))
    m.mem[b] = 0x37  # RTN
    _until(m, b + 0x10)
    seen = {a: m.mem[a] for lo, hi in ranges + _states(w) for a in range(lo, hi)}
    m.mem[b + 0x10] = 0x37
    m.run(CLOCK)
    return seen


def _hidden(w: workarea.Layout, seen: dict[int, int]) -> set[int]:
    """比べない番地: 文字列の値の前の4バイト(ROMの中の受け渡しで残った値)"""
    out = set()
    for at in [w.copy, *range(w.values, w.values + 8 * w.values_size, 8)]:
        if seen.get(at + 4) == workarea.STRING:
            out |= set(range(at, at + 4))
    return out


STATEMENTS = [
    "A=1+2*(3+4)", 'A$="AB"+"C"', "B$=STR$ (-1/7)", "B$=STR$ 12", "B$=STR$ (1[E]20)",
    "A=-SIN 30", 'A$=MID$("ABCD",1+1,2)', "CLEAR:DIM C(2,2):A=C(1,1+1)", "A=2*-3",
    'A=LEN "ABC"+1', 'B$="XY":A$=B$+"C"', "A=1<2", "A=ABS (2-3)", 'A$=LEFT$("ABC",2)+"D"',
    "FOR I=1 TO 3", "FOR I=2 TO 300 STEP 5:FOR J=-1 TO 2", "FOR I=1 TO 2:FOR J=1 TO 2:NEXT J",
    "GOSUB 20:END\n20 CALL &%X:RETURN", "READ A,B,C:CALL &%X:END\n30 DATA 1,2\n40 DATA 3",
    "RESTORE 30:CALL &%X:END\n30 DATA 1,2", 'USING "###.##"', 'USING "&&&"', "A=RND 10",
]  # fmt: skip
# PRINT・PAUSE(PC-1251系だけ。PC-1261系とPC-1350は代入の写しの場所に置く値の決まりが違う)
PRINTS = ['WAIT 0:PRINT 12', 'WAIT 0:PRINT "AB";3', 'WAIT 0:PRINT 1,"X"', 'WAIT 0:PRINT "X",1',
          'WAIT 0:PAUSE -4', 'WAIT 0:PRINT "A";"BC";"D"']  # fmt: skip


@pytest.mark.parametrize("model", ["1251", "1245", "1261", "1350"])
def test_work_area_matches_rom(model, monkeypatch):
    """文を実行したあと(次のCALLの入口)の作業領域が、ROMのある本体と同じ"""
    if not HAVE[model]:
        pytest.skip("ROMがない")
    monkeypatch.setattr(helpers, "MODEL", model)
    w = LAYOUT[model]
    bad = []
    for stmt in STATEMENTS + (PRINTS if model in ("1251", "1245") else []):
        rom, hle = boot(model)[0], basic_machine(model)
        a, b = at_call(rom, model, stmt), at_call(hle, model, stmt)
        skip = _hidden(w, a)
        if stmt in PRINTS:  # PRINTのあとの液晶RAMは出した字(字の形はROMと違う)
            skip |= {x for lo, hi in rom.model.lcd for x in range(lo, hi)}
        diff = [x for x in a if a[x] != b[x] and x not in skip]
        if diff:
            bad.append(f"{stmt}: " + " ".join(f"{x:04X}:{a[x]:02X}/{b[x]:02X}" for x in diff))
    assert not bad, "\n".join(bad)


def test_pc1251_stacks_without_rom(monkeypatch):
    """PC-1251: 演算子はF800h〜、待たせている値はF840h〜に8バイトずつ積む(ROMのある本体で
    観察した形)"""
    monkeypatch.setattr(helpers, "MODEL", "1251")
    m = basic_machine("1251")
    seen = at_call(m, "1251", "A=1+2*(3+4)")
    assert [seen[a] for a in range(0xF800, 0xF804)] == [0x35, 0x37, 0x30, 0x35]
    assert bytes(seen[a] for a in range(0xF840, 0xF858)) == bytes.fromhex(
        "000010000000000000002000000000000000300000000000"
    )
    assert seen[0xC6F6] == 0 and seen[0xC6F5] == 0x40  # 下ろしたあと
    assert [seen[a] for a in range(0xC6EB, 0xC6EE)] == [0x97, 0xC6, 0x88]  # Aの番地−1、数
    assert [seen[a] for a in (0xC6DC, 0xC6DD)] == [0xC2, 0x10]  # 2つ目のCALLの番地
    seen = at_call(m, "1251", 'A$="AB"+"C"')
    assert bytes(seen[a] for a in range(0xF844, 0xF848)) == bytes([0xD0, 0x60, 0xC7, 2])
    assert bytes(seen[a] for a in range(0xC760, 0xC763)) == bytes([0x51, 0x52, 0x53])
    assert bytes(seen[a] for a in range(0xC6CA, 0xC6CE)) == bytes([0xD0, 0x60, 0xC7, 3])
    assert seen[0xC6F7] == 0x60  # 文の終わりで作業場所を空にする


def test_pc1251_str_leaves_text(monkeypatch):
    """PC-1251: STR$のあと、F810h〜F81Bhに字を並べた跡、F820h〜にSTR$の字が残る"""
    monkeypatch.setattr(helpers, "MODEL", "1251")
    seen = at_call(basic_machine("1251"), "1251", "B$=STR$ (-1/7)")
    # 「-1.428571428E-01」の小数点の後ろの字(F80Fhから)のうち、F810h〜
    work = bytes(seen[a] for a in range(0xF810, 0xF81C))
    assert work == bytes.fromhex("42 48 45 47 41 44 42 48 4B 36 40 41")
    text = bytes(seen[a] for a in range(0xF820, 0xF838))
    assert text == bytes.fromhex("36 41 4A 44 42 48 45 47 41 44 42 48 4B 36 40 41") + b"\xff" * 8


@pytest.mark.parametrize(
    "line",
    ["A=((((((((((((((((((((1))))))))))))))))))))", "A=1+(2+(3+(4+(5+(6+(7+(8+(9+1))))))))"],
)
def test_too_deep_is_error_5(line, monkeypatch):
    """演算子を16より多く、値を8より多く待たせるとERROR 5(観察)"""
    monkeypatch.setattr(helpers, "MODEL", "1251")
    m = basic_machine("1251")
    t = Typer(m)
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK)
    t.add_text(line + "\n")
    finish(m, t)
    m.run(CLOCK // 2)
    from basic_diff import lcd

    assert lcd(m).split() == ["ERROR", "5"]


DEEP = [
    "A=1+(2+(3+(4+(5+(6+(7+(8+(9+1))))))))", "A=1+2*(3+4*(5+6*(7+8*(9+1))))",
    "((((((((((((((((2*3)))))))))))))))):B=2", "((((((((((((((((-1))))))))))))))))",
    "((((((((((((((((SIN 1))))))))))))))))", "(((((((((((((((((1)))))))))))))))))",
    "((((((((((((((((A(1)))))))))))))))))",
]  # fmt: skip


@pytest.mark.parametrize("model", ["1251", "1245"])
def test_too_deep_matches_rom(model, monkeypatch):
    """積みきれないときのエラーの番号と位置(←で呼び出したときのカーソル)が、ROMのある本体と
    同じ"""
    if not HAVE[model]:
        pytest.skip("ROMがない")
    from basic_diff import differences, play

    monkeypatch.setattr(helpers, "MODEL", model)
    steps: list[tuple[str, object]] = [("mode", "RUN"), ("wait", 1.5)]
    for line in DEEP:
        steps += [("keys", ["CL"]), ("type", line + "\n"), ("wait", 0.3), ("look", None),
                  ("keys", ["LEFT"]), ("look", None)]  # fmt: skip
    assert not differences(play(boot(model)[0], steps), play(basic_machine(model), steps))


def test_full_operators_then_binary_is_error_1(monkeypatch):
    """演算子が16段積んであり、値に空きがあるところへ2項の演算子が来るとERROR 1(観察)"""
    monkeypatch.setattr(helpers, "MODEL", "1251")
    m = basic_machine("1251")
    t = Typer(m)
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK)
    t.add_text(DEEP[2] + "\n")
    finish(m, t)
    m.run(CLOCK // 2)
    from basic_diff import lcd

    assert lcd(m).split() == ["ERROR", "1"]


def test_entry_of_value():
    """積む値の8バイト: 数は変数と同じ形、文字列は印と番地と長さ"""
    assert workarea.entry(Decimal("-1")) == bytes.fromhex("0008100000000000")
    s = workarea.Text(b"AB")
    s.at = 0xC761
    assert workarea.entry(s) == bytes([0, 0, 0, 0, 0xD0, 0x61, 0xC7, 2])


@pytest.mark.parametrize("model", ["1251", "1245", "1261", "1350"])
def test_random_matches_rom(model, monkeypatch):
    """RNDの種(最初のRNDの前のRAMも)と答えの並びが、電源を入れた直後から、負の数で種を決めた
    あとも、ROMのある本体と同じ"""
    if not HAVE[model]:
        pytest.skip("ROMがない")
    from sc61box import number

    monkeypatch.setattr(helpers, "MODEL", model)
    xs = ["100", "100", "0.5", "-7", "1000", "6", "-0.25", "6"]
    var = {"1251": 0xC698, "1245": 0xC698, "1261": 0x65C8, "1350": 0x6CF8}[model]  # A
    seen = []
    for m in (boot(model)[0], basic_machine(model)):
        at = number._seed_place(m)[0]
        t = Typer(m)
        t.add_mode("RUN")
        finish(m, t)
        m.run(CLOCK)
        seq: list[object] = [bytes(m.mem[at : at + 8])]
        for x in xs:
            t.add_text(f"A=RND {x}\n")
            finish(m, t)
            m.run(CLOCK // 2)
            seq.append((x, number_of(m, var), bytes(m.mem[at : at + 8])))
        seen.append(seq)
    assert seen[0] == seen[1]


@pytest.mark.parametrize("model", ["1251", "1261", "1350"])
def test_small_seeds_match_rom(model, monkeypatch):
    """種が0のときや小さいとき(指数が−1より小さいとき)も、RNDの答えと次の種がROMのある本体と
    同じ"""
    if not HAVE[model]:
        pytest.skip("ROMがない")
    from sc61box import number

    monkeypatch.setattr(helpers, "MODEL", model)
    var = {"1251": 0xC698, "1261": 0x65C8, "1350": 0x6CF8}[model]  # A
    starts = ["0000000000000000", "9970123456789012", "9890987654321098"]
    seen = []
    for m in (boot(model)[0], basic_machine(model)):
        at = number._seed_place(m)[0]
        t = Typer(m)
        t.add_mode("RUN")
        finish(m, t)
        m.run(CLOCK)
        seq = []
        for start in starts:
            m.mem[at : at + 8] = bytes.fromhex(start)
            for x in ("10", "0.5", "7.5", "100", "0.5", "6"):
                t.add_text(f"A=RND {x}\n")
                finish(m, t)
                m.run(CLOCK // 4)
                seq.append((start, x, number_of(m, var), bytes(m.mem[at : at + 8])))
        seen.append(seq)
    assert seen[0] == seen[1]


@pytest.mark.parametrize("model", ["1251", "1245", "1261", "1350"])
def test_seed_set_at_power_on(model, monkeypatch):
    """電源を入れると、最初のRNDの前から種がRAMにある。RNDで進めても、電源を入れ直すと戻る
    (観察)"""
    from sc61box import number

    monkeypatch.setattr(helpers, "MODEL", model)
    m = basic_machine(model)
    at, init = number._seed_place(m)
    t = Typer(m)
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK)
    assert bytes(m.mem[at : at + 8]) == init
    t.add_text("A=RND 10\n")
    finish(m, t)
    m.run(CLOCK // 2)
    assert bytes(m.mem[at : at + 8]) != init
    m.mode = "OFF"
    m.run(CLOCK)
    m.mode = "RUN"
    m.wake()
    m.run(CLOCK)
    assert bytes(m.mem[at : at + 8]) == init


def test_bench_machine_has_seed():
    """BASICのないROMなしの本体も、作ったときから電源を入れたときの種がある(FRNDが使う)"""
    from sc61box.app import open_machine

    m, norom = open_machine("1251", norom=True, basic=False)
    assert norom and m.basic is None
    assert bytes(m.mem[0xF8B0:0xF8B8]) == bytes.fromhex("0000314159265359")


@pytest.mark.parametrize(
    ("model", "var", "want"),
    [("1251", 0xC698, "0.1"), ("1261", 0x65C8, "0.9921411586"), ("1350", 0x6CF8, "0.9921411586")],
)
def test_negative_random_without_rom(model, var, want, monkeypatch):
    """電源を入れた直後のA=RND −7の答え(ROMのある本体で観察した値)"""
    monkeypatch.setattr(helpers, "MODEL", model)
    m = basic_machine(model)
    t = Typer(m)
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK)
    t.add_text("A=RND -7\n")
    finish(m, t)
    m.run(CLOCK // 2)
    assert number_of(m, var) == Decimal(want)


def test_random_sequence_without_rom(monkeypatch):
    """PC-1251: 電源を入れた直後のRND 10は3、2、4(ROMのある本体で観察した並び)"""
    monkeypatch.setattr(helpers, "MODEL", "1251")
    m = basic_machine("1251")
    t = Typer(m)
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK)
    values = []
    for _ in range(3):
        t.add_text("A=RND 10\n")
        finish(m, t)
        m.run(CLOCK // 2)
        values.append(int(number_of(m, 0xC698)))
    assert values == [3, 2, 4]
    assert bytes(m.mem[0xF8B0:0xF8B8]) == bytes.fromhex("9994375781619731")


def number_of(m, at: int) -> Decimal:
    from sc61box.number import get_num

    return get_num(m.mem, at)


@pytest.mark.parametrize("model", ["1251", "1245"])
def test_sample_stack_shows_work_area(model, monkeypatch):
    """見本stack.bas: 表示をオンにしたまま式を計算すると、液晶RAMに積んだ演算子と値が見える。
    止まったときの点の並びは、ROMのある本体で観察したものと同じ"""
    from sc61box import programs

    monkeypatch.setattr(helpers, "MODEL", model)
    prog = programs.find("stack", model)
    assert prog is not None and not prog.errors and prog.runs_on(model)
    m = basic_machine(model)
    t = Typer(m)
    t.add_mode("PRO")
    finish(m, t)
    m.run(CLOCK)
    t.add_text(prog.basic)
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK)
    t.add_text("RUN\n")
    finish(m, t)
    m.run(CLOCK * 20)
    assert m.display_on()
    # 演算子: +と(を交互に、最後に/
    assert bytes(m.mem[0xF800:0xF80C]) == bytes.fromhex("35 30 35 30 35 30 35 30 35 30 35 38")
    # 待たせている値: I/7、2*I/7、…、6*I/7(Iは30)と、I/7のI
    values = bytes.fromhex(
        "0000428571428571" "0000857142857142" "0010128571428571" "0010171428571428"
        "0010214285714285" "0010257142857142" "0010300000000000"
    )  # fmt: skip
    assert bytes(m.mem[0xF840:0xF878]) == values


def _stack_running(model: str = "1251"):
    from sc61box import programs

    prog = programs.find("stack", model)
    assert prog is not None
    m = basic_machine(model)
    t = Typer(m)
    t.add_mode("PRO")
    finish(m, t)
    m.run(CLOCK)
    t.add_text(prog.basic)
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK)
    t.add_text("RUN\n")
    finish(m, t)
    m.run(CLOCK * 3)
    return m


def test_work_area_changes_during_statement(monkeypatch):
    """文の時間のあいだに、積んだ演算子と値が少しずつ変わって見える(ROMのある本体では、2秒の
    あいだに液晶RAMの作業領域が65回変わった。文の終わりに一度に変わるのではない)"""
    monkeypatch.setattr(helpers, "MODEL", "1251")
    m = _stack_running()
    prev, changes = None, 0
    for _ in range(400):  # 2秒を5msごとに見る
        m.run(CLOCK // 200)
        cur = bytes(m.mem[0xF800:0xF880])
        changes += prev is not None and cur != prev
        prev = cur
    assert changes >= 40


def test_snapshot_settles_work_area(monkeypatch):
    """書き戻しの途中で状態を保存すると、文が終わったときの作業領域を保存する"""
    import base64

    monkeypatch.setattr(helpers, "MODEL", "1251")
    m = _stack_running()
    for _ in range(200):
        m.run(CLOCK // 500)
        assert m.basic is not None
        tl = m.basic.runner.timeline
        if tl is not None and tl.pending:
            break
    else:
        raise AssertionError("書き戻しの途中にならない")
    after = list(tl.after)
    mem = base64.b64decode(m.snapshot()["mem"])
    assert all(mem[lo : lo + len(data)] == data for lo, data in after)
    assert m.basic.runner.timeline is None


def _stack_states(m, model: str) -> set:
    """式を計算しているあいだに1msごとに見た、積んだ数・値のポインタと、積んである演算子と
    値の組"""
    w = LAYOUT[model]
    assert w.ops_count is not None and w.values_top is not None
    t = Typer(m)
    t.add_mode("PRO")
    finish(m, t)
    m.run(CLOCK)
    t.add_text("NEW\n10 I=30\n20 A=I/7+(2*I/7+(3*I/7+(4*I/7+(5*I/7+(6*I/7+I/7)))))\n30 GOTO 20\n")
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK)
    t.add_text("RUN\n")
    finish(m, t)
    m.run(CLOCK * 2)
    states = set()
    for _ in range(1500):
        m.run(CLOCK // 1000)
        ops = m.mem[w.ops_count] - (w.ops & 0xFF)
        top = m.mem[w.values_top]
        values = bytes(m.mem[w.values : w.values & 0xFF00 | top])
        states.add((ops, top, bytes(m.mem[w.ops : w.ops + ops]), values))
    return states


@pytest.mark.parametrize("model", ["1251", "1261"])
def test_stack_counts_follow_data(model, monkeypatch):
    """文の時間のあいだに書き戻すとき、積んだ数と値のポインタも積んだものと同じ時に変わる。
    見えるどの形も、ROMのある本体で見えた形のどれかと同じ"""
    monkeypatch.setattr(helpers, "MODEL", model)
    states = _stack_states(basic_machine(model), model)
    assert len(states) >= 10
    w = LAYOUT[model]
    assert max(s[1] for s in states) == w.values + 8 * 6 & 0xFF  # 6つの値を待たせる
    if HAVE[model]:
        assert states <= _stack_states(boot(model)[0], model)


def test_machine_freed_while_replaying(monkeypatch):
    """書き戻しの途中の本体も、参照を捨てれば回収される"""
    import gc
    import weakref

    monkeypatch.setattr(helpers, "MODEL", "1251")
    m = _stack_running()
    for _ in range(200):
        m.run(CLOCK // 500)
        assert m.basic is not None
        tl = m.basic.runner.timeline
        if tl is not None and tl.pending:
            break
    else:
        raise AssertionError("書き戻しの途中にならない")
    ref = weakref.ref(m)
    del m, tl
    gc.collect()
    assert ref() is None


def _sample_lcd(m, name: str, seconds: int) -> bytes:
    from sc61box import programs

    prog = programs.find(name, "1251")
    assert prog is not None and not prog.errors
    t = Typer(m)
    t.add_mode("PRO")
    finish(m, t)
    m.run(CLOCK)
    t.add_text("NEW\n" + prog.basic)
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK)
    t.add_text("RUN\n")
    finish(m, t)
    m.run(CLOCK * seconds)
    assert m.display_on()
    return bytes(m.mem[0xF800:0xF880])


@pytest.mark.parametrize(("name", "seconds"), [("mix", 20), ("func", 18)])
def test_sample_matches_rom(name, seconds, monkeypatch):
    """見本mix.bas・func.bas: 止まったときの液晶RAMが、ROMのある本体と同じ"""
    monkeypatch.setattr(helpers, "MODEL", "1251")
    hle = _sample_lcd(basic_machine("1251"), name, seconds)
    assert any(hle[:0x10]) and any(hle[0x40:])  # 演算子と値を積んだ跡がある
    if HAVE["1251"]:
        assert hle == _sample_lcd(boot("1251")[0], name, seconds)

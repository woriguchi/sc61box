"""ROMなしのPC-1260/1261/1262で、代替ROMルーチン(norom1261.ROUTINES)と文字の形の表が、
ROMのある本体と同じに働くか"""

import pytest
from basic_diff import basic_machine
from conftest import HAVE_ROM_1260
from helpers import boot, finish

from sc61box import charset, norom, norom1261, romsyms, routinecheck, routines
from sc61box.autotype import Typer
from sc61box.machine import CLOCK, new_machine

A = routines.symbols("1261")
RET = 0x5000  # 呼ぶときに積む戻り番地


def _call(m, addr: int, limit: int = CLOCK * 3, ratio: tuple[int, int] = (1, 1)) -> int:
    """戻り番地RETを積んでaddrを呼び、戻るまでのCPUのサイクル数を返す。ROMのある本体はROMを
    動かし、ROMなしの本体はnorom.callで代替ROMルーチンを動かす。ratioは、CPUのサイクルを時刻に
    直す比(本当の速さは3/4)"""
    cpu = m.cpu
    cpu.ratio = ratio
    cpu.r = 0x5C
    cpu.push(RET >> 8)
    cpu.push(RET & 0xFF)
    cpu.pc = addr
    m.halted = False
    c0 = cpu.cycles
    try:
        while cpu.pc != RET:
            if m.norom:
                assert routines.call(m, cpu.pc)
            else:
                guard = bytearray(0x10000)
                guard[RET] = 1
                m.run(64, guard)
                if not m.power:  # 電源を切った
                    break
            assert cpu.cycles - c0 < limit, f"{addr:04X}から戻らない"
    finally:
        cpu.ratio = (3, 4)
    return cpu.cycles - c0


def _hle():
    m = new_machine("1261", rom=False)
    norom.install(m)
    return m


def test_routines_listed_for_pc1261_only():
    """入口の表はPC-1260/1261/1262の名前で引け、ROMなしのPC-1261がこの表の代替ROMルーチンを使う"""
    assert set(norom1261.ROUTINES) == set(romsyms.ROUTINES_1261)
    table = routines.for_machine(_hle())
    assert {r.addr for r in table.values()} == set(romsyms.ROUTINES_1261.values())
    assert all(r.family == "1261" and r.builtin for r in table.values())
    m = _hle()
    m.norom = False  # ROMのある本体では使わない
    assert not routines.for_machine(m)
    assert A["INKEY"] == 0x1138 and routines.symbols("1262") == A


def test_glyph_table_is_drawn():
    """BASIC ROMの番地に置く字の形は、エミュレータで描いた形(右の列が先)。空白は8045h"""
    from sc61box.basic.pc1261 import font

    m = _hle()
    assert bytes(m.mem[0x8045:0x804A]) == bytes(5)
    assert bytes(m.mem[0x80EA:0x80EF]) == bytes(reversed(charset.glyph("A")))
    at = norom1261.FONT_TOP + 5 * (0xB1 - 0x45)
    assert bytes(m.mem[at : at + 5]) == bytes(reversed(norom1261.glyph(0xB1)))
    at = norom1261.FONT_TOP + 5 * (0xF1 - 0x55)
    assert bytes(m.mem[at : at + 5]) == bytes(reversed(norom1261.glyph(0xF1)))
    assert norom1261.glyph(0xB1) == font.glyph("ｱ") and norom1261.glyph(0xF1) == font.glyph("年")


def test_copy_and_glyph_without_rom():
    """COPYBはX+1からBバイトをY+1からへ写し、GLYPHは形の終わりの次の番地をXに入れる"""
    m = _hle()
    ram = m.cpu.ram
    m.mem[0x6001:0x6004] = b"ABC"
    ram[1], ram[3] = 1, 3
    ram[4:8] = bytes([0x00, 0x60, 0x00, 0x61])
    _call(m, A["COPYB"])
    assert bytes(m.mem[0x6101:0x6104]) == b"ABC" and ram[4:8] == bytes([0x03, 0x60, 0x03, 0x61])
    ram[2] = 0x41
    _call(m, A["GLYPH"])
    assert ram[4] | ram[5] << 8 == 0x80EF


@pytest.fixture(scope="module")
def pair():
    """(ROMのある本体, ROMなしの本体)。routinecheckが比べるときと同じもの"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    return routinecheck.machines("1261")


def _wait2ms(m, t2: int, flag: int, frac: int) -> tuple[int, int, int, int]:
    """本当の速さで、タイマを刻みのt2、刻みの印をflag、時刻の端数をfracにしてWAIT2MSを呼ぶ。
    (サイクル数, 戻ったときのt2, 印, 端数)"""
    m.cpu.ram[1] = 1
    m.t2, m.t2ms, m.cpu._frac = t2, flag, frac
    cycles = _call(m, A["WAIT2MS"], ratio=(3, 4))
    return cycles, m.t2, m.t2ms, m.cpu._frac


def test_wait2ms_counts_time_fraction():
    """WAIT2MSは、時刻の端数のぶん早く刻みに届く(刻みの11番目で印がなく、端数が1なら766
    サイクル。ROMのある本体で確かめた値)"""
    assert _wait2ms(_hle(), 11, 0, 1)[0] == 766
    assert _wait2ms(_hle(), 11, 0, 0)[0] == 774


def test_wait2ms_like_rom_at_real_speed(pair):
    """本当の速さ(CPUのサイクルの3/4が時刻)で、刻みのどこで呼んでも、印と時刻の端数がどうでも、
    WAIT2MSが戻るまでのサイクル数とタイマが、ROMのある本体と同じ(routinecheckは速さを1/1にして
    比べるので、ここで比べる)"""
    from sc61box.machine import TICK_2MS

    rom, hle = pair
    for t2 in range(0, TICK_2MS, 3):
        for flag in (0, 1):
            for frac in range(4):
                got = _wait2ms(hle, t2, flag, frac)
                assert got == _wait2ms(rom, t2, flag, frac), (t2, flag, frac)


@pytest.mark.parametrize("name", [n for n in romsyms.ROUTINES_1261 if n != "INKEY"])
def test_routine_like_rom(pair, name):
    """値を与えて呼ぶと、内部RAM、フラグ、P・Q・DP、ポート、メモリと、かかったサイクル数が、
    ROMのある本体と同じ(routinecheck)"""
    rom, hle = pair
    r = routines.by_name("1261", name)
    assert r is not None
    report = routinecheck.check_routine(rom, hle, r, trials=30)
    assert report.ok, routinecheck.report_text([report])


def _inkey_rom_and_hle(presses):
    """FENSCERのようにINKEYを呼び、presses(秒, 押すキーの組)の順にキーを押す。ROMのある本体と
    ROMなしの本体の(戻ったか, A, B, 203Dh, 戻るまでの秒)"""
    out = []
    for rom in (True, False):
        m = boot("1261")[0] if rom else _hle()
        if rom:
            m.mode = "RUN"
            m.run(CLOCK)
        m.mem[0x66E8], m.mem[0x66E9], m.mem[0x662B] = 0x46, 0x85, 0x17
        cpu = m.cpu
        cpu.ram[1] = 1
        cpu.r = 0x5C
        cpu.push(RET >> 8)
        cpu.push(RET & 0xFF)
        cpu.pc = A["INKEY"]
        m.halted = False
        c0, i = cpu.cycles, 0
        guard = bytearray(0x10000)
        guard[RET] = 1
        while cpu.pc != RET and cpu.cycles - c0 < CLOCK * 2:
            t = (cpu.cycles - c0) / CLOCK
            while i < len(presses) and t >= presses[i][0]:
                m.held.clear()
                m.held.update(presses[i][1])
                i += 1
            if m.norom:
                routines.call(m, cpu.pc)
            else:
                m.run(64, guard)
        done = cpu.pc == RET
        out.append((done, cpu.ram[2], cpu.ram[3], m.mem[0x203D], (cpu.cycles - c0) / CLOCK))
    return out


@pytest.mark.parametrize(
    "presses",
    [
        [(0.2, {"A"}), (0.3, set())],
        [(0.2, {"SHIFT"}), (0.25, set()), (0.4, {"Z"}), (0.5, set())],
        [(0.2, {"DEF"}), (0.25, set()), (0.4, {"5"}), (0.5, set())],
        [(0.2, {"4", "A"}), (0.3, {"4"}), (0.5, set()), (0.7, {"6"}), (0.8, set())],
        [(0.2, {"A"}), (0.2005, {"A", "B"}), (0.4, set()), (0.6, {"ENTER"}), (0.7, set())],
        [(0.2, {"SHIFT"}), (0.25, set()), (0.3, {"8"}), (0.35, set()), (0.6, {"Q"}), (0.7, set())],
    ],
)
def test_inkey_like_rom(presses):
    """INKEYは、すべてのキーを離したあとに1つだけ押したキーを受け付け、SHIFT・DEF・カナで字を
    変える。返す字と記号、戻るまでの時間がROMのある本体と同じ(時間は3ms以内)"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    rom, hle = _inkey_rom_and_hle(presses)
    assert rom[:4] == hle[:4]
    assert abs(rom[4] - hle[4]) < 0.003


def _entry(m, typed: str, lines=()) -> tuple[int, bytes, int]:
    """打ったCALLで呼ばれたマシン語の頭の(X, 67B0hからの16バイト, R)"""
    m.mem[0x5000] = 0x37  # RTN
    t = Typer(m)
    t.add_mode("PRO")
    finish(m, t)
    m.run(CLOCK * 3 // 2)
    for line in ("NEW", *lines):
        t.add_text(line + "\n")
        finish(m, t)
        m.run(CLOCK // 3)
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK * 3 // 2)
    t.add_text(typed + "\n")
    guard = bytearray(0x10000)
    guard[0x5000] = 1
    for _ in range(20000):
        if t.busy:
            t.step()
        if m.run(256, guard):
            break
    cpu = m.cpu
    assert cpu.pc == 0x5000
    return cpu.ram[4] | cpu.ram[5] << 8, bytes(m.mem[0x67B0:0x67C0]), cpu.r


@pytest.mark.parametrize(
    ("typed", "lines"), [("CALL &5000,P", ()), ("CALL 20480", ()), ("RUN", ("10 CALL &5000,XY",))]
)
def test_call_puts_line_position_in_x(typed, lines):
    """CALLで呼んだ先の頭では、Xが行の中の番地の最後のバイトを指す。打った行は中間コードにして
    67B0hに置き、あとを0Dhで埋める。Rは56h"""
    m = basic_machine("1261")
    x, typed_line, r = _entry(m, typed, lines)
    assert r == 0x56
    if lines:
        assert m.mem[x - 4 : x + 3] == b"&5000,X"
    else:
        assert x == 0x67B5 and typed_line == (b"\xcc" + typed[5:].encode()).ljust(16, b"\r")
    if HAVE_ROM_1260:
        rom_x, rom_line, rom_r = _entry(boot("1261")[0], typed, lines)
        assert (rom_x, rom_r) == (x, r) and (lines or rom_line == typed_line)


def test_call_runs_in_extended_ram():
    """# ram:で広げたRAMのマシン語も、ROMなしのBASICのCALLで動く"""
    m = basic_machine("1261")
    m.set_ram_top(0x8000)
    m.mem[0x7000:0x7007] = bytes([0x10, 0x60, 0x00, 0x02, 0x5A, 0x52, 0x37])  # DP←6000, A←5A
    t = Typer(m)
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK * 3 // 2)
    t.add_text("CALL &7000\n")
    finish(m, t)
    m.run(CLOCK)
    assert m.basic is not None and m.basic.notice is None and m.mem[0x6000] == 0x5A


def test_app_runs_code_in_extended_ram():
    """作業欄を出したアプリでも、# ram:で広げたRAMのマシン語をCALLで動かせる(作業欄が
    RAMの外として止めない)"""
    from helpers import make_app

    app = make_app(model="1261", frames=3, norom=True)
    m = app.m
    m.set_ram_top(0x8000)
    m.mem[0x7000:0x7007] = bytes([0x10, 0x60, 0x00, 0x02, 0x5A, 0x52, 0x37])  # DP←6000, A←5A
    app.typer.add_text("CALL &7000\n")
    for _ in range(300):
        app.frame()
    assert m.mem[0x6000] == 0x5A and app.bench.state != "pause"
    app.close()

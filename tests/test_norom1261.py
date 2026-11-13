"""ROMなしのPC-1260/1261/1262で、代替ROMルーチン(norom1261.ROUTINES)と文字の形の表が、
ROMのある本体と同じに働くか"""

import json
import os

import pytest
from basic_diff import basic_machine
from conftest import HAVE_ROM_1260
from helpers import boot, finish, make_app

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
    at = norom1261.FONT_TOP + 5 * (0x60 - 0x20)
    assert bytes(m.mem[at : at + 5]) == bytes(5)  # 60hは何も描かない(PC-1350では`の形)


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


def _wait2ms(
    m, t2: int, flag: int, frac: int, name: str = "WAIT2MS", z: int = 0
) -> tuple[int, int, int, int, int]:
    """本当の速さで、タイマを刻みのt2、刻みの印をflag、時刻の端数をfrac、Zをzにしてnameを呼ぶ。
    (サイクル数, 戻ったときのt2, 印, 端数, Z)"""
    m.cpu.ram[1] = 1
    m.cpu.z = z
    m.t2, m.t2ms, m.cpu._frac = t2, flag, frac
    cycles = _call(m, A[name], ratio=(3, 4))
    return cycles, m.t2, m.t2ms, m.cpu._frac, m.cpu.z


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


def test_wait2msz_like_rom_at_real_speed(pair):
    """WAIT2MSZも、本当の速さで刻みのどこで呼んでも、Zが0でも1でも、ROMのある本体と同じ
    (刻みの直前に呼ぶと、戻るまでに来た次の刻みの印が残る)"""
    from sc61box.machine import TICK_2MS

    rom, hle = pair
    for t2 in range(TICK_2MS):
        for flag in (0, 1):
            for z in (0, 1):
                frac = t2 % 4
                got = _wait2ms(hle, t2, flag, frac, "WAIT2MSZ", z)
                assert got == _wait2ms(rom, t2, flag, frac, "WAIT2MSZ", z), (t2, flag, z)


@pytest.mark.parametrize("name", [n for n in romsyms.ROUTINES_1261 if n not in ("INKEY", "CLOAD")])
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


def _inkey_held(m, held) -> int | None:
    """速さ1対1でINKEYを呼ぶ。held(入ってからのCPUのサイクル数)が押しているキー。戻るまでの
    サイクル数(2秒で戻らなければNone)"""
    cpu = m.cpu
    cpu.ram[1] = 1
    cpu.r = 0x5C
    cpu.push(RET >> 8)
    cpu.push(RET & 0xFF)
    cpu.pc = A["INKEY"]
    m.halted = False
    guard = bytearray(0x10000)
    guard[RET] = 1
    c0 = cpu.cycles
    while cpu.pc != RET and cpu.cycles - c0 < CLOCK * 2:
        m.held.clear()
        m.held.update(held(cpu.cycles - c0))
        if m.norom:
            routines.call(m, cpu.pc)
        else:
            m.run(16, guard)
    return cpu.cycles - c0 if cpu.pc == RET else None


def _repeat(rom: bool, key: str, count: int, release: int | None = None, then: str = ""):
    """FENSCERのように、keyを受け付けたあと662Eをcountにし、662Bのビット1を立てて、keyを押した
    ままもう一度INKEYを呼ぶ。releaseがあれば、そのサイクルで離し、2万サイクルのちにthenを押す。
    (戻るまでのサイクル数, I, A, B, Yの下位, キャリー, Z, 662E, 662B, 512msのタイマの印)"""
    m = boot("1261")[0] if rom else _hle()
    if rom:
        m.mode = "RUN"
        m.run(CLOCK)
    m.cpu.ratio = (1, 1)
    m.mem[0x66E8], m.mem[0x66E9], m.mem[0x662B] = 0x46, 0x85, 0x17
    _inkey_held(m, lambda t: {key} if t > 20000 else set())
    assert not m.mem[0x662B] & 0x02  # 受け付けると662Bのビット1を消す
    m.mem[0x662E], m.mem[0x662F] = count & 0xFF, count >> 8
    m.mem[0x662B] |= 0x17
    if release is None:
        n = _inkey_held(m, lambda t: {key})
    else:
        n = _inkey_held(
            m, lambda t: {key} if t < release else {then} if t > release + 20000 else set()
        )
    cpu = m.cpu
    return (n, cpu.ram[0], cpu.ram[2], cpu.ram[3], cpu.ram[6], cpu.c, cpu.z,
            m.mem[0x662E] | m.mem[0x662F] << 8, m.mem[0x662B], m.t512)  # fmt: skip


def test_inkey_repeats_held_key():
    """前に返したキーを押したまま呼ぶと、662Eの数が0になるまで、決まった間隔で1を足し、0なら
    662EをFFFEにして同じ字を返す(FENSCERは0.5秒ほど待ってから繰り返す)"""
    got = _repeat(False, "RIGHT", 0xFFCE)
    line = norom1261.KEY_NUMBERS["RIGHT"][1]
    cycles = norom1261.REPEAT_FIRST + 38 * line + 1 + 50 * (norom1261.REPEAT_EVERY + 38 * line)
    assert got[:8] == (cycles, 0xFB, 0x0E, 0, 0x0E, 0, 1, 0xFFFE)


@pytest.mark.parametrize("key", ["RIGHT", "1", "A", "SPC", "Z"])
@pytest.mark.parametrize("count", [0x0000, 0xFFFF, 0xFFFE, 0xFFF0, 0xFFCE])
def test_inkey_repeat_like_rom(key, count):
    """押し続けたキーの繰り返しで、戻るまでのサイクル数、レジスタ、662E・662B、512msのタイマの印
    (繰り返しを待つあいだは見ない)が、ROMのある本体と同じ"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    assert _repeat(True, key, count) == _repeat(False, key, count)


@pytest.mark.parametrize(("release", "then"), [(30000, "LEFT"), (30000, "RIGHT"), (60000, "A")])
def test_inkey_repeat_stops_when_released_like_rom(release, then):
    """繰り返しを待つ途中で離すと、すべて離したあとのキーを受け付ける待ちに戻る。返す字と、
    数えた662Eの値がROMのある本体と同じ(時間は1%以内)"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    rom = _repeat(True, "RIGHT", 0xFFCE, release, then)
    hle = _repeat(False, "RIGHT", 0xFFCE, release, then)
    assert (rom[2], rom[3], rom[7]) == (hle[2], hle[3], hle[7])
    assert rom[0] is not None and hle[0] is not None
    assert abs(rom[0] - hle[0]) <= rom[0] // 100


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


def _start_inkey(m) -> None:
    cpu = m.cpu
    cpu.ram[1] = 1
    cpu.r = 0x5C
    cpu.push(RET >> 8)
    cpu.push(RET & 0xFF)
    cpu.pc = A["INKEY"]
    m.halted = False


def _run_inkey(m, cycles: int, held) -> bool:
    """INKEYをcyclesだけ動かす(held(経過サイクル)が押しているキー)。戻ったらTrue"""
    cpu = m.cpu
    c0 = cpu.cycles
    while cpu.pc != RET and cpu.cycles - c0 < cycles:
        m.held.clear()
        m.held.update(held(cpu.cycles - c0))
        routines.call(m, cpu.pc)
    return cpu.pc == RET


def test_inkey_wait_survives_restore():
    """繰り返しを待つINKEYの様子は本体の状態と一緒に保存し、戻す。保存してから先へ進めて戻したあと
    に短く押したキーを受け付ける(待ちの様子が先へ進んだままだと、取りこぼす)"""
    m = _hle()
    m.cpu.ratio = (1, 1)
    m.mem[0x66E8], m.mem[0x66E9], m.mem[0x662B] = 0x46, 0x85, 0x17
    _inkey_held(m, lambda t: {"RIGHT"} if t > 20000 else set())
    m.mem[0x662E], m.mem[0x662F] = 0xCE, 0xFF
    m.mem[0x662B] |= 0x17
    _start_inkey(m)
    assert not _run_inkey(m, 30000, lambda t: {"RIGHT"})
    state = m.snapshot()
    assert "1261" in state["waits"]
    assert not _run_inkey(m, 60000, lambda t: {"RIGHT"})
    m.restore(state)
    assert _run_inkey(m, CLOCK, lambda t: {"A"} if 20000 < t < 30000 else set())
    assert m.cpu.ram[2] == 0x41


@pytest.mark.parametrize(
    ("key", "value"),
    [("pc", -1), ("r", 0x80), ("seen", "x"), ("armed", 1), ("key", "NOKEY"), ("repeat", 5),
     ("reset", -2), ("checks", None), ("sampled", "no"), ("extra", 0), ("repeat", []),
     ("key", {}), ("key", ["A"])],
)  # fmt: skip
def test_bad_inkey_wait_state_is_refused(key, value):
    """壊れた待ちの様子の状態は断り、いまの状態には手を付けない"""
    m = _hle()
    m.cpu.ratio = (1, 1)
    m.mem[0x66E8], m.mem[0x66E9], m.mem[0x662B] = 0x46, 0x85, 0x17
    _start_inkey(m)
    _run_inkey(m, 20000, lambda t: set())
    state = m.snapshot()
    state["waits"]["1261"][key] = value
    before = m.snapshot()
    with pytest.raises(ValueError):
        m.restore(state)
    assert m.snapshot() == before
    del state["waits"]  # 前の版の状態(待ちの様子がない)は読み、待ちを捨てる
    m.restore(state)
    assert norom1261.save_wait(m) is None


def test_app_names_broken_state_file(tmp_path):
    """壊れた状態ファイルを読むと、読み込めないことと、どのファイルかを出す"""
    app = make_app("1261", frames=5, norom=True)
    norom1261._inputs[app.m] = norom1261._Input(0x1138, 0x5A, app.m.cpu.cycles, repeat="A")
    path = str(tmp_path / "state.json")
    app.m.save_state(path)
    with open(path, encoding="utf-8") as f:
        state = json.load(f)
    state["waits"]["1261"]["repeat"] = []
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)
    app.load_state(path)
    from sc61box.app import _short  # ホームの下なら~で始める(Windowsの一時フォルダはホームの下)

    assert app.status == f"状態を読み込めません({_short(path)}): 状態ファイルが破損しています"


# ---- FENSCERの記録の読み込み(9695h) ----

FENSCER = os.path.join(os.path.dirname(__file__), "..", "programs", "private", "pc1261")
needs_fenscer = pytest.mark.skipif(
    not os.path.exists(os.path.join(FENSCER, "90FENSCER.hex")), reason="FENSCERのファイルがない"
)
CALL_SITE = {"90FENSCER": 0x5735, "90FENSCER-4000": 0x57C1}  # 探した番地を書くCALLの番地


def _fenscer(m, name: str = "90FENSCER") -> Typer:
    """FENSCERを書き込み、RUNモードで# run:の行(CALL &4000,)を打つ"""
    from sc61box import programs

    prog = programs.load_program(os.path.join(FENSCER, name + ".hex"))
    m.set_ram_top(prog.ram_top)
    for addr, data in prog.blocks:
        m.mem[addr : addr + len(data)] = data
    t = Typer(m)
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK * 3 // 2)
    t.add_text(prog.run + "\n")
    finish(m, t)
    return t


def _until(m, addrs, seconds: float, t: Typer | None = None) -> float | None:
    """CPUがaddrsのどれかの番地に来るまで動かす。来るまでの秒(来なければNone)。ROMなしの
    BASICのCALLの最中は、BASICの見張る番地(代替ROMルーチンの入口など)も見張って扱わせる"""
    c0 = m.cpu.cycles
    while m.cpu.cycles - c0 < seconds * CLOCK:
        guard = bytearray(0x10000) if m.basic is None else bytearray(m.basic.guard)
        for a in addrs:
            guard[a] = 1
        if t is not None and t.busy:
            t.step()
        if m.run(CLOCK // 200, guard):
            if m.cpu.pc in addrs:
                return (m.cpu.cycles - c0) / CLOCK
            assert m.basic is not None and m.basic.trapped(m.cpu.pc, True)
    return None


def _record_screen(m) -> None:
    """FENSCERを動かし、DEF+Zで抜けてCALL &4003(予約キーCの命令)で記録の画面を出す"""
    t = _fenscer(m)
    m.run(CLOCK * 4)
    m.held.update({"DEF", "Z"})
    assert _until(m, [0x58F0], 5) is not None  # 抜ける処理に入った
    m.held.clear()
    m.run(CLOCK * 5)
    t.add_keys([["CL"]])
    t.add_text("CALL &4003\n")
    assert _until(m, [0x5720], 20, t) is not None  # 記録の画面でキーを待つ
    finish(m, t)
    m.run(CLOCK // 2)


def _fenscer_cload(m, path: str) -> tuple[float | None, int]:
    """記録の画面でテープpathを入れ、ENTERでCLOADを選ぶ。FENSCERは`M"2";&5F00`(記録の画面に
    入るたびに番号を1つ進める)をX+1に置いて、探した番地を呼ぶ。(戻るまでの秒, キャリー)"""
    from sc61box import tape

    _record_screen(m)
    m.tape = tape.TapeIn(path)
    m.held.add("ENTER")
    assert _until(m, [0x5735], 3) is not None
    m.held.clear()
    assert bytes(m.mem[0x4283:0x428E]) == b'M"2";&5F00\r'
    took = _until(m, [0x5738], 20)
    return took, m.cpu.c


RECORD = bytes(range(0x50, 0x60))  # テープに録る記録


@pytest.fixture(scope="module")
def record_wav(tmp_path_factory):
    """ROMなしのBASICでCSAVE Mした、FENSCERの記録の形のテープ(名前は2、5F00h〜5F0Fh)"""
    from sc61box import tape

    m = basic_machine("1261")
    m.mem[0x5F00:0x5F10] = RECORD
    path = str(tmp_path_factory.mktemp("fenscer") / "record.wav")
    tape.write_wav(path, tape.record(m, 'CSAVE M "2";&5F00,&5F0F'))
    return path


@needs_fenscer
@pytest.mark.parametrize("name", ["90FENSCER", "90FENSCER-4000"])
def test_fenscer_finds_cload_without_rom(name):
    """FENSCERは起動したときに、自分の645Ch〜6466hと同じ11バイトをメモリから探し、見つけた番地を
    記録を読み込むCALLの飛び先にする。ROMなしでも、ROMのある本体と同じ9695hが見つかる(探す並びを
    9695hに置く)。探し終えるまでの時間もROMのある本体と同じく短い(前はメモリを一周して約3秒)"""
    m = basic_machine("1261")
    _fenscer(m, name)
    took = _until(m, [0x644A], 5)  # 探し終え、見つけた番地を書いた
    assert took is not None and took < 0.3
    at = CALL_SITE[name]
    assert m.mem[at + 1] << 8 | m.mem[at + 2] == 0x9695
    assert bytes(m.mem[0x9695:0x96A0]) == bytes(m.mem[0x645C:0x6467])
    if HAVE_ROM_1260:
        rom = boot("1261")[0]
        _fenscer(rom, name)
        rom_took = _until(rom, [0x644A], 5)
        assert rom_took is not None and abs(rom_took - took) < 0.05
        assert rom.mem[at + 1 : at + 3] == m.mem[at + 1 : at + 3]


@needs_fenscer
def test_fenscer_loads_record_without_rom(record_wav):
    """ROMなしで、FENSCERの記録の画面からCLOADを選ぶと、テープの記録を5F00hに読み込んで、
    キャリー0で戻る"""
    m = basic_machine("1261")
    took, carry = _fenscer_cload(m, record_wav)
    assert took is not None and abs(took - 10.77) < 0.1  # ROMのある本体は10.77秒
    assert carry == 0
    assert bytes(m.mem[0x5F00:0x5F10]) == RECORD
    assert m.basic is not None and m.basic.notice is None


@needs_fenscer
def test_fenscer_loads_record_in_app(record_wav):
    """作業欄の見張りを通るアプリでも、FENSCERの記録を読み込める(止まらずに続ける)"""
    from sc61box import programs, tape

    app = make_app(model="1261", frames=3, norom=True)
    m = app.m
    app.open_program(programs.load_program(os.path.join(FENSCER, "90FENSCER.hex")), run=True)

    def frames(seconds: float, until=lambda: False) -> None:
        c0 = m.cpu.cycles
        while m.cpu.cycles - c0 < seconds * CLOCK and not until():
            app.frame()

    frames(6)
    assert m.mem[0x5736] << 8 | m.mem[0x5737] == 0x9695
    for name in ("DEF", "Z"):
        app.typer.press_live(name)
    frames(2)
    for name in ("DEF", "Z"):
        app.typer.release_live(name)
    frames(5)
    app.typer.add_keys([["CL"]])
    app.typer.add_text("CALL &4003\n")
    frames(20, lambda: m.cpu.pc in (0x5720, 0x5722))  # 記録の画面でキーを待つ
    assert m.cpu.pc in (0x5720, 0x5722)
    m.tape = tape.TapeIn(record_wav)
    app.typer.press_live("ENTER")
    frames(0.5)
    app.typer.release_live("ENTER")
    frames(12)
    assert bytes(m.mem[0x5F00:0x5F10]) == RECORD
    assert app.bench.state != "pause" and not app.warning
    app.close()


@pytest.fixture(scope="module")
def rom_tapes(tmp_path_factory):
    """ROMのある本体でCSAVE Mしたテープ(名前は1)。16バイトと256バイト。badは256バイトで、
    初めの120バイトのチェックサムが合わないもの(ROMなしのBASICで録る)"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    from sc61box import tape
    from sc61box.basic.pc1261 import cassette

    d = tmp_path_factory.mktemp("cload")
    out = {}
    for name, size in (("small", 16), ("big", 256)):
        m, _t = boot("1261")
        m.mem[0x5F00 : 0x5F00 + size] = bytes(i * 7 + 3 & 0xFF for i in range(size))
        out[name] = str(d / f"{name}.wav")
        tape.write_wav(out[name], tape.record(m, f'CSAVE M "1";&5F00,&{0x5EFF + size:04X}'))
    blocks = cassette.blocks

    def broken(data: bytes) -> bytes:
        b = bytearray(blocks(data))
        b[3] ^= 0x55
        return bytes(b)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(cassette, "blocks", broken)
        m = basic_machine("1261")
        m.mem[0x5F00:0x6000] = bytes(i * 7 + 3 & 0xFF for i in range(256))
        out["bad"] = str(d / "bad.wav")
        tape.write_wav(out["bad"], tape.record(m, 'CSAVE M "1";&5F00,&5FFF'))
    return out


def _cload_entry(m, text: bytes, path: str | None, brk: float | None = None, limit: float = 16):
    """X+1(4283h)にtextと0Dhを置き、テープpathを入れて、9695hを呼ぶ。brk秒からBRKを0.3秒押す。
    液晶は先に全部の点を点けておく。(戻るまでの秒, モータを回した秒と止めた秒, 戻ったときの様子)"""
    from sc61box import tape

    cpu = m.cpu
    m.mem[0x4283 : 0x4284 + len(text)] = text + b"\r"
    m.tape = None if path is None else tape.TapeIn(path)
    for base in (0x2000, 0x2040, 0x2800, 0x2840):
        m.mem[base : base + 60] = bytes([0x7F]) * 60
    cpu.ram[4], cpu.ram[5], cpu.ram[1], cpu.ram[0x35] = 0x82, 0x42, 1, 0
    cpu.r = 0x5C
    cpu.push(RET >> 8)
    cpu.push(RET & 0xFF)
    cpu.pc = 0x9695
    m.halted = False
    m.sound_events.clear()
    guard = bytearray(0x10000)
    guard[RET] = 1
    c0 = cpu.cycles
    while cpu.pc != RET and cpu.cycles - c0 < limit * CLOCK:
        t = (cpu.cycles - c0) / CLOCK
        m.brk = brk is not None and brk <= t < brk + 0.3
        if m.norom:
            assert routines.call(m, cpu.pc)
        else:
            m.run(64, guard)
    m.brk = False
    motor = [round((c - c0) / CLOCK, 4) for c, v in m.sound_events if v in (0, 7)]
    ram = cpu.ram
    regs = {"c": cpu.c, "z": cpu.z, "a": ram[2], "b": ram[3], "x": ram[4] | ram[5] << 8,
            "p": cpu.p, "q": cpu.q, "dp": cpu.dp, "34h": ram[0x34] if cpu.c else 0,
            "35h": ram[0x35], "motor": m.pc_out >> 4, "lcd": bytes(m.columns()),
            "busy": "BUSY" in m.symbols()}  # fmt: skip
    took = (cpu.cycles - c0) / CLOCK if cpu.pc == RET else None
    return took, motor, regs, bytes(m.mem[0x5F00:0x6000])


CLOAD_CASES = [
    (b'M"1";&5F00', "small", None),  # FENSCERと同じ形
    (b'M"1"', "small", None),  # テープの番地に置く
    (b"M", "small", None),
    (b'M"1";&5F10', "small", None),
    (b'M"2";&5F00', "small", 11.5),  # 名前の違うファイルは飛ばして待ち、BRKでやめる
    (b'M"1";&5F00', None, 2.0),  # テープを待っているあいだのBRK
    (b'M"1";&5F00', "big", 9.6),  # 読んでいるあいだのBRK
    (b'M"1";&5F00', "bad", None),  # チェックサムが合わない: ERROR 8
    (b'M"1";', None, None),  # 文の誤り: ERROR 1
    (b"Q", None, None),
]


@pytest.mark.parametrize(("text", "name", "brk"), CLOAD_CASES)
def test_cload_entry_like_rom(rom_tapes, text, name, brk):
    """9695h(CLOAD)をFENSCERのように呼ぶと、ROMのある本体と同じに、X+1からの文をCLOADの続きと
    して実行する。戻るときのフラグ・A・B・X・P・Q・DP、エラーの番号(34h)とBREAK(35h)、読んだRAM、
    液晶と記号、モータ(Cポートの上位)を回す時刻と戻るまでの時間を比べる(作業欄だけの本体とBASICの
    ある本体の両方。時間は1%まで)"""
    path = None if name is None else rom_tapes[name]
    rom_m = boot("1261")[0]
    rom_m.mode = "RUN"
    rom_m.run(CLOCK)
    rom = _cload_entry(rom_m, text, path, brk)
    assert rom[0] is not None
    for hle_m in (_hle(), basic_machine("1261")):
        hle = _cload_entry(hle_m, text, path, brk)
        assert hle[0] is not None and abs(hle[0] - rom[0]) <= max(rom[0] / 100, 0.002)
        assert len(hle[1]) == len(rom[1])
        assert all(abs(a - b) <= max(a / 100, 0.004) for a, b in zip(hle[1], rom[1], strict=True))
        assert hle[2] == rom[2]
        if name == "big" and brk is not None:  # BRKを見る時刻で、読み終えたバイトが1つ違ってよい
            n = len(rom[3].rstrip(b"\0"))
            assert hle[3][: n - 1] == rom[3][: n - 1] and abs(len(hle[3].rstrip(b"\0")) - n) <= 1
        else:
            assert hle[3] == rom[3]


@needs_fenscer
def test_fenscer_record_like_rom(tmp_path):
    """FENSCERの記録の画面からCLOADを選んだときの、戻るまでの時間、キャリー、読んだ記録、戻った
    ときの液晶と記号、そのあと1秒たったときの液晶が、ROMのある本体と同じ(時間は1%まで。FENSCERは
    BASIC ROMの字の形を使うので、ROMのある本体の字の形をROMなしのものにそろえる)"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    from sc61box import tape

    src, _t = boot("1261")
    src.mem[0x5F00:0x5F10] = RECORD
    path = str(tmp_path / "record.wav")
    tape.write_wav(path, tape.record(src, 'CSAVE M "2";&5F00,&5F0F'))
    out = []
    rom_m, hle_m = boot("1261")[0], basic_machine("1261")
    for a in routinecheck.font_table("1261"):
        rom_m.mem[a] = hle_m.mem[a]
    for m in (rom_m, hle_m):
        took, carry = _fenscer_cload(m, path)
        assert took is not None
        shown = (bytes(m.columns()), sorted(m.symbols()))
        m.run(CLOCK)
        out.append((took, carry, bytes(m.mem[0x5F00:0x5F10]), shown, bytes(m.columns())))
    rom, hle = out
    assert abs(rom[0] - hle[0]) <= rom[0] / 100
    assert rom[1:] == hle[1:]


def test_state_saved_before_search_target_loads():
    """FENSCERが探す並びを置く前の版で保存したROMなしの状態も、ROMの印が違うと断らずに読み込む。
    並び(BASIC ROMの番地)は読み込んだあとも残る"""
    old = _hle()
    old.mem[0x9695:0x96A0] = bytes(11)  # 前の版のROMの番地
    state = old.snapshot()
    m = _hle()
    assert bytes(m.mem[0x9695:0x96A0]) == norom1261.SEARCHED
    m.restore(state)
    assert bytes(m.mem[0x9695:0x96A0]) == norom1261.SEARCHED
    m.restore(m.snapshot())


@needs_fenscer
def test_cload_restarts_after_restore(record_wav):
    """テープを待つCLOADの様子は保存しない。待っているあいだの状態を戻すと、CLOADの入口から
    やり直し、入れ直したテープを読む"""
    from sc61box import tape

    m = _hle()
    cpu = m.cpu
    m.mem[0x4283:0x428E] = b'M"2";&5F00\r'
    cpu.ram[4], cpu.ram[5], cpu.ram[1] = 0x82, 0x42, 1
    cpu.r = 0x5C
    cpu.push(RET >> 8)
    cpu.push(RET & 0xFF)
    cpu.pc = norom1261.SEARCHED_AT

    def run(seconds: float) -> None:
        c0 = cpu.cycles
        while cpu.pc != RET and cpu.cycles - c0 < seconds * CLOCK:
            assert routines.call(m, cpu.pc)

    run(2)
    state = m.snapshot()
    assert m.pc_out & 0x70  # テープを待ってモータを回している
    run(1)
    m.restore(state)
    assert "cload" not in m.routine_data
    m.tape = tape.TapeIn(record_wav)
    run(15)
    assert cpu.pc == RET and cpu.c == 0 and bytes(m.mem[0x5F00:0x5F10]) == RECORD


@pytest.mark.parametrize("with_basic", [True, False])
def test_cload_entry_lets_machine_go(with_basic):
    """9695h(CLOAD)を呼んだあとでも、本体を捨てれば本体は回収される(CLOADが本体ごとに持つもの
    を、本体の外から握らない。誤った文でエラーにして戻る)"""
    import gc
    import weakref

    m = basic_machine("1261") if with_basic else _hle()
    took = _cload_entry(m, b"Q", None)[0]
    assert took is not None and m.cpu.c == 1
    gone = weakref.ref(m)
    del m
    gc.collect()
    assert gone() is None


@pytest.mark.parametrize("with_basic", [True, False])
def test_restore_during_cload_keeps_ram(record_wav, with_basic):
    """9695h(CLOAD)がファイルを読んでいるあいだに保存した状態を、読み続けてから同じ本体に戻すと、
    RAMは保存したときのまま(戻す前のCLOADの後始末で、BUSYの記号を消さない)"""
    import base64

    from sc61box import tape

    m = basic_machine("1261") if with_basic else _hle()
    cpu = m.cpu
    text = b'M"2";&5F00'
    m.mem[0x4283 : 0x4284 + len(text)] = text + b"\r"
    m.tape = tape.TapeIn(record_wav)
    cpu.ram[4], cpu.ram[5] = 0x82, 0x42
    cpu.push(RET >> 8)
    cpu.push(RET & 0xFF)
    cpu.pc = 0x9695
    m.halted = False
    state, saved_at = None, 0
    while cpu.pc != RET and cpu.cycles < 20 * CLOCK:
        assert routines.call(m, cpu.pc)
        if state is None and "BUSY" in m.symbols():  # ファイルを見つけて読んでいる
            state, saved_at = json.loads(json.dumps(m.snapshot())), cpu.cycles
        elif state is not None and cpu.cycles - saved_at > CLOCK // 2:
            break
    assert state is not None and cpu.pc != RET
    m.restore(state)
    assert bytes(m.mem) == base64.b64decode(state["mem"])

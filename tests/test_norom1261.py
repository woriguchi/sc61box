"""ROMなしのPC-1260/1261/1262で、代替ROMルーチン(norom1261.ROUTINES)と文字の形の表が、
ROMのある本体と同じに働くか"""

import json

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

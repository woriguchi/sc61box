"""ROMなしのPC-1350で、代替ROMルーチン(norom1350.ROUTINES)と文字の形の表が、ROMのある
本体と同じに働くか"""

import pytest
from conftest import HAVE_ROM_1350
from helpers import finish

from sc61box import norom, norom1350, romsyms, routinecheck, routines
from sc61box.autotype import Typer
from sc61box.basic import attach
from sc61box.basic.pc1261 import console
from sc61box.machine import CLOCK, new_machine

A = routines.symbols("1350")
RET = 0x6500  # 呼ぶときに積む戻り番地


def _call(m, addr: int) -> int:
    """戻り番地RETを積んでaddrを呼び、戻るまでのCPUのサイクル数を返す"""
    cpu = m.cpu
    cpu.ratio = (1, 1)
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
            assert cpu.cycles - c0 < CLOCK * 3, f"{addr:04X}から戻らない"
    finally:
        cpu.ratio = (3, 4)
    return cpu.cycles - c0


def _hle():
    m = new_machine("1350", rom=False)
    norom.install(m)
    return m


def test_routines_listed():
    """入口の表はPC-1350の名前で引け、ROMなしのPC-1350がこの表の代替ROMルーチンを使う"""
    assert set(norom1350.ROUTINES) == set(romsyms.ROUTINES_1350)
    table = routines.for_machine(_hle())
    assert {r.addr for r in table.values()} == set(romsyms.ROUTINES_1350.values())
    assert A["SHOWTEXT"] == 0x1DD9


def test_glyph_table_and_text_without_rom():
    """BASIC ROMの番地に置く字の形はROMなしのBASICの液晶の字(右の列が先)。SHOWTEXTは6D00hからの
    96字をその形で液晶に書く"""
    m = _hle()
    assert bytes(m.mem[0x812F:0x8134]) == bytes(reversed(console.glyph(0x41)))
    assert bytes(m.mem[0x808A:0x808F]) == bytes(5)
    m.mem[0x6D00:0x6D60] = b"A".ljust(0x60)
    m.mem[0x7000:0x7E00] = b"\xff" * 0xE00
    m.cpu.ram[1] = 1
    _call(m, A["SHOWTEXT"])
    cols = m.columns()
    assert cols[:12] == [0] * 6 + list(console.glyph(0x41)) + [0]
    assert not any(cols[12:150]) and not any(cols[450:600])


@pytest.mark.parametrize("name", list(romsyms.ROUTINES_1350))
def test_routine_like_rom(name):
    """値を与えて呼ぶと、内部RAM、フラグ、P・Q・DP、ポート、メモリと、かかったサイクル数が、
    ROMのある本体と同じ(routinecheck)。SHOWTEXTは、決めていないX・B・0Bh番地とポートAを
    比べず、サイクル数は1.2%まで違ってよい"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    r = routines.by_name("1350", name)
    assert r is not None
    if not routinecheck.comparable(r):
        pytest.skip("BASICのCALLから呼んで比べる")
    rom, hle = routinecheck.machines("1350")
    report = routinecheck.check_routine(rom, hle, r, trials=30)
    assert report.ok, routinecheck.report_text([report])


def _entry(m, typed: str, lines=()) -> tuple[int, bytes, int]:
    """打ったCALLで呼ばれたマシン語の頭の(X, 6EB0hからの16バイト, R)"""
    m.mem[0x6800] = 0x37  # RTN
    t = Typer(m)
    if lines:
        t.add_keys([["MODE"]])
        finish(m, t)
        m.run(CLOCK)
        for line in ("NEW", *lines):
            t.add_text(line + "\n")
            finish(m, t)
            m.run(CLOCK // 3)
        t.add_keys([["MODE"]])
        finish(m, t)
        m.run(CLOCK)
    t.add_text(typed + "\n")
    guard = bytearray(0x10000)
    guard[0x6800] = 1
    for _ in range(40000):
        if t.busy:
            t.step()
        if m.run(256, guard):
            break
    cpu = m.cpu
    assert cpu.pc == 0x6800
    return cpu.ram[4] | cpu.ram[5] << 8, bytes(m.mem[0x6EB0:0x6EC0]), cpu.r


@pytest.mark.parametrize(
    ("typed", "lines"), [("CALL &6800,P", ()), ("CALL 26624", ()), ("RUN", ("10 CALL &6800,XY",))]
)
def test_call_puts_line_position_in_x(typed, lines):
    """CALLで呼んだ先の頭では、Xが行の中の番地の最後のバイトを指す。打った行は中間コードにして
    6EB0hに置き、あとを0Dhで埋める。Rは56h"""
    m = new_machine("1350", rom=False)
    norom.install(m)
    attach(m)
    m.run(CLOCK // 2)
    x, typed_line, r = _entry(m, typed, lines)
    assert r == 0x56
    if lines:
        assert m.mem[x - 4 : x + 3] == b"&6800,X"
    else:
        assert x == 0x6EB5 and typed_line == (b"\xcc" + typed[5:].encode()).ljust(16, b"\r")
    if HAVE_ROM_1350:
        rom = new_machine("1350")
        rom.run(CLOCK)
        rom_x, rom_line, rom_r = _entry(rom, typed, lines)
        assert (rom_x, rom_r) == (x, r) and (lines or rom_line == typed_line)


def test_copy_glyph_and_push_pop_x():
    """COPY5RはX−1から下へ5バイトをY+1から上へ写して次を0にする。PUSHXで積んだXをPOPXで戻す"""
    m = _hle()
    cpu = m.cpu
    m.mem[0x6100:0x6105] = bytes([1, 2, 3, 4, 5])
    m.mem[0x6200:0x6208] = b"\xff" * 8
    cpu.ram[4:8] = bytes([0x05, 0x61, 0xFF, 0x61])
    assert _call(m, A["COPY5R"]) == 135
    assert bytes(m.mem[0x6200:0x6207]) == bytes([5, 4, 3, 2, 1, 0, 0xFF])
    assert bytes(cpu.ram[4:8]) == bytes([0x00, 0x61, 0x05, 0x62]) and cpu.dp == 0x6205
    # PUSHXのあとで別のCALLを挟んでも、POPXでXが戻る
    code = bytes([0xF1, 0x5C, 0x02, 0x34, 0x03, 0x12, 0xE2, 0x82, 0xF1, 0x67, 0x37])
    m.mem[0x6400 : 0x6400 + len(code)] = code
    cpu.ram[1] = 1
    cpu.ram[4:6] = bytes([0x78, 0x56])
    cpu.r = 0x5C
    cpu.push(RET >> 8)
    cpu.push(RET & 0xFF)
    cpu.pc = 0x6400
    while cpu.pc != RET:
        if cpu.pc < 0x2000:
            assert routines.call(m, cpu.pc)
        else:
            cpu.step()
    assert bytes(cpu.ram[4:6]) == bytes([0x78, 0x56])


# 「CALL &6800,式」で、EVALとF2Iの結果(キャリー、X、10h〜17h、34h、F2Iのキャリー・18h・19h・
# B・34h)を6900hからに書くマシン語
def _store(regs, at: int) -> list[int]:
    """内部RAMのregsを、6900h+atからに1バイトずつ書く命令(LP、LIDL、MVDM)"""
    return [b for k, n in enumerate(regs, at) for b in (0x80 | n, 0x11, k, 0x53)]


EVAL_CODE = bytes(
    [0x24, 0xEA, 0xB8, 0x02, 0x00, 0x5A, 0x10, 0x69, 0x00, 0x52]
    + _store([4, 5, *range(0x10, 0x18), 0x34], 1)
    + [0xF6, 0x3A, 0x02, 0x00, 0x5A, 0x11, 0x20, 0x52]
    + _store([0x18, 0x19, 0x03, 0x34], 0x21)
    + [0x37]
)


def _typed_call(m, code: bytes, typed: str, lines=()) -> bytes:
    """codeを6800hに置いて打った行(linesがあればプログラムを入れてから)を動かし、6900hからを返す"""
    m.mem[0x6800 : 0x6800 + len(code)] = code
    t = Typer(m)
    if lines:
        t.add_keys([["MODE"]])
        finish(m, t)
        for line in ("NEW", *lines):
            t.add_text(line + "\n")
            finish(m, t)
        t.add_keys([["MODE"]])
        finish(m, t)
    t.add_text(typed + "\n")
    finish(m, t)
    m.run(CLOCK)
    return bytes(m.mem[0x6900:0x6925])


def _basic_1350(rom: bool):
    m = new_machine("1350", rom=rom)
    if not rom:
        norom.install(m)
        attach(m)
    m.run(CLOCK // 2)
    return m


@pytest.mark.parametrize(
    ("expr", "number", "string", "error", "integer"),
    [
        ("123", "0020123000000000", None, None, 123),
        ("&3021", "0040123210000000", None, None, 0x3021),
        ("-5", "0008500000000000", None, None, None),
        ("65536", "0040655360000000", None, None, None),
        ('"AB"+"C"', None, b"ABC", None, None),
        ("(", None, None, 1, None),
    ],
)
def test_eval_from_basic_call(expr, number, string, error, integer):
    """EVALは、BASICのCALLのXの次からの式を計算する(数は10h〜17h、文字列は6E60hからと14h〜17h)。
    F2Iは数を0〜65535の整数にして18h・19hに置き、範囲の外はエラー3、文字列はエラー9"""
    m = _basic_1350(rom=False)
    out = _typed_call(m, EVAL_CODE, f"CALL &6800,{expr}")
    c, x, num, err = out[0], out[1] | out[2] << 8, out[3:11], out[11]
    if error is not None:
        assert (c, err) == (1, error)
    else:
        assert c == 0 and x == 0x6EB6 + len(expr)
    if number is not None:
        assert num.hex() == number
    if string is not None:
        assert num[4:] == bytes([0xD0, 0x60, 0x6E, len(string)])
        assert bytes(m.mem[0x6E60 : 0x6E60 + len(string)]) == string
    f2i = out[0x20:0x25]
    if integer is not None:
        assert f2i[0] == 0 and f2i[1] | f2i[2] << 8 == integer
    elif error is None:
        assert f2i[0] == 1 and f2i[4] == (9 if string else 3)
    if HAVE_ROM_1350:
        rom = _basic_1350(rom=True)
        rom_out = _typed_call(rom, EVAL_CODE, f"CALL &6800,{expr}")
        assert rom_out[0:3] == out[0:3]
        if error is None and string is None:
            assert rom_out[3:11] == out[3:11]
        assert rom_out[0x20] == out[0x20]


@pytest.mark.parametrize(
    ("code", "expect"),
    [
        # Xを2つ進め、キャリーを0にして戻り番地を捨ててRTN: 行の続き(:PRINT 7)を実行する
        (bytes([0x04, 0x04, 0xD1, 0x5B, 0x5B, 0x37]), "7."),
        # 34h番地を3、キャリーを1にして同じく戻る: ERROR 3
        (bytes([0x02, 0x03, 0xB4, 0xDB, 0xD0, 0x5B, 0x5B, 0x37]), "ERROR 3 IN 10"),
    ],
)
def test_call_returns_past_basic_return(code, expect):
    """CALLの戻り番地を捨ててRTNすると、BASICの命令の続きへ戻る。キャリーが0ならXの次のバイト
    から行を続け、1なら内部RAMの34h番地の番号のエラー"""
    for rom in (False, True) if HAVE_ROM_1350 else (False,):
        m = _basic_1350(rom)
        _typed_call(m, code, "RUN", ("10 CALL &6800,1:PRINT 7:END", "20 PRINT 8"))
        from sc61box.lcdtext import lcd_text

        assert expect in lcd_text(m), (rom, lcd_text(m))


# 6900h番地が0のあいだ待ってから、Xを2つ進めてキャリー0で(または、34h番地を3にしてキャリー1で)
# 戻り番地を捨ててRTNするマシン語
_WAIT = bytes([0x10, 0x69, 0x00, 0x57, 0x67, 0x00, 0x39, 0x07])
_GO_ON = _WAIT + bytes([0x04, 0x04, 0xD1, 0x5B, 0x5B, 0x37])
_FAIL = _WAIT + bytes([0x02, 0x03, 0xB4, 0xDB, 0xD0, 0x5B, 0x5B, 0x37])


@pytest.mark.parametrize(
    ("code", "typed", "lines", "expect"),
    [
        (_GO_ON, "RUN", ("10 CALL &6800,1:PRINT 7:END", "20 PRINT 8"), "7."),
        (_FAIL, "RUN", ("10 CALL &6800,1:PRINT 7:END", "20 PRINT 8"), "ERROR 3 IN 10"),
        (_GO_ON, "CALL &6800,1", (), ">"),
        (_GO_ON, "CALL &6800,1:PRINT 7", (), "ERROR 1"),
        (_FAIL, "CALL &6800", (), "ERROR 3"),
    ],
)
def test_call_past_basic_return_after_restore(code, typed, lines, expect):
    """CALLの最中に保存した状態を別の本体に戻してから、マシン語がBASICの命令の続きへ戻っても、
    保存しなかったときと同じに行を続けるかエラーにする"""
    import json

    from sc61box.lcdtext import lcd_text

    m = _basic_1350(rom=False)
    m.mem[0x6900] = 0
    _typed_call(m, code, typed, lines)
    assert 0x6800 <= m.cpu.pc < 0x6808  # 待っているところ
    state = json.loads(json.dumps(m.snapshot()))
    again = _basic_1350(rom=False)
    again.restore(state)
    again.mem[0x6900] = 1
    again.run(CLOCK)
    assert expect in lcd_text(again), lcd_text(again)

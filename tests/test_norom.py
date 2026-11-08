"""ROMなしで、PC-1251系の代替ROMルーチン(norom.py)が入口と出口の仕様どおりに働くか"""

import os
import re
from decimal import Decimal

import pytest
from conftest import HAVE_ROM
from test_workbench import bench, run_until_stop

from sc61box import charset, norom, number, routines, workbench
from sc61box.basictext import CHARS
from sc61box.machine import CLOCK, TICK_2MS, new_machine

A = routines.symbols()
FX, FY = norom.FX, norom.FY


def call(m, name, limit=CLOCK):
    """CALと同じ形で戻り番地を積んでnameのルーチンを呼び、戻るまでのサイクル数を返す"""
    cpu = m.cpu
    cpu.push(0xC4)
    cpu.push(0xF0)
    cpu.pc = routines.symbols(m.model.name)[name]
    c0 = cpu.cycles
    while cpu.pc != 0xC4F0:
        if m.norom:
            assert routines.call(m, cpu.pc)
        else:
            cpu.step()
        assert cpu.cycles - c0 < limit, f"{name}から戻らない"
    return cpu.cycles - c0


def num(m, name, y=None, x=None):
    """演算Yにy、演算Xにxを入れてnameを呼び、(演算X, キャリー, エラーの番号)を返す"""
    ram = m.cpu.ram
    if y is not None:
        number.put_num(ram, FY, Decimal(y))
    if x is not None:
        number.put_num(ram, FX, Decimal(x))
    ram[1], ram[norom.ERRNO], m.cpu.c = 1, 0, 0
    call(m, name)
    return number.get_num(ram, FX), m.cpu.c, ram[norom.ERRNO]


def string(m, at, text, where):
    """本体の文字コードにしたtextをメモリのwhereに置き、演算X(at=FX)か演算Y(FY)を指させる"""
    codes = {ch: code for code, ch in CHARS.items()}
    data = bytes(codes[ch] for ch in re.findall(r"\[E\]|.", text))
    m.mem[where : where + len(data)] = data
    m.cpu.ram[at : at + 8] = bytes([0, 0, 0, 0, 0xD0, where & 0xFF, where >> 8, len(data)])


@pytest.fixture
def m():
    return new_machine("1251", rom=False)


def test_number_format(m):
    """数はBASICの変数と同じ形(指数3桁の10の補数、符号、仮数12桁)。12桁より下は切り捨てる"""
    ram = m.cpu.ram
    for v, raw in (("-0.00123", "9978123000000000"), ("1E99", "0990100000000000"),
                   ("2/3", "9990666666666666"), ("1E-100", "0000000000000000")):  # fmt: skip
        number.put_num(ram, FX, Decimal(2) / 3 if v == "2/3" else Decimal(v))
        assert bytes(ram[FX : FX + 8]).hex() == raw
    number.put_num(ram, FX, Decimal("-123.456"))
    assert number.get_num(ram, FX) == Decimal("-123.456")


def test_arithmetic(m):
    assert num(m, "FSUB", "5", "7") == (-2, 0, 0)
    assert num(m, "FDIV", "1", "3")[0] == Decimal("0.333333333333")
    assert num(m, "FDIV", "1", "0")[1:] == (1, 2)
    assert num(m, "FMUL", "1E99", "10")[1:] == (1, 2)  # 1E100以上はエラー
    assert num(m, "FMUL", "1E-99", "0.1") == (0, 0, 0)  # 小さすぎれば0
    assert num(m, "FPOW", "-2", "3")[0] == -8
    assert num(m, "FPOW", "-2", "0.5")[1:] == (1, 2)
    assert num(m, "FROUND", x="0.666666666666")[0] == Decimal("0.6666666667")
    assert num(m, "FINT", x="-2.5")[0] == -3
    assert num(m, "FLN", x="0")[1:] == (1, 2)
    assert num(m, "FDEG", x="30.3")[0] == Decimal("30.5")
    assert num(m, "FDMS", x="-12.5761")[0] == Decimal("-12.343396")
    assert [num(m, "FLT", y, "2")[0] for y in "123"] == [1, 0, 0]


def test_angle_unit_from_lcd_symbols(m):
    """角度の単位は液晶の記号(F83C・F83D)で決まる。DEGで直角の倍数なら答えはちょうどになる"""
    m.mem[0xF83C], m.mem[0xF83D] = 0x0C, 0x00  # DEG
    assert num(m, "FSIN", x="30")[0] == Decimal("0.5")
    assert num(m, "FTAN", x="270")[1:] == (1, 2)
    assert num(m, "FSIN", x="1E10")[1:] == (1, 2)
    m.mem[0xF83C], m.mem[0xF83D] = 0x00, 0x04  # RAD
    assert num(m, "FATN", x="1")[0] == Decimal("0.785398163397")
    assert num(m, "FTAN", x="1.5707963268")[1:] == (1, 2)  # 度にすると90
    m.mem[0xF83C], m.mem[0xF83D] = 0x04, 0x04  # GRAD
    assert num(m, "FATN", x="1")[0] == 50


def test_integers(m):
    ram = m.cpu.ram
    ram[FY], ram[FY + 1] = 0xFF, 0xFF
    m.cpu.c = 1  # 前のエラーのキャリーが残っていても、0にして戻る
    call(m, "I2F")
    assert number.get_num(ram, FX) == -1 and m.cpu.c == 0
    assert num(m, "F2I", x="-1")[1:] == (1, 3)  # 範囲は0〜65535
    assert num(m, "F2I", x="65535")[1] == 0 and ram[FY : FY + 2] == b"\xff\xff"
    call(m, "RANGE16")
    assert num(m, "F2I", x="-1.9")[1] == 0 and ram[FY : FY + 2] == b"\xff\xff"
    assert num(m, "F2I", x="32768")[1:] == (1, 3)


def test_strings(m):
    for text, v in (("1 . 5", "1.5"), ("--5", "5"), ("1.2.3", "1.23"), ("1[E]-3", "0.001"),
                    ("1[E]200", "1"), ("12A3", "12"), ("", "0")):  # fmt: skip
        string(m, FX, text, 0xC600)
        assert num(m, "FVAL")[0] == Decimal(v), text
    string(m, FX, "B", 0xC600)
    assert num(m, "FASC")[0] == 66
    string(m, FY, "AB", 0xC600)
    string(m, FX, "B", 0xC610)
    assert num(m, "SLT")[0] == 1 and num(m, "SEQ")[0] == 0


def text_of(m):
    """演算Xの文字列を字にする"""
    ram = m.cpu.ram
    a, n = ram[FX + 5] | ram[FX + 6] << 8, ram[FX + 7]
    return "".join(CHARS.get(c, f"<{c:02X}>") for c in m.mem[a : a + n])


def test_str_and_chr(m):
    """STR$とCHR$は、C701〜C7AFの空いている所(C6F7が次の位置)に文字列を置く"""
    for v, text in (("-12.5", "-12.5"), ("1234567890", "1234567890"),
                    ("12345678901", "1.23456789[E] 10"), ("0.00012", "0.00012"),
                    ("2/3", "6.666666666[E]-01"), ("1.5E-9", "1.5[E]-09")):  # fmt: skip
        m.mem[norom.STR_PTR] = 1
        num(m, "FSTRS", x=Decimal(2) / 3 if v == "2/3" else v)
        assert text_of(m) == text, v
    assert m.mem[norom.STR_PTR] == 1 + 7  # 1.5[E]-09は7字
    m.mem[norom.STR_PTR] = 0xAF
    assert num(m, "FCHRS", x="66.7")[1] == 0 and text_of(m) == "B"
    assert num(m, "FCHRS", x="66")[1:] == (1, 6)  # 置く場所がいっぱい
    m.mem[norom.STR_PTR] = 1
    assert num(m, "FCHRS", x="97")[1:] == (1, 9)  # 英小文字は本体にない
    num(m, "FCHRS", x="0")
    assert text_of(m) == ""


def test_random(m):
    assert {int(num(m, "FRND", x="6")[0]) for _ in range(200)} == set(range(1, 7))
    assert all(0 < num(m, "FRND", x="0.5")[0] < 1 for _ in range(20))
    assert num(m, "FRND", x="-3")[0] == num(m, "FRND", x="-3")[0]  # 負の数で種を決める


def test_random_seed_is_saved(m):
    """RNDの乱数の種は、どこでもセーブに入る。種のない前の版の状態のファイルも読める"""
    num(m, "FRND", x="0.5")
    state = m.snapshot()
    a = num(m, "FRND", x="0.5")
    m2 = new_machine("1251", rom=False)
    m2.restore(state)
    assert num(m2, "FRND", x="0.5") == a
    del state["machine"]["rnd_seed"]
    new_machine("1251", rom=False).restore(state)


def test_display_and_wait(m):
    m.out_c(0xF2)
    call(m, "DISPON")
    assert m.pc_out == 0x01 and m.display_on()
    call(m, "DISPOFF")
    assert m.pc_out == 0x00
    m.t2ms = 0
    n = call(m, "WAIT4MS")
    assert TICK_2MS < n <= 2 * TICK_2MS + 12


def test_keywait_takes_key_pressed_after_call():
    """キーを待つルーチンは、呼ぶ前から押していたキーでは戻らず、あとで押したキーで戻る。
    待つあいだは入口にとどまって時間を進める"""
    m, b = bench()
    b.paste(f"C000 {0xE000 | A['KEYWAIT']:04X}37")  # CAL KEYWAIT / RTN
    b.start = 0xC000
    m.held.add("A")
    b.run()
    run_until_stop(m, b, 0.2)
    assert b.state == "run" and m.cpu.pc == A["KEYWAIT"]
    m.held.discard("A")
    m.held.update({"SHIFT", "B"})  # SHIFTは数えない
    run_until_stop(m, b)
    assert b.state == "edit" and m.cpu.ram[2] == 0x52 and m.cpu.c == 0
    m.held.clear()
    b.run()
    run_until_stop(m, b, 0.1)
    m.held.add("ENTER")
    run_until_stop(m, b)
    assert b.state == "edit" and m.cpu.ram[2] == 0x00 and m.cpu.c == 1


def test_step_at_keywait():
    """キーを待っているあいだに一時停止して1命令進めても、ROMの番地の0は実行せず、入口に
    とどまる。入口にブレークポイントを設定して続けても同じで、キーを押せば戻る"""
    m, b = bench()
    b.paste(f"C000 {0xE000 | A['KEYWAIT']:04X}37")  # CAL KEYWAIT / RTN
    b.start = 0xC000
    b.run()
    run_until_stop(m, b, 0.1)
    b.pause()
    b.step()
    assert b.state == "pause" and m.cpu.pc == A["KEYWAIT"] and b.reason == ""
    b.toggle_break(A["KEYWAIT"])
    b.resume()
    run_until_stop(m, b, 0.1)
    assert b.state == "run" and m.cpu.pc == A["KEYWAIT"]
    m.held.add("A")
    run_until_stop(m, b)
    assert b.state == "edit" and m.cpu.ram[2] == 0x51


@pytest.mark.parametrize("model", ["1261", "1350"])
def test_not_on_other_models(model):
    """PC-1261・PC-1350のROMなしの本体では、代替ROMルーチンも文字の形の表も使わない(ROMの入口の
    番地が違い、PC-1251の入口はRAMの中やROMの番地に当たる)"""
    m = new_machine(model, rom=False)
    b = workbench.Bench(m)
    at = norom.font_addr(0x51)
    assert bytes(m.mem[at : at + 5]) != charset.glyph("A")
    assert not routines.call(m, A["FDEG"]) and not routines.call(m, A["FSTRS"])
    assert b.blocked(A["KEYSCAN"]) and not b.target_ok(A["KEYSCAN"])


@pytest.mark.skipif(not HAVE_ROM, reason="ROMがない")
def test_same_as_rom():
    """ROMのある本体で同じ値を与えて呼んだときと、答え・キャリー・エラーの番号が同じ"""
    rom = new_machine("1251")
    rom.run(CLOCK)
    hle = new_machine("1251", rom=False)
    cases = [(n, y, x) for n in ("FADD", "FSUB", "FMUL", "FDIV", "FPOW", "FEQ", "FGE")
             for y, x in (("1", "2"), ("-8", "3"), ("123456789012", "3"), ("5", "0"),
                          ("1E99", "10"), ("1E-99", "0.1"), ("0", "0"), ("-8", "0.5"))]  # fmt: skip
    cases += [(n, None, x) for n in ("FSQR", "FLN", "FLOG", "FABS", "FSGN", "FINT", "FROUND",
                                     "FDMS", "FDEG", "FATN", "FASN")
              for x in ("0", "2", "-2", "0.5", "-12.5761", "1000", "9.99999999995")]  # fmt: skip
    for name, y, x in cases:
        a, b = num(rom, name, y, x), num(hle, name, y, x)
        assert a[1:] == b[1:], (name, y, x)
        assert a[1] or abs(a[0] - b[0]) <= Decimal("1E-10") * max(abs(a[0]), 1), (name, y, x)
    for name, x in (("FSTRS", "0.1234567891"), ("FSTRS", "-9.87654321E99"), ("FCHRS", "39")):
        for mm in (rom, hle):
            mm.mem[norom.STR_PTR] = 0x10
        assert num(rom, name, x=x) == num(hle, name, x=x), (name, x)
        assert text_of(rom) == text_of(hle), (name, x)
    for text in ("12 3", "+-5", "1..2", "99999999999999", "1[E] 3", "-.5E"):
        for mm in (rom, hle):
            string(mm, FX, text, 0xC600)
        assert num(rom, "FVAL") == num(hle, "FVAL"), text


def test_leading_number_cuts_long_digits_without_rounding():
    """桁の多い数は、丸めずに10桁に切り捨ててから指数を掛ける(ROMのある本体で観察)"""
    codes = {ch: c for c, ch in CHARS.items()}

    def val(text: str) -> Decimal:
        return number.leading_number(bytes(codes["[E]" if ch == "E" else ch] for ch in text))

    assert val("0." + "9" * 30) == Decimal("0.9999999999")
    assert val("9" * 30 + "E70") == Decimal("9.999999999E99")
    assert val("1" * 10 + "9") == Decimal("11111111110")


@pytest.mark.skipif(not HAVE_ROM, reason="ROMがない")
def test_register_routines_same_as_rom():
    """PC-インタープリタが使うレジスタの受け渡しと作業場所のルーチンが、ROMのある本体で
    同じ値を与えて呼んだときと、同じレジスタ・スタック・ポートを返す"""
    from basic_diff import lcd

    rom = new_machine("1251")
    rom.run(CLOCK)
    hle = new_machine("1251", rom=False)
    norom.install(hle)  # 液晶の字を読むのに使う
    regs = bytes([0x20, 0x01, 0x12, 0x34, 0x45, 0xB8, 0x7F, 0xF8, 0x38, 0x00, 0x53, 0x05])
    text = bytes([0x58, 0x55, 0x5C, 0x5C, 0x5F]) + bytes([0x21]) * 27  # HELLO と空き
    for name in ("PRGTOP", "TEXTBUF", "BA2Y", "BA2YM", "X1C", "SWAPC", "KEYSCAN", "PUSHX",
                 "POPX", "SHOWBUF", "SHOWBUF0"):  # fmt: skip
        got = []
        for mm in (rom, hle):
            cpu = mm.cpu
            cpu.ram[0:12] = regs
            cpu.ram[0x1C:0x1E] = b"\xab\xcd"
            cpu.ram[0x5F] = 0x05
            mm.mem[0xC6E1:0xC6E3] = b"\x30\xb8"
            mm.mem[0xC7B0:0xC7D0] = text if name != "SHOWBUF0" else text[:3] + bytes(29)
            mm.out_c(0x41)
            if name == "POPX":
                cpu.r = 0x56
                cpu.ram[0x56:0x58] = b"\x11\x22"
            else:
                cpu.r = 0x58
            n = call(mm, "SHOWBUF" if name == "SHOWBUF0" else name, 400000)
            stack = bytes(cpu.ram[0x56:0x58]) if name in ("PUSHX", "POPX") else b""
            # SHOWBUFが返すのは内部RAMの20h〜37h番地と液晶だけ(レジスタは決めない)
            got.append((bytes(cpu.ram[0:8]) if not name.startswith("SHOWBUF") else b"", cpu.r,
                        stack, mm.pc_out,
                        bytes(cpu.ram[0x20:0x38]) if name.startswith("SHOWBUF") else b"",
                        lcd(mm) if name.startswith("SHOWBUF") else "", n))  # fmt: skip
        a, b = got
        assert a[:-1] == b[:-1], name
        assert abs(a[-1] - b[-1]) <= max(3, a[-1] // 50), (name, a[-1], b[-1])


@pytest.mark.skipif(not HAVE_ROM, reason="ROMがない")
@pytest.mark.parametrize("name", ["BA2XM", "LCDXM", "EXBAY", "Y2DP", "SAVEX", "LOADX"])
def test_register_routines_with_j_same_as_rom(name):
    """Jバイト数を使うレジスタの受け渡しのルーチンが、ROMのある本体と同じ内部RAM・メモリ・
    DP・P・Q・フラグを返し、同じ時間がかかる(いろいろなJ・値・DPで)"""
    import random

    rnd = random.Random(name)
    rom = new_machine("1251")
    rom.run(CLOCK)
    hle = new_machine("1251", rom=False)
    norom.install(hle)
    for _ in range(40):
        regs = bytes(rnd.randrange(256) for _ in range(0x60))
        j, dp = rnd.randrange(6), 0xC700 + rnd.randrange(0x60)
        area = bytes(rnd.randrange(256) for _ in range(0xC0))
        flags = rnd.randrange(2), rnd.randrange(2)
        got = []
        for mm in (rom, hle):
            cpu = mm.cpu
            cpu.ram[0:0x60] = regs
            cpu.ram[1] = j
            cpu.r, cpu.dp, cpu.p, cpu.q = 0x58, dp, 0x30, 0x31
            cpu.c, cpu.z = flags
            mm.mem[0xC6B0:0xC770] = area
            n = call(mm, name)
            got.append((bytes(cpu.ram[0:0x50]), bytes(mm.mem[0xC6B0:0xC770]), cpu.dp, cpu.p,
                        cpu.q, cpu.c, cpu.z, cpu.r, n))  # fmt: skip
        assert got[0] == got[1], (name, j)


DUMP = os.path.join(os.path.dirname(__file__), "..", "programs", "pcint.hex")


@pytest.mark.skipif(not os.path.exists(DUMP), reason="PC-インタープリタのダンプがない")
def test_pc_interpreter_without_rom():
    """ROMなしのBASICで、PC-インタープリタの見本ともぐらたたきが動く。見本は字を出して流し、
    STOPでENTERを待ってBASICに戻る。もぐらたたきは、押さなければGAME OVERになり、BASICに
    戻って得点を出す"""
    from basic_diff import basic_machine, play
    from test_norom_basic import _program

    from sc61box import programs

    for name, start, want in (
        ("pcint", "CALL &C300\n", ["PC-INTERPRETER", ">"]),
        ("mogura", "RUN 900\n", ["GAME OVER", "SCORE=0", ">"]),
    ):
        prog = programs.load_program(os.path.join(os.path.dirname(DUMP), f"{name}.bas"))
        m = basic_machine("1251")
        for addr, data in prog.blocks:
            m.mem[addr : addr + len(data)] = data
        lines = [x for x in prog.basic.splitlines() if x[:1].isdigit()]
        step = 0.05 if name == "pcint" else 1.0  # 見本は字を出してすぐに流し始める
        acts = (
            [start] + [("wait", step), None] * int(16 / step) + [["ENTER"], ("wait", 1), None] * 2
        )
        shown = " / ".join(r.lcd.strip() for r in play(m, _program(lines, acts)))
        at = 0
        for w in want:
            at = shown.find(w, at)
            assert at >= 0, (name, w, shown)
        assert m.basic is not None and m.basic.notice is None


@pytest.mark.skipif(not HAVE_ROM or not os.path.exists(DUMP), reason="ROMかダンプがない")
@pytest.mark.parametrize(
    ("lines", "acts"),
    [
        # PC-インタープリタの知らない命令: マシン語がエラーで戻り、エラーの行はC6B1hが指す行
        (['10 COS:PRINT "A"', "20 RUN"], ["CALL &C300\n", ("wait", 2), None]),
        (['10 COS:PRINT "A"', "20 RUN", '30 "="CALL &C300:PRINT 5'],
         ["RUN 30\n", ("wait", 2), None]),
        # BRK: CALLの行で止まる(打った行なら0)
        (['10 COS:PRINT "A":WAIT FF:GOTO 10'],
         ["CALL &C300\n", ("wait", 1), ("brk", None), ("wait", 1), None]),
        # CONTはC6B1hが指す文の次から。PC-インタープリタはC6B1hを自分が読んでいる行の中に
        # 動かすので、行10の最後の文で止まると、次の行30のCALLから続く
        (['10 COS:PRINT "A":WAIT FF:COS:PRINT "B":WAIT FF:GOTO 10', "30 CALL &C300:PRINT 5"],
         ["RUN 30\n", ("wait", 1.5), ("brk", None), ("wait", 1), None, "CONT\n", ("wait", 0.2),
          None]),
        # STOPでキーを待っているときのBRK。CONTは行10のSTOPの次の文(文字列の中の:は飛ばす)から
        (['10 COS:PRINT "A":STOP:PRINT "B:C":PRINT "D"', "30 CALL &C300:PRINT 5"],
         ["RUN 30\n", ("wait", 1), None, ("brk", None), ("wait", 1), None, "CONT\n",
          ("wait", 0.5), None, ["ENTER"], ("wait", 0.5), None]),
        (['10 COS:PRINT "A":STOP:PRINT "B:C":PRINT "D"'],
         ["CALL &C300\n", ("wait", 1), None, ("brk", None), ("wait", 1), None, "CONT\n",
          ("wait", 0.5), None]),
    ],
)  # fmt: skip
@pytest.mark.parametrize("model", ["1251", "1245"])
def test_call_error_and_break_like_rom(lines, acts, model):
    """CALLしたマシン語がエラーやBREAKで戻ったときの出し方と、そのあとのCONTが、ROMのある
    本体と同じ"""
    from basic_diff import basic_machine, play
    from helpers import boot
    from test_norom_basic import _program

    from sc61box import programs

    dump = programs.load_program(DUMP)
    shown = []
    for m in (boot(model)[0], basic_machine(model)):
        for addr, data in dump.blocks:
            m.mem[addr : addr + len(data)] = data
        shown.append([r.lcd for r in play(m, _program(lines, acts))])
    assert shown[0] == shown[1]


BREAK_CODE = bytes([0x12, 0x15, 0x02, 0x30, 0xDB, 0x37])  # LIP 15h、LIA 30h、EXAM、RTN


@pytest.mark.skipif(not HAVE_ROM, reason="ROMがない")
@pytest.mark.parametrize(
    "lines",
    [["10 CALL &C300:PRINT 5", "20 PRINT 6"], ["10 CALL &C300", "20 PRINT 6"],
     ["10 PRINT 4:CALL &C300"], ['10 A=1:CALL &C300:PRINT "X;Y":PRINT 5']],
)  # fmt: skip
@pytest.mark.parametrize("model", ["1251", "1245"])
def test_call_break_then_cont_like_rom(lines, model):
    """内部RAMの15hを30hにして戻るマシン語: BREAKになり、CONTはCALLの次の文から続ける"""
    from basic_diff import basic_machine, play
    from helpers import boot
    from test_norom_basic import _program

    acts = ["RUN\n", ("wait", 0.5), None, "CONT\n", ("wait", 0.5), None, ["ENTER"],
            ("wait", 0.5), None]  # fmt: skip
    shown = []
    for m in (boot(model)[0], basic_machine(model)):
        m.mem[0xC300 : 0xC300 + len(BREAK_CODE)] = BREAK_CODE
        shown.append([r.lcd for r in play(m, _program(lines, acts))])
    assert shown[0] == shown[1]


@pytest.mark.skipif(not HAVE_ROM, reason="ROMがない")
@pytest.mark.parametrize("model", ["1251", "1245"])
def test_typed_call_line_in_ram_like_rom(model):
    """RUNモードで打ったCALLの行は、中間コードにしてC7B0hから置かれ(残りの80バイトまでは
    00h)、C6B1hはその中の番地の最後のバイトを指す"""
    from basic_diff import basic_machine, play
    from helpers import boot

    for text in ("CALL &C300", "CALL &C300:", "CALL 49920"):
        got = []
        for m in (boot(model)[0], basic_machine(model)):
            m.mem[0xC7A0:0xC810] = bytes([0xEE]) * 0x70
            m.mem[0xC300:0xC303] = bytes([0x79, 0xC3, 0x00])  # JP C300(そこにとどまる)
            play(m, [("mode", "RUN"), ("wait", 1.5), ("type", text + "\n"), ("wait", 0.5)])
            got.append((m.cpu.pc, bytes(m.mem[0xC7A0:0xC810]), bytes(m.mem[0xC6B1:0xC6B3])))
        assert got[0] == got[1], text


@pytest.mark.skipif(not HAVE_ROM, reason="ROMがない")
def test_key_routines_with_brk_like_rom():
    """BRKを押していると、キーを読むルーチンは、待ち始めから押していても、ROMのある本体と
    同じA・B・C・Zで戻る"""
    for name in ("KEYSCAN", "KEYWAIT", "KEYWAIT2", "KEYWAIT0"):
        rom = new_machine("1251")
        rom.run(CLOCK)
        hle = new_machine("1251", rom=False)
        norom.install(hle)
        got = []
        for mm in (rom, hle):
            cpu = mm.cpu
            cpu.ram[0:12] = bytes(range(1, 13))
            cpu.r = 0x58
            mm.brk = True
            call(mm, name, 400000)
            got.append((bytes(cpu.ram[2:4]), cpu.c, cpu.z, cpu.r))
        assert got[0] == got[1], name


@pytest.mark.skipif(not os.path.exists(DUMP), reason="PC-インタープリタのダンプがない")
def test_state_restore_during_call():
    """CALLの最中にどこでもセーブを戻しても、マシン語がエラー・BREAKで戻ったときの扱いと、
    BREAKのあとのCONTは、戻さなかったときと同じ。戻した直後にもう一度保存して戻しても同じ"""
    import json

    from basic_diff import basic_machine, play
    from test_norom_basic import _program

    from sc61box import programs

    dump = programs.load_program(DUMP)
    for lines, before, after, want in (
        (['10 COS:PRINT "A":WAIT FF', "20 RUN", "30 CALL &C300:PRINT 5"],
         ["RUN 30\n", ("wait", 0.3)], [("wait", 3), ("look", None)], ["ERROR 1 IN 20"]),
        (['10 COS:PRINT "A":WAIT FF:COS:PRINT "B":WAIT FF:GOTO 10', "30 CALL &C300:PRINT 5"],
         ["RUN 30\n", ("wait", 1.5)],
         [("brk", None), ("wait", 1), ("look", None), ("type", "CONT\n"), ("wait", 0.2),
          ("look", None), ("wait", 3), ("look", None)], ["BREAK IN 30", "A", "B"]),
        (['10 COS:PRINT "A":STOP:PRINT "B:C":PRINT "D"'], ["CALL &C300\n", ("wait", 1)],
         [("brk", None), ("wait", 1), ("look", None), ("type", "CONT\n"), ("wait", 0.5),
          ("look", None)], ["BREAK IN 0", "D"]),
    ):  # fmt: skip
        for times in (0, 1, 2):
            m = basic_machine("1251")
            for addr, data in dump.blocks:
                m.mem[addr : addr + len(data)] = data
            play(m, _program(lines, before))
            assert m.basic is not None and not m.basic.active  # CALLの最中
            for _ in range(times):
                saved = json.loads(json.dumps(m.snapshot()))
                m = basic_machine("1251")
                m.restore(saved)
            shown = [r.lcd.strip() for r in play(m, after)]
            assert shown == want, (lines, times, shown)


def test_more_register_routines(m):
    """BA2X・EXX1C・TEXTXM・TEXTX・COPYBの働き(PiOのゲームとMUSICサブルーチンが呼ぶ)"""
    ram = m.cpu.ram
    ram[1], ram[2], ram[3] = 1, 0x34, 0x12
    call(m, "BA2X")
    assert ram[4:6] == bytes([0x34, 0x12])
    ram[0x1C:0x1E] = bytes([0x78, 0x56])
    call(m, "EXX1C")
    assert ram[4:6] == bytes([0x78, 0x56]) and ram[0x1C:0x1E] == bytes([0x34, 0x12])
    ram[2] = 0x10
    call(m, "TEXTXM")
    assert ram[4:6] == bytes([0x0F, 0xC7]) and m.cpu.dp == 0xC70F
    call(m, "TEXTX")
    assert ram[2:6] == bytes([0xB0, 0xC7, 0xAF, 0xC7])
    m.mem[0xC001:0xC004] = b"ABC"
    ram[3], ram[4:8] = 3, bytes([0x00, 0xC0, 0x00, 0xC2])
    assert call(m, "COPYB") == 1 + 24 * 3
    assert bytes(m.mem[0xC201:0xC204]) == b"ABC" and ram[3] == 0


def test_show_ram_draws_internal_text(m):
    """SHOWRAMは内部RAMの20h番地からの字を、字の形の表で液晶に書く"""
    norom.install(m)
    codes = {ch: code for code, ch in CHARS.items()}
    m.cpu.ram[1] = 1
    m.cpu.ram[0x20:0x38] = bytes(codes[ch] for ch in "HELLO".ljust(24))
    call(m, "SHOWRAM")
    assert m.columns()[:10] == list(charset.glyph("H")) + list(charset.glyph("E"))


def test_print_buffer_with_basic():
    """PRINTBUFは、X+1番地からの出すものをPRINTの字にしてC7B0h番地から置き、あとに00hを置く"""
    from basic_diff import basic_machine

    m = basic_machine("1251")
    codes = {ch: code for code, ch in CHARS.items()}
    number.put_num(m.mem, 0xC698, Decimal(9750))  # 変数A
    text = bytes(codes[ch] for ch in '"   SCORE : ";A')
    m.mem[0xC100 : 0xC100 + len(text) + 2] = b"\0" + text + b"\0"
    m.cpu.ram[1], m.cpu.ram[4:6] = 1, bytes([0x00, 0xC1])
    call(m, "PRINTBUF")
    shown = "   SCORE : 9750."
    expected = bytes(codes[c] for c in shown) + b"\0\x11"
    assert bytes(m.mem[0xC7B0 : 0xC7B0 + len(shown) + 2]) == expected


def test_noise_rotates_a_into_port():
    """NOISE(PC-1245): 2msのタイマを待ち、Aを右へ回したキャリーをCポートのビット4に出す"""
    m = new_machine("1245", rom=False)
    cpu = m.cpu
    cpu.ram[2], cpu.ram[0x5F], cpu.c = 0x0E, 0x21, 1
    m.t2, m.t2ms = 0, 0
    assert call(m, "NOISE") == 402
    assert cpu.ram[2] == 0x87 and cpu.c == 0 and m.pc_out == cpu.ram[0x5F] == 0x21


@pytest.mark.parametrize("model", ["1251", "1245"])
def test_basic_rom_filled_with_random_bytes(model, tmp_path):
    """BASIC ROMの番地は乱数の並びで埋め、字の形の表と7FFFh番地(0)はそのまま。並びは毎回同じ。
    埋める前に保存した状態も読み込める"""
    old = new_machine(model, rom=False)
    norom.install(old)
    path = str(tmp_path / "old.json")
    old.save_state(path)
    m = new_machine(model, rom=False)
    norom.fill_data(m)
    data = bytes(m.mem[norom.DATA_TOP : norom.DATA_END])
    assert len(set(data)) == 256 and data.count(0) < 0x100
    at = norom.font_addr(0x41)
    assert bytes(m.mem[at : at + 5]) == bytes(old.mem[at : at + 5]) != bytes(5)
    assert m.mem[norom.VERSION_AT] == 0 and not any(m.mem[0:0x2000])
    again = new_machine(model, rom=False)
    norom.fill_data(again)
    assert bytes(again.mem) == bytes(m.mem)
    m.load_state(path)
    assert bytes(m.mem[norom.DATA_TOP : norom.DATA_END]) == data


def test_rom_bytes_as_random_table():
    """ROMの番地を乱数の表として読むマシン語は、埋めた本体ではいろいろな値を読む"""
    m = new_machine("1251", rom=False)
    norom.fill_data(m)
    cpu = m.cpu
    cpu.ram[4:8] = bytes([0xFF, 0x4F, 0xFF, 0xBF])  # X=4FFFh、Y=BFFFh
    # 64回、IXLで5000h〜を読み、下の2ビットをIYSでC000h〜に書く
    code = bytes.fromhex("023F34246403262F0537")
    m.mem[0xC100 : 0xC100 + len(code)] = code
    cpu.push(0xC4)
    cpu.push(0xF0)
    cpu.pc = 0xC100
    while cpu.pc != 0xC4F0:
        cpu.step()
    assert set(m.mem[0xC000:0xC040]) == {0, 1, 2, 3}


def test_keywait_state_saved_and_restored():
    """キーを待つルーチンの待ちの様子は、本体の状態と一緒に保存して戻す。壊れたものは断る"""
    m = new_machine("1251", rom=False)
    norom.install(m)
    norom._waits[m] = norom._Wait(0x1D17, 0x5A, 1234, {"A"})
    state = m.snapshot()
    assert state["waits"] == {"1251": {"pc": 0x1D17, "r": 0x5A, "seen": 1234, "old": ["A"]}}
    norom._waits[m] = norom._Wait(0x1D17, 0x5A, 9999, set())
    m.restore(state)
    assert norom.save_wait(m) == state["waits"]["1251"]
    for key, value in (("pc", 0x10000), ("seen", -1), ("old", ["NOKEY"]), ("old", "A"),
                       ("old", [[]]), ("old", [{}]), ("old", {"A": 1})):  # fmt: skip
        bad = m.snapshot()
        bad["waits"]["1251"][key] = value
        with pytest.raises(ValueError):
            m.restore(bad)
    del state["waits"]
    m.restore(state)
    assert norom.save_wait(m) is None

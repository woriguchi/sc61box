"""PC-1251のROMで電卓、BASIC、PC-インタープリタを動かす

PC-インタープリタはprograms/pcint.hexを使う(環境変数SC61BOX_PCINT_DUMPで別のファイルにできる)。
"""

import os

from helpers import boot, finish, typ

from sc61box.app import Typer, parse_hexdump
from sc61box.audio import Buzzer
from sc61box.lcdtext import lcd_text
from sc61box.machine import CLOCK, PC1251

DUMP = os.environ.get(
    "SC61BOX_PCINT_DUMP",
    os.path.join(os.path.dirname(__file__), "..", "programs", "pcint.hex"),
)


def test_prompt():
    m, _ = boot()
    assert m.display_on()
    assert {"RUN", "DE", "G"} <= m.symbols()


def test_calc():
    m, t = boot()
    assert typ(m, t, "12*3\n").strip() == "36?"  # 末尾は小数点(記号は?で出る)


def test_program():
    m, t = boot()
    m.mode = "PRO"
    m.run(CLOCK // 5)
    typ(m, t, "10 FOR I=1 TO 20:NEXT I\n20 PRINT I*2\n")
    m.mode = "RUN"
    m.run(CLOCK // 5)
    typ(m, t, "RUN\n", wait=3)
    assert lcd_text(m).strip().startswith("40")


def _enter_program(text):
    m, t = boot()
    m.mode = "PRO"
    m.run(CLOCK // 5)
    typ(m, t, text)
    return m, t


def test_long_line():
    """79字を超える行は、途中まで打ってから▶で行末へ行き、続きを足す"""
    from sc61box.basictext import program_text

    line = "20 " + ": ".join(f"PRINT A{i}" for i in range(9))  # 空白込みで100字
    assert len(line) > 79
    m, t = boot()
    m.mode = "PRO"
    m.run(CLOCK // 5)
    typ(m, t, "10 PRINT 1\n")
    t.add_program(line + "\n30 END\n")
    finish(m, t)
    m.run(CLOCK // 2)
    lines = program_text(m.mem).splitlines()
    assert lines[1].replace(" ", "") == line.replace(" ", "")
    assert lines[2] == "30 END"


FULL = (  # 行番号と中間コードでちょうど79字。後ろに足すだけでは最後のNEXTであふれる
    '310 "C":LPRINT "":FOR K=0 TO M-11:FOR J=0 TO N-11:D(K,J)=0:FOR I=0 TO L-1:'
    "D(K,J)=D(K,J)+B(K,I)*C(I,J):NEXT I"
)


def test_full_line_by_inserting():
    """上限ちょうどの長い行は、命令を先に打ってから残りを途中に挿入して入れる"""
    from sc61box.basictext import program_lines, program_text
    from sc61box.keytype import insert_plan

    assert insert_plan(FULL) is not None
    m, t = boot()
    m.mode = "PRO"
    m.run(CLOCK // 5)
    t.add_program(FULL + "\n320 END\n")
    finish(m, t)
    m.run(CLOCK // 2)
    lines = dict(program_lines(m.mem))
    assert len("310") + len(lines[310]) == 79
    text = program_text(m.mem).splitlines()
    assert text[0].replace(" ", "") == FULL.replace(" ", "")
    assert text[1] == "320 END"


def test_exponent_sign():
    """指数のE(4Bh)は「[E]」か「€」で書いて打ち込め、書き出すと「[E]」に戻る。
    英字のE(55h)とは別の字で、指数として計算される"""
    from sc61box.basictext import program_lines, program_text

    m, t = _enter_program("10 A=1[E]-8\n20 B=[E]3\n30 C=2.5€2\n40 PRINT A*1[E]8+B+C\n")
    lines = dict(program_lines(m.mem))
    assert lines[10] == bytes([0x51, 0x34, 0x41, 0x4B, 0x36, 0x48])
    assert lines[20] == bytes([0x52, 0x34, 0x4B, 0x43])
    assert program_text(m.mem).splitlines()[:3] == ["10 A=1[E]-8", "20 B=[E]3", "30 C=2.5[E]2"]
    m.mode = "RUN"
    m.run(CLOCK // 5)
    assert typ(m, t, "RUN\n", wait=2).strip().startswith("1251")  # 1+1000+250


def test_pi_and_words_in_strings():
    """π(19h)は書き出して打ち直せる。文字列の中の中間コードは、LISTと同じく綴りを
    空白で挟んで出す"""
    from sc61box.basictext import keyword_table, line_text, program_lines, program_text

    m, _ = _enter_program("10 A=π*2\n")
    assert dict(program_lines(m.mem))[10] == bytes([0x51, 0x34, 0x19, 0x37, 0x42])
    assert program_text(m.mem) == "10 A=π*2\n"
    body = bytes([0xC2, 0x12, 0x51, 0xCB, 0xC1, 0x13, 0x12])  # INPUT "A{DATA}{PRINT}?"
    assert line_text(body, keyword_table(m.mem)) == 'INPUT "A DATA PRINT ?"'


def test_after_dump_written_after_run():
    """# after: のダンプは、実行の文字列を打ったあとに書く(DIMで消されない)"""
    from sc61box.programs import Program

    m, t = boot()
    m.mode = "PRO"
    m.run(CLOCK // 5)
    typ(m, t, "NEW\n10 CLEAR:DIM O$(153)*1:PRINT 1\n")
    m.mode = "RUN"
    m.run(CLOCK // 5)
    prog = Program(name="x", run="RUN", after=[(0xC530, bytes([0x12, 0x34]))])
    t.add_text(prog.run_command + "\n")
    t.add_write(prog.after)
    finish(m, t)
    m.run(CLOCK // 2)
    assert (m.mem[0xC530], m.mem[0xC531]) == (0x12, 0x34)


def test_program_survives_power_off():
    """スイッチをOFFにしてから戻しても、プログラムが残る"""
    m, t = _enter_program("10 PRINT 123\n")
    assert m.power_off()
    m.wake()
    m.mode = "PRO"
    m.run(CLOCK)
    assert typ(m, t, "LIST\n").startswith("10")


def test_program_survives_restart(tmp="/tmp/pc1251_test_ram.bin"):
    """終了時の保存と次の起動での読み込みで、プログラムが残る"""
    m, _ = _enter_program("10 PRINT 123\n")
    assert m.power_off()
    m.save_ram(tmp)
    m2 = PC1251()
    assert m2.load_ram(tmp)
    m2.mode = "PRO"
    m2.run(CLOCK)
    assert typ(m2, Typer(m2), "LIST\n").startswith("10")


def test_auto_power_off_about_11_minutes():
    """何もしないと約11分で電源が切れ、プログラムは残る"""
    m, t = _enter_program("10 PRINT 123\n")
    m.mode = "RUN"
    seconds = 0
    while m.power and seconds < 900:
        m.run(CLOCK)
        seconds += 1
    assert 600 <= seconds <= 720, seconds
    m.brk = True  # ONキー
    m.run(CLOCK // 10)
    m.brk = False
    m.mode = "PRO"
    m.run(CLOCK)
    assert typ(m, t, "LIST\n").startswith("10")


def test_direct_print_is_error_1():
    """手動計算の状態のPRINTはERROR 1になる"""
    m, t = boot()
    assert typ(m, t, "PRINT 3\n").strip() == "ERROR 1"


def test_basic_beep_uses_4khz():
    m, t = boot()
    typ(m, t, "BEEP 1", wait=0.0)
    m.sound_events.clear()
    c0 = m.cpu.cycles
    typ(m, t, "\n", wait=0.5)
    modes = {e[1] for e in m.sound_events}
    assert 3 in modes  # 内蔵の4kHz発振
    assert Buzzer().render(m.sound_events, c0, m.cpu.cycles)


def test_pc_interpreter():
    if not os.path.exists(DUMP):
        return
    m, t = boot()
    for addr, data in parse_hexdump(DUMP):
        for i, b in enumerate(data):
            m.write(addr + i, b)
    m.mode = "PRO"
    m.run(CLOCK // 5)
    typ(m, t, "10 A=03+04*02:B=A*02:BEEP 09,05:END\n")
    m.mode = "RUN"
    m.run(CLOCK // 5)
    m.sound_events.clear()
    typ(m, t, "CALL &C300\n", wait=1)
    # 変数はC686〜C69Fの1バイト(A=C686)
    assert m.mem[0xC686] == 0x0E
    assert m.mem[0xC687] == 0x1C
    # BEEPは5と4を交互に書いて振動板を動かす
    ev = [e for e in m.sound_events if e[1] in (4, 5)]
    assert {4, 5} <= {e[1] for e in ev}
    # 書き込みの時刻は命令ごとのサイクルで記録される。BEEP 09の1周期は128サイクル
    gaps = [ev[i + 1][0] - ev[i][0] for i in range(len(ev) - 1)]
    assert min(gaps) > 0
    assert gaps[0] + gaps[1] == 128


def test_store_basic_matches_typing():
    """中間コードを直に置くと、打ち込んだときとプログラムと終わりの番地が同じになり、
    MEMも同じで、そのまま動く。長すぎる行があれば置かずに打ち込みに回す"""
    from helpers import typed_and_stored

    from sc61box import basictext, keytype

    src = (
        '10 PRINT "GOTO 10";A$:INPUT "X?";X\n'
        "20 A=1[E]3:B=π*√4:IF A>=B AND C<>D THEN 10\n"
        '30 DATA 1,TO,"a b":REM  print  TO\n'
        '5 print "ok":END:@(1)=0\n'
        "20 B=2\n"
    )
    typed, stored = typed_and_stored("1251", src)
    end = typed.mem[0xC6E3] | typed.mem[0xC6E4] << 8  # 終わりのFFの番地
    assert stored.mem[0xC6E3:0xC6E5] == typed.mem[0xC6E3:0xC6E5]
    assert bytes(stored.mem[0xB830 : end + 1]) == bytes(typed.mem[0xB830 : end + 1])
    assert typ(typed, Typer(typed), "MEM\n") == typ(stored, Typer(stored), "MEM\n")
    t = Typer(stored)
    assert typ(stored, t, "RUN\n", wait=1, mode="RUN").strip() == "OK"
    long = "10 A$=" + '"' + "1" * 80 + '"\n'
    assert basictext.encode_program(keytype.typed_text(long), stored.mem) is None


def test_pc1250_and_pc1255():
    """PC-1250とPC-1255はPC-1251のROMで動き、RAMの範囲だけが違う。MEMはカタログの値になり、
    PC-1251用の見本は、番地がRAMに収まりBASICにかからなければ一覧に出る"""
    from sc61box import basictext, programs

    for model, start, free in (
        ("1250", 0xC030, "1438"),
        ("1251", 0xB830, "3486"),
        ("1255", 0xA030, "9630"),
    ):
        m, t = boot(model)
        assert typ(m, t, "MEM\n").strip().rstrip("?") == free
        assert m.program_start() == start
        typ(m, t, "10 PRINT 7\n", mode="PRO")
        assert basictext.program_text(m.mem, start=start) == "10 PRINT 7\n"
        assert typ(m, t, "RUN\n", mode="RUN").strip().rstrip("?") == "7"
    here = os.path.join(os.path.dirname(__file__), "..", "programs")
    items = programs.scan([here])
    names = {
        model: {p.name for p in programs.for_model(items, model)} for model in ("1250", "1255")
    }
    assert {"break", "scroll", "ball", "pcint"} <= names["1255"]
    assert "pcint" in names["1250"]
    assert "break" not in names["1250"]  # C000からの見本はBASICにかかる
    # 絵はPC-1251のものを使い、型番を刷り替えた本体の絵だけが機種ごとにある
    from sc61box import display

    for model in ("1250", "1255"):
        assert display.asset_path(model, "keys.json") == display.asset_path("1251", "keys.json")
        assert f"pc{model}" in display.asset_path(model, "body_top.png")

"""PC-1245として動かす(rom/cpu-1245.romとrom/bas-1245.romが必要)"""

import os

from helpers import boot as _boot
from helpers import finish, make_app, settle, typ

from sc61box import basictext
from sc61box.app import export_program, parse_hexdump
from sc61box.lcdtext import lcd_text
from sc61box.machine import CLOCK

DUMP = os.path.join(os.path.dirname(__file__), "..", "programs", "pcint.hex")


def boot():
    return _boot("1245")


def value(text):
    """表示の数(末尾の小数点は字の表にないので?になる)"""
    return text.replace("?", " ").strip()


def enter(m, t, program):
    m.mode = "PRO"
    m.run(CLOCK // 5)
    t.add_program(program)
    finish(m, t)
    m.run(CLOCK // 2)


def test_prompt_and_memory():
    m, t = boot()
    assert m.display_on()
    assert len(lcd_text(m)) == 16  # 液晶は16桁
    assert m.symbols() == {"DE", "G"}  # モードの記号はない
    assert value(typ(m, t, "MEM\n")) == "1486"


def test_parentheses_are_on_1_and_2():
    """PC-1245の括弧はSHIFT+1、SHIFT+2(PC-1251は↓↑)"""
    m, t = boot()
    assert value(typ(m, t, "(1+2)*3\n")) == "9"


def test_shift_letter_gives_keyword():
    """A〜=の段とZ〜SPCの段は、SHIFTのあとで命令になる"""
    m, t = boot()
    m.mode = "PRO"
    m.run(CLOCK // 5)
    typ(m, t, "10 ")
    t.add_keys([["SHIFT"], ["Z"], ["1"], ["SHIFT"], ["N"], ["ENTER"]])
    typ(m, t, "")
    text = basictext.program_text(m.mem, start=m.model.prog_start)
    assert text == "10 PRINT 1 END\n" or text.replace(" ", "") == "10PRINT1END\n", text


def test_program_at_c000_and_export(tmp_path=None):
    import tempfile

    m, t = boot()
    enter(m, t, '10 A=(2+3)*4\n20 PRINT "X";A\n')
    assert m.mem[0xC000] == 0xFF and m.mem[0xC001] == 0xE0
    d = tmp_path or tempfile.mkdtemp()
    path = export_program(m, str(d))
    assert path is not None
    body = open(path, encoding="utf-8").read().split("\n", 1)[1]
    assert body == '10 A=(2+3)*4\n20 PRINT "X";A\n', body
    m.mode = "RUN"
    m.run(CLOCK // 5)
    assert value(typ(m, t, "RUN\n", wait=3)).replace(" ", "") == "X20"


def test_long_line():
    """79字を超える行も分けて打ち込める"""
    line = "20 " + ": ".join(f"PRINT A{i}" for i in range(9))
    m, t = boot()
    enter(m, t, "10 PRINT 1\n" + line + "\n30 END\n")
    lines = basictext.program_text(m.mem, start=m.model.prog_start).splitlines()
    assert lines[1].replace(" ", "") == line.replace(" ", "")
    assert lines[2] == "30 END"


def test_full_line_by_inserting():
    """上限ちょうど(79字)の行も、命令を先に打ってから挿入して入れられる"""
    line = (
        '310 "C":LPRINT "":FOR K=0 TO M-11:FOR J=0 TO N-11:D(K,J)=0:FOR I=0 TO L-1:'
        "D(K,J)=D(K,J)+B(K,I)*C(I,J):NEXT I"
    )
    m, t = boot()
    enter(m, t, line + "\n")
    lines = dict(basictext.program_lines(m.mem, m.model.prog_start))
    assert len("310") + len(lines[310]) == 79
    text = basictext.program_text(m.mem, start=m.model.prog_start)
    assert text.splitlines()[0].replace(" ", "") == line.replace(" ", "")


def test_program_survives_power_off():
    m, t = boot()
    enter(m, t, "10 PRINT 123\n")
    assert m.power_off()
    m.mode = "RUN"
    m.wake()
    m.run(CLOCK)
    assert basictext.program_text(m.mem, start=m.model.prog_start) == "10 PRINT 123\n"


def test_pc_interpreter():
    m, t = boot()
    for addr, data in parse_hexdump(DUMP):
        for i, b in enumerate(data):
            m.write(addr + i, b)
    enter(m, t, "10 A=03+04*02:B=A*02:BEEP 09,05:END\n")
    m.mode = "RUN"
    m.run(CLOCK // 5)
    m.sound_events.clear()
    typ(m, t, "CALL &C300\n", wait=1)
    assert (m.mem[0xC686], m.mem[0xC687]) == (0x0E, 0x1C)
    assert {4, 5} <= {e[1] for e in m.sound_events}


def test_lcd_right_part():
    """左の12桁はF800から順に、残りの4桁はF87Bから逆順に並ぶ"""
    m, _t = boot()
    m.mem[0xF800] = 0x7F
    m.mem[0xF87B] = 0x41
    m.mem[0xF868] = 0x22
    m.mem[0xF867] = 0x7F  # 17桁目(液晶にない)
    cols = m.columns()
    assert len(cols) == 80
    assert (cols[0], cols[60], cols[79]) == (0x7F, 0x41, 0x22)


def test_breakout_versions():
    """ブロック崩しはPC-1251用とPC-1245用があり、一覧にはその機種のものだけが出る"""
    from sc61box import programs

    here = os.path.join(os.path.dirname(__file__), "..", "programs")
    items = programs.scan([here])
    for model in ("1251", "1245"):
        shown = [p for p in programs.for_model(items, model) if p.title.startswith("ブロック崩し")]
        assert [p.model for p in shown] == [model]
        assert os.path.basename(os.path.dirname(shown[0].paths[0])) == "pc" + model
        found = programs.find("break", model)
        assert found is not None and found.model == model
    old = next(p for p in items if p.name == "break" and p.model == "1251")
    assert old.label("1245").endswith("(PC-1251用)")
    app = make_app("1245", frames=0)
    app.open_program(old, run=True)  # PC-1251用はPC-1245では読み込まない
    assert not app.typer.busy and "PC-1251用" in app.status
    app.close()


def test_breakout_on_pc1245():
    from test_smoke import _play_breakout

    for level, height in (("1", 3), ("2", 2)):
        _play_breakout(level, height, "1245")


def test_app_starts_as_pc1245():
    import pygame

    app = make_app("1245")
    assert pygame.display.get_caption()[0] == "SHARP PC-1245"
    assert [m for m, _y in app.sw_stops] == ["PRO", "RUN", "OFF"]
    app.move_switch(-1)
    assert app.m.mode == "PRO"
    app.move_switch(-1)  # いちばん上で止まる(RSVはない)
    assert app.m.mode == "PRO"
    app.key_down(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F3, mod=0))
    assert app.m.mode == "PRO"
    app.set_mode("RUN")
    for _ in range(20):
        app.frame()
    app.typer.add_text("6*7\n")
    settle(app, 200)
    assert value(lcd_text(app.m)) == "42"
    app.close()


def test_store_basic_matches_typing():
    """中間コードを直に置くと、打ち込んだときと同じになる(PC-1245)"""
    from helpers import typed_and_stored

    src = '10 FOR I=1 TO 3:PRINT I;"A B":NEXT I\n20 REM  X\n5 WAIT 0\n'
    typed, stored = typed_and_stored("1245", src)
    end = typed.mem[0xC6E3] | typed.mem[0xC6E4] << 8  # 終わりのFFの番地
    assert stored.mem[0xC6E3:0xC6E5] == typed.mem[0xC6E3:0xC6E5]
    assert bytes(stored.mem[0xC000 : end + 1]) == bytes(typed.mem[0xC000 : end + 1])

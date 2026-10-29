"""PC-1350として動かす(rom/cpu-1350.romとrom/bas-1350.romが必要)"""

import types

import pygame
from helpers import boot as _boot
from helpers import make_app
from helpers import typ as _typ

from sc61box import basictext, display, keytype, tape
from sc61box.lcdtext import lcd_text
from sc61box.machine import CLOCK, KEYS_1350, PC1350, new_machine


def boot(card=0):
    return _boot("1350", card)


def typ(m, t, text, wait=0.5, mode=None):
    _typ(m, t, text, wait, mode)
    return lines(m)


def lines(m):
    """液晶の4行。入力のカーソル(点滅する「_」)は除く"""
    return [s.rstrip().rstrip("_") for s in lcd_text(m).split("\n")]


def test_boot_shows_run_mode():
    m, t = boot()
    assert isinstance(m, PC1350)
    assert m.display_on()
    assert lines(m) == [" RUN MODE", " >", "", ""]  # 4行。字は左から2つ目の桁から
    assert len(m.columns()) == 4 * 150
    assert m.symbols() == {"RUN"}


def test_memory_with_ram_cards():
    for card, free, start in (
        (0, "3070.", 0x6030),
        (8, "11262.", 0x4030),
        (16, "19454.", 0x2030),
    ):
        m, t = boot(card)
        assert m.model.prog_start == start
        assert typ(m, t, "MEM\n")[2].strip() == free


def test_every_key_types_its_character():
    """どのキーも、そのキーの字が入る(SHIFTで記号、カナキーでカナ)"""
    plain = "QWERTYUIOPASDFGHJKL=ZXCVBNM0123456789()/*-+.,;:"
    m, t = boot()
    assert typ(m, t, plain)[1] == " " + plain[:24]
    m, t = boot()
    keys: list[list[str]] = []
    for k in "QWERTYUP()*-":
        keys.append(["SHIFT"])
        keys.append([k])
    t.add_keys(keys)
    assert typ(m, t, "")[1] == ' !"#$%&?@<>¥^'
    m, t = boot()
    # ｰは-と同じ形なので、液晶からは見分けられない
    assert typ(m, t, "ｱｶｻﾀﾅﾊﾏﾔﾗﾜｦﾝｰﾞﾟ｡｢｣､･ｧｯ")[1] == " ｱｶｻﾀﾅﾊﾏﾔﾗﾜｦﾝ-ﾞﾟ｡｢｣､･ｧｯ"
    assert m.symbols() == {"RUN"}  # 打ち終わったらカナの入力から戻す


def test_mode_key_and_symbols():
    m, t = boot()
    typ(m, t, "", mode="PRO")
    assert m.symbols() == {"PRO"}
    assert lines(m)[0] == " PROGRAM MODE"
    t.add_keys([["SHIFT"]])
    typ(m, t, "")
    assert m.symbols() == {"PRO", "SHIFT"}


def test_program_runs_and_lists_back():
    m, t = boot()
    src = '10 A$="ｱｲｳ":B=√4:C=π\n20 PRINT A$;B\n'
    typ(m, t, src, mode="PRO")
    assert basictext.program_text(m.mem, start=m.model.prog_start) == (
        '10 A$="ｱｲｳ":B=√4:C=π\n20 PRINT A$;B\n'
    )
    assert typ(m, t, "RUN\n", mode="RUN")[2].strip() == "ｱｲｳ2."


def test_power_switch_keeps_program():
    """電源スイッチを切って入れ直しても、プログラムが残る"""
    m, t = boot()
    typ(m, t, "10 PRINT 1\n", mode="PRO")
    assert m.power_off() and not m.power
    m.run(CLOCK)
    assert not m.power  # スイッチがOFFのあいだはONキーでも入らない
    m.power_on()
    m.run(CLOCK)
    assert m.power and lines(m)[0] == " RUN MODE"
    assert basictext.program_text(m.mem, start=m.model.prog_start) == "10 PRINT 1\n"


def test_save_and_load_ram(tmp_path):
    m, t = boot(16)
    typ(m, t, "10 GPRINT 255\n", mode="PRO")
    path = tmp_path / "ram.bin"
    m.save_ram(str(path))
    m2 = new_machine("1350", 16)
    assert m2.load_ram(str(path))
    assert basictext.program_text(m2.mem, start=m2.model.prog_start) == "10 GPRINT 255\n"
    assert not new_machine("1350").load_ram(str(path))  # カードの大きさが違う


def test_tape_round_trip(tmp_path):
    m, t = boot()
    typ(m, t, '10 PRINT "ｱｲｳ";123\n', mode="PRO")
    path = str(tmp_path / "t.wav")
    tape.write_wav(path, tape.record(m, 'CSAVE "TEST"'))
    m2, _t2 = boot()
    m2.tape = tape.TapeIn(path)
    tape._type(m2, 'CLOAD "TEST"\n', "RUN")
    while not m2.tape.done(m2.cpu.cycles):
        m2.run(CLOCK)
    m2.run(CLOCK)
    assert basictext.program_text(m2.mem, start=m2.model.prog_start) == '10 PRINT "ｱｲｳ";123\n'


def test_keytype_tables_cover_keys():
    for keys in keytype.keys_for('AZ09()<>¥^ｱｧﾝｰ"', "1350"):
        for k in keys:
            assert k in KEYS_1350


def test_panel_and_app():
    pygame.init()
    pygame.display.set_mode(display.out_size("1350"))
    m, t = boot()
    typ(m, t, "GPRINT 255\n")
    panel = display.Panel("1350")
    panel.set_fps(30, persist=0)
    assert set(panel.key_rects) <= set(KEYS_1350) | {"BRK"}
    surf = panel.draw(m.columns(), m.symbols(), m.display_on(), m.mode)
    assert surf.get_size() == display.out_size("1350")
    app = make_app("1350")
    app.set_mode("OFF")
    assert not app.m.power and app.m.mode == "OFF"
    app.set_mode("ON")
    for _ in range(30):
        app.frame()
    assert app.m.power and app.m.symbols() == {"RUN"}


def test_bouncing_ball_uses_whole_lcd():
    """見本の弾むボールは液晶のいちばん下で弾んでいちばん上まで上がり、左右の端をまたいで
    進む。地面に着いたときだけ鳴り、BRKでBASICに戻る"""
    from sc61box import programs

    prog = programs.find("ball", "1350")
    assert prog is not None and prog.blocks[0][0] == 0x6100
    end = prog.blocks[-1][0] + len(prog.blocks[-1][1])
    assert end < 0x6C00  # BASICの変数の場所(6C2Fから下)にかからない
    m, t = boot()
    for addr, data in prog.blocks:
        for i, b in enumerate(data):
            m.write(addr + i, b)
    typ(m, t, "CALL &6100\n", wait=0)
    m.sound_events.clear()
    rows = 0  # 点いたことのあるドットの行のビット(32ビット)
    cols_lit = set()
    for _ in range(30 * 8):  # 8秒(5回弾んで1周する)
        m.run(CLOCK // 30)
        cols = m.columns()
        lit = 0
        for x in range(150):
            v = sum(cols[band * 150 + x] << (8 * band) for band in range(4))
            if v:
                cols_lit.add(x)
                rows |= v
                lit += bin(v).count("1")
        assert lit <= 120  # ボールは1個だけ
    assert rows & 1 and rows >> 31 & 1  # いちばん上の行にも、いちばん下の行にも出る
    assert len(cols_lit) == 150  # 1周で全部の列を通る
    # 弾みごとに1回、短く鳴る
    ups = [c for c, v in m.sound_events if v == 1]
    groups = [[ups[0]]]
    for c in ups[1:]:
        if c - groups[-1][-1] > CLOCK // 10:
            groups.append([])
        groups[-1].append(c)
    assert len(groups) >= 4
    assert all(g[-1] - g[0] < CLOCK // 20 for g in groups)
    m.brk = True
    m.run(CLOCK // 5)
    m.brk = False
    m.run(CLOCK // 2)
    assert m.cpu.pc < 0x6100 or m.cpu.pc >= 0x6C00  # マシン語から戻った


def test_recording_uses_pc1350_picture(tmp_path, monkeypatch):
    """⇧⌘Rで録画すると、PC-1350の大きさの絵が渡され、拡大した液晶の帯に液晶が映る"""
    import subprocess

    from PIL import Image

    from sc61box import recorder

    monkeypatch.setenv("SC61BOX_PROGRAMS", str(tmp_path))
    pygame.init()
    pygame.display.set_mode(display.out_size("1350"))
    app = make_app("1350")
    rec_key = types.SimpleNamespace(key=pygame.K_r, mod=pygame.KMOD_META | pygame.KMOD_SHIFT)
    app.key_down(rec_key)
    assert app.recorder is not None
    for _ in range(45):
        app.frame()
    app.key_down(rec_key)
    assert app.recorder is None
    files = sorted(tmp_path.glob("rec-*.mp4"))
    assert len(files) == 1, app.status
    shot = tmp_path / "frame.png"
    subprocess.run(
        [recorder.ffmpeg_exe(), "-loglevel", "error", "-ss", "1", "-i", str(files[0]),
         "-frames:v", "1", str(shot)],
        check=True,
    )  # fmt: skip
    lcd_h, _top, _body_h = recorder.layout(app.panel.lcd_box())
    x0 = (recorder.W - recorder.LCD_W) // 2
    band = (
        Image.open(shot)
        .convert("RGB")
        .crop(
            (
                x0 + 200,
                recorder.LCD_TOP + lcd_h // 2,
                x0 + recorder.LCD_W - 20,
                recorder.LCD_TOP + lcd_h - 10,
            )
        )
    )
    r, g, b = band.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))  # type: ignore[misc]
    assert 140 < g < 220 and g > b + 8 and abs(r - g) < 20  # 灰緑の液晶の地


def test_store_basic_matches_typing():
    """App.store_basicでRAMに置いたプログラムと終わりの番地が打ち込んだときと同じで、
    MEMの残りも同じになり、電源を入れ直しても残って動く"""
    src = (
        '10 FORT=1TO3:PRINT T;"ab c":NEXT T\n'
        "20 IF A>=B AND C<>D THEN 10:REM print  TO\n"
        '30 A=1E3:B=π*√4:C$="¥ｱｲ ポ\\"\n'
        '5 DATA 1,TO:WAIT 0:PRINT "OK":END\n'
    )
    for card in (0, 16):
        m, t = boot(card)
        lo = m.model.ram[0]
        typ(m, t, "NEW\n", mode="PRO")
        t.add_program(src)
        typ(m, t, "")
        typed = bytes(m.mem[lo + 0x30 : lo + 0x100])
        ptrs = bytes(m.mem[lo + 9 : lo + 11]), bytes(m.mem[0x6F03:0x6F05])
        free = typ(m, t, "MEM\n")[2]
        app = make_app("1350", card=card)
        app.typer.add_mode("PRO")
        app.typer.add_text("NEW\n")
        app.typer.add_call(lambda a=app: a.store_basic(src))
        while app.typer.busy:
            app.frame()
        m2, t2 = app.m, app.typer
        assert bytes(m2.mem[lo + 0x30 : lo + 0x100]) == typed
        assert (bytes(m2.mem[lo + 9 : lo + 11]), bytes(m2.mem[0x6F03:0x6F05])) == ptrs
        assert typ(m2, t2, "MEM\n")[2] == free
        assert basictext.program_text(m2.mem, start=m2.program_start()).startswith("5 DATA 1,TO:")
        app.set_mode("OFF")
        app.set_mode("ON")
        for _ in range(30):
            app.frame()
        shown = typ(m2, t2, "RUN 5\n", wait=1)
        assert "OK" in [s.strip() for s in shown], shown
        app.close()

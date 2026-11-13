"""ROMなしのBASICのPC-1261系とPC-1350: MEM#、英小文字の入力、エラーの知らせのあいだのキー、
CHR$のカナの+、PROモードで止まった行を出すとき、CHR$ 1の出し方、RUNの始めのCポート"""

import pytest
from conftest import HAVE_ROM_1260, HAVE_ROM_1350
from helpers import boot

from sc61box.machine import CLOCK


def _steps(session: list[str]) -> list[tuple[str, object]]:
    """!はモード、@はキー、BRKはBRK、ほかは打つ字。1つごとに0.4秒待って様子を見る"""
    steps: list[tuple[str, object]] = []
    for s in session:
        if s.startswith("!"):
            steps += [("mode", s[1:]), ("wait", 1.5)]
        elif s == "BRK":
            steps.append(("brk", None))
        elif s.startswith("@"):
            steps.append(("keys", s[1:].split(",")))
        else:
            steps.append(("type", s))
        steps += [("wait", 0.4), ("look", None)]
    return steps


def _own(model: str, session: list[str]):
    """ROMなしの本体にsessionを与えて、(本体, 様子の列)"""
    from basic_diff import basic_machine, play

    m = basic_machine(model)
    return m, play(m, _steps(session))


def _like_rom(model: str, session: list[str]) -> None:
    from basic_diff import basic_machine, differences, play

    rom = boot(model)[0]
    if model == "1350":
        rom.run(CLOCK)
    steps = _steps(session)
    assert differences(play(rom, steps), play(basic_machine(model), steps)) == []


def _rows(look) -> list[str]:
    return [row.rstrip() for row in look.lcd.split("\n")]


def _shown(look, *want: str) -> bool:
    """液晶の頭の行がwantか(点滅するカーソルの#の桁は、どの字とも同じとみる)"""
    rows = _rows(look)
    return all(
        len(r) == len(w) and all(a == b or "#" in (a, b) for a, b in zip(r, w, strict=True))
        for r, w in zip(rows, want, strict=False)
    )


# ---- MEM#と、命令の綴りのあいだの空白 ----
def test_mem_head_without_rom():
    """MEM#はプログラムの場所の頭の番地からRAMの頭を引いた数(初めは128、EQU#3で512)。番地は
    16ビットで引く(観察)"""
    _m, looks = _own(
        "1261",
        ["!RUN", "MEM#\n", "@CL", "MEM #+1\n", "@CL", "!PRO", "NEW\n", "EQU#3\n", "!RUN",
         "MEM#\n", "@CL", "POKE &66E1,&13,&30\n", "MEM#\n"],
    )  # fmt: skip
    assert _rows(looks[1])[1].strip() == "128."
    assert _rows(looks[3])[1].strip() == "129."
    assert _rows(looks[9])[1].strip() == "512."
    assert _rows(looks[12])[1].strip() == "61459."


def test_mem_head_not_in_1350():
    """PC-1350にMEM#はない(MEMと#になる)"""
    from sc61box.basic.pc1261.pc1350 import Evaluator

    assert Evaluator.T_MEM_HEAD == -1


@pytest.mark.parametrize(
    ("model", "typed", "code"),
    [
        ("1261", "A=MEM #", "41 3d ba"),
        ("1261", "A=M E M#", "41 3d ba"),
        ("1261", "PRI NT 1", "de 31"),
        ("1261", "A=M.#", "41 3d ba"),
        ("1261", "A=M. #", "41 3d af 23"),
        ("1261", "A=MEM.#", "41 3d af 2e 23"),
        ("1261", "EQU #1", "b9 31"),
        ("1261", "EQ.#1", "b9 23 31"),
        ("1261", "PR I.1", "de 31"),
        ("1261", "A=B .5", "41 3d c4 35"),
        ("1261", 'A$="MEM #"', "41 24 3d 22 4d 45 4d 20 23 22"),
        ("1350", "A$=OP.$", "41 24 3d ee"),
        ("1350", "A$=OPEN $", "41 24 3d ee"),
        ("1350", "A=MEM #", "41 3d af 23"),
        ("1251", "P R. 5", "c1 45"),
        ("1251", "A=CH R$ 65", "51 34 88 46 45"),
    ],
)
def test_keyword_spelled_with_spaces(model, typed, code):
    """命令の綴りの字のあいだの空白は飛ばす。「.」の省略のすぐあとの#・$は綴りの続きにする
    (ROMのある本体で打った行の中間コード)"""
    from basic_diff import basic_machine

    b = basic_machine(model).basic
    assert b is not None
    assert b.lexer.tokenize(b._codes(typed)).hex(" ") == code


@pytest.mark.parametrize("body", ["A=MEM", "A=MEM#"])
def test_mem_time_like_rom(body):
    """MEMとMEM#の時間(PC-1261)が、ROMのある本体と10%以内"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine
    from test_norom_pc1261 import _loop_time

    def per_loop(make) -> float:
        return (_loop_time(make(), body, 150) - _loop_time(make(), body, 50)) / 100

    rom = per_loop(lambda: boot("1261")[0])
    own = per_loop(lambda: basic_machine("1261"))
    assert abs(own / rom - 1) < 0.1, (body, rom, own)


def test_mem_like_rom():
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    _like_rom(
        "1261",
        ["!PRO", "NEW\n", "EQU#3\n", "10 A=MEM#:B=MEM #\n", "20 PRINT MEM#;MEM#*2\n",
         "!RUN", "MEM#\n", "@CL", "SIN MEM#\n", "@CL", "MEM#(1)\n", "@CL", "RUN\n", "\n",
         "@CL", "POKE &66E1,&13\n", "MEM#\n", "@CL", "POKE &66E1,&80\n"],
    )  # fmt: skip


# ---- 英小文字の入力(SMALL・SML) ----
def test_small_letters_1261_without_rom():
    """電源を入れると203Chのビット7を立てる。0にすると、SHIFTのあと8で英小文字の入力(SMALL)を
    切り替える。SMALLの記号は電源を入れ直しても残り、そのあとのSHIFTのあと8はカナの入力を
    切り替える(両方の記号が点き、カナが勝つ。観察)"""
    from basic_diff import basic_machine, lcd_pc1261, play

    m = basic_machine("1261")
    assert m.mem[0x203C] & 0x80
    play(m, _steps(["!RUN", "POKE &203C,PEEK &203C AND &7F\n", "@SHIFT,8", "@Q,W"]))
    assert "SMALL" in m.symbols() and "KANA" not in m.symbols()
    assert lcd_pc1261(m).startswith("qw")
    m.power_off()
    m.mode = "RUN"
    m.wake()
    m.run(CLOCK)
    assert m.mem[0x203C] & 0x80 and "SMALL" in m.symbols()
    play(m, _steps(["@Q", "@CL", "@SHIFT,8", "@Q"]))
    assert {"SMALL", "KANA"} <= set(m.symbols())
    assert lcd_pc1261(m).startswith("ｱ")


def test_small_letters_like_rom_1261():
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    _like_rom(
        "1261",
        ["!RUN", "POKE &203C,PEEK &203C AND &7F\n", "!PRO", "NEW\n", "10 A$=", "@SHIFT,W",
         "@SHIFT,8", "@A,B", "@SHIFT,8", "@SHIFT,W", ":", "@SHIFT,8", "@P,R,I,N,T", "@SHIFT,8",
         " A$;CHR$ 97;LEN A$\n", "20 B$=", "@SHIFT,W", "@SHIFT,8", "@X", "@SHIFT,8", "@1",
         "@SHIFT,8", "@Y", "@SHIFT,8", "@SHIFT,W", ":PRINT B$;ASC B$;CHR$ 122\n", "!RUN",
         "RUN 20\n", "\n", "@CL", "RUN\n", "\n", "@CL", "@SHIFT,8", "@X,Y", "@SHIFT,8", "\n",
         "@LEFT", "@CL", "@SHIFT,8", "@A", "@SHIFT,Q"],
    )  # fmt: skip


def test_input_modes_reset_at_power_on_1350():
    """PC-1350は、電源を入れるとカナ・英小文字の入力をやめる(観察)"""
    from basic_diff import basic_machine, lcd_1350, play

    for keys in (["KANA"], ["SHIFT", "KANA"]):
        m = basic_machine("1350")
        play(m, [("keys", keys), ("wait", 0.4)])
        assert {"KANA", "SML"} & set(m.symbols())
        m.power_off()
        m.mode = "RUN"
        m.wake()
        m.run(CLOCK * 2)
        play(m, [("keys", ["A"]), ("wait", 0.4)])
        assert not {"KANA", "SML"} & set(m.symbols())
        assert lcd_1350(m).split("\n")[1].strip().startswith("A")


# ---- エラーの知らせのあいだのキー ----
def test_keys_ignored_while_error_shown_1350():
    """エラーの知らせ(打った行、プログラム、INPUTの答え)を出しているあいだは、KANA・SHIFTの
    あとKANA・MODEのキーが効かない。BREAKの知らせでは効く(観察)"""
    _m, looks = _own(
        "1350",
        ["1/0\n", "@KANA", "@SHIFT,KANA", "@MODE", "@CLS", "@MODE", "10 INPUT A\n",
         "20 GOTO 20\n", "@MODE", "RUN\n", "1/0\n", "@KANA", "@MODE", "@CLS", "1\n",
         "BRK", "@KANA", "@KANA", "@MODE"],
    )  # fmt: skip
    for i in (1, 2, 3, 11, 12):
        assert looks[i].symbols == "RUN", i
    assert looks[3].lcd.split("\n")[2].strip() == "ERROR 2"
    assert looks[16].symbols == "KANA RUN"
    assert looks[18].symbols == "PRO"


def test_keys_ignored_while_error_shown_like_rom_1350():
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    _like_rom(
        "1350",
        ["1/0\n", "@KANA", "@SHIFT,KANA", "@MODE", "@CLS", "@MODE", "10 INPUT A\n",
         "20 A=1/0\n", "30 GOTO 30\n", "@MODE", "RUN\n", "1/0\n", "@KANA", "@MODE", "@CLS",
         "1\n", "@KANA", "@SHIFT,KANA", "@MODE", "@CLS", "@KANA", "@KANA", "GOTO 30\n", "BRK",
         "@KANA", "@SHIFT,KANA", "@MODE"],
    )  # fmt: skip


def test_kana_key_ignored_while_error_shown_1261():
    """PC-1261系も、エラーの知らせのあいだはSHIFTのあと8が効かない(BREAKでは効く。観察)"""
    _m, looks = _own(
        "1261",
        ["!PRO", "10 INPUT A\n", "20 GOTO 20\n", "!RUN", "1/0\n", "@SHIFT,8", "@CL", "RUN\n",
         "1/0\n", "@SHIFT,8", "@CL", "@CL", "BRK", "@SHIFT,8"],
    )  # fmt: skip
    assert "KANA" not in looks[5].symbols and "KANA" not in looks[9].symbols
    assert "KANA" in looks[13].symbols


def test_kana_key_ignored_while_error_shown_like_rom_1261():
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    _like_rom(
        "1261",
        ["!PRO", "10 INPUT A\n", "20 A=1/0\n", "30 GOTO 30\n", "!RUN", "1/0\n", "@SHIFT,8",
         "@CL", "RUN\n", "1/0\n", "@SHIFT,8", "@CL", "@SHIFT,8", "@SHIFT,8", "\n", "@SHIFT,8",
         "@CL", "GOTO 30\n", "BRK", "@SHIFT,8", "@SHIFT,8"],
    )  # fmt: skip


# ---- CHR$のカナを+でつなぐ ----
def test_chr_kana_joined_1261_without_rom():
    """PC-1261系では、CHR$で作ったカナに+でつなぐと、つないだ字がカナの字のコードに重なる
    (CHR$ 177+"X"は「FEh、58h」でXと出る。変数のカナ、右につなぐとき、PC-1350はそのまま。観察)"""
    _m, looks = _own(
        "1261",
        ["!RUN", 'CHR$ 177+"X"\n', "@CL", 'LEN (CHR$ 177+"XY")\n', "@CL",
         'ASC (CHR$ 177+"X")\n', "@CL", 'CHR$ 177+""\n', "@CL", '"X"+CHR$ 177\n', "@CL",
         "B$=CHR$ 177\n", "@CL", 'B$+"X"\n'],
    )  # fmt: skip
    assert [_rows(looks[i])[1].strip() for i in (1, 3, 5, 7, 9, 13)] == [
        "X", "2.", "88.", "ｱ", "Xｱ", "ｱX",
    ]  # fmt: skip
    _m, looks = _own("1350", ['CHR$ 177+"X"\n'])
    assert _rows(looks[0])[0].strip() == "ｱX"


def test_chr_kana_joined_like_rom():
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    _like_rom(
        "1261",
        ["!RUN", 'CHR$ 177+"X"\n', "@CL", '"X"+CHR$ 177\n', "@CL", 'LEN (CHR$ 177+"XY")\n',
         "@CL", 'ASC (CHR$ 177+"X")\n', "@CL", 'MID$(CHR$ 177+"XY",2,1)\n', "@CL",
         '"Q"+(CHR$ 177+"X")\n', "@CL", 'CHR$ 177+""\n', "@CL", "B$=CHR$ 177\n", "@CL",
         'B$+"X"\n'],
    )  # fmt: skip


# ---- PROモードで止まった行を出す(PC-1261系) ----
def test_stopped_line_notice_1261_without_rom():
    """プログラムのエラーのあと、PROモードの↓・↑で止まった行を出すと、2行目にエラーの
    メッセージを出す(次のキーで消える)。BREAKなら2行目は次の行。長い行はカーソルのある行を
    「行番号:」に続けて出す。そのあとの打った行のエラーは、メッセージの番号を変える(観察)"""
    _m, looks = _own(
        "1261",
        ["!PRO", "10 A=1\n", "20 B=1/0:C=2\n", "30 STOP\n", "40 D=3\n",
         "60 ABCDEFGHIJKLMNOPQRSTU=1/0\n", "!RUN", "RUN\n", "!PRO", "@DOWN", "@RIGHT", "@CL",
         "!RUN", "RUN 30\n", "!PRO", "@DOWN", "@CL", "!RUN", "RUN 60\n", "!PRO", "@DOWN",
         "@CL", "!RUN", "RUN 20\n", "@CL", "RUN 50\n", "!PRO", "@DOWN"],
    )  # fmt: skip
    assert _shown(looks[9], "20:B=1/0:C=2", "CALCULATION ERROR")
    assert _shown(looks[10], "20 B=1/0:C=2", "30:STOP")
    assert _rows(looks[15])[1] == "40:D=3"
    assert _shown(looks[20], "60:=1/0", "CALCULATION ERROR")
    assert _shown(looks[27], "20:B=1/0:C=2", "TOO LARGE A LINE NUMBER")


def test_stopped_line_kept_after_missing_line():
    """RUN・GOTOの跳ぶ先がなくてエラーになっても、止まった行は忘れない(PC-1251も。観察)"""
    for model, mode in (("1261", "!PRO"), ("1251", "!PRO")):
        _m, looks = _own(
            model,
            [mode, "10 A=1\n", "20 B=1/0\n", "!RUN", "RUN\n", "@CL", "RUN 30\n", "@CL",
             "GOTO 30\n", "@CL", "!PRO", "@DOWN"],
        )  # fmt: skip
        assert _rows(looks[11])[0][:6] == "20:B=1", model


def test_stopped_line_like_rom_1261():
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    _like_rom(
        "1261",
        ["!PRO", "10 A=1\n", "20 B=1/0:C=2\n", "30 STOP\n", "40 GOTO 40\n", "50 PRINT 1+\n",
         "60 ABCDEFGHIJKLMNOPQRSTU=1/0\n", "70 B=1/0:CDEFGHIJKLMNOPQRSTUVWX=1\n",
         "80 ABCDEFGHIJKLMNOPQRSTUVWXYZ=1:STOP:A=1\n", "!RUN", "RUN 30\n", "!PRO", "@DOWN",
         "@CL", "!RUN", "RUN 40\n", "BRK", "!PRO", "@DOWN", "@CL", "!RUN", "RUN 50\n", "!PRO",
         "@DOWN", "@CL", "!RUN", "RUN 20\n", "@CL", "RUN 90\n", "@CL", "1+\n", "@CL", "!PRO",
         "@DOWN", "@DOWN", "@UP", "@RIGHT", "@CL", "!RUN", "RUN 60\n", "!PRO", "@UP", "@LEFT",
         "@CL", "!RUN", "RUN 70\n", "!PRO", "@DOWN", "@DOWN", "@CL", "!RUN", "RUN 80\n",
         "!PRO", "@DOWN", "@RIGHT", "@CL", "!RUN", "RUN 20\n", "!PRO", "@DOWN", "@DOWN",
         "@DOWN", "@CL", "15 X=1\n", "@DOWN"],
    )  # fmt: skip


def test_long_line_edit_indented_1261():
    """登録した行の編集でも、続きの行は「行番号:」の幅だけ空ける。2行に入らなければ、
    カーソルのある行を2行目にして出す(観察)"""
    line = '70 PRINT "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ABCDEFGHIJ"'
    right = ",".join(["RIGHT"] * 24)
    _m, looks = _own("1261", ["!PRO", line + "\n", "LIST 70\n", "@RIGHT", f"@{right}",
                              f"@{right}"])  # fmt: skip
    assert _shown(looks[3], '70 PRINT "ABCDEFGHIJKLMN', "   OPQRSTUVWXYZ012345678")
    assert _shown(looks[5], "70 OPQRSTUVWXYZ012345678", '   9ABCDEFGHIJ"')


def test_long_line_edit_like_rom_1261():
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    right = ",".join(["RIGHT"] * 24)
    left = ",".join(["LEFT"] * 10)
    _like_rom(
        "1261",
        ["!PRO", '70 PRINT "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ABCDEFGHIJ"\n',
         "60 ABCDEFGHIJKLMNOPQRSTU=1/0\n", "LIST 70\n", "@RIGHT", f"@{right}", f"@{right}",
         f"@{left}", f"@{left}", f"@{right}", f"@{right}", "X", "Y", "\n", "LIST 60\n",
         "@RIGHT", "@RIGHT", "XYZ", "@LEFT,LEFT", "@DEL", "\n", "@UP", "@RIGHT", "@DOWN"],
    )  # fmt: skip


# ---- CHR$ 1と挿入マーク ----
def test_chr1_blank_insert_mark_drawn():
    """文字列の01h(PC-1350のCHR$ 1、PC-1261系でPOKEで入れた01h)は空白で出す。打っている行の
    挿入マークは形を出す(観察。PC-1251系は、文字列の01hも挿入マークの形)"""
    from sc61box.basic.screen import INSERT_MARK

    m, _looks = _own("1350", ['CHR$ 1+"A"\n'])
    cols = m.columns()
    assert bytes(cols[150 + 6 : 150 + 11]) == bytes(5)  # 2行目の1字目
    m, _looks = _own("1350", ["@CLS", "AB", "@LEFT", "@INS", "@RIGHT"])
    assert bytes(m.columns()[12:17]) == INSERT_MARK
    m, _looks = _own("1261", ["!RUN", 'A$="ABC"\n', "@CL", "POKE &65CA,1\n", "A$\n"])
    assert bytes(m.columns()[120 + 5 : 120 + 10]) == bytes(5)
    m, _looks = _own("1261", ["!RUN", "AB", "@LEFT", "@SHIFT,RIGHT", "@RIGHT"])
    assert bytes(m.columns()[5:10]) == INSERT_MARK


def test_chr1_like_rom_1350():
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    _like_rom("1350", ['CHR$ 1+"A"\n', '"X"+CHR$ 1\n', "@CLS", "AB", "@LEFT", "@INS"])


# ---- PC-1350のRUNの始めと、PRINTで書き直す桁 ----
def _pulses(m, typed: str) -> list[tuple[int, int]]:
    """typedとENTERを打ったあと1秒のあいだの、Cポートのビット4の変化(時刻ms, 値)"""
    from sc61box.autotype import Typer

    t = Typer(m)
    t.add_keys([["CLS"]])
    t.add_text(typed)
    while t.busy:
        t.step()
        m.run(CLOCK // 200)
    m.run(CLOCK // 5)
    log: list[tuple[int, int]] = []
    out_c = m.out_c

    def spy(v: int) -> None:
        if (v ^ m.pc_out) & 0x10:
            log.append((m.cpu.cycles, v >> 4 & 1))
        out_c(v)

    m.out_c = spy
    start = m.cpu.cycles
    t.add_keys([["ENTER"]])
    while t.busy:
        t.step()
        m.run(CLOCK // 200)
    m.run(CLOCK)
    m.out_c = out_c
    return [(round((c - start) * 1000 / CLOCK), v) for c, v in log]


def test_run_raises_c4_1350_without_rom():
    """RUN・GOTOで実行を始めると、Cポートのビット4を36.2ms立てる。CONTと、跳ぶ先がなくて
    エラーになるときは立てない(観察)"""
    from basic_diff import basic_machine, play

    m = basic_machine("1350")
    play(m, [("keys", ["MODE"]), ("type", "10 A=1\n20 STOP\n"), ("keys", ["MODE"])])
    for typed in ("RUN", "GOTO 10"):
        (t0, on), (t1, off) = _pulses(m, typed)
        assert (on, off) == (1, 0) and abs(t1 - t0 - 36) <= 1, typed
    assert _pulses(m, "RUN 30") == []
    assert _pulses(m, "CONT") == []


def test_run_raises_c4_like_rom_1350():
    """ROMのある本体も、RUN・GOTOで同じ長さだけ立て、CONTでは立てない"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, play

    for m in (boot("1350")[0], basic_machine("1350")):
        m.run(CLOCK)
        play(m, [("keys", ["MODE"]), ("type", "10 A=1\n20 STOP\n"), ("keys", ["MODE"])])
        widths = [_pulses(m, typed) for typed in ("RUN", "GOTO 10", "RUN 30", "CONT")]
        assert widths[2:] == [[], []]
        assert all(abs(p[1][0] - p[0][0] - 36) <= 1 for p in widths[:2]), widths


# 行の頭の6列と、字のあいだのあきの列(字の形によらない列)
WATCHED = [*range(6), *(6 * k + 11 for k in range(24))]


def _print_dots(m, line: str) -> list[list[int]]:
    """行ごとに3つの点をPOKEで描いてからlineを実行し、点が残った列を行ごとに返す"""
    from basic_diff import play

    from sc61box.machine import LCD_BANDS_1350, LCD_BLOCKS_1350

    pokes = (
        "11 POKE 28675,17:POKE 28683,17:POKE 29201,17\n"
        "12 POKE 28739,34:POKE 28747,34:POKE 29265,34\n"
        "13 POKE 28705,68:POKE 28713,68:POKE 30779,68\n"
        "14 POKE 28769,8:POKE 28777,8:POKE 30843,8\n"
    )
    play(m, [("mode", "PRO"), ("wait", 1.5), ("type", "10 CLS:WAIT 0\n" + pokes + line + "\n"),
             ("type", "20 GOTO 20\n"), ("mode", "RUN"), ("wait", 1.5), ("type", "RUN\n"),
             ("wait", 2)])  # fmt: skip
    return [
        [c for c in WATCHED if m.mem[LCD_BLOCKS_1350[c // 30] + band + c % 30] in (17, 34, 68, 8)]
        for band in LCD_BANDS_1350
    ]


def test_print_rewrites_rest_of_row_1350():
    """PRINTは、書いた行の残りの桁も字を書き直す(あきの列の点は消える。書き始めより左は
    そのまま。観察)"""
    from basic_diff import basic_machine

    dots = _print_dots(basic_machine("1350"), '16 CURSOR 3,0:PRINT "A";')
    assert dots[0] == [3, 11]
    dots = _print_dots(basic_machine("1350"), '16 CURSOR 0,2:PRINT "A"')
    assert dots[2] == [3]


@pytest.mark.parametrize(
    "line",
    ['16 CURSOR 3,0:PRINT "A";', '16 CURSOR 0,2:PRINT "A"', '16 PRINT "A":CURSOR 0,3:PRINT "B"',
     '16 CURSOR 3,1:PRINT "ABCDEFGHIJKLMNOPQRSTUVWXYZ";'],
)  # fmt: skip
def test_print_rewrites_rest_of_row_like_rom_1350(line):
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine

    rom = boot("1350")[0]
    rom.run(CLOCK)
    assert _print_dots(rom, line) == _print_dots(basic_machine("1350"), line)


def test_state_restore_keeps_stopped_error():
    """どこでもセーブから戻しても、PROモードで止まった行に添えるエラーメッセージは同じ"""
    import json

    from basic_diff import basic_machine, play

    m, _looks = _own("1261", ["!PRO", "10 A=1/0\n", "!RUN", "RUN\n", "@CL"])
    state = json.loads(json.dumps(m.snapshot()))
    m = basic_machine("1261")
    m.restore(state)
    m.run(CLOCK // 5)
    looks = play(m, _steps(["!PRO", "@DOWN"]))
    assert _rows(looks[1])[1] == "CALCULATION ERROR"

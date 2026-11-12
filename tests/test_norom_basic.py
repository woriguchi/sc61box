"""ROMなしのBASIC(sc61box/basic)が、ROMのある本体と同じふるまいをするか"""

import helpers
import pytest
from conftest import HAVE_ROM, HAVE_ROM_1245
from helpers import boot, finish

from sc61box import basictext
from sc61box.basic.pc1251 import tokens
from sc61box.machine import CLOCK

# ROMなしのBASICで動かす機種。どの試験も、両方の機種で、その機種のROMのある本体と比べる
BASIC_MODELS = ["1251", "1245"]


@pytest.fixture(autouse=True, params=BASIC_MODELS)
def basic_model(request, monkeypatch):
    """この試験で使う機種(boot()とbasic_machine()が作る本体の機種)"""
    monkeypatch.setattr(helpers, "MODEL", request.param)
    return request.param


def have_rom() -> bool:
    """いまの機種のROMがあるか"""
    return HAVE_ROM_1245 if helpers.MODEL == "1245" else HAVE_ROM


def only_1251(feature: str) -> None:
    """PC-1251だけにあるものの試験は、ほかの機種では飛ばす"""
    if helpers.MODEL != "1251":
        pytest.skip(f"PC-{helpers.MODEL}には{feature}がない")


def typed_body(m, t, text):
    """PROモードで「10 text」を打ち、10行の中身(中間コード)を返す"""
    t.add_text(f"10 {text}\n")
    finish(m, t)
    m.run(CLOCK // 10)
    lines = basictext.program_lines(m.mem, m.program_start())
    return lines[0][1] if lines else b""


@pytest.mark.parametrize(
    ("model", "table", "have"),
    [("1251", tokens.KEYWORDS_1251, HAVE_ROM), ("1245", tokens.KEYWORDS_1245, HAVE_ROM_1245)],
)
def test_keywords_match_rom(model, table, have):
    """綴りを打つと、ROMのある本体はその中間コード1つにする"""
    if not have:
        pytest.skip("ROMがない")
    m, t = boot(model)
    t.add_mode("PRO")
    finish(m, t)
    for code, word in table.items():
        if word in (">=", "<=", "<>"):
            assert typed_body(m, t, f"A{word}B") == bytes([0x51, code, 0x52]), word
        else:
            assert typed_body(m, t, word) == bytes([code]), word


def test_diff_tool_is_repeatable():
    """差分試験の道具は、同じ手順を2台の同じ本体に与えると、違いを出さない"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import differences, play

    steps = [("mode", "PRO"), ("type", "10 A=1:PRINT A\n20 DIM B(3)\n"), ("look", None),
             ("mode", "RUN"), ("type", "RUN\n"), ("wait", 1), ("look", None),
             ("type", "B(2)=5\n"), ("look", None)]  # fmt: skip
    a = play(boot()[0], steps)
    b = play(boot()[0], steps)
    assert not differences(a, b)
    assert a[0].program[:3] == b"\xff\xe0\x10" and a[2].variables


RUN_LINES = [
    "1", "-5", "1+2", "2/3", "2/3*3", "1[E]20", "-1[E]-20", "123456789012", "0.000012345",
    "1[E]99*10", "1/0", "0^0", "0^-1", "0^0.5", "(-2)^0.5", "SQR -4", "-2^2", "2^-1", "2^3^2",
    "SQR 4+5", "SQR 2^2", "SIN 30*2",
    "-SQR 4", "ABS -3+1", "INT -2.5", "NOT 0", "NOT 1=1", "1+NOT 0", "3 AND 5", "3 OR 5",
    "-1 AND 255", "65536 AND 1", "1.5 AND 3", "1+2=3", "1<2=1", "2*-3", "2--3", "(1+2)*3",
    "PI", 'LEN "ABC"', 'ASC "A"', '"AB"="AB"', '"A"<"B"', '"A"+"B"',
    "A=5", "A", "-A", "2A", "A B", "B=2/3", "B*3-1", 'C$="XY"', "C$", "C", "D$",
    'E$="ABCDEFGHIJ"', "E$", '"A"+1', "1+", "2PI", "PRINT 1", "A=1:B=2", "ATN 1",
    "ASN 0.5", "STR$ 12.5", "CHR$ 66", 'VAL "12"', 'LEFT$("ABC",2)', 'MID$("ABCDE",2,3)',
    'RIGHT$("ABC",1)', "&FF", "&FFFF", "&10000", "&", "&ABC+1", "&FFFFF", "A=&10", "-&1F",
    "((((((((((((((((1))))))))))))))))", "((((((((((((((((((((1))))))))))))))))))))",
    "1+(2+(3+(4+(5+(6+(7+(8+1)))))))", "1+(2+(3+(4+(5+(6+(7+(8+(9+1))))))))",
]  # fmt: skip


def test_run_mode_lines_match_rom():
    """RUNモードで式や代入を打ったときの液晶、記号、変数が、ROMのある本体と同じ"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    steps: list[tuple[str, object]] = []
    for line in RUN_LINES:
        steps += [("keys", ["CL"]), ("type", line + "\n"), ("wait", 0.3), ("look", None)]
    a = play(boot()[0], steps)
    b = play(basic_machine(), steps)
    bad = differences(a, b)
    assert not bad, "\n".join(f"{RUN_LINES[int(d.split('番目')[0])]}: {d}" for d in bad)


DIGITS = "1234567890" * 8


def test_run_mode_editing_matches_rom():
    """RUNモードの打ち込み(答えに続ける計算、長い行、カーソル、エラーの行の呼び出し)が、
    ROMのある本体と同じ"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    steps: list[tuple[str, object]] = [
        ("type", "12\n"), ("type", "+3"), ("look", None), ("type", "\n"), ("look", None),
        ("type", "*2\n"), ("look", None), ("type", "7"), ("look", None),
        ("keys", ["CL"]), ("look", None),
        ("type", "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"), ("look", None),
        ("keys", ["LEFT"]), ("look", None), ("keys", ["LEFT", "LEFT", "LEFT"]), ("look", None),
        ("type", "9"), ("look", None), ("keys", ["RIGHT", "RIGHT"]), ("look", None),
        ("keys", ["CL"]), ("type", "1/0\n"), ("look", None), ("keys", ["LEFT"]), ("look", None),
        ("keys", ["CL"]), ("type", "X+\n"), ("keys", ["RIGHT"]), ("look", None),
        ("keys", ["CL"]), ("type", "5\n"), ("keys", ["LEFT"]), ("look", None),
        ("keys", ["CL"]), ("type", DIGITS[:79] + "X"), ("look", None), ("type", "Y"),
        ("look", None), ("type", "\n"), ("look", None), ("keys", ["CL"]),
        ("type", DIGITS[:78] + "*2\n"), ("look", None), ("keys", ["CL"]),
        ("type", DIGITS[:77] + "*2\n"), ("look", None),
    ]  # fmt: skip
    a = play(boot()[0], steps)
    b = play(basic_machine(), steps)
    assert not differences(a, b), "\n".join(differences(a, b))


def test_cursor_blinks_with_512ms_timer():
    """字の上のカーソルは、キーを押すと出て、512msのタイマが回るたびに字と入れ替わる"""
    from basic_diff import basic_machine, lcd, play

    m = basic_machine()
    play(m, [("type", "ABC"), ("keys", ["LEFT"]), ("wait", 0.02)])
    seen = []
    for _ in range(300):
        seen.append(lcd(m)[2])
        m.run(CLOCK // 200)
    changes = [i for i in range(1, len(seen)) if seen[i] != seen[i - 1]]
    assert set(seen) == {"#", "C"} and len(changes) >= 2
    assert all(abs((b - a) - 102) <= 1 for a, b in zip(changes, changes[1:], strict=False))


def _pro(lines):
    """PROモードで行を打ち、液晶を見る手順"""
    steps: list[tuple[str, object]] = [("mode", "PRO")]
    for line in lines:
        if isinstance(line, list):
            steps += [("keys", line), ("look", None)]
        else:
            steps += [("type", line), ("look", None)]
    return steps


def test_pro_mode_matches_rom():
    """PROモードの行の登録・表示・↑↓・編集・LIST・NEWが、ROMのある本体と同じ"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    steps = _pro([
        "10 A=1\n", "20B=2:C=3\n", '15 PRINT "HI"\n', ["UP"], ["UP"], ["UP"], ["DOWN"],
        ["DOWN"], ["DOWN"], ["CL"], ["DOWN"], ["CL"], ["UP"],
        ["UP"], ["RIGHT"], ["RIGHT"], ["LEFT"], "X", "\n", ["UP"], ["LEFT"], ["CL"],
        "LIST\n", ["DOWN"], ["CL"], "LIST 15\n", ["CL"], "LIST 17\n", ["CL"], "LIST 30\n",
        ["CL"], "LIST 0\n", ["CL"], "15\n", ["UP"], ["CL"], "MEM\n", ["CL"], "0A=1\n",
        ["CL"], "1000A=1\n", ["CL"], "999A=1\n", ["CL"], "5 A=1+\n", ["CL"], "A=7\n",
        ["CL"], "RUN\n", ["CL"],
        "30 A=SIN 30:PRINT \"AB\";X\n", ["RIGHT"], ["RIGHT"], ["RIGHT"], ["RIGHT"],
        ["RIGHT"], ["RIGHT"], ["RIGHT"], ["LEFT"], ["SHIFT", "LEFT"], ["SHIFT", "RIGHT"],
        "Q", "\n", ["CL"], "40 X=A>=B:Y=-SIN 3:Z=PI+1\n", ["CL"],
        "50 A=12345678901234567890123:B=1\n", ["LEFT"],
        ["RIGHT"] * 21, ["RIGHT"], ["RIGHT"], ["RIGHT"] * 6, ["RIGHT"], ["RIGHT"],
        ["LEFT"] * 5, ["CL"], "60 END\n", ["RIGHT"], ["RIGHT"], ["RIGHT"], "X", "\n",
        ["LEFT"], ["LEFT"], ["LEFT"], ["SHIFT", "RIGHT"], "\n", ["CL"],
        "12 A=1", ["SHIFT", "LEFT"], ["LEFT", "LEFT"], ["SHIFT", "LEFT"], ["SHIFT", "RIGHT"],
        "\n", ["CL"], "NEW\n", ["DOWN"], "A\n", ["CL"], "10 A=1\n", ["LEFT"],
        ["LEFT"], "2\n", ["UP"], ["UP"], "5", ["CL"], ["DOWN"], ["DOWN"], ["DOWN"], ["CL"],
        "20 A=" + DIGITS[:77] + "\n", ["CL"], "30 A=" + DIGITS[:73] + "\n", ["LEFT"],
    ])  # fmt: skip
    a = play(boot()[0], steps)
    b = play(basic_machine(), steps)
    assert not differences(a, b), "\n".join(differences(a, b))


def _program(lines, actions):
    """NEWしてから行を登録し、RUNモードでactionsを行う手順。actionsの字の並びは打ち、
    リストはキーを押し、Noneは液晶を見る。組はそのまま手順にする"""
    # ROMはスイッチを動かしてから気づくまでに時間がかかることがあるので、待ってから打つ
    steps: list[tuple[str, object]] = [("mode", "PRO"), ("wait", 1.5), ("type", "NEW\n")]
    steps += [("type", line + "\n") for line in lines]
    steps += [("mode", "RUN"), ("wait", 1.5)]
    for a in actions:
        if a is None:
            steps.append(("look", None))
        elif isinstance(a, list):
            steps.append(("keys", a))
        elif isinstance(a, tuple):
            steps.append(a)
        else:
            steps.append(("type", a))
    return steps


PROGRAMS = [
    (["10 PRINT 1:PRINT \"AB\":PRINT 1;2;\"X\":PRINT 1,2",
      "20 PRINT \"ABC\",-5:PRINT 12345678901:PRINT 2/3;\"Q\"", "30 A=5:PRINT A,B", "40 END"],
     ["RUN\n", None, "\n", None, "\n", None, "\n", None, "\n", None, "\n", None, "\n", None,
      "\n", None, "\n", None]),
    (["10 A=1/0"], ["RUN\n", None, ["LEFT"], None, ["CL"], ["UP"], None]),
    (["10 INPUT A:PRINT A*2", "20 INPUT \"VAL\";B:PRINT B", "30 INPUT \"W=\",C$:PRINT C$",
      "40 STOP", "50 PRINT 9"],
     ["RUN\n", None, "7", None, "\n", None, "\n", None, "3", None, "\n", None, "\n", None,
      "HI", None, "\n", None, "\n", None, "CONT\n", None, "\n", None]),
    (["5 STOP", "6 A=1/0", "100 STOP", "101 GOTO 777", "999 STOP"],
     ["RUN\n", None, "CONT\n", None, ["CL"], "RUN 100\n", None, "CONT\n", None, ["CL"],
      "RUN 999\n", None, ["CL"], "GOTO 5\n", None, ["CL"], "RUN 50\n", None]),
    (["10 PRINT 1,2,3"], ["RUN\n", None]),
    (["30 PRINT \"A\";"], ["RUN\n", None]),
    (["10 FOR I=1 TO 3:PRINT I:NEXT I:PRINT I", "20 GOSUB 40:PRINT 8:END",
      "40 PRINT 7:RETURN", "50 RETURN", "60 NEXT J", "70 ON 2 GOTO 80,90", "80 PRINT 80",
      "90 PRINT 90:ON 5 GOTO 80", "95 PRINT 95:IF 1 THEN PRINT 96", "97 IF 0 PRINT 98",
      "99 IF 1 GOTO 50"],
     ["RUN\n", None, "\n", None, "\n", None, "\n", None, "\n", None, "\n", None, "\n",
      ["CL"], "GOTO 50\n", None, ["CL"], "GOTO 60\n", None, ["CL"], "GOTO 70\n", None, "\n",
      None, "\n", None, "\n", None]),
    (["10 S=0:FOR I=1 TO 4 STEP 2:S=S*10+I:NEXT I", "20 FOR J=5 TO 1 STEP -2:S=S+J:NEXT J"],
     ["A=9\n", "RUN\n", None, "S\n", None, "I\n", None, "J\n", None, "A\n", None]),
    (["10 DIM B(3),C$(2)*5,D(1,2):B(1)=7:C$(2)=\"XYZ\":D(1,2)=9", "20 A(28)=4:A$(30)=\"HI\""],
     ["RUN\n", None, "B(1)\n", None, "C$(2)\n", None, "D(1,2)\n", None, "A(28)\n", None,
      "A$(30)\n", None, "B(4)\n", None]),
    (["5 B=1", "10 A=1/0:B=2", "20 C=1", "30 STOP:D=1"],
     ["RUN\n", ("wait", 1), None, ["LEFT"], None, "7", None, ["ENTER"], None, ["UP"], None,
      "GOTO 20\n", ("wait", 1), None, ["LEFT"], None, ["ENTER"], None, "GOTO 20\n",
      ("wait", 1), "CONT\n", ("wait", 1), None, ["CL"], "RUN\n", ("wait", 1),
      ("mode", "PRO"), ("wait", 1.5), None, ["UP"], None, ["UP"], None, ["CL"], ["DOWN"], None,
      ["RIGHT"], None, "X", None, ["CL"], ["UP"], None, ["DOWN"], None, ["DOWN"], None,
      ["CL"], ("mode", "RUN"), ("wait", 1.5), "GOTO 20\n", ("wait", 1), ("mode", "PRO"),
      ("wait", 1.5), ["DOWN"], None, ["ENTER"], None, ["CL"], ["UP"], None, ["LEFT"], None,
      ["CL"], "NEW\n", "10 GOTO 50\n", ("mode", "RUN"), ("wait", 1.5), "RUN\n", ("wait", 1),
      ("mode", "PRO"), ("wait", 1.5), ["UP"], None, ["RIGHT"], None]),
    (["10 A(28)=1:A$(30)=\"Q\"", "20 DIM B(1):A(29)=3:A(31)=4"],
     ["RUN\n", ("wait", 1), None, ["CL"], "A(28)\n", None, "A$(30)\n", None, "A(29)\n",
      None, "A(31)\n", None, ["CL"], "CLEAR\n", "A(27)=5\n", None, "A(29)=6\n", None,
      "A(27)\n", None]),
    (["10 READ A,B$,C:PRINT A;B$;C", "20 READ D", "30 RESTORE 50:READ E:PRINT E",
      "40 DATA 1,\"XY\"", "45 DATA 3+4,5", "50 DATA 9,8:DATA 4", "60 RESTORE:READ F",
      "70 READ G$", "80 DATA PI,2*A", "90 READ H:PRINT H:READ I:RESTORE 85", "95 DATA ,1"],
     ["RUN\n", None, "\n", None, "\n", None, "D\n", None, "F\n", None, ["CL"],
      "GOTO 70\n", None, ["CL"], "GOTO 90\n", None, "\n", None, ["CL"], "RESTORE 95\n",
      "GOTO 90\n", None, ["CL"], "RUN 90\n", None, "\n", None]),
    (["10 READ A:READ B,", "20 DATA 5,6", "30 READ C:READ", "40 A=1:", "50 B=1::C=2",
      "60 +", "70 TO", "80 PI", "90 NEW", "100 LIST", "110 STEP"],
     ["RUN\n", None, ["CL"], "GOTO 30\n", None, ["CL"], "GOTO 40\n", None, ["CL"],
      "GOTO 50\n", None, ["CL"], "GOTO 60\n", None, ["CL"], "GOTO 70\n", None, ["CL"],
      "GOTO 80\n", None, ["CL"], "GOTO 90\n", None, ["CL"], "GOTO 100\n", None, ["CL"],
      "GOTO 110\n", None, ["CL"], "RESTORE 20\n", "RESTORE\n", "RESTORE 25\n", None]),
    (["10 INPUT A:PRINT A", "20 INPUT B$:PRINT B$", "30 INPUT C,D:PRINT C;D",
      "40 INPUT \"N=\";E,\"M=\";F:PRINT E;F", "50 INPUT G:PRINT G"],
     ["RUN\n", ("wait", 1), None, ["ENTER"], ("wait", 1), None, "ABCDEFGHIJ\n", ("wait", 1),
      None, ["ENTER"], ("wait", 1), None, "1\n", ("wait", 1), None, "2\n", ("wait", 1), None,
      ["ENTER"], ("wait", 1), None, "3\n", ("wait", 1), None, "4\n", ("wait", 1), None,
      ["ENTER"], ("wait", 1), None, "2*3+A\n", ("wait", 1), None, ["ENTER"], ("wait", 1),
      None]),
    (["10 A=A+1:GOSUB 10", "20 A=A+1:FOR I=1 TO 2:GOTO 20", "30 A=A+1:GOSUB 40",
      "40 B=B+1:FOR I=1 TO 2:GOTO 30", "50 FOR I=1 TO 2:FOR J=1 TO 2:FOR I=1 TO 3:NEXT J"],
     ["A=0\n", "RUN\n", ("wait", 2), None, ["CL"], "A\n", None, "A=0\n", "GOTO 20\n",
      ("wait", 2), None, ["CL"], "A\n", None, "A=0\n", "B=0\n", "GOTO 30\n", ("wait", 2),
      None, ["CL"], "A\n", None, "B\n", None, "GOTO 50\n", ("wait", 1), None, "I\n", None,
      "J\n", None]),
    (["10 A=1:PRINT A:B=2:PRINT B", "20 C=3", "30 STOP:D=4", "40 E=5"],
     ["TRON\n", "RUN\n", ("wait", 1), None, ["DOWN"], ("wait", 1), None, ["DOWN"],
      ("wait", 1), None, ["UP"], ("wait", 1), None, "A\n", None, ["DOWN"], ("wait", 1), None,
      ["DOWN"], ("wait", 1), None, ["DOWN"], ("wait", 1), None, ["DOWN"], ("wait", 1), None,
      ["DOWN"], ("wait", 1), None, ["CL"], "TROFF\n", "RUN\n", ("wait", 1), None, ["DOWN"],
      ("wait", 1), None, ["ENTER"], ("wait", 1), None, ["CL"], "RUN\n", ("wait", 1), ["UP"],
      ("wait", 1), None, "CONT\n", ("wait", 1), None, ["ENTER"], ("wait", 1), None, ["DOWN"],
      ("wait", 1), None, ["DOWN"], ("wait", 1), None, "CONT\n", ("wait", 1), None, ["DOWN"],
      ("wait", 1), None, ["UP"], None, ("mode", "PRO"), ("wait", 1.5), ["UP"], None]),
    (["10 PRINT 1:PRINT 2", "20 PRINT 3", "30 INPUT A:PRINT A"],
     ["RUN\n", ("wait", 1), None, ["CL"], None, "CONT\n", ("wait", 1), None, ["CL"], "5",
      None, ["ENTER"], None, ["CL"], "RUN\n", ("wait", 1), ["LEFT"], None, ["ENTER"], None,
      ["CL"], "GOTO 30\n", ("wait", 1), None, ["DOWN"], ("wait", 1), None, ["CL"],
      "GOTO 30\n", ("wait", 1), "7", ["CL"], None, ["UP"], None]),
    # ラベル: GOTO・GOSUB・THEN・ON・RESTOREと、RUN・GOTOを打つときは、行番号の代わりに
    # 文字列を書ける。行の頭がその文字列の行へ跳ぶ。DATAはラベルのあとにあってもよい
    (['10 GOTO "B"', '20 PRINT 2', '30 "B" PRINT 3:GOSUB A$:IF 1 THEN "BC"', '40 "A" PRINT 4',
      '45 RETURN', '50 "BC" RESTORE "D":READ X:PRINT X:ON 2 GOTO 10,"Z"', '60 "D":DATA 8'],
     ["RUN\n", None, "\n", None, "\n", None, "\n", None, "\n", None, ["CL"], 'A$="A"\n',
      'RUN "B"\n', None, "\n", None, "\n", None, "\n", None, ["CL"], 'GOTO "Q"\n', None,
      ["LEFT"], None, ["CL"], 'GOTO ""\n', None]),
]  # fmt: skip

USING_LINES = [
    '"###.##";12.346', '"###";-12.6', '"###";1234', '"#.#";0.5', '"##.#";0.05', '"##";-1',
    '"###";-0.4', '"##.##^";12345', '"#^";-5', '"##.^";5', '"###.##^";-0.00012345',
    '"&&&";"ABCDE"', '"&";"XY"', '"##,###";1', '".##";1', '"#&#";1', '"###.##"',
    '"###.##";1,2', '"###.##";1;"AB";2', '"&&&";1;"AB";2', '"###";12,"AB"',
    '"&&&";"ABCDEFGHIJKLMNO","XY"', '"###.###";0.5;0.05;0.005;0.0005', '"##.#";-0.05',
    '"##.##";"ABCDEFGH"', '"#########################";1', '"&&";"A";', '"##.##^^";1',
    '"##.##^#";1', '"##^.#";1', '"&&#";1', '"##&&";1;"ABC"', '"###.#&&";1;"ABC"', '"##..#";1',
    '"###.##";2[E]-3;0', '"##.##";99.999', '"###";1[E]30', '"###.##";-1[E]99',
    '"#########################.#########";1/3', '"##";10', '"##.##^";1[E]-99',
    # 数は10桁に丸め、小数は12桁(指数の形では9桁)まで。PC-1245は桁の和が14を越えると
    # ERROR 7で、書式を「.」で始めてよい
    '"##.#############";1/3', '"##.###########";2/3', '"#.##########^";2/3',
    '"############.#####";1/3', '"#####.###########";1/3', '".##";0', '".^";5', '"##.#";0.04',
    '"###.##";-0.001',
]  # fmt: skip


def test_print_using_matches_rom():
    """PRINT USINGの書式の読み方と出し方、USINGの書式が続くこととRUNで消えることが、ROMの
    ある本体と同じ"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    lines = [f"{10 * (i + 1)} PRINT USING {u}" for i, u in enumerate(USING_LINES)]
    actions: list = []
    for i in range(len(USING_LINES)):
        actions += [["CL"], f"GOTO {10 * (i + 1)}\n", ("wait", 0.5), None, ["CL"]]
    steps = _program(lines, actions)
    steps += _program(
        ["10 USING \"##.#\":PRINT 1", "20 PRINT 2:PRINT USING;3", "30 USING:PRINT 1.25",
         "40 USING \"##.Q\"", "50 USING 5", "60 A$=\"&&\":USING A$:PRINT \"ABC\"", "70 PRINT",
         "80 USING \"&&\":PRINT 1.5;\"ABC\":USING \"##.#\":PRINT 1.5;\"ABC\":USING \"&\""],
        ["RUN\n", ("wait", 1), None, "\n", None, "\n", None, "\n", None, "\n", ["CL"],
         "GOTO 20\n", ("wait", 1), None, ["CL"], "RUN 20\n", ("wait", 1), None, ["CL"],
         "GOTO 40\n", None, ["CL"], "GOTO 50\n", None, ["CL"], "GOTO 60\n", ("wait", 1), None,
         ["CL"], "GOTO 70\n", None, ["CL"], "GOTO 80\n", ("wait", 1), None, "\n", None]
    )  # fmt: skip
    a = play(boot()[0], steps)
    b = play(basic_machine(), steps)
    assert not differences(a, b), "\n".join(differences(a, b))


MISC_CASES = [
    (["10 POKE &C000,55:CALL &C000:PRINT PEEK &C000"], ["RUN\n", ("wait", 1), None]),
    (["10 PRINT 1", "20 PRINT 2"],
     ["RUN\n", ("wait", 1), None, ("mode", "PRO"), ("wait", 2), None, ["UP"], None,
      ("mode", "RUN"), ("wait", 2), None, "CONT\n", ("wait", 1), None]),
    (["10 INPUT A", "20 PRINT A"],
     ["RUN\n", ("wait", 1), None, ("mode", "PRO"), ("wait", 2), None, ("mode", "RUN"),
      ("wait", 2), "CONT\n", ("wait", 1), None, "5\n", ("wait", 1), None]),
    (["10 REM  A B", "20 REMX Y", "30 A=1: REM  Z", '40 PRINT "A  B"'], [None]),
    (['10 A$="X":IF A$ THEN PRINT 1', '20 PRINT 2'],
     ['RUN\n', ('wait', 1), None]),
    (['10 IF "A"="A" PRINT 1'],
     ['RUN\n', ('wait', 1), None]),
    (['10 ON 2 GOSUB 30,40:PRINT 9:END', '30 PRINT 3:RETURN', '40 PRINT 4:RETURN'],
     ['RUN\n', ('wait', 1), None, '\n', None, '\n', None]),
    (['10 ON 0 GOTO 30:PRINT 8', '30 PRINT 3'],
     ['RUN\n', ('wait', 1), None]),
    (['10 ON -1 GOTO 30:PRINT 8', '30 PRINT 3'],
     ['RUN\n', ('wait', 1), None]),
    (['10 ON 1.9 GOTO 30,40', '30 PRINT 3', '40 PRINT 4'],
     ['RUN\n', ('wait', 1), None]),
    (['10 ON 1 GOTO 35', '30 PRINT 3'],
     ['RUN\n', ('wait', 1), None]),
    (['10 DEGREE:A=SIN 30:RADIAN:B=SIN 30:GRAD:C=SIN 30', '20 PRINT A:PRINT B:PRINT C'],
     ['RUN\n', ('wait', 1), None, '\n', None, '\n', None]),
    (['10 POKE 50000,1,2:A=PEEK 50000:B=PEEK 50001:PRINT A;B'],
     ['RUN\n', ('wait', 1), None]),
    (['10 POKE 50000,256'],
     ['RUN\n', ('wait', 1), None]),
    (['10 A=5:DIM B(2):CLEAR:PRINT A'],
     ['RUN\n', ('wait', 1), None, 'B(1)\n', None]),
    (['10 WAIT 32:PRINT 1:PRINT 2:WAIT:PRINT 3'],
     ['RUN\n', ('wait', 2), None]),
    (['10 A=10:GOSUB A+10:END', '20 PRINT 2:RETURN'],
     ['RUN\n', ('wait', 1), None]),
    (['10 FOR I=1 TO 3 STEP 0:A=A+1:IF A<5 NEXT I', '20 PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    (['10 FOR I=3 TO 1:A=A+1:NEXT I:PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    (['10 FOR A$=1 TO 3'],
     ['RUN\n', ('wait', 1), None]),
    (['10 NEXT'],
     ['RUN\n', ('wait', 1), None]),
    (['10 FOR I=1 TO 2:NEXT:PRINT I'],
     ['RUN\n', ('wait', 1), None]),
    (['10 END:PRINT 1'],
     ['RUN\n', ('wait', 1), None]),
    (['10 REM PRINT 1:PRINT 2', '20 PRINT 3'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LET A=5:PRINT A'],
     ['RUN\n', ('wait', 1), None]),
    (['10 A=5:RANDOM:PRINT RND 10<11'],
     ['RUN\n', ('wait', 1), None]),
    (['10 DEBUG'],
     ['RUN\n', ('wait', 1), None]),
    (['10 PRINT 1'],
     ['DEBUG\n', ('wait', 1), None, ['DOWN'], ('wait', 1), None]),
    (['10 PRINT 1'],
     ['DEBUG 10\n', ('wait', 1), None]),
    (['10 GOSUB 20', '20 RETURN 5'],
     ['RUN\n', ('wait', 1), None]),
    (['10 GOTO'],
     ['RUN\n', ('wait', 1), None]),
    (['10 IF 1 THEN 30', '30 PRINT 3'],
     ['RUN\n', ('wait', 1), None]),
    (['10 IF 1 THEN A=5:PRINT A'],
     ['RUN\n', ('wait', 1), None]),
    (['10 IF 1 THEN GOTO 30', '30 PRINT 3'],
     ['RUN\n', ('wait', 1), None]),
    (['10 IF 0 THEN 30:PRINT 7', '20 PRINT 8', '30 PRINT 3'],
     ['RUN\n', ('wait', 1), None]),
    (['10 FOR I=1 TO 3 STEP 0:A=A+1:IF A>=5 END', '15 NEXT I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None, 'A\n', None]),
    (['10 A=1:IF A<5 NEXT I'],
     ['RUN\n', ('wait', 1), None]),
    (['10 A=1:IF A<5 A=7:PRINT A'],
     ['RUN\n', ('wait', 1), None]),
    (['10 A=1:IF A<5 PRINT A'],
     ['RUN\n', ('wait', 1), None]),
    (['10 IF "" THEN PRINT 1', '20 PRINT 2'],
     ['RUN\n', ('wait', 1), None]),
    (['10 IF "A" THEN PRINT 1', '20 PRINT 2'],
     ['RUN\n', ('wait', 1), None]),
    (['10 A$="":IF A$ THEN PRINT 1', '20 PRINT 2'],
     ['RUN\n', ('wait', 1), None]),
    (['10 IF 1 THEN 20+10', '30 PRINT 3'],
     ['RUN\n', ('wait', 1), None]),
    (['10 IF 1 THEN A', '30 PRINT 3'],
     ['A=30\n', 'RUN\n', ('wait', 1), None]),
    (['10 GOTO 30 5', '30 PRINT 3'],
     ['RUN\n', ('wait', 1), None]),
    (['10 GOTO 30:PRINT 5', '30 PRINT 3'],
     ['RUN\n', ('wait', 1), None]),
    (['10 GOSUB 30 X:END', '30 PRINT 3:RETURN'],
     ['RUN\n', ('wait', 1), None]),
    (['10 STOP 5'],
     ['RUN\n', ('wait', 1), None]),
    (['10 END 5'],
     ['RUN\n', ('wait', 1), None]),
    (['10 CLEAR:A=1'],
     ['RUN\n', ('wait', 1), None, 'A\n', None]),
    (['10 TRON:A=1'],
     ['RUN\n', ('wait', 1), None]),
    (['10 RANDOM:A=1'],
     ['RUN\n', ('wait', 1), None]),
    (['10 DEGREE:A=1'],
     ['RUN\n', ('wait', 1), None]),
    (['10 WAIT:A=1:PRINT 2'],
     ['RUN\n', ('wait', 1), None]),
    (['10 USING:A=1:PRINT 2'],
     ['RUN\n', ('wait', 1), None]),
    (['10 ON 1 GOTO 20:PRINT 5', '20 PRINT 2'],
     ['RUN\n', ('wait', 1), None]),
    (['10 ON 2 GOTO 20:PRINT 5', '20 PRINT 2'],
     ['RUN\n', ('wait', 1), None]),
    (['10 FOR I=1 TO 2 STEP 1 X'],
     ['RUN\n', ('wait', 1), None]),
    (['10 NEXT I 5'],
     ['RUN\n', ('wait', 1), None]),
    (['10 GOSUB 30:PRINT 5:END', '30 PRINT 3:RETURN'],
     ['RUN\n', ('wait', 1), None, '\n', None, '\n', None]),
    (['10 GOSUB 30:END', '30 RETURN:PRINT 4'],
     ['RUN\n', ('wait', 1), None]),
    (['10 ON 1 GOSUB 30:PRINT 5:END', '30 PRINT 3:RETURN'],
     ['RUN\n', ('wait', 1), None, '\n', None]),
    (['10 IF 1 THEN 30:PRINT 5', '30 PRINT 3'],
     ['RUN\n', ('wait', 1), None]),
    (['10 IF 1 GOTO 30:PRINT 5', '30 PRINT 3'],
     ['RUN\n', ('wait', 1), None]),
    (['10 GOTO 30 :', '30 PRINT 3'],
     ['RUN\n', ('wait', 1), None]),
    (['10 GOTO 30', '30 PRINT 3:GOTO 40:', '40 PRINT 4'],
     ['RUN\n', ('wait', 1), None, '\n', None]),
    (['10 GOTO 30:REM', '30 PRINT 3'],
     ['RUN\n', ('wait', 1), None]),
    (['10 FOR I=1 TO 2 STEP 0'],
     ['RUN\n', ('wait', 1), None]),
    (['10 FOR I=1 TO 2 STEP -0.5:A=A+1:NEXT I:PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    (['10 CONT'],
     ['RUN\n', ('wait', 1), None]),
    (['10 GOTO 30', '30 PRINT 3:END:'],
     ['RUN\n', ('wait', 1), None, '\n', None]),
    (['10 FOR I=1 TO 4 STEP 0.5:A=A+1:NEXT I:PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    (['10 FOR I=1 TO 4 STEP 1.5:A=A+1:NEXT I:PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    (['10 FOR I=1 TO 4 STEP -1.5:A=A+1:NEXT I:PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    (['10 FOR I=1 TO 4 STEP 2.5:A=A+1:NEXT I:PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    (['10 FOR I=1 TO 4 STEP -0.1:A=A+1:NEXT I:PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    (['10 FOR I=1 TO 4 STEP 0.99:A=A+1:NEXT I:PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    (['10 FOR I=1 TO 4 STEP 1.0001:A=A+1:NEXT I:PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    (['10 FOR I=1 TO 4 STEP -1:A=A+1:NEXT I:PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    (['10 FOR I=1 TO 4 STEP 1E1:A=A+1:NEXT I:PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    (['10 FOR I=0.5 TO 3:A=A+1:NEXT I:PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    (['10 FOR I=1 TO 2.5:A=A+1:NEXT I:PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    (['10 FOR I=-1.5 TO 0:A=A+1:NEXT I:PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    (['10 FOR I=1 TO 1:A=A+1:NEXT I:PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    (['10 FOR I=70000 TO 70001:A=A+1:NEXT I:PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    (['10 FOR I=1 TO 100000:A=A+1:NEXT I:PRINT A;I'],
     ['A=0\n', 'RUN\n', ('wait', 1), None]),
    ([],
     ['DEBUG\n', ('wait', 0.8), None, ['CL'], None]),
    (['10 DEBUG', '20 PRINT 7'],
     ['RUN\n', ('wait', 1.5), None, ['CL'], None]),
    ([],
     ['DEBUG 10\n', ('wait', 0.8), None, ['CL'], None]),
    (['10 DEBUG 10', '20 PRINT 7'],
     ['RUN\n', ('wait', 1.5), None, ['CL'], None]),
    ([],
     ['OFF\n', ('wait', 0.8), None, ['CL'], None]),
    (['10 OFF', '20 PRINT 7'],
     ['RUN\n', ('wait', 1.5), None, ['CL'], None]),
    ([],
     ['ERROR\n', ('wait', 0.8), None, ['CL'], None]),
    (['10 ERROR', '20 PRINT 7'],
     ['RUN\n', ('wait', 1.5), None, ['CL'], None]),
    ([],
     ['KEY\n', ('wait', 0.8), None, ['CL'], None]),
    (['10 KEY', '20 PRINT 7'],
     ['RUN\n', ('wait', 1.5), None, ['CL'], None]),
    ([],
     ['SETCOM\n', ('wait', 0.8), None, ['CL'], None]),
    (['10 SETCOM', '20 PRINT 7'],
     ['RUN\n', ('wait', 1.5), None, ['CL'], None]),
    ([],
     ['ROM\n', ('wait', 0.8), None, ['CL'], None]),
    (['10 ROM', '20 PRINT 7'],
     ['RUN\n', ('wait', 1.5), None, ['CL'], None]),
    ([],
     ['OUTSTAT\n', ('wait', 0.8), None, ['CL'], None]),
    (['10 OUTSTAT', '20 PRINT 7'],
     ['RUN\n', ('wait', 1.5), None, ['CL'], None]),
    ([],
     ['INSTAT\n', ('wait', 0.8), None, ['CL'], None]),
    (['10 INSTAT', '20 PRINT 7'],
     ['RUN\n', ('wait', 1.5), None, ['CL'], None]),
    ([],
     ['LIST\n', ('wait', 0.8), None, ['CL'], None]),
    (['10 LIST', '20 PRINT 7'],
     ['RUN\n', ('wait', 1.5), None, ['CL'], None]),
    ([],
     ['RUN\n', ('wait', 0.8), None, ['CL'], None]),
    (['10 RUN', '20 PRINT 7'],
     ['RUN\n', ('wait', 1.5), None, ['CL'], None]),
    ([],
     ['NEW\n', ('wait', 0.8), None, ['CL'], None]),
    (['10 NEW', '20 PRINT 7'],
     ['RUN\n', ('wait', 1.5), None, ['CL'], None]),
    ([],
     ['CONT\n', ('wait', 0.8), None, ['CL'], None]),
    (['10 CONT', '20 PRINT 7'],
     ['RUN\n', ('wait', 1.5), None, ['CL'], None]),
    ([],
     ['MEM\n', ('wait', 0.8), None, ['CL'], None]),
    (['10 MEM', '20 PRINT 7'],
     ['RUN\n', ('wait', 1.5), None, ['CL'], None]),
    ([],
     ['PASS "A"\n', ('wait', 0.8), None, ['CL'], None]),
    (['10 PASS "A"', '20 PRINT 7'],
     ['RUN\n', ('wait', 1.5), None, ['CL'], None]),
    ([],
     ['LLIST\n', ('wait', 0.8), None, ['CL'], None]),
    (['10 LLIST', '20 PRINT 7'],
     ['RUN\n', ('wait', 1.5), None, ['CL'], None]),
    ([],
     ['TRON\n', ('wait', 0.8), None, ['CL'], None]),
    (['10 TRON', '20 PRINT 7'],
     ['RUN\n', ('wait', 1.5), None, ['CL'], None]),
    (['10 PRINT π', '20 C=2π:PRINT C', '30 PRINT SIN 2A^2', '40 PRINT -2^2A',
 '50 PRINT 2A^-1B'],
     ['A=3:B=0\n', ['CL'], '2π\n', None, ['CL'], 'Aπ\n', None, ['CL'], 'πA\n', None, ['CL'],
      'ππ\n', None, ['CL'], '2ππ\n', None, ['CL'], '3*2π\n', None, ['CL'], '2π^2\n', None,
      ['CL'], '-2π\n', None, ['CL'], '2π+1\n', None, ['CL'], '2.5π\n', None, ['CL'], '(2)π\n',
      None, ['CL'], '(2)A\n', None, ['CL'], 'A(1)π\n', None, ['CL'], '1E2π\n', None, ['CL'],
      '2PI\n', None, ['CL'], 'π√4\n', None, ['CL'], '√4\n', None, ['CL'], '2*√9\n', None,
      ['CL'], '√-1\n', None, ['CL'], '√π\n', None, ['CL'], '√4^2\n', None, ['CL'], '√\n', None,
      ['CL'], 'SIN 30A\n', None, ['CL'], 'SIN 30π\n', None, ['CL'], 'EXP 1π\n', None, ['CL'],
      'SQR 4A\n', None, ['CL'], '√4A\n', None, ['CL'], '-√4A\n', None, ['CL'], 'SIN 10πA\n',
      None, ['CL'], 'SIN 30A+1\n', None, ['CL'], 'SIN 2A*2\n', None, ['CL'], 'A^2B\n', None,
      ['CL'], '2^2A\n', None, ['CL'], 'A^2π\n', None, ['CL'], '2^AB\n', None, ['CL'],
      '2SIN 30\n', None, ['CL'], '2(3)\n', None, ['CL'], '2√4\n', None, ['CL'], 'RUN\\n',
      ('wait', 2), None, ['ENTER'], ('wait', 1), None, ['ENTER'], ('wait', 1), None, ['ENTER'],
      ('wait', 1), None, ['ENTER'], ('wait', 1), None]),
    ([],
     ['A=3:B=0\n', ['CL'], '6/2A\n', None, ['CL'], '6/2π\n', None, ['CL'], '12/AB\n', None,
      ['CL'], '6/2A^2\n', None, ['CL'], '2A/6\n', None, ['CL'], '6/2*A\n', None, ['CL'],
      '-6/2A\n', None, ['CL'], '6/2πA\n', None, ['CL'], '6/πA\n', None, ['CL'], 'SIN 30/2A\n',
      None, ['CL'], '6/A(1)\n', None, ['CL'], '6*2A\n', None, ['CL']]),
    # RUNはWAITをやめる(PRINTはENTERを待つ)。GOTOではやめない
    (["10 WAIT 0:END", "20 PRINT 1:PRINT 2"],
     ["RUN\n", ("wait", 1), None, "GOTO 20\n", ("wait", 1), None, ['CL'], "RUN 20\n",
      ("wait", 1), None, "\n", None, "\n", None]),
    # IFの数の条件は正のときだけ成り立つ(負の数では成り立たない)
    (["10 A=0:B=0:C=0:D=0:X=-3", "20 IF -1 LET A=1", "30 IF -0.5 LET B=1", "40 IF 0.5 LET C=1",
      "50 IF X LET D=1", "60 PRINT A;B;C;D"],
     ["RUN\n", ("wait", 2), None]),
]  # fmt: skip


@pytest.mark.parametrize("index", range(len(MISC_CASES)))
def test_statements_match_rom(index):
    """文ごとの細かいふるまい(IFの条件とTHEN、行の流れを変える文のあとの:、FORの終わりと
    増分、ON、POKE、CLEAR、WAITなど)が、ROMのある本体と同じ"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    steps = _program(*MISC_CASES[index])
    a = play(boot()[0], steps)
    b = play(basic_machine(), steps)
    assert not differences(a, b), "\n".join(differences(a, b))


ERROR_LINES = [
    "A=1/0+5", "A=SQR -1+5", "PRINT 1", "A=(1/0)*3+4", "GOTO 50", "B=1:C=2", "1+(2*3",
    "A=B(5)+1", "A=1/0", "LET A=5", "RUN 50", 'A="X"', "C$=1", 'A$=MID$ ("ABC",0,1)+"X"',
    'A$=LEFT$ ("ABC",81)', 'A$=RIGHT$ ("ABC",-0.5)', 'A$=MID$ ("ABC",1,81)',
]  # fmt: skip


def test_direct_error_position_matches_rom():
    """RUNモードでエラーになった行を←・→で呼び出したときのカーソルの位置(エラーの位置)が、
    ROMのある本体と同じ"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    actions: list = []
    for line in ERROR_LINES:
        for key in ("LEFT", "RIGHT"):
            actions += [["CL"], line + "\n", [key], "X", None]
    steps = _program(["5 B=1"], actions)
    a = play(boot()[0], steps)
    b = play(basic_machine(), steps)
    assert not differences(a, b), "\n".join(differences(a, b))


@pytest.mark.parametrize("index", range(len(PROGRAMS)))
def test_programs_match_rom(index):
    """プログラムの実行(PRINTの出し方、エラーとBREAKの出し方、INPUT、FOR、GOSUB、ON、IF、
    配列)が、ROMのある本体と同じ"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    steps = _program(*PROGRAMS[index])
    a = play(boot()[0], steps)
    b = play(basic_machine(), steps)
    assert not differences(a, b), "\n".join(differences(a, b))


SPEED_PROGRAMS = [
    "10 FOR I=1 TO {n}|11 NEXT I",
    "10 FOR I=1 TO {n}|11 A=A+1:B=A*3|12 NEXT I",
    "10 FOR I=1 TO {n}:IF I>2 A=1/7|11 NEXT I",
    "10 FOR I=1 TO {n}:GOSUB 20|11 NEXT I:END|20 C=SQR 2:RETURN",
    '10 FOR I=1 TO {n}:GOSUB "B"|11 NEXT I:END|12 "C" REM|13 REM|20 "B" RETURN',
    '10 FOR I=1 TO {n}:GOSUB "BCDEF"|11 NEXT I:END|20 "BCDEF" RETURN',
    "10 I=0|20 I=I+1:IF I<{n} GOTO 20",
    '10 FOR I=1 TO {n}:WAIT 0:PRINT I;"X"|11 NEXT I',
]


def _run_ms(m, lines) -> float:
    """プログラムを登録し、RUNのENTERを押してから「>」に戻るまでのミリ秒"""
    from basic_diff import lcd, play

    play(m, _program(lines, ["RUN"]))
    m.held.add("ENTER")
    c0, k = m.cpu.cycles, 0
    while not lcd(m).startswith(">") and m.cpu.cycles - c0 < CLOCK * 60:
        m.run(CLOCK // 1000)
        k += 1
        if k == 60:
            m.held.discard("ENTER")
    return (m.cpu.cycles - c0) * 1000 / CLOCK


@pytest.mark.parametrize("template", SPEED_PROGRAMS)
def test_speed_matches_rom(template):
    """繰り返し1回にかかる時間が、ROMのある本体と10%以内で同じ"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine

    def per_loop(make) -> float:
        a, b = (_run_ms(make(), template.format(n=n).split("|")) for n in (10, 30))
        return (b - a) / 20

    rom, ours = per_loop(lambda: boot()[0]), per_loop(basic_machine)
    assert abs(ours - rom) <= rom * 0.1, (rom, ours)


def _entry_registers(m, line):
    """lineを打って、CALLで呼んだC000番地の頭に来たときのCPU"""
    from sc61box.autotype import Typer

    m.write(0xC000, 0x37)
    t = Typer(m)
    t.add_mode("RUN")
    t.add_text(line + "\n")
    guard = bytearray(0x10000)
    guard[0xC000] = 1
    for _ in range(4000):
        if t.busy:
            t.step()
        if m.run(CLOCK // 1000, guard):
            return m.cpu
    raise AssertionError("C000番地に来ない")


def test_call_entry_registers_match_rom():
    """CALLで呼んだ先の頭では、ROMのある本体と同じくJが1、Rが58h"""
    from basic_diff import basic_machine

    cpu = _entry_registers(basic_machine(), "CALL &C000")
    assert cpu.ram[1] == 1 and cpu.r == 0x58
    if have_rom():
        rom = _entry_registers(boot()[0], "CALL &C000")
        assert rom.ram[1] == cpu.ram[1] and rom.r == cpu.r


def _answer_ms(m, line) -> float:
    """RUNモードでlineを打ち、ENTERを押してから液晶が終わりの形になるまでのミリ秒"""
    from basic_diff import lcd, play

    play(m, [("mode", "RUN"), ("wait", 1), ("type", line)])
    m.held.add("ENTER")
    c0, k, last, prev = m.cpu.cycles, 0, m.cpu.cycles, lcd(m)
    while m.cpu.cycles - c0 < CLOCK * 2:
        m.run(CLOCK // 2000)
        k += 1
        if k == 120:
            m.held.discard("ENTER")
        if lcd(m) != prev:
            prev, last = lcd(m), m.cpu.cycles
    return (last - c0) * 1000 / CLOCK


def test_direct_statement_time_matches_rom():
    """RUNモードで打った文の時間はその行で使い、次に打つ行に残さない"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine

    for make in (lambda: boot()[0], basic_machine):
        m = make()
        first = _answer_ms(m, "POKE 50000,SIN 30")
        second = _answer_ms(m, "1")
        assert 330 < first < 420 and 70 < second < 95, (first, second)


def test_state_restore_continues_program():
    """どこでもセーブを戻すと、PRINTの待ち、FOR・GOSUBの続き、INPUTの待ち(打ちかけの字は
    消える)から続ける"""
    import json

    from basic_diff import basic_machine, lcd, play

    def restored(lines, before):
        m = basic_machine()
        play(m, _program(lines, before))
        m2 = basic_machine()
        m2.restore(json.loads(json.dumps(m.snapshot())))
        m2.run(CLOCK // 5)
        return m2

    m = restored(["10 FOR I=1 TO 3:GOSUB 30:NEXT I:END", "30 PRINT I:RETURN"],
                 ["RUN\n", ("wait", 1), "\n", ("wait", 1)])  # fmt: skip
    assert lcd(m).strip() == "2."
    looks = play(m, [("type", "\n"), ("look", None), ("type", "\n"), ("look", None)])
    assert [x.lcd.strip() for x in looks] == ["3.", ">"]
    m = restored(["10 INPUT A:PRINT A*2"], ["RUN\n", ("wait", 1), "3"])
    assert lcd(m).strip() == "?"
    assert play(m, [("type", "4\n"), ("look", None)])[0].lcd.strip() == "8."


def test_abbreviations_match_rom():
    """「P.」のような省略が、PROモードでもRUNモードでも、ROMのある本体と同じ命令になる"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    lines = [f"{i + 1} {head}." for i, head in enumerate(sorted(tokens.ABBREVIATIONS_1251))]
    lines += ["900 C=A.5:X=I.5:P.1", "910 PRINT.5:G.10:LET.", "920 F.I=1T.3:N.I"]
    steps = _program(lines, ["P.1\n", None, ["CL"], "SQ.4\n", None, ["CL"], "2*SI.30\n", None])
    a = play(boot()[0], steps)
    b = play(basic_machine(), steps)
    assert not differences(a, b), "\n".join(differences(a, b))


_DEF_PROGRAM_1 = ["10 PRINT 1"]
_DEF_PROGRAM_2 = [
    '10 "A" PRINT 1',
    '20 "S":AREAD X:PRINT X*2',
    '30 "D"',
    "40 PRINT 4",
    '50 "="PRINT 50',
    '60 " " PRINT 60',
    '70 "Q" PRINT 70',
    '80 "Z" AREAD Y$:PRINT Y$',
]
_DEF_PROGRAM_3 = [
    '10 "AB" PRINT 1',
    '20 "S" AREAD X$:PRINT X$',
    '30 A=1:"X":PRINT 3',
    '40 "D" PRINT 40',
    '50 "F" AREAD X:PRINT X',
]
_DEF_PROGRAM_4 = ['50 "F" AREAD X:PRINT X:PRINT B']
_DEF_PROGRAM_5 = ['10 "F" X=AREAD']
_DEF_PROGRAM_6 = ['10 "F" PRINT 1:AREAD X:PRINT X']
_DEF_PROGRAM_7 = ['10 "A" INPUT X:PRINT X*2', '20 "S" AREAD Y:PRINT Y+1', '30 "D" PRINT 4']
# AREADは、打っていた行を読むときに計算する(文字列の変数には字のまま)。誤りは打った行のエラー
_DEF_PROGRAM_9 = [
    '10 "M" AREAD A:PRINT A',
    '20 "N" AREAD A$:PRINT A$',
    '30 "P" PRINT 7:AREAD A:PRINT A',
]
_DEF_PROGRAM_8 = [
    '10 "A" INPUT X:PRINT X*2',
    '20 "S" PRINT 9',
    '30 "D" FOR I=1 TO 3:NEXT I:PRINT I',
]
RESERVE_CASES = [
    ([],
     [('mode', 'RSV'), ('wait', 1.5), None, ['SHIFT'], None, ['A'], None, 'PRINT ', None,
      ['ENTER'], None, ['SHIFT'], ['S'], 'X=1@', None, ['ENTER'], None, ('mode', 'RUN'),
      ('wait', 1.5), ['SHIFT'], ['A'], None, '5', None, ['ENTER'], None, ['CL'], ['DEF'], None,
      ['A'], None, ['CL'], ['DEF'], ['S'], None, ['ENTER'], None]),
    ([],
     [('mode', 'RSV'), ('wait', 1.5), ['SHIFT'], ['='], 'Q', ['ENTER'], ['SHIFT'], ['SPC'],
      'W', ['ENTER'], ['SHIFT'], ['S'], 'X=1@', ['ENTER'], ['SHIFT'], ['A'], 'PRINT ',
      ['ENTER'], ['SHIFT'], ['D'], '12345678901234567890123456789012345678901234567890',
      ['ENTER'], None, ('mode', 'RUN'), ('wait', 1.5), ['SHIFT'], ['S'], ('wait', 0.5), None,
      'X\n', None, ['CL'], ['SHIFT'], ['D'], None, ('mode', 'RSV'), ('wait', 1.5), ['SHIFT'],
      ['A'], None, ['LEFT'], None, 'Q', ['ENTER'], None, ['SHIFT'], ['A'], ['CL'], None,
      ['ENTER'], None]),
    ([],
     [('mode', 'RSV'), ('wait', 1.5), ['SHIFT'], ['A'], 'SIN ', ['ENTER'], None, ['LEFT'],
      None, ['RIGHT'], None, 'Q', None, ['CL'], None, ['SHIFT'], ['A'], None, ['ENTER'], None,
      ['SHIFT'], ['A'], ['LEFT'], ['LEFT'], 'X', None, ['ENTER'], None, ['SHIFT'], ['S'],
      '1+1@2', ['ENTER'], None, ['SHIFT'], ['D'], ['ENTER'], None, ['SHIFT'], ['S'], ['DOWN'],
      None, ['UP'], None, ('mode', 'RUN'), ('wait', 1.5), '2*', ['SHIFT'], ['A'], None, '30\n',
      None, '5\n', ['SHIFT'], ['A'], None, ['CL'], ['SHIFT'], ['S'], ('wait', 1), None,
      ('mode', 'PRO'), ('wait', 1.5), ['SHIFT'], ['A'], None]),
    ([],
     [('mode', 'RSV'), ('wait', 1.5), ['SHIFT'], ['A'], 'AB', ['ENTER'], ['SHIFT'], ['A'],
      ['ENTER'], None, ['SHIFT'], ['A'], ['CL'], ['ENTER'], None, ['SHIFT'], ['A'], None, 'Q',
      ['CL'], None, ['ENTER'], None]),
    ([],
     [('mode', 'RSV'), ('wait', 1.5), ['SHIFT'], ['A'], 'AB', ['ENTER'], ['SHIFT'], ['S'],
      'CD', ['ENTER'], ['SHIFT'], ['A'], 'Q', None, ['ENTER'], None, ['SHIFT'], ['A'],
      ['LEFT'], None, ['SHIFT'], ['LEFT'], None, ['ENTER'], None, ['SHIFT'], ['A'], None,
      ['CL'], ['SHIFT'], ['S'], ['RIGHT'], ['SHIFT'], ['LEFT'], ['LEFT'], ['SHIFT'], ['LEFT'],
      ['LEFT'], ['SHIFT'], ['LEFT'], None, ['ENTER'], None, '5', None, ['ENTER'], None]),
    (_DEF_PROGRAM_1,
     [('mode', 'RSV'), ('wait', 1.5), 'RUN\n', ('wait', 1), None, ['CL'], 'A=5\n', None,
      ['CL'], 'LIST\n', None, ['CL'], ['DEF'], ['A'], None, ['CL'], '1/0\n', ['LEFT'], None,
      ['CL'], ['SHIFT'], ['A'], '1/0@', ['ENTER'], None, ['SHIFT'], ['A'], None, ['RIGHT'],
      ['RIGHT'], ['RIGHT'], ['RIGHT'], ['RIGHT'], None, ['LEFT'], ['LEFT'], ['LEFT'], ['LEFT'],
      ['LEFT'], ['LEFT'], None, ['UP'], None]),
    (_DEF_PROGRAM_2,
     [['DEF'], None, ['A'], ('wait', 1), None, ['ENTER'], None, '7\n', ['DEF'], ['S'],
      ('wait', 1), None, ['ENTER'], '7', ['DEF'], ['S'], ('wait', 1), None, ['ENTER'], ['CL'],
      ['DEF'], ['S'], ('wait', 1), None, ['ENTER'], ['DEF'], ['D'], ('wait', 1), None,
      ['ENTER'], ['DEF'], ['='], ('wait', 1), None, ['ENTER'], ['DEF'], ['SPC'], ('wait', 1),
      None, ['ENTER'], ['DEF'], ['Q'], ('wait', 1), None, ['CL'], '"HI"\n', ['DEF'], ['Z'],
      ('wait', 1), None, ['ENTER'], '12+3\n', ['DEF'], ['S'], ('wait', 1), None]),
    (_DEF_PROGRAM_3,
     [['DEF'], None, ['DEF'], None, ['A'], ('wait', 1), None, ['CL'], '14\n', ['DEF'], ['S'],
      ('wait', 1), None, ['ENTER'], ['CL'], 'GOTO 30\n', ('wait', 1), None, ['CL'], ['DEF'],
      '5', None, ['CL'], '5', ['DEF'], ['ENTER'], None, ['CL'], '2+3', ['DEF'], ['F'],
      ('wait', 1), None, ['ENTER'], ['CL'], '"AB"\n', ['DEF'], ['F'], ('wait', 1), None,
      ['ENTER'], ['CL'], '1/0\n', ['DEF'], ['F'], ('wait', 1), None, ('mode', 'PRO'),
      ('wait', 1.5), ['DEF'], ['D'], ('wait', 1), None]),
    (_DEF_PROGRAM_4,
     [['CL'], 'B=4', ['DEF'], ['F'], ('wait', 1), None, ['ENTER'], ('wait', 1), None,
      ['ENTER'], ['CL'], 'PRINT 1', ['DEF'], ['F'], ('wait', 1), None, ['CL'], '1+', ['DEF'],
      ['F'], ('wait', 1), None, ['CL'], '3\n', '4', ['DEF'], ['F'], ('wait', 1), None,
      ['ENTER'], ['ENTER'], 'RUN\n', ('wait', 1), None, ['ENTER'], ['ENTER'], ['DEF'], ['F'],
      ('wait', 1), None]),
    (_DEF_PROGRAM_5,
     [['DEF'], ['F'], ('wait', 1), None]),
    (_DEF_PROGRAM_9,
     ['7Z751Z161?', ['DEF'], ['M'], ('wait', 1), None, ['LEFT'], None, ['CL'], '12+', ['DEF'],
      ['Q'], ('wait', 1), None, ['RIGHT'], None, ['CL'], '1+', ['DEF'], ['N'], ('wait', 1),
      None, ['ENTER'], None, ['CL'], 'A$', ['DEF'], ['M'], ('wait', 1), None, ['LEFT'], None,
      ['CL'], '3)', ['DEF'], ['P'], ('wait', 1), None, ['ENTER'], ('wait', 1), None]),
    (_DEF_PROGRAM_6,
     ['9\n', ['DEF'], ['F'], ('wait', 1), None, ['ENTER'], None]),
    (_DEF_PROGRAM_2,
     ['7\n', ['DEF'], ['S'], ('wait', 1), None, ['ENTER'], ('wait', 1), None, ['ENTER'],
      ('wait', 1), None]),
    (_DEF_PROGRAM_2,
     [['DEF'], ['D'], ('wait', 1), None, ['ENTER'], ('wait', 1), None]),
    (_DEF_PROGRAM_2,
     [['DEF'], ['='], ('wait', 1), None, ['ENTER'], ('wait', 1), None]),
    (_DEF_PROGRAM_2,
     [['DEF'], ['SPC'], ('wait', 1), None, ['ENTER'], ('wait', 1), None]),
    (_DEF_PROGRAM_2,
     [['DEF'], ['Q'], ('wait', 1), None, ['ENTER'], ('wait', 1), None]),
    (_DEF_PROGRAM_2,
     [['DEF'], ['A'], ('wait', 1), None, ['CL'], None, ['DEF'], ['S'], ('wait', 1), None]),
    (_DEF_PROGRAM_7,
     [['DEF'], ['A'], ('wait', 1), '5', ['DEF'], None, ['S'], ('wait', 1), None]),
    (_DEF_PROGRAM_7,
     [['DEF'], ['D'], ('wait', 1), ['DEF'], None, ['S'], ('wait', 1), None]),
    (_DEF_PROGRAM_7,
     [['DEF'], ['A'], ('wait', 1), ['DEF'], '7', None, ['ENTER'], ('wait', 1), None, ['ENTER'],
      None]),
    (_DEF_PROGRAM_7,
     [['DEF'], ['A'], ('wait', 1), ['DEF'], ['DEF'], None, '7', None, ['ENTER'], ('wait', 1),
      None]),
    (_DEF_PROGRAM_7,
     [['DEF'], ['D'], ('wait', 1), ['DEF'], '7', None, ['ENTER'], None, 'CONT\n', ('wait', 1),
      None]),
    (_DEF_PROGRAM_7,
     [['DEF'], ['D'], ('wait', 1), ['DEF'], ['ENTER'], ('wait', 1), None]),
    (_DEF_PROGRAM_7,
     [['DEF'], ['A'], ('wait', 1), ['DEF'], ['CL'], None, '3', ['ENTER'], ('wait', 1), None]),
    (_DEF_PROGRAM_7,
     [['DEF'], ['A'], ('wait', 1), ['SHIFT'], ['A'], None, ['ENTER'], ('wait', 1), None]),
    (_DEF_PROGRAM_8,
     [['DEF'], ['A'], ('wait', 1), None, ['DEF'], None, ['S'], ('wait', 1), None, ['ENTER'],
      ('wait', 1), None]),
    (_DEF_PROGRAM_8,
     [('mode', 'RSV'), ('wait', 1), ['SHIFT'], ['A'], '12', ['ENTER'], ['ENTER'],
      ('mode', 'RUN'), ('wait', 1.5), ['DEF'], ['A'], ('wait', 1), ['SHIFT'], ['A'], None,
      ['ENTER'], ('wait', 1), None, ['DEF'], ['S'], ('wait', 1), ['SHIFT'], ['A'], None,
      ['ENTER'], None]),
]  # fmt: skip


@pytest.mark.parametrize("index", range(len(RESERVE_CASES)))
def test_reserve_and_def_match_rom(index):
    """RSVモードでの登録と編集、SHIFTのあとのリザーブのキー、DEFのキーとAREADが、ROMの
    ある本体と同じ(リザーブを置くRAMも比べる)"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    from sc61box.basic.pc1251 import reserve
    from sc61box.machine import MODELS

    has_rsv = "RSV" in MODELS[helpers.MODEL].modes
    if not has_rsv and ("mode", "RSV") in RESERVE_CASES[index][1]:
        pytest.skip(f"PC-{helpers.MODEL}にはRSVモードがない")
    steps = _program(*RESERVE_CASES[index])
    ma, mb = boot()[0], basic_machine()
    a = play(ma, steps)
    b = play(mb, steps)
    assert not differences(a, b), "\n".join(differences(a, b))
    if has_rsv:
        lo, hi = reserve.PC1251.area(mb)
        assert bytes(ma.mem[lo:hi]) == bytes(mb.mem[lo:hi])


SHIFT_KEY_CASES = [
    # PC-1245はSHIFTのあとリザーブの位置のキーで命令を打つ(PC-1251は登録がなければキーの字)
    (["10 INPUT A$:PRINT A$"],
     [["SHIFT"], ["G"], None, ["CL"], ("mode", "PRO"), ("wait", 1.5), "20 ", ["SHIFT"], ["Z"],
      '"X"\n', None, ("mode", "RUN"), ("wait", 1.5), "RUN\n", None, ["SHIFT"], ["S"], None,
      "\n", None, "\n", None, ["SHIFT"], ["SPC"], ["SHIFT"], ["="], None, "\n", ("wait", 1),
      None]),
    # 文字列に入った命令は1バイトで、PRINTではLISTと同じ綴りで出す(観察)
    (["10 INPUT A$:PRINT LEN A$:PRINT A$"],
     ["RUN\n", ["SHIFT"], ["S"], "1\n", None, "\n", None, "\n", ["CL"], "RUN\n", ["SHIFT"],
      ["SPC"], "\n", None, "\n", None]),
]  # fmt: skip


@pytest.mark.parametrize("index", range(len(SHIFT_KEY_CASES)))
def test_shift_keys_match_rom(index):
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    steps = _program(*SHIFT_KEY_CASES[index])
    a = play(boot()[0], steps)
    b = play(basic_machine(), steps)
    assert not differences(a, b), "\n".join(differences(a, b))


PASS_CASES = [
    ([],
     [('mode', 'PRO'), ('wait', 1.5), 'PASS "X"\n', None, ['CL'], None, '10 A=1\n', None,
      'PASS "X"\n', None, 'PASS "Y"\n', None, ['CL'], None, 'PASS "X"\n', None, 'PASS ""\n',
      None, 'PASS "Z"\n', None, ['CL'], None, 'PASS ""\n', None]),
    (['10 PRINT 1', '20 PRINT 2'],
     [('mode', 'PRO'), ('wait', 1.5), 'PASS ""\n', None, 'LIST\n', None, ['CL'], None,
      'PASS "A"\n', None, ['CL'], None, 'PASS ""\n', None, 'LIST\n', None]),
    (['10 PRINT 1', '20 PRINT 2'],
     [('mode', 'PRO'), ('wait', 1.5), 'PASS "AB":A=1\n', None, ['CL'], None, 'PASS "AB" A\n',
      None, ['CL'], None, 'PASS "AB\n', None, 'PASS "AB\n', None, 'PASS "AB":\n', None]),
    (['10 PRINT 1', '20 PRINT 2'],
     [('mode', 'PRO'), ('wait', 1.5), 'PASS "AB"\n', None, 'NEW\n', None, 'LIST\n', None,
      '10 A=1\n', None, 'PASS "AB"\n', None, 'PASS "AB"\n', None, 'NEW\n', None]),
    (['10 PRINT 1', '20 PRINT 2'],
     ['PASS "AB"\n', None, 'RUN\n', None, ['ENTER'], None, ['ENTER'], None, 'CONT\n', None,
      ['CL'], None, 'A=5\n', None, 'PRINT A\n', None, 'PASS "AB"\n', None, 'LIST\n', None]),
    (['10 PASS "Q"', '20 PRINT 3'],
     ['RUN\n', None, ['ENTER'], None, ('mode', 'PRO'), ('wait', 1.5), 'LIST\n', None]),
    (['10 PRINT 1', '20 PRINT 2'],
     [('mode', 'PRO'), ('wait', 1.5), 'PASS "AB"\n', None, ('mode', 'RSV'), ('wait', 1.5),
      'PASS "AB"\n', None, ['CL'], None, ('mode', 'PRO'), ('wait', 1.5), 'LIST\n', None]),
    (['10 PRINT 1', '20 PRINT 2'],
     [('mode', 'PRO'), ('wait', 1.5), 'PASS "AB"\n', None, 'PASS "ABC"\n', None, ['CL'], None,
      'PASS "A"\n', None, ['CL'], None, 'PASS "B"\n', None, ['CL'], None, 'PASS "AB"\n', None]),
    (['10 PRINT 1', '20 PRINT 2'],
     [('mode', 'PRO'), ('wait', 1.5), 'PASS "ABCDEFG"\n', None, 'PASS "ABCDEFGH"\n', None,
      'PASS "ABCDEFGH"\n', None, 'PASS "ABCDEF"\n', None]),
    (['10 PRINT 1', '20 PRINT 2'],
     [('mode', 'PRO'), ('wait', 1.5), 'PASS "AB"\n', None, 'LIST 20\n', None, ['CL'], None,
      'LIST 15\n', None, ['CL'], None, ['UP'], None, ['DOWN'], None, '20\n', None,
      '20 PRINT 5\n', None, 'RUN\n', None, ['CL'], None, 'MEM\n', None]),
    (['10 A=1', '20 B=1/0'],
     ['PASS "AB"\n', None, 'RUN\n', None, ['UP'], None, ['CL'], None, ['UP'], None,
      ('mode', 'PRO'), ('wait', 1.5), ['UP'], None, ['DOWN'], None, ['CL'], None, ['UP'],
      None]),
    (['10 A=1', '20 B=1/0'],
     ['RUN\n', None, ['UP'], None, ['CL'], None, ['UP'], None, ('mode', 'PRO'), ('wait', 1.5),
      ['UP'], None, ['DOWN'], None, ['CL'], None, ['UP'], None]),
    (['10 PRINT 1', '20 PRINT 2'],
     ['PASS "AB"\n', None, 'RUN\n', None, ['UP'], None, ['CL'], None, 'TRON\n', None, 'RUN\n',
      None, ['DOWN'], None, 'TROFF\n', None, 'CONT\n', None]),
    (['10 PRINT 1', '20 PRINT 2'],
     ['RUN\n', None, ['ENTER'], None, ['ENTER'], None, 'CONT\n', None]),
    (['10 PRINT 1', '20 PRINT 2', '30 PRINT 3'],
     ['TRON\n', None, 'RUN\n', None, ['DOWN'], None, 'CONT\n', None, ['ENTER'], None,
      ['ENTER'], None]),
    (['10 PRINT 1', '20 PRINT 2', '30 PRINT 3'],
     ['RUN\n', None, ['DOWN'], None, 'CONT\n', None, ['ENTER'], None, ['ENTER'], None]),
    (['10 PRINT 1', '20 PRINT 2', '30 PRINT 3'],
     ['RUN\n', None, ['DOWN'], None, ['DOWN'], None, ['DOWN'], None, ['DOWN'], None]),
    (['10 A=1:STOP', '20 B=2', '30 PRINT 3'],
     ['RUN\n', None, ['DOWN'], None, ['DOWN'], None, ['DOWN'], None]),
    (['10 A=1:STOP:B=5', '20 B=2', '30 PRINT 3'],
     ['RUN\n', None, ['DOWN'], None, ['DOWN'], None, ['DOWN'], None]),
    (['10 A=1:STOP', '20 B=2', '30 PRINT 3'],
     ['RUN\n', None, 'CONT\n', None]),
    (['10 A=1', '20 A=2', '30 A=3'],
     ['A=0\n', None, 'TRON\n', None, 'RUN\n', None, 'CONT\n', None, 'A\n', None]),
    (['10 A=1', '20 A=2', '30 A=3'],
     ['A=0\n', None, 'TRON\n', None, 'RUN\n', None, ['DOWN'], None, 'CONT\n', None, 'A\n',
      None]),
    (['10 A=1', '20 A=2', '30 A=3'],
     ['A=0\n', None, 'TRON\n', None, 'RUN\n', None, ['DOWN'], None, ['DOWN'], None, 'A\n',
      None]),
    (['10 A=1:STOP', '20 A=2', '30 A=3:STOP:A=4'],
     ['A=0\n', None, 'RUN\n', None, ['DOWN'], None, 'CONT\n', None, 'A\n', None]),
    (['10 A=1:STOP', '20 A=2', '30 A=3:STOP:A=4'],
     ['A=0\n', None, 'RUN\n', None, ['DOWN'], None, ['CL'], None, 'CONT\n', None, 'A\n', None]),
    (['10 A=1:STOP', '20 A=2', '30 A=3:STOP:A=4'],
     ['A=0\n', None, 'RUN\n', None, ['DOWN'], None, ['CL'], None, ['DOWN'], None, 'A\n', None]),
    (['10 PRINT 1', '20 A=2', '30 A=3'],
     ['A=0\n', None, 'RUN\n', None, ['DOWN'], None, 'CONT\n', None, 'A\n', None, 'CONT\n',
      None, 'A\n', None]),
    (['10 PRINT 1', '20 A=2', '30 A=3'],
     ['A=0\n', None, 'RUN\n', None, ['DOWN'], None, ['CL'], None, 'CONT\n', None, 'A\n', None]),
    (['10 PRINT 1', '20 A=2', '30 A=3'],
     ['A=0\n', None, 'RUN\n', None, ['DOWN'], None, 'CONT\n', None, ['DOWN'], None, 'A\n',
      None]),
    (['10 INPUT B', '20 A=2', '30 A=3'],
     ['A=0\n', None, 'RUN\n', None, ['DOWN'], None, 'CONT\n', None, 'A\n', None]),
    (['10 B=1/0', '20 A=1'],
     ['RUN\n', None, ('mode', 'PRO'), ('wait', 1.5), ['UP'], None, ['UP'], None, ['DOWN'],
      None, ['UP'], None]),
    (['10 A=1', '20 B=1/0'],
     ['RUN\n', None, ('mode', 'PRO'), ('wait', 1.5), ['DOWN'], None, ['DOWN'], None, ['UP'],
      None]),
]  # fmt: skip


@pytest.mark.parametrize("index", range(len(PASS_CASES)))
def test_password_and_stepping_match_rom(index):
    """PASSで保護したときと外したときのふるまい(パスワードを置くRAMと保護のビットも比べる)と、
    ↓で1行ずつ進めたあとのCONTと↓が、ROMのある本体と同じ"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    from sc61box.basic.pc1251 import password

    steps = _program(*PASS_CASES[index])
    ma, mb = boot()[0], basic_machine()
    a = play(ma, steps)
    b = play(mb, steps)
    assert not differences(a, b), "\n".join(differences(a, b))
    p = password.PC1251
    store = slice(p.STORE, p.STORE + 1 + p.SIZE)
    assert bytes(ma.mem[store]) == bytes(mb.mem[store])
    assert p.locked(ma) == p.locked(mb)


PRINTER_CASES = [
    (['10 LPRINT "B",'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LPRINT USING "###.##";1.5;2'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LPRINT "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123";1'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LPRINT 1;"ABCDEFGHIJKLMNOPQRSTUVWXYZ"'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LPRINT "ABCDEFGHIJKLMNOPQRSTU",1'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LPRINT 1,"ABCDEFGHIJKLMNO"'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LPRINT "ABCDEFGHIJKLMNO",1'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LPRINT 12345678901'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LPRINT 1E99;-1E-99'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LPRINT "A","B","C"'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LPRINT 1;2;3;4;5;6;7;8;9'],
     ['RUN\n', ('wait', 1), None]),
    (['10 USING "##.#":LPRINT 1.25:LPRINT USING;1.25'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LPRINT "AB";1;"C"'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LPRINT "ABCDEFGHIJKLMNOPQRSTUVWX"'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LPRINT "ABCDEFGHIJKLMNOPQRSTUVWXY"'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LPRINT 1:LPRINT 2'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LPRINT CHR$ 39;CHR$ 91;CHR$ 92;CHR$ 93;CHR$ 94;CHR$ 95;CHR$ 96'],
     ['RUN\n', ('wait', 1), None]),
    (['10 A$="X":LPRINT A$;A$'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LPRINT 1,'],
     ['RUN\n', ('wait', 1), None]),
    (['10 LPRINT ,1'],
     ['RUN\n', ('wait', 1), None]),
    (['10 PRINT 1'],
     [('mode', 'PRO'), ('wait', 1.5), 'LLIST\n', ('wait', 1), None, ['CL'], None, 'LLIST 10\n',
      ('wait', 1), None, ['CL'], None, 'LLIST 10,20\n', ('wait', 1), None, ['CL'], None,
      ('mode', 'RUN'), ('wait', 1.5), 'LLIST\n', ('wait', 1), None, ['CL'], None, 'LLIST 10\n',
      ('wait', 1), None]),
    (['10 FOR I=1 TO 2', '20 LPRINT I', '30 NEXT I',
      '40 PRINT "AB";"CDEFGHIJKLMNOPQRSTUVWXYZ0123456789"',
      '50 A$="ABCDEFGHIJKLMNOPQRSTUVWXYZ":B=1:C=2:D=3:E=4:F=5:G=6:H=7:I=8'],
     [('mode', 'PRO'), ('wait', 1.5), 'LLIST\n', ('wait', 4), None]),
    (['10 PRINT 1', '20 A=1', '30 B=2'],
     [('mode', 'PRO'), ('wait', 1.5), 'LLIST 10,10\n', ('wait', 1.5), None, ['CL'], None]),
    (['10 PRINT 1', '20 A=1', '30 B=2'],
     [('mode', 'PRO'), ('wait', 1.5), 'LLIST 10,30\n', ('wait', 1.5), None, ['CL'], None]),
    (['10 PRINT 1', '20 A=1', '30 B=2'],
     [('mode', 'PRO'), ('wait', 1.5), 'LLIST 10,25\n', ('wait', 1.5), None, ['CL'], None]),
    (['10 PRINT 1', '20 A=1', '30 B=2'],
     [('mode', 'PRO'), ('wait', 1.5), 'LLIST 5,10\n', ('wait', 1.5), None, ['CL'], None]),
    (['10 PRINT 1', '20 A=1', '30 B=2'],
     [('mode', 'PRO'), ('wait', 1.5), 'LLIST ,20\n', ('wait', 1.5), None, ['CL'], None]),
    (['10 PRINT 1', '20 A=1', '30 B=2'],
     [('mode', 'PRO'), ('wait', 1.5), 'LLIST 20,10\n', ('wait', 1.5), None, ['CL'], None]),
    (['10 PRINT 1', '20 A=1', '30 B=2'],
     [('mode', 'PRO'), ('wait', 1.5), 'LLIST 15,25\n', ('wait', 1.5), None, ['CL'], None]),
    (['10 PRINT 1', '20 A=1', '30 B=2'],
     [('mode', 'PRO'), ('wait', 1.5), 'LLIST 10,20,30\n', ('wait', 1.5), None, ['CL'], None]),
    (['10 PRINT 1', '20 A=1', '30 B=2'],
     [('mode', 'PRO'), ('wait', 1.5), 'LLIST 0,10\n', ('wait', 1.5), None, ['CL'], None]),
    (['10 PRINT 1'],
     [('mode', 'RSV'), ('wait', 1.5), 'LLIST\n', ('wait', 1.5), None, ['CL'], None]),
    (['10 PRINT 1'],
     [('mode', 'PRO'), ('wait', 1.5), 'PASS "A"\n', None, 'LLIST\n', ('wait', 1.5), None,
      'LLIST 10,10\n', ('wait', 1.5), None]),
]  # fmt: skip
NO_PRINTER_CASES = [
    (['10 LPRINT 1', '20 PRINT 2'],
     ['RUN\n', ('wait', 3), None, ['CL'], 'LLIST\n', ('wait', 3), None, ['CL'],
      ('mode', 'PRO'), ('wait', 1.5), 'LLIST\n', ('wait', 3), None, 'LLIST 10,10\n', None]),
    (['10 LPRINT 1', '20 PRINT 2'],
     ['RUN\n', None, ('wait', 0.3), None, ('wait', 0.5), None]),
    (['10 FOR I=1 TO 20:LPRINT I:NEXT I', '20 PRINT 2'],
     ['RUN\n', None, ('wait', 0.5), None, ('wait', 1), None]),
    (['10 PRINT 1'],
     [('mode', 'PRO'), ('wait', 1.5), 'LLIST 10\n', None, ['CL'], 'LLIST 5,10\n', None, ['CL'],
      'LLIST X\n', None]),
    (['10 LPRINT 1/0', '20 PRINT 2'],
     ['RUN\n', ('wait', 0.5), None]),
    (['10 LPRINT "A",', '20 PRINT 2'],
     ['RUN\n', ('wait', 0.5), None]),
    (['10 LPRINT X$+1', '20 PRINT 2'],
     ['RUN\n', ('wait', 0.5), None]),
    (['10 A=0:LPRINT 1:A=5', '20 PRINT A'],
     ['RUN\n', ('wait', 0.5), None]),
    (['10 A=0:LPRINT "X:A=5":A=7', '20 PRINT A'],
     ['RUN\n', ('wait', 0.5), None]),
]  # fmt: skip


def _printer_machine(rom: bool):
    """プリンタをつないだ本体(PC-1251は電源を入れたときにプリンタを調べるので入れ直す)"""
    from basic_diff import basic_machine

    m = boot()[0] if rom else basic_machine()
    m.connect_printer()
    m.power_off()
    m.mode = "RUN"
    m.wake()
    m.run(CLOCK)
    return m


@pytest.mark.parametrize("index", range(len(PRINTER_CASES)))
def test_printer_matches_rom(index):
    """LPRINTとLLISTの印字(プリンタに送るコードと行の分け方)と液晶が、ROMのある本体と同じ"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import differences, play

    steps = _program(*PRINTER_CASES[index])
    ma, mb = _printer_machine(True), _printer_machine(False)
    a = play(ma, steps)
    b = play(mb, steps)
    assert not differences(a, b), "\n".join(differences(a, b))
    assert ma.printer is not None and mb.printer is not None
    assert ma.printer.rows() == mb.printer.rows()


@pytest.mark.parametrize("index", range(len(NO_PRINTER_CASES)))
def test_without_printer_matches_rom(index):
    """プリンタがなければ、LPRINTとLLISTは何もしない(ROMのある本体と同じ)"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    steps = _program(*NO_PRINTER_CASES[index])
    a = play(boot()[0], steps)
    b = play(basic_machine(), steps)
    assert not differences(a, b), "\n".join(differences(a, b))


def test_printing_time_matches_rom():
    """LPRINTとLLISTで送り終わるまでの時間が、ROMのある本体と10%以内で同じ"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import play

    def took(rom, lines, command, mode):
        m = _printer_machine(rom)
        play(m, _program(lines, [("mode", mode), ("wait", 1.5)] if mode == "PRO" else []))
        times = []
        printer = m.printer
        assert printer is not None
        orig = printer.put

        def put(code):
            times.append(m.cpu.cycles)
            orig(code)

        printer.put = put
        start = m.cpu.cycles
        play(m, [("type", command), ("wait", 4)])
        return (times[-1] - start) / CLOCK

    lines = ['10 LPRINT "ABCDEFGHIJKLMNOPQRSTUVWXYZ";1', "20 LPRINT 1,2:LPRINT 3"]
    for command, mode in (("RUN\n", "RUN"), ("LLIST\n", "PRO")):
        a, b = took(True, lines, command, mode), took(False, lines, command, mode)
        assert abs(b - a) / a < 0.1, (command, a, b)


AUTO_OFF_CASES = [
    ([], ["12"]),
    (["10 PRINT 1", "20 PRINT 2"], ["RUN\n"]),
    (["10 INPUT A"], ["RUN\n"]),
]


@pytest.mark.parametrize("index", range(len(AUTO_OFF_CASES)))
def test_auto_power_off_matches_rom(index):
    """キーを待ったまま約11分たつと電源が切れ、ONキーで入れると、液晶もキーを待っていた
    ところもそのままで続く(ROMのある本体と同じ)"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    lines, actions = AUTO_OFF_CASES[index]
    after = [["ENTER"], None, "3\n", None]
    out = []
    for m in (boot()[0], basic_machine()):
        play(m, _program(lines, actions))
        start = m.cpu.cycles
        while m.power and m.cpu.cycles - start < 700 * CLOCK:
            m.run(CLOCK // 10)
        took = (m.cpu.cycles - start) / CLOCK
        m.brk = True
        m.run(CLOCK // 10)
        m.brk = False
        out.append((took, play(m, [("wait", 1), ("look", None)] + _program([], after)[4:])))
    (ta, a), (tb, b) = out
    assert ta < 700 and abs(ta - tb) < 2, (ta, tb)
    assert not differences(a, b), "\n".join(differences(a, b))


def _tape_bits(m, since: int) -> list[int]:
    """Cポートの音の切り替え(サイクルsinceから)を、2msごとのビットの並びにする"""
    from sc61box.basic.pc1251 import cassette

    ev = [(c, v) for c, v in m.sound_events if c >= since]
    out: list[int] = []
    for (c, v), (c2, _) in zip(ev, ev[1:], strict=False):
        if v in (cassette.ONE, cassette.ZERO):
            out += [1 if v == cassette.ONE else 0] * round((c2 - c) / cassette.BIT)
    while out and out[0] == 1:  # 初めの1の長さはROMでも1ビットほど揺れる
        out.pop(0)
    return out


CSAVE_CASES = [
    (["10 PRINT 1", "20 A=5"], 'CSAVE "AB"\n'),
    (["10 PRINT 1", '20 A$="ABCDEFGHIJKLMNOP":B=12345', "30 PRINT A$;B"], 'CSAVE "ABCDEFGHI"\n'),
    (["10 PRINT 1"], "CSAVE\n"),
    (["10 PRINT 1"], 'CSAVE M "Q";&C000,&C00F\n'),
    (["10 PRINT 1"], "CSAVE M &B830,&B838\n"),
    (['10 CSAVE "Z"', "20 PRINT 7"], "RUN\n"),
    (["10 CSAVE M &C000,&C05F"], "RUN\n"),
    ([f'{n} A$="ABCDEFGHIJKLMNOP":B=12345' for n in range(10, 100, 10)], 'CSAVE "LONG"\n'),
]


@pytest.mark.parametrize("index", range(len(CSAVE_CASES)))
def test_csave_matches_rom(index):
    """CSAVEとCSAVE Mでカセットに送る音(ビットの並び)と、終わって>を出す時刻が、ROMの
    ある本体と同じ"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    lines, command = CSAVE_CASES[index]
    out = []
    for m in (boot()[0], basic_machine()):
        for i in range(96):  # チェックサムがオーバーフローするように、大きな値を多く置く
            m.mem[0xC000 + i] = (0xFF, 0xEE, 0xF8, 0x8F, i * 37 & 0xFF)[i % 5]
        play(m, _program(lines, []))
        start = m.cpu.cycles
        looks = play(m, [("type", command), ("wait", 25), ("look", None)])
        out.append((_tape_bits(m, start), looks, max(c for c, _ in m.sound_events) - start))
    (bits_a, a, end_a), (bits_b, b, end_b) = out
    assert len(bits_a) > 100 and bits_a == bits_b
    assert not differences(a, b), "\n".join(differences(a, b))
    assert abs(end_a - end_b) < CLOCK // 20


@pytest.fixture(scope="module")
def rom_tapes(tmp_path_factory):
    """ROMのある本体にCSAVEさせたテープ(wav)"""
    if not have_rom():
        pytest.skip("ROMがない")
    from sc61box import tape

    d = tmp_path_factory.mktemp("tapes")
    out = {}
    for name, lines, command, poke in (
        ("ab", ["10 PRINT 1", "20 A=5"], 'CSAVE "AB"', False),
        ("cd", ["30 PRINT 3", '40 B=7:C$="XYZ"'], 'CSAVE "CD"', False),
        ("m", ["10 PRINT 1"], 'CSAVE M "Q";&C000,&C00F', True),
        (
            "long",
            [f'{n} A$="ABCDEFGHIJKLMNOP":B=12345' for n in range(10, 100, 10)],
            'CSAVE "LONG"',
            False,
        ),
        ("mlong", ["10 PRINT 1"], 'CSAVE M "R";&C000,&C05F', True),
    ):
        m, t = boot()
        if poke:  # チェックサムがオーバーフローするように、大きな値を多く置く
            for i in range(96):
                m.mem[0xC000 + i] = (0xFF, 0xEE, 0xF8, 0x8F, i * 37 & 0xFF)[i % 5]
        t.add_mode("PRO")
        t.add_text("NEW\n")
        t.add_program("\n".join(lines) + "\n")
        t.add_mode("RUN")
        finish(m, t)
        m.run(CLOCK * 3 // 2)
        path = str(d / f"{name}.wav")
        tape.write_wav(path, tape.record(m, command))
        out[name] = path
    # チェックサムの合わないテープ(中身を1ビット変えたもの)
    from sc61box.basic.pc1251 import cassette

    program = bytes.fromhex("E010C14100E02051344500E030C1414200")
    machine = bytes(range(0, 0xF0, 0x0F))
    for name, kind, data, place, flip, cut in (
        ("bad", cassette.BASIC, program, b"", 12, None),
        ("badm", cassette.MACHINE, machine, cassette.place_field(0xC000, 16), 22, None),
        ("badhead", cassette.BASIC, program, b"", 9, None),
        ("cutm", cassette.MACHINE, machine, cassette.place_field(0xC000, 16), None, 14),
        ("cutm2", cassette.MACHINE, machine, cassette.place_field(0xC000, 16), None, 24),
        ("cut", cassette.BASIC, program, b"", None, 15),
    ):
        raw = bytearray(cassette.file_bytes(kind, bytes([0x51, 0x52]), data, place))
        if flip is not None:
            raw[flip] ^= 0x01
        bits = cassette.bits(bytes(raw))
        if cut is not None:  # テープを途中で切る(1バイトは19ビット)
            bits = bits[: cassette.LEADER + 19 * cut]
        events, c, mode = [], CLOCK // 5, -1
        for bit in bits:
            want = cassette.ONE if bit else cassette.ZERO
            if want != mode:
                events.append((c, want))
                mode = want
            c += cassette.BIT
        events.append((c, 0))
        path = str(d / f"{name}.wav")
        tape.write_wav(path, tape.render(events, 0, c + CLOCK // 3))
        out[name] = path
    return out


CLOAD_CASES = [
    (["5 X=1"], "ab", "CLOAD\n"),
    (["5 X=1"], "ab", 'CLOAD "AB"\n'),
    (["5 X=1"], "ab", 'CLOAD "XY"\n'),
    (["10 PRINT 1", "20 A=5"], "ab", 'CLOAD? "AB"\n'),
    (["10 PRINT 1", "20 A=6"], "ab", "CLOAD?\n"),
    (["5 X=1"], "m", "CLOAD M\n"),
    (["5 X=1"], "m", 'CLOAD M "Q";&C004\n'),
    (["5 X=1"], "m", "CLOAD M &C008\n"),
    (["5 X=1"], "ab", "CLOAD M\n"),
    (["5 X=1"], "m", "CLOAD\n"),
    (["5 X=1", "30 Y=2"], "cd", "MERGE\n"),
    (['10 CHAIN "AB"', "20 PRINT 7"], "ab", "RUN\n"),
    (["10 A=3", '20 CHAIN "CD",40', "30 PRINT 7"], "cd", "RUN\n"),
    (['10 CLOAD "AB"'], "ab", "RUN\n"),
    (["5 X=1"], None, "CLOAD\n"),
    (["5 X=1", "7 Y=2:Z=3"], "bad", 'CLOAD "AB"\n'),
    (["5 X=1", "7 Y=2:Z=3"], "bad", "MERGE\n"),
    (["5 X=1", "7 Y=2:Z=3"], "bad", "CLOAD?\n"),
    (["5 X=1"], "badm", "CLOAD M\n"),
    (["5 X=1"], "badhead", "CLOAD\n"),
    (["5 X=1"], "long", "CLOAD\n"),
    (["5 X=1"], "mlong", "CLOAD M\n"),
    (["5 X=1"], "cut", "CLOAD\n"),
    (["5 X=1"], "cutm", "CLOAD M\n"),
    (["5 X=1"], "cutm2", "CLOAD M\n"),
]


@pytest.mark.parametrize("index", range(len(CLOAD_CASES)))
def test_cload_matches_rom(index, rom_tapes):
    """CLOAD・CLOAD?・CLOAD M・MERGE・CHAINで、ROMのある本体が録ったテープを読んだ結果
    (液晶、プログラム、変数、マシン語を置いたRAM)と時刻が、ROMのある本体と同じ"""
    from basic_diff import basic_machine, differences, play

    from sc61box import tape

    lines, name, command = CLOAD_CASES[index]
    out = []
    for m in (boot()[0], basic_machine()):
        play(m, _program(lines, []))
        if name is not None:
            m.tape = tape.TapeIn(rom_tapes[name])
        looks = play(m, [("type", command)] + [("wait", 2.35), ("look", None)] * 7)
        m.brk = True  # 待ち続けていれば、BRKで止める
        m.run(CLOCK * 3 // 10)
        m.brk = False
        looks += play(m, [("wait", 0.5), ("look", None)])
        out.append((looks, bytes(m.mem[0xC000:0xC060])))
    (a, ram_a), (b, ram_b) = out
    assert not differences(a, b), "\n".join(differences(a, b))
    assert ram_a == ram_b


@pytest.mark.parametrize("place", ["&B000", "&7FF8", "&FFF8"])
def test_cload_m_writes_like_the_bus(place, rom_tapes):
    """CLOAD Mは本体の書き込みと同じに置く(ROMの番地には置かず、ミラーの番地は元の
    RAMに置く)。ROMのある本体と同じ"""
    from basic_diff import basic_machine, play

    from sc61box import tape

    out = []
    for m in (boot()[0], basic_machine()):
        play(m, _program(["5 X=1"], []))
        before = bytes(m.mem[:0xC600])
        m.tape = tape.TapeIn(rom_tapes["m"])
        play(m, [("type", f'CLOAD M "Q";{place}\n'), ("wait", 14)])
        after = bytes(m.mem[:0xC600])
        out.append([(a, after[a]) for a in range(0xC600) if after[a] != before[a]])
    assert out[0] == out[1]


def test_csave_break_in_program_stops_sound():
    """プログラムの中のCSAVEをBRKで止めると、音を止めて「BREAK IN 行番号」を出す
    (ROMのある本体と同じ)"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    out = []
    for m in (boot()[0], basic_machine()):
        play(m, _program(['10 CSAVE "Z"', "20 PRINT 7"], ["RUN\n", ("wait", 3)]))
        m.brk = True
        m.run(CLOCK * 6 // 10)  # 初めの1のあいだ、BRKは約500msごとに見る
        m.brk = False
        looks = play(m, [("wait", 1), ("look", None)])
        out.append((looks, m.pc_out & 0xF0))
    (a, sound_a), (b, sound_b) = out
    assert sound_a == sound_b == 0
    assert not differences(a, b), "\n".join(differences(a, b))


def test_state_restore_keeps_def_and_auto_off():
    """どこでもセーブは、DEFの記号を出している状態、AREADに渡す答え、自動で電源が
    切れるまでの時間と切れた状態も保存する"""
    import json

    from basic_diff import basic_machine, lcd, play

    def restored(m):
        m2 = basic_machine()
        m2.restore(json.loads(json.dumps(m.snapshot())))
        m2.run(CLOCK // 5)
        return m2

    # DEFを押したところで保存し、戻してからラベルのキーを押す。答えの5がAREADに渡る
    m = basic_machine()
    play(m, _program(['10 "A" AREAD X:PRINT X*2'], ["5\n", ["DEF"], ("wait", 0.5)]))
    state = json.loads(json.dumps(m.snapshot()))
    m.restore(state)  # 同じ本体に戻しても、DEFの記号は消えない
    assert "DEF" in m.symbols()
    m = restored(m)
    assert "DEF" in m.symbols()
    assert play(m, [("keys", ["A"]), ("wait", 1), ("look", None)])[0].lcd.strip() == "10."
    # 自動で電源が切れるまでの時間は、戻しても続きから数える
    m = basic_machine()
    play(m, _program(["10 PRINT 1"], ["RUN\n", ("wait", 600)]))
    m = restored(m)
    m.run(CLOCK * 60)
    assert not m.power
    # 切れたところで保存して戻し、ONキーで入れると、PRINTの待ちから続ける
    m = restored(m)
    m.brk = True
    m.run(CLOCK // 10)
    m.brk = False
    m.run(CLOCK // 2)
    assert m.power and lcd(m).strip() == "1."
    assert play(m, [("keys", ["ENTER"]), ("look", None)])[0].lcd.strip() == ">"


def test_call_into_missing_rom_routine_stops():
    """CALLの先のマシン語が、ROMなしに代替ROMルーチンのないROMのルーチンへ入ると、そこでやめて
    BASICに戻る(プログラムの中ならBREAKで、CONTで次から続く。行番号なしならそのまま>)。
    番地はbasic.noticeで本体の外に知らせる"""
    from basic_diff import basic_machine, play

    m = basic_machine()
    lines = ["10 POKE &C200,2,1,255,160,55", "20 CALL &C200", "30 PRINT 5"]
    looks = play(m, _program(lines, ["RUN\n", ("wait", 1), None, "CONT\n", ("wait", 1), None]))
    basic = m.basic
    assert basic is not None
    assert [x.lcd.strip() for x in looks] == ["BREAK IN 20", "5."]
    assert basic.notice == 0x1FA0
    basic.notice = None
    looks = play(m, [("keys", ["CL"]), ("type", "CALL &C200\n"), ("wait", 1), ("look", None)])
    assert looks[0].lcd.strip() == ">" and basic.notice == 0x1FA0


DISPLAY_CASES = [
    (["10 FOR I=1 TO 30:NEXT I"], "RUN\n"),
    (["10 PRINT 1"], "RUN\n"),
    (["10 WAIT 64:PRINT 1:PRINT 2"], "RUN\n"),
    (["10 PAUSE 1:A=1"], "RUN\n"),
    (["10 BEEP 1"], "RUN\n"),
    (["10 X$=INKEY$:GOTO 10"], "RUN\n"),
    (["10 INPUT A"], "RUN\n"),
    ([], "1+2\n"),
    ([], "\n"),
    # CALLで液晶を点けると、そのあとの文のあいだも点けたまま(見本noise.basの使い方)
    (["10 POKE &C200,18,95,97,1,223,55:CALL &C200:FOR I=1 TO 30:NEXT I"], "RUN\n"),
]


def _dark_spans(m, text: str) -> list[tuple[int, int]]:
    """textを打ってから3秒のあいだ、液晶を消していた区間(打ち始めからのミリ秒)。ROMが
    ときどき1msほど消すのは数えない"""
    from basic_diff import play

    log: list[tuple[int, int]] = []
    out_c = m.out_c

    def logged(v: int) -> None:
        if (v ^ m.pc_out) & 1:
            log.append((m.cpu.cycles, v & 1))
        out_c(v)

    m.out_c = logged
    start = m.cpu.cycles
    play(m, [("type", text), ("wait", 3)])
    m.out_c = out_c
    spans, off = [], None
    for c, on in log:
        t = (c - start) * 1000 // CLOCK
        if not on:
            off = t
        elif off is not None:
            if t - off > 3:
                spans.append((off, t))
            off = None
    if off is not None:
        spans.append((off, -1))  # 消したまま
    return spans


@pytest.mark.parametrize("index", range(len(DISPLAY_CASES)))
def test_display_is_off_while_running_like_rom(index):
    """ENTERで実行を始めると液晶を消し、PRINTの字を出すときと、キーを待つとき(答え・
    エラー・INPUT・>)に点ける。消している区間の数と端の時刻がROMと合う(観察)"""
    from basic_diff import basic_machine, play

    if not have_rom():
        pytest.skip("ROMがない")
    lines, text = DISPLAY_CASES[index]
    spans = []
    for m in (boot()[0], basic_machine()):
        play(m, _program(lines, []))
        spans.append(_dark_spans(m, text))
    rom, own = spans
    assert len(rom) == len(own), (rom, own)
    for (a, b), (c, d) in zip(rom, own, strict=True):
        assert abs(a - c) <= 60 and (b < 0) == (d < 0) and abs(b - d) <= max(80, (b - a) // 10)


CSAVE_BRK_CASES = [
    ('CSAVE "LONG"\n', 300),  # 初めの1のあいだは約500msごとに見る
    ('CSAVE "LONG"\n', 8100),  # 名前のあいだは見ず、中身に入ってから見る
    ('CSAVE "LONG"\n', 12000),  # 中身は1バイトごと
    ("CSAVE M &C000,&C3FF\n", 8000),  # CSAVE Mは置く場所のあとから
]


@pytest.mark.parametrize("index", range(len(CSAVE_BRK_CASES)))
def test_csave_checks_brk_like_rom(index):
    """CSAVEがBRKを見て音を止める時刻が、ROMのある本体と同じ(音を出し始めてからの時刻で
    比べる)"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, play

    command, at = CSAVE_BRK_CASES[index]
    lines = [f'{n} A$="ABCDEFGHIJKLMNOP":B=12345' for n in range(10, 100, 10)]
    stops = []
    for m in (boot()[0], basic_machine()):
        play(m, _program(lines, []))
        start = m.cpu.cycles
        play(m, [("type", command)])
        first = next(c for c, v in m.sound_events if c >= start and v)
        m.run(first + at * CLOCK // 1000 - m.cpu.cycles)
        m.brk = True
        m.run(CLOCK)
        m.brk = False
        stop = next(c for c, v in m.sound_events if c > first and v == 0)
        stops.append((stop - first) * 1000 // CLOCK)
    rom, own = stops
    assert rom > at + 5 and abs(rom - own) < 8, stops


@pytest.mark.parametrize("name", ["badm", "cutm2"])
def test_cload_m_error_marks_program_end(name, rom_tapes):
    """CLOAD Mをチェックサムの誤りかBRKで止めると、プログラムの終わりの番地にFFを置く(読んだ
    バイトがそこに入っていても)。ROMのある本体と同じ"""
    from basic_diff import basic_machine, differences, play

    from sc61box import tape

    out = []
    for m in (boot()[0], basic_machine()):
        play(m, _program(["5 X=1"], []))
        end = m.mem[0xC6E3] | m.mem[0xC6E4] << 8
        m.tape = tape.TapeIn(rom_tapes[name])
        looks = play(m, [("type", f"CLOAD M &{end - 7:X}\n"), ("wait", 15), ("look", None)])
        m.brk = True
        m.run(CLOCK * 3 // 10)
        m.brk = False
        looks += play(m, [("wait", 0.5), ("look", None)])
        out.append((looks, bytes(m.mem[end - 7 : end + 9])))
    (a, ram_a), (b, ram_b) = out
    assert not differences(a, b), "\n".join(differences(a, b))
    assert ram_a == ram_b and ram_a[7] == 0xFF


DIRECT_STATEMENT_CASES = [
    # 代入は「,」で区切って続けられる。行番号なしなら、代入と式を並べて最後の値を出す
    (["10 A=1,B=2:PRINT A;B", '20 LET C=3,D$="X":PRINT C;D$', "30 A=1,2", "40 LET A=1,B",
      "50 A=7,B=1/0", "60 A(1)=1,A(2)=2:PRINT A;B", "70 A=0:B=0:A=1,B:PRINT A"],
     ["RUN\n", None, "\n", None, "\n", None, ["CL"], "RUN 30\n", None, ["CL"], "RUN 40\n",
      None, ["CL"], "RUN 50\n", None, ["CL"], "A\n", None, ["CL"], "RUN 60\n", None, ["CL"],
      "RUN 70\n", None, ["LEFT"], None, ["CL"], "1,A=2\n", None, ["CL"], "B,A=4\n", None,
      ["CL"], "1+1,2*3\n", None, ["CL"], "A=1,B=2,C\n", None, ["CL"], '"X",A=2\n', None,
      ["CL"], "A=3,B\n", None, ["LEFT"], None, ["CL"], "A=1,\n", None]),
    # RUNモードで行番号なしに打ったBEEPとUSINGは実行する。INPUTはERROR 9(観察)
    (["10 PRINT 1/3", '20 PRINT "AB"'],
     ['USING "##.##"\n', None, ["CL"], "1/3\n", None, ["CL"], "RUN\n", None, "\n", None, ["CL"],
      "BEEP 2\n", None, ("wait", 1), None, ["CL"], "INPUT A\n", None, ["LEFT"], None, ["CL"],
      'USING "##":A=1\n', None, ["LEFT"], None, ["CL"], "BEEP 1:A=3\n", ("wait", 1), None]),
    # USINGはGOTOとCONTで続けるプログラムにも効き、RUNで戻る
    (["10 PRINT 1/3", "20 STOP", "30 PRINT 2/3"],
     ['USING "##.##"\n', ["CL"], "GOTO 10\n", None, "\n", None, ["CL"], 'USING "#.#"\n', ["CL"],
      "CONT\n", None, ["CL"], "RUN\n", None, "\n", ["CL"], 'USING "#.#"\n', ["CL"], "CONT\n",
      None]),
]  # fmt: skip


@pytest.mark.parametrize("index", range(len(DIRECT_STATEMENT_CASES)))
def test_direct_statements_match_rom(index):
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    steps = _program(*DIRECT_STATEMENT_CASES[index])
    a = play(boot()[0], steps)
    b = play(basic_machine(), steps)
    assert not differences(a, b), "\n".join(differences(a, b))


QUIRK_CASES = [
    # VALの指数: 3桁以上なら下の2桁、仮数がなければ1。PC-1245は指数の中の空白を飛ばす
    ([], ['VAL "1€123"', 'VAL "€-123"', 'VAL "€"', 'VAL "-€2"', 'VAL ".€2"', 'VAL "€0"',
          'VAL "1€ 2"', 'VAL "1€ - 2"', 'VAL "1€2 3"', 'VAL "+€ 1"']),
    # PC-1251は、2次元の配列の2つ目の添字に配列の要素があると、入れるときだけ1つ目の
    # 添字を0にする(A(n)では起きない)
    (["10 DIM B(3,3),C(3):C(1)=2:A(30)=2"],
     ["B(1,C(1))=5", "B(0,2)*10+B(1,2)", "B(2,C(1)+1)=7", "B(0,3)*10+B(2,3)", "B(1,A(30))=9",
      "B(0,2)+B(1,2)*10", "B(1,(C(1)))=4", "B(0,2)+B(1,2)*10", "B(1,C(1))"]),
    # 数の字の並びもVALと同じに読む: 仮数は10桁まで(切り捨て)、指数は下の2桁、2つ目からの
    # 小数点は飛ばす。1E100以上はERROR 9、1E-99より小さければ0
    ([], ["12345678901-12345678900", "1.23456789019*10-12.3456789", "12345678905", "1€123",
          "5€1000", "12345€99", "0.0001€-99", "1€", "€5", "2*€2", "1.2.3", "1€2.5",
          'VAL "1€2.5"', 'VAL "1€.2"', 'VAL "12345€99"', 'VAL "-0.001€-99"', 'VAL "123€98"*0',
          # 桁の多い数も、丸めずに10桁に切り捨てる
          "0." + "9" * 30, "9" * 30 + "€70", 'VAL "0.' + "9" * 30 + '"',
          'VAL "' + "9" * 30 + '€70"']),
]  # fmt: skip


@pytest.mark.parametrize("index", range(len(QUIRK_CASES)))
def test_quirks_match_rom(index):
    """機種で違う細かい計算のふるまいが、ROMのある本体と同じ"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    lines, exprs = QUIRK_CASES[index]
    actions: list = ["RUN\n", ("wait", 1)] if lines else []
    for e in exprs:
        actions += [["CL"], e + "\n", None]
    steps = _program(lines, actions)
    a = play(boot()[0], steps)
    b = play(basic_machine(), steps)
    assert not differences(a, b), "\n".join(differences(a, b))


@pytest.mark.parametrize("seconds", [0.5, 1.0, 1.5, 2.3])
def test_cursor_keys_repeat_like_rom(seconds):
    """←・→・↑・↓は押し続けると繰り返す(約0.73秒後から約0.116秒ごと)。字のキーは
    繰り返さない(ROMのある本体と同じ)"""
    if not have_rom():
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    out = []
    for m in (boot()[0], basic_machine()):
        looks = play(m, _program([f"{n} A={n}" for n in range(1, 31)], []))
        for setup, key in (
            ([("mode", "PRO"), ("wait", 1.5), ("type", "ABCDEFGHIJKLMNOPQRST")], "LEFT"),
            ([("keys", ["CL"])], "DOWN"),
            ([("mode", "RUN"), ("wait", 1.5)], "A"),
        ):
            play(m, setup)
            m.held = {key}
            m.run(int(CLOCK * seconds))
            m.held = set()
            m.run(CLOCK // 10)
            looks += play(m, [("type", "*"), ("look", None), ("keys", ["CL"])])
        out.append(looks)
    a, b = out
    assert not differences(a, b), "\n".join(differences(a, b))


def test_cload_too_long_program_stops_with_error_6(tmp_path):
    """CLOADで、行が固定の変数の場所に届くとERROR 6になり、プログラムは空になる。固定の変数は
    書きかえない(PC-1251で録った長いプログラムをPC-1250で読む。ROMのある本体と同じ)"""
    if helpers.MODEL != "1251" or not have_rom():
        pytest.skip("PC-1251のROMで試す")
    from basic_diff import basic_machine, differences, play

    from sc61box import tape
    from sc61box.basic.pc1251 import variables

    v = variables.PC1251
    lines = [f'{10 * k} A$="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"' for k in range(1, 45)]
    src, _t = boot("1251")
    play(src, _program(lines, []))
    path = str(tmp_path / "long.wav")
    tape.write_wav(path, tape.record(src, 'CSAVE "S"'))
    out = []
    for m in (boot("1250")[0], basic_machine("1250")):
        play(m, _program(["5 X=1"], ["A=5\n", ("wait", 0.5)]))
        fixed = bytes(m.mem[v.ARRAY_TOP : v.FIXED_TOP])
        m.tape = tape.TapeIn(path)
        looks = play(m, [("type", "CLOAD\n")] + [("wait", 10), ("look", None)] * 7)
        assert bytes(m.mem[v.ARRAY_TOP : v.FIXED_TOP]) == fixed
        out.append(looks)
    a, b = out
    assert a[-1].lcd.strip() == "ERROR 6"
    assert not differences(a, b), "\n".join(differences(a, b))


def test_runner_keeps_typed_line_for_aread():
    """AREADに渡す打っていた行(run.Typed)も、BASICの状態の保存と読み込みで残る"""
    import json

    from basic_diff import basic_machine

    from sc61box.basic.run import Typed

    m = basic_machine()
    assert m.basic is not None
    r = m.basic.runner
    r.aread = Typed(b"\x51\x1c\x52")
    saved = json.loads(json.dumps(r.save()))
    assert r.parse(saved)["aread"] == Typed(b"\x51\x1c\x52")


@pytest.mark.parametrize(
    ("line", "wait", "mark"),
    [('WAIT 4660:PRINT "AB"', b"\x34\x12", True), ('WAIT 0:PRINT "X",7', b"\0\0", True),
     ("WAIT 3:PRINT 5", b"\x03\0", True), ('WAIT 1:PAUSE " /OKU/ ";A', b"\x01\0", False),
     ('WAIT 2:PAUSE "AB"', b"\x02\0", False)],
)  # fmt: skip
def test_wait_value_and_print_text_in_ram(line, wait, mark):
    """WAITの値はC6E5h・C6E6h番地に、PRINT・PAUSEの字の並びはC7B0h番地
    からに、ROMのある本体と同じに置く(PRINTは字のあとに00h、PAUSEは置かない。どちらも残りは
    空白。マシン語のゲームが読む)"""
    from basic_diff import basic_machine

    from sc61box.autotype import Typer

    machines = [basic_machine()] + ([boot()[0]] if have_rom() else [])
    seen = []
    for m in machines:
        t = Typer(m)
        t.add_mode("PRO")
        finish(m, t)
        m.run(CLOCK * 3 // 2)
        t.add_text(f"NEW\n10 A=1:{line}:CALL &C000\n")
        t.add_mode("RUN")
        finish(m, t)
        m.run(CLOCK * 3 // 2)
        m.mem[0xC000] = 0x37  # RTN
        guard = bytearray(0x10000)
        guard[0xC000] = 1
        t.add_text("RUN\n")
        for _ in range(4000):
            if t.busy:
                t.step()
            if m.run(256, None if m.norom else guard) or m.cpu.pc == 0xC000:
                break
        seen.append((bytes(m.mem[0xC6E5:0xC6E7]), bytes(m.mem[0xC7B0:0xC800])))
    got, text = seen[0]
    assert got == wait
    assert (0 in text) == mark and text.rstrip(b"\x11")[-1:] != b"\x11"
    if len(seen) > 1:
        assert seen[0] == seen[1]


def test_array_in_lcd_mirror_like_rom():
    """配列の要素は、本体の番地の割り当てどおりに読み書きする。PC-1245で配列の表を作り替え、
    要素の番地を液晶RAMのミラー(E800h〜)に向けると、液晶に書かれる(もぐらたたきのPC-1245版の
    やり方。ROMのある本体と同じ)"""
    if helpers.MODEL != "1245":
        pytest.skip("液晶RAMのミラーにかかる配列の試験はPC-1245で行う")
    from basic_diff import basic_machine, play

    prog = (
        'NEW\n10 POKE &C6FC,&C9,&C5: POKE &C5C9,234,&FF,&FF,&FF,&FF,5\n'
        '20 W$="Q":Z$(7,0)=W$:X$=Z$(7,0)\n'
    )  # fmt: skip
    machines = [basic_machine()] + ([boot()[0]] if have_rom() else [])
    seen = []
    for m in machines:
        play(m, [("mode", "PRO"), ("wait", 1.5), ("type", prog), ("mode", "RUN"), ("wait", 1.5),
                 ("type", "RUN\n"), ("wait", 1)])  # fmt: skip
        seen.append((m.mem[0xF8CF], bytes(m.mem[0xE8CF:0xE8D4]), m.mem[0xC5E9]))
    assert seen[0] == (0x61, bytes(5), 0x61)
    if len(seen) > 1:
        assert seen[0] == seen[1]

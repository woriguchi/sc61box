"""ROMなしのBASICのPC-1261系とPC-1350の部分が、ROMのある本体と同じか"""

from decimal import Decimal

import pytest
from conftest import HAVE_ROM, HAVE_ROM_1260, HAVE_ROM_1350
from helpers import boot, finish

from sc61box.basic.errors import BasicError
from sc61box.basic.pc1261 import tokens
from sc61box.machine import CLOCK, new_machine

PC1261_MODELS = [
    ("1261", tokens.KEYWORDS_1261, HAVE_ROM_1260),
    ("1350", tokens.KEYWORDS_1350, HAVE_ROM_1350),
]


def _put_lines(m, bodies: list[bytes], first: int = 10) -> None:
    """プログラムの領域に行を書く(行番号の上位・下位、長さ、中身、0Dh)"""
    data = bytearray(b"\xff")
    for i, body in enumerate(bodies):
        n = first + i
        data += bytes([n >> 8, n & 0xFF, len(body) + 1]) + body + b"\x0d"
    data += b"\xff"
    start = m.model.prog_start
    m.mem[start : start + len(data)] = data
    end = start + len(data) - 1
    m.mem[m.model.prog_end_ptr] = end & 0xFF
    m.mem[m.model.prog_end_ptr + 1] = end >> 8


@pytest.mark.parametrize(("model", "keywords", "have"), PC1261_MODELS)
def test_keywords_list_like_rom(model, keywords, have):
    """中間コードの表(pc1261.tokens)のとおりに、ROMのある本体がLISTで綴りを出す"""
    if not have:
        pytest.skip("ROMがない")
    from sc61box.lcdtext import lcd_text

    m, t = boot(model)
    if model == "1350":
        t.add_keys([["MODE"]])  # PC-1350はMODEのキーでPROモードにする
    else:
        t.add_mode("PRO")
    finish(m, t)
    m.run(CLOCK * 3 // 2)
    codes = sorted(keywords)
    _put_lines(m, [bytes([c]) for c in codes])
    for i, c in enumerate(codes):
        t.add_keys([["CL"]])
        t.add_text(f"LIST {10 + i}\n")
        finish(m, t)
        m.run(CLOCK // 4)
        shown = lcd_text(m).split("\n")
        assert f"{10 + i}:{keywords[c]}" in "".join(s.strip() for s in shown), (hex(c), shown)


def test_program_and_variables_layout_like_rom():
    """PC-1261系とPC-1350のプログラムの行と変数・配列の置き方(pc1261.program、pc1261.variables)が、ROMのある
    本体のRAMと同じ(PC-1261)"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    from sc61box.basic.pc1261 import program, variables
    from sc61box.machine import new_machine

    m, t = boot("1261")
    t.add_mode("PRO")
    finish(m, t)
    m.run(CLOCK * 3 // 2)
    lines = ["NEW", "10 PRINT 1", "65279 A=B+C*2:GOTO 10", '30 A$="AB"', "20 REM X", "30"]
    for line in lines:
        t.add_text(line + "\n")
        finish(m, t)
        m.run(CLOCK // 5)
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK * 3 // 2)
    for line in ["DIM B(3)", "DIM C$(2)*5", "DIM D(1,2)", "D(1,2)=5", "A(30)=1", 'Z$="XY"']:
        t.add_text(line + "\n")
        finish(m, t)
        m.run(CLOCK // 2)

    own = new_machine("1261", rom=False)
    p, v = program.PC1261, variables.PC1261
    v.initialize(own)
    for n, a in p.lines(m):
        p.store(own, n, p.body(m, a))
    v.dim(own, 0x42, False, [3], 8)
    v.dim(own, 0x43, True, [2], 5)
    v.dim(own, 0x44, False, [1, 2], 8)
    v.write(own, v.element(own, 0x44, False, [1, 2]), Decimal(5))
    v.write(own, v.element(own, 0x41, False, [30]), Decimal(1))
    v.write(own, v.Ref(v.fixed_addr(26), True), b"XY")
    start, end = m.model.prog_start, p.end(m)
    assert p.end(own) == end
    assert bytes(own.mem[start : end + 1]) == bytes(m.mem[start : end + 1])
    bottom = v.word(m, v.ARRAY_PTR)
    assert v.word(own, v.ARRAY_PTR) == bottom
    assert bytes(own.mem[bottom : v.FIXED_TOP]) == bytes(m.mem[bottom : v.FIXED_TOP])


@pytest.mark.parametrize("card", [0, 8, 16])
def test_program_and_variables_layout_like_rom_1350(card):
    """PC-1350のプログラムの行と変数・配列の置き方、6F00hとRAMの頭+6に置くポインタ(pc1261.program、
    pc1261.variables)が、ROMのある本体のRAMと同じ(RAMカードなし、8KB、16KB)"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from sc61box.autotype import Typer
    from sc61box.basic.pc1261 import program, variables
    from sc61box.machine import new_machine

    if card:
        m = new_machine("1350", card)
        m.run(CLOCK)
        t = Typer(m)
    else:
        m, t = boot("1350")
        m.run(CLOCK)
    t.add_keys([["MODE"]])  # PROモード
    for line in ["NEW", "10 PRINT 1", "65279 A=B+C*2:GOTO 10", '30 A$="AB"', "20 REM X", "30"]:
        t.add_text(line + "\n")
    t.add_keys([["MODE"]])
    for line in ["DIM B(3)", "DIM C$(2)*5", "DIM D(1,2)", "D(1,2)=5", "A(30)=1", 'Z$="XY"', "QR=4"]:
        t.add_text(line + "\n")
    finish(m, t)
    m.run(CLOCK // 2)

    own = new_machine("1350", card, rom=False)
    p, v = program.PC1350, variables.PC1350
    v.initialize(own)
    for n, a in p.lines(m):
        p.store(own, n, p.body(m, a))
    v.dim(own, 0x42, False, [3], 8)
    v.dim(own, 0x43, True, [2], 5)
    v.dim(own, 0x44, False, [1, 2], 8)
    v.write(own, v.element(own, 0x44, False, [1, 2]), Decimal(5))
    v.write(own, v.element(own, 0x41, False, [30]), Decimal(1))
    v.write(own, v.Ref(v.fixed_addr(26), True), b"XY")
    v.write(own, v.simple(own, 0x5251, False), Decimal(4))
    start, end = m.model.prog_start, p.end(m)
    assert p.end(own) == end
    assert bytes(own.mem[start : end + 1]) == bytes(m.mem[start : end + 1])
    bottom = v.word(m, v.ARRAY_PTR)
    assert v.word(own, v.ARRAY_PTR) == bottom
    assert bytes(own.mem[bottom : v.FIXED_TOP]) == bytes(m.mem[bottom : v.FIXED_TOP])
    head = m.model.ram[0] + 6
    for a in (0x6F00, head):
        assert bytes(own.mem[a : a + 9]) == bytes(m.mem[a : a + 9]), hex(a)


LEXER_LINES = [
    "PRINT 1", "A = B + C * 2 : GOTO 10", 'A$="A B"', "IF A>=1 THEN 10", "REM  X Y", "P.1:G.10",
    "FOR I=1TO 3STEP 2", "DEG.:DEG 30", "X=SIN30+LOG 2", "INPUT \"N\";N", "PRINT A;B,C$",
    "MEM.", "LET A=PI", "CH.:CHA.", "ON A GOSUB 10,20",
]  # fmt: skip


@pytest.mark.parametrize(("model", "keywords", "have"), PC1261_MODELS)
def test_lexer_like_rom(model, keywords, have):
    """打った行を中間コードにしたもの(pc1261.lexer)が、ROMのある本体のRAMに入る行と同じ"""
    if not have:
        pytest.skip("ROMがない")
    from sc61box.basic.pc1261 import lexer, program

    m, t = boot(model)
    if model == "1350":
        t.add_keys([["MODE"]])
    else:
        t.add_mode("PRO")
    finish(m, t)
    m.run(CLOCK * 3 // 2)
    t.add_text("NEW\n")
    for i, line in enumerate(LEXER_LINES):
        t.add_text(f"{i + 1} {line}\n")
    finish(m, t)
    m.run(CLOCK // 5)
    abbr = tokens.ABBREVIATIONS_1350 if model == "1350" else tokens.ABBREVIATIONS_1261
    lex = lexer.Lexer(keywords, abbr)
    got = {n: program.PC1261.body(m, a) for n, a in program.PC1261.lines(m)}
    for i, line in enumerate(LEXER_LINES):
        assert lex.tokenize(line.encode("ascii")) == got[i + 1], line


EXPRESSIONS = [
    "1+1", "1/3", "1E5", "2E3+1", "-5", "1E-5", "2A", "3E", "1E2E", "PI", '"AB"', "1>=1",
    "1> =1", "1<>2", "1=<1", "1E100", "1/0", "SIN 30", "SIN 30A", "2^3^2", "-2^2", "2^-1",
    "&FF", "&123456789", 'ASC "A"', "CHR$ 66", "STR$ 1.5", 'VAL "12E2"', '"AB"<"B"',
    'MID$("ABCD",2,2)', "NOT 0", "5 AND 3", "1E99*10", "12345678901", "1E2E3", "1E2.5",
    "1E+-2", "1.2.3", "E5", ".E2", "3E+", "1E2E+1", "1EE2", "1E2A", "1.5E1.2",
    "0.000000000012345", 'VAL "1E 2"', 'VAL " -1.5E-2X"', "AB", "ABC", "XY$", "2PI", "PI A",
]  # fmt: skip


@pytest.mark.parametrize("model", ["1261", "1350"])
def test_char_60_like_rom(model):
    """60hの字は、PC-1261系の液晶では何も描かず、PC-1350では`の形(ROMのある本体と同じ。
    M・MON KITTは、液晶の2行の字を60hで埋めて空白にする)"""
    if not (HAVE_ROM_1350 if model == "1350" else HAVE_ROM_1260):
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, lcd_1350, lcd_pc1261, play

    read = lcd_1350 if model == "1350" else lcd_pc1261
    shown = []
    for m in (boot(model)[0], basic_machine(model)):
        play(m, [("mode", "RUN"), ("wait", 1.5), ("type", '"A"+CHR$ 96+"B"\n'), ("wait", 1.0)])
        shown.append([line.strip() for line in read(m).splitlines() if "CHR$" not in line])
    assert shown[0] == shown[1]
    assert ("A`B" if model == "1350" else "A B") in shown[1]


def test_expressions_like_rom():
    """RUNモードで打った式の答え(pc1261.evaluate)が、ROMのある本体の2行目と同じ(PC-1261)"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    from sc61box.basic.evaluate import expect_end
    from sc61box.basic.pc1261 import evaluate, lexer, variables
    from sc61box.lcdtext import lcd_text
    from sc61box.machine import new_machine

    m, t = boot("1261")
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK * 3 // 2)
    own = new_machine("1261", rom=False)
    variables.PC1261.initialize(own)
    lex = lexer.Lexer(tokens.KEYWORDS_1261, tokens.ABBREVIATIONS_1261)
    for text in EXPRESSIONS:
        t.add_keys([["CL"]])
        t.add_text(text + "\n")
        finish(m, t)
        m.run(CLOCK // 2)
        first, second = lcd_text(m).split("\n")
        e = evaluate.Evaluator(own, lex.tokenize(text.encode("ascii")))
        try:
            v = e.expression()
            expect_end(e)
        except BasicError as err:
            assert first.strip() == f"ERROR {err.number}", text
            continue
        want = evaluate.display_number(v) if isinstance(v, Decimal) else v
        assert second.strip() == want.decode("ascii"), text


def test_two_letter_variables_like_rom():
    """2字の名前の変数と配列の置き方(pc1261.variables)が、ROMのある本体のRAMと同じ(PC-1261)"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    from sc61box.basic.pc1261 import variables
    from sc61box.machine import new_machine

    m, t = boot("1261")
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK * 3 // 2)
    for line in ["AB=5", 'AC$="XY"', "B1=7", "Z9", "ZZ$", "DIM AB$(2)", "DIM C1(1)",
                 "DIM D9$(1)*3", "DIM E(1)", "DIM F$(1)", "DIM GH$(1,1)*2", "AB(1)=3",
                 "A(30)=2", "XY=8"]:  # fmt: skip
        t.add_keys([["CL"]])
        t.add_text(line + "\n")
        finish(m, t)
        m.run(CLOCK // 2)
    own = new_machine("1261", rom=False)
    v = variables.PC1261
    v.initialize(own)
    name = lambda s: ord(s[0]) | (ord(s[1]) << 8 if len(s) > 1 else 0)  # noqa: E731
    v.write(own, v.simple(own, name("AB"), False), Decimal(5))
    v.write(own, v.simple(own, name("AC"), True), b"XY")
    v.write(own, v.simple(own, name("B1"), False), Decimal(7))
    v.simple(own, name("Z9"), False)
    v.simple(own, name("ZZ"), True)
    v.dim(own, name("AB"), True, [2], 16)
    v.dim(own, name("C1"), False, [1], 8)
    v.dim(own, name("D9"), True, [1], 3)
    v.dim(own, name("E"), False, [1], 8)
    v.dim(own, name("F"), True, [1], 16)
    v.dim(own, name("GH"), True, [1, 1], 2)
    with pytest.raises(BasicError):
        v.element(own, name("AB"), False, [1])  # 数の配列ABはない
    v.write(own, v.element(own, 0x41, False, [30]), Decimal(2))
    v.write(own, v.simple(own, name("XY"), False), Decimal(8))
    bottom = v.word(m, v.ARRAY_PTR)
    assert v.word(own, v.ARRAY_PTR) == bottom
    assert bytes(own.mem[bottom : v.FIXED_TOP]) == bytes(m.mem[bottom : v.FIXED_TOP])


# ROMなしのBASICを、ROMのある本体と同じ手順で比べる。!はモード、@はキー、ほかは打つ字
SESSIONS = {
    # LEFT$・RIGHT$の字数は0〜80、MID$の始めは1〜80、字数は0〜80(ほかはERROR 3)
    "substring": [
        'MID$ ("ABC",0,1)\n', "@LEFT", "@CL", 'MID$ ("ABC",80,1)\n', "@CL",
        'LEFT$ ("ABC",81)\n', "@CL", 'RIGHT$ ("ABC",-0.5)\n', "@CL", 'MID$ ("ABC",1.9,80)\n',
    ],
    # RUNはWAITをやめる(PRINTはENTERを待つ)。GOTOではやめない
    "wait-run": [
        "!PRO", "10 WAIT 0:END\n", "20 PRINT 1:PRINT 2\n", "!RUN", "RUN\n", "GOTO 20\n", "@CL",
        "RUN 20\n", "\n", "\n",
    ],
    # IFの数の条件は正のときだけ成り立つ(NOT 0の-1、負の数では成り立たない)
    "if-negative": [
        "!PRO", "10 A=0:B=0:C=0:D=0:E=0\n", "20 IF NOT 0 LET A=1\n", "30 IF -0.5 LET B=1\n",
        "40 IF 0.0001 LET C=1\n", "50 IF 1 AND -1 LET D=1\n", "60 IF (2>1)*-1 LET E=1\n",
        "70 PRINT A;B;C;D;E\n", "!RUN", "RUN\n",
    ],
    "run": [
        "!RUN", "1+2", "\n", "+3", "\n", "@CL", "AB=5\n", "@CL", "1/0\n", "@CL", "SIN 30\n",
        "@CL", '"AB"\n', "@CL", "RADIAN\n", "@CL", "GRAD\n", "@CL", "DEGREE\n", "@CL",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ12345=1\n", "@LEFT", "@CL", "1+", "@LEFT", "X", "@CL",
        "PRINT 1\n", "@CL", "INPUT A\n", "@CL", "XY\n", "@CL", "QR=GH\n",
    ],
    "recall": [
        "!RUN", "@DOWN", "@CL", "3+4\n", "@CL", "@DOWN", "@CL", "@UP", "@CL", "A=9\n", "@DOWN",
        "\n", "@CL", '"XY"\n', "@CL", "@DOWN", "@CL", "1/0\n", "@DOWN", "@CL", "@DOWN",
    ],
    "lines": [
        "!PRO", '10 PRINT "A";:PRINT "B"\n', "20 PRINT 1;:PRINT 2\n", '30 PRINT "C";:END\n',
        '40 WAIT 0:PRINT "D";:PRINT "E"\n',
        "100 A=1:B=2:C=3:D=4:E=5:F=6:G=7:H=8:I=9:J=10:K=11:L=12\n",
        "110 REM ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMNOPQRSTUVWXYZ\n", "@UP", "@UP", "@UP",
        "@DOWN", "@DOWN", "@DOWN", "@DOWN", "@CL", "LIST\n", "@CL", "LIST 35\n", "!RUN", "RUN\n",
        "\n", "\n", "\n", "@CL", "RUN 30\n", "\n",
    ],
    "program": [
        "!PRO", "10 FOR I=1 TO 2:PRINT I;I*2:NEXT I\n", '20 READ X,Y$:PRINT Y$;X\n',
        '30 DATA 5,"QQ"\n', '40 GOSUB 60:PRINT "R":END\n', "60 BEEP 1:RETURN\n", "70 A=1/0\n",
        "@UP", "@RIGHT", "@RIGHT", "@LEFT", "Z", "\n", "!RUN", "RUN\n", "\n", "\n", "\n", "@CL",
        "GOTO 70\n", "@UP", "@CL", "@DOWN", "@CL", "RUN 20\n", "@CL", "CONT\n",
    ],
    "input": [
        "!PRO", "10 INPUT A:PRINT A*2\n", '20 INPUT "NAME?";N$:PRINT "HI ";N$\n',
        '30 INPUT "V=",V:PRINT V\n', "40 STOP:PRINT 9:END\n", "!RUN", "RUN\n", "5\n", "\n",
        "BOB\n", "\n", "@CL", "42\n", "\n", "\n", "@CL", "CONT\n", "\n", "@CL", "RUN 10\n",
        "1/0\n", "@CL", "\n",
    ],
    "print": [
        "!PRO", '10 PRINT "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"\n', '20 CLS:PRINT "X"\n',
        '30 CURSOR 5:PRINT "Y"\n', '40 CURSOR 30:PRINT "Z";:PRINT "W"\n',
        '50 CLS:CURSOR 3:PRINT "Q";\n', "60 PRINT 1,2\n", '70 PRINT "A","B"\n',
        '80 PRINT "A";:PRINT 1,2\n', "90 CURSOR 5:PRINT 1\n", '100 PRINT "B"\n',
        '110 CURSOR 2:PRINT "C":PRINT "D"\n', '120 PRINT "E";:PRINT "F";:CLS:PRINT "G"\n',
        '130 PRINT "H";:CURSOR 10:PRINT "I"\n', '140 CURSOR 46:PRINT "JKL"\n',
        '150 PRINT "M";:PRINT "N";:PRINT 5\n', '160 IF A>1 THEN PRINT "AB":GOTO 10\n', "!RUN",
        "RUN\n", *["\n"] * 22,
    ],
    "errors": [
        "!RUN", "1+\n", "@LEFT", "@CL", "1/0\n", "@LEFT", "@CL", "DIM A(300)\n", "@LEFT", "@CL",
        "GOTO 5\n", "@LEFT", "@CL", '"A"+1\n', "@LEFT", "@LEFT", "@RIGHT", "@CL",
        "DIM Q(255,255)\n", "@RIGHT", "@CL", "A=1/0+2\n", "@LEFT", "@CL", "A$=1\n", "@LEFT",
        "@CL", 'USING "##"\n', "123\n", "@LEFT", "@CL", 'USING "###.##"\n', "3.14159\n", "@CL",
        '"AB"\n', "@CL", 'USING "##.##^"\n', "12345\n", "@CL", "USING\n", "7\n", "!PRO",
        "10 RETURN\n", "!RUN", "RUN\n", "@LEFT", "@DOWN", "@CL", "RUN\n", "@UP",
    ],
    "kana": [
        "!PRO", "10 ", "@SHIFT,8", "@Q,W", "@SHIFT,Q", "@1,A", "@SHIFT,8", "@B", "\n",
        '20 A$="', "@SHIFT,8", "@Q,W,E", "@SHIFT,8",
        '":PRINT A$;LEN A$;ASC A$:PRINT MID$(A$,2,1)\n', "@UP", "@RIGHT", "@RIGHT,RIGHT", "@LEFT",
        "!RUN", "RUN 20\n", "\n", "\n", "@CL", "CHR$ 254\n", "@CL", '"X"+CHR$ 177\n',
    ],
    "strings": [
        "!RUN", 'A$="ABCDEFG"\n', "@CL", 'A$="XY"\n', "@CL", 'AB$="1234567890ABCDEF"\n', "@CL",
        'AB$="Q"\n', "@CL", "DIM C$(1)*5\n", "@CL", 'C$(0)="VWXYZ"\n', "@CL", 'C$(0)="M"\n',
        "@CL", 'A$="ABCDEFGHIJ"\n', "@CL", 'A$=""\n',
    ],
    "brk": [
        "!PRO", "10 GOTO 10\n", '20 PRINT "END"\n', "30 A=7:B=3:END\n", "!RUN", "RUN\n", "BRK",
        "@UP", "@CL", "CONT\n", "BRK", "@DOWN", "@DOWN", "@CL", "CONT\n", "BRK", "@CL",
        "GOTO 20\n", "\n", "BEEP 3\n", "", "TRON\n", "RUN 20\n", "@DOWN", "@DOWN", "@DOWN",
        "@CL", "TROFF\n", "RUN 20\n", "@DOWN", "@DOWN", "@DOWN", "@CL", "GOTO 30\n", "@DOWN",
    ],
    "rsv": [
        "!RSV", "@SHIFT,A", "PRINT 1\n", "@SHIFT,S", "ABC@\n", "@SHIFT,A", "@SHIFT,F", "@CL",
        "@SHIFT,A", "@RIGHT", "X", "\n", "!RUN", "@SHIFT,A", "@CL", "@SHIFT,S", "@CL", "@SHIFT,Q",
        "@SHIFT,SPC", "@SHIFT,=", "@DEF", "@A", "@CL", "!PRO", "@SHIFT,A", "\n",
    ],
    "def": [
        "!PRO", '10 "A" AREAD X:PRINT X*2\n', '20 "S" PRINT "S":END\n', "!RUN", "5", "@DEF", "@A",
        "\n", "@CL", "@DEF", "@S", "\n", "@CL", "@SHIFT,Q", "@DEF", "@A", "@CL", "3+4\n", "@DEF",
        "@A", "\n", "@CL", "@DEF", "@DEF", "@A", "@CL", "@DEF", "@D",
    ],
    # AREADは、打っていた行を読むときに計算する(文字列の変数には字のまま)。誤りは打った行のエラー
    "def-typed": [
        "!PRO", '10 "M" AREAD A:PRINT A\n', '20 "N" AREAD A$:PRINT A$\n', "!RUN", "7Z751Z161?",
        "@DEF", "@M", "@LEFT", "@CL", "12+", "@DEF", "@Q", "@RIGHT", "@CL", "1+", "@DEF", "@N",
        "\n", "@CL", "A$", "@DEF", "@M", "@LEFT",
    ],
    "pass": [
        "!PRO", "10 A=1\n", 'PASS "AB"\n', "LIST\n", "@UP", "20 B=2\n", "NEW\n", "LIST\n",
        'PASS "AB"\n', "LIST\n", 'PASS "ABC"\n', 'PASS "AB"\n', "@CL", "!RUN", "@UP",
        'PASS "ABC"\n', "!PRO", "@CL", "LIST\n", "@CL", 'PASS "XYZ"\n', "PASS\n", "@CL",
        'PASS "XYZ" 1\n',
    ],
    "labels": [
        "!PRO", '10 GOTO "C"\n', "20 GOSUB A$:X=1\n", '30 "B" PRINT 3:RESTORE "Q"\n',
        '40 GOTO "B":X=1\n', '50 ON 2 GOSUB 30,"Z"\n', '60 "BC" READ X:PRINT X\n',
        '70 "D":DATA 8\n', '80 RESTORE "D":READ Y:PRINT Y:IF Y THEN "BC"\n', "!RUN", "RUN\n",
        "@CL", "RUN 20\n", "@CL", 'RUN "B"\n', "\n", "@CL", "GOTO 40\n", "@CL", "GOTO 50\n",
        "@CL", 'GOTO "Z"\n', "@LEFT", "@CL", 'RUN "\n', "@CL", 'GOTO ""\n', "@LEFT", "@CL",
        'GOTO "B"+"\n', "\n", "@CL", 'A$="B"\n', "GOTO A$\n", "\n", "@CL", "GOTO 80\n", "\n",
        "\n", "@CL", "GOTO B$\n",
    ],
    # 何も打たずにENTER(答えを消して>)、INPUTの答えのエラーの呼び出し(メッセージは2行目に出る)
    "enter-empty": [
        "\n", "1\n", "\n", '"A"\n', "\n", "!PRO", "\n", "!RUN", "1/0\n", "@CL", "3", "@LEFT",
        "@DEL", "\n", "!PRO", "10 INPUT A:PRINT A*2\n", "!RUN", "RUN\n", "1/0\n", "@LEFT", "X",
        "@LEFT", "5", "\n",
    ],
    # EQU#でプログラムの領域の始まりを128バイトずつ後ろへずらす(NEWではそのまま、EQU#0で戻す)
    "equ": [
        "!PRO", "NEW\n", "EQU#43\n", "10 A=1\n", "20 PRINT A\n", "LIST\n", "@CL", "EQU#3\n",
        "@CL", "!RUN", "RUN\n", "\n", "EQU#3\n", "@CL", "!PRO", "NEW\n", "EQU#72\n",
        "EQU#73\n", "@CL", "EQU#-1\n", "@CL", "EQU#40+3.7\n", "EQU#-.5\n", "@CL", "10 EQU#1\n",
        "!RUN", "RUN\n", "@CL", "!PRO", "NEW\n", 'EQU#"A"\n', "@CL", "EQU#0:PRINT 1\n", "@CL",
        "EQU#73:PRINT 1\n", "@CL", "EQU#43:\n", "@CL", "EQU#0\n", "10 B=2\n",
    ],
    # 出すもののないPRINT・PAUSE・LPRINT(PRINT ""と同じ)
    "empty-print": [
        "!PRO", '10 PRINT "A":PRINT:PRINT "B"\n', '20 PRINT "A";:PRINT:PRINT "B"\n',
        '30 USING "###":PRINT:PRINT 5\n', '40 LPRINT "A":LPRINT 1,2\n', "!RUN", "RUN\n", "\n",
        "\n", "\n", "RUN 20\n", "\n", "\n", "RUN 30\n", "\n", "\n", "RUN 40\n",
    ],
}  # fmt: skip


@pytest.mark.parametrize("name", list(SESSIONS))
def test_basic_like_rom(name):
    """ROMなしのBASIC(PC-1261)が、ROMのある本体と同じ液晶・RAMになる"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    steps: list[tuple[str, object]] = []
    for s in SESSIONS[name]:
        if s.startswith("!"):
            steps += [("mode", s[1:]), ("wait", 1.5)]
        elif s == "BRK":
            steps.append(("brk", None))
        elif s.startswith("@"):
            steps.append(("keys", s[1:].split(",")))
        else:
            steps.append(("type", s))
        steps += [("wait", 0.4), ("look", None)]
    m, _t = boot("1261")
    assert differences(play(m, steps), play(basic_machine("1261"), steps)) == []


def _loop_time(m, body: str, n: int, more: tuple[str, ...] = (), marker: int = 0x4010) -> float:
    """FORでbodyをn回くり返すプログラム(あとに行moreを足す)を、ENTERを押してから終わるまでの
    秒。終わりは、プログラムが番地markerに書く1で見る"""
    from sc61box.autotype import Typer

    t = Typer(m)
    t.add_mode("PRO")
    finish(m, t)
    m.run(CLOCK * 3 // 2)
    m.mem[marker] = 0
    loop = f"10 FOR I=1 TO {n}:{body}:NEXT I" if body else f"10 FOR I=1 TO {n}:NEXT I"
    t.add_text(f"NEW\n{loop}\n20 POKE {marker},1:END\n" + "".join(x + "\n" for x in more))
    finish(m, t)
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK * 3 // 2)
    t.add_text("RUN")
    finish(m, t)
    start = m.cpu.cycles
    t.add_keys([["ENTER"]])
    finish(m, t)
    while m.mem[marker] != 1 and m.cpu.cycles - start < CLOCK * 60:
        m.run(CLOCK // 200)
    return (m.cpu.cycles - start) / CLOCK


LOOP_BODIES = ["", "A=1", "A=I+1", "A=I/3", "A=SQR I", "PRINT 1", "CLS", "CURSOR 24", "A=A(2)"]


@pytest.mark.parametrize("body", LOOP_BODIES)
def test_loop_time_like_rom(body):
    """FORの繰り返し1回にかかる時間(pc1261/timing.py)が、ROMのある本体と10%以内(PC-1261)"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine

    body = "WAIT 0:" + body if body.startswith("PRINT") else body

    def per_loop(make) -> float:
        return (_loop_time(make(), body, 150) - _loop_time(make(), body, 50)) / 100

    rom = per_loop(lambda: boot("1261")[0])
    own = per_loop(lambda: basic_machine("1261"))
    assert abs(own / rom - 1) < 0.1, (body, rom, own)


READ_LOOPS = [
    ("RESTORE 30:READ A,B,C", ("30 DATA 1,2.5,3",)),
    ("RESTORE 30:READ A(2)", ("30 DATA 1",)),
]


@pytest.mark.parametrize(("body", "more"), READ_LOOPS)
def test_read_time_like_rom(body, more):
    """RESTOREとREADの時間が、ROMのある本体と10%以内(PC-1261)"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine

    def per_loop(make) -> float:
        return (_loop_time(make(), body, 150, more) - _loop_time(make(), body, 50, more)) / 100

    rom = per_loop(lambda: boot("1261")[0])
    own = per_loop(lambda: basic_machine("1261"))
    assert abs(own / rom - 1) < 0.1, (body, rom, own)


LABEL_LOOPS = [
    ("GOSUB 30", ("30 RETURN",)),
    ('GOSUB "B"', ('30 "B" RETURN',)),
    ('GOSUB "B"', (*(f"{n} REM" for n in range(30, 50)), '90 "BCDEFG" RETURN', '95 "B" RETURN')),
    ('GOSUB "BCDEFG"', (*(f"{n} REM" for n in range(30, 50)), '90 "BCDEFG" RETURN')),
    # 行の長さにはよらない
    ('GOSUB "B"', (*(f"{n} B=1234567890:C=1234567890" for n in range(30, 50)), '90 "B" RETURN')),
    (
        'GOSUB "B"',
        (*(f'{n} "C" B=1234567890:C=1234567890' for n in range(30, 50)), '90 "B" RETURN'),
    ),
]


@pytest.mark.parametrize(("body", "more"), LABEL_LOOPS)
def test_label_jump_time_like_rom(body, more):
    """ラベルの行へ跳ぶ時間(探す行の数とラベルの字の数による)が、ROMのある本体と10%以内
    (PC-1261)"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine

    def per_loop(make) -> float:
        return (_loop_time(make(), body, 150, more) - _loop_time(make(), body, 50, more)) / 100

    rom = per_loop(lambda: boot("1261")[0])
    own = per_loop(lambda: basic_machine("1261"))
    assert abs(own / rom - 1) < 0.1, (body, rom, own)


_REMS = tuple(f"{n} REM" for n in range(30, 70))
LINE_LOOPS = [
    ("GOSUB 30", ("30 RETURN",)),
    ("GOSUB 30", ("30 GOTO 31", "31 RETURN")),
    ("GOSUB 100", (*_REMS, "100 RETURN")),
    ("GOSUB 100", (*_REMS, "100 GOSUB 101:RETURN", "101 RETURN")),
    ("GOSUB 100", (*_REMS, "100 A=A+1:IF A<3 GOTO 100", "101 A=0:RETURN")),
]


@pytest.mark.parametrize("model", ["1261", "1350"])
@pytest.mark.parametrize(("body", "more"), LINE_LOOPS)
def test_line_jump_time_like_rom(model, body, more):
    """行番号で跳ぶ時間が、ROMのある本体と10%以内。先の行へはいまの行から、前の行(いまの行も)へは
    プログラムの頭から探す。RETURNは、戻る行より前の行の数だけ長くかかる(PC-1261系とPC-1350)"""
    if not (HAVE_ROM_1260 if model == "1261" else HAVE_ROM_1350):
        pytest.skip("ROMがない")
    from basic_diff import basic_machine

    marker = 0x6B00 if model == "1350" else 0x4010

    def rom():
        m = boot(model)[0]
        m.run(CLOCK)
        return m

    def per_loop(make) -> float:
        times = [_loop_time(make(), body, n, more, marker) for n in (50, 150)]
        return (times[1] - times[0]) / 100

    a, b = per_loop(rom), per_loop(lambda: basic_machine(model))
    assert abs(b / a - 1) < 0.1, (body, more[-1], a, b)


FOR_CASES = [
    "0 TO 1 STEP .5", "40000 TO 40001", "1 TO 4 STEP 1.5", "1 TO 3 STEP 0", "1 TO 0 STEP -.5",
    "1E99 TO 1E99", "1 TO 3 STEP 1E-5", "0 TO 2 STEP 2.9", "2 TO 1", "1 TO 3 STEP \"A\"",
]  # fmt: skip


@pytest.mark.parametrize("bounds", FOR_CASES)
def test_for_bounds_like_rom(bounds):
    """PC-1261系とPC-1350のFORは、終わりと増分を整数にせず、範囲も限らない。増分が0でも繰り返す(PC-1261。
    ROMのある本体と同じ)"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    lines = [f"10 C=0:S=0:FOR I={bounds}:C=C+1:S=S+I:IF C>5 GOTO 30", "20 NEXT I", "30 PRINT C;S;I"]
    steps = _pc1261_program(lines) + [("type", "RUN\n"), ("wait", 2), ("look", None)]
    a, b = play(boot("1261")[0], steps), play(basic_machine("1261"), steps)
    assert not differences(a, b), "\n".join(differences(a, b))


# ---- カセット ----


def _pc1261_program(lines: list[str]) -> list[tuple[str, object]]:
    """PROモードでNEWして行を入れ、RUNモードにする手順"""
    steps: list[tuple[str, object]] = [("mode", "PRO"), ("wait", 1.5), ("type", "NEW\n")]
    steps += [("type", line + "\n") for line in lines]
    return steps + [("mode", "RUN"), ("wait", 1.5)]


# MERGEで2つに分けたプログラム(10・30の行と、区切りのFFのあとの30・40の行。ROMのある本体で
# MERGEしたときのRAMと同じ)
BLOCKS = bytes.fromhex(
    "ff 00 0a 07 22 41 22 58 3d 31 0d 00 1e 04 59 3d 32 0d ff"
    " 00 1e 03 de 33 0d 00 28 0d 42 3d 37 3a 43 24 3d 22 58 59 5a 22 0d ff"
)
# チェックサムがオーバーフローするように、大きな値を多く置く
POKE = {0x6000 + i: (0xFF, 0xEE, 0xF8, 0x8F, i * 37 & 0xFF)[i % 5] for i in range(0x101)}


def _put_blocks(m) -> None:
    """プログラムの領域にBLOCKSを置き、いまのプログラムを2つ目にする"""
    from sc61box.basic.pc1261 import program

    start = m.model.prog_start
    m.mem[start : start + len(BLOCKS)] = BLOCKS
    end, head = start + len(BLOCKS) - 1, start + BLOCKS.index(0xFF, 1)
    m.mem[m.model.prog_end_ptr : m.model.prog_end_ptr + 2] = bytes([end & 0xFF, end >> 8])
    m.mem[program.PC1261.START_PTR : program.PC1261.START_PTR + 2] = bytes([head & 0xFF, head >> 8])


def _tape_bits(m, since: int) -> list[int]:
    """Cポートの音の切り替え(サイクルsinceから)を、2msごとのビットの並びにする"""
    from sc61box.basic.pc1261 import cassette

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
    ([f'{n} A$="ABCDEFGHIJKLMNOP":B=12345' for n in range(10, 90, 10)], 'CSAVE "LONG"\n'),
    (["10 PRINT 1"], "CSAVE\n"),
    (["10 PRINT 1"], 'CSAVE M "Q";&6000,&6013\n'),
    (["10 PRINT 1"], "CSAVE M &6000,&6100\n"),
    (None, 'CSAVE "ZZ"\n'),
]


@pytest.mark.parametrize("index", range(len(CSAVE_CASES)))
def test_csave_like_rom(index):
    """CSAVEとCSAVE Mでカセットに送る音(ビットの並び)、音を出し始める時刻と終わる時刻、
    液晶が、ROMのある本体と同じ(PC-1261。MERGEで分けたプログラムは区切りごと送る)"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    lines, command = CSAVE_CASES[index]
    out = []
    for m in (boot("1261")[0], basic_machine("1261")):
        play(m, _pc1261_program(lines or []))
        if lines is None:
            _put_blocks(m)
        for a, v in POKE.items():
            m.mem[a] = v
        start = m.cpu.cycles
        looks = play(m, [("type", command), ("wait", 25), ("look", None)])
        sound = [c for c, v in m.sound_events if c >= start and v]
        out.append((_tape_bits(m, start), looks, sound[0] - start, sound[-1] - start))
    (bits_a, a, first_a, end_a), (bits_b, b, first_b, end_b) = out
    assert len(bits_a) > 100 and bits_a == bits_b
    assert not differences(a, b), "\n".join(differences(a, b))
    assert abs(first_a - first_b) < CLOCK // 50 and abs(end_a - end_b) < CLOCK // 50


@pytest.fixture(scope="module")
def pc1261_tapes(tmp_path_factory):
    """PC-1261のROMのある本体にCSAVEさせたテープ(wav)"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    from basic_diff import play

    from sc61box import tape

    d = tmp_path_factory.mktemp("pc1261_tapes")
    out = {}
    for name, lines, command in (
        ("ab", ["10 PRINT 1", "20 A=5"], 'CSAVE "AB"'),
        ("cd", ["30 PRINT 3", '40 B=7:C$="XYZ"'], 'CSAVE "CD"'),
        ("m", ["10 PRINT 1"], 'CSAVE M "Q";&6000,&600F'),
        ("long", [f'{n} A$="ABCDEFGHIJKLMNOP"' for n in range(10, 100, 10)], 'CSAVE "LONG"'),
        ("mlong", ["10 PRINT 1"], 'CSAVE M "R";&6000,&60FF'),
        ("zz", None, 'CSAVE "ZZ"'),
    ):
        m, _t = boot("1261")
        play(m, _pc1261_program(lines or []))
        if lines is None:
            _put_blocks(m)
        for a, v in POKE.items():
            m.mem[a] = v
        path = str(d / f"{name}.wav")
        tape.write_wav(path, tape.record(m, command))
        out[name] = path
    return out


CLOAD_CASES = [
    (["5 X=1"], "ab", "CLOAD\n"),
    (["5 X=1"], "ab", 'CLOAD "AB"\n'),
    (["5 X=1"], "ab", 'CLOAD "XY"\n'),
    (["10 PRINT 1", "20 A=5"], "ab", 'CLOAD? "AB"\n'),
    (["10 PRINT 1", "20 A=6"], "ab", "CLOAD?\n"),
    (["5 X=1"], "m", "CLOAD M\n"),
    (["5 X=1"], "m", 'CLOAD M "Q";&6004\n'),
    (["5 X=1"], "ab", "CLOAD M\n"),
    (["5 X=1"], "m", "CLOAD\n"),
    (['10 CHAIN "AB"', "20 PRINT 7"], "ab", "RUN\n"),
    (["5 X=1"], "long", "CLOAD\n"),
    (["5 X=1"], "mlong", "CLOAD M\n"),
    (["5 X=1"], None, "CLOAD\n"),
    # MERGE: 読んだ行の最初の行番号が、いまのプログラムの最後の行番号より大きくなければ、
    # 区切りを置いて別のプログラムにする
    (["5 X=1", "30 Y=2"], "cd", "MERGE\n"),
    (["10 X=1", "20 Y=2"], "cd", "MERGE\n"),
    ([], "cd", "MERGE\n"),
    (["5 X=1"], "zz", "CLOAD\n"),
    # 区切りのあるテープのMERGE: 読んだ行の前の区切りだけを除き、テープの中の区切りは残す
    (["5 X=1"], "zz", "MERGE\n"),
    (["50 X=1"], "zz", "MERGE\n"),
]


@pytest.mark.parametrize("index", range(len(CLOAD_CASES)))
def test_cload_like_rom(index, pc1261_tapes):
    """CLOAD・CLOAD?・CLOAD M・MERGE・CHAINで、ROMのある本体が録ったテープを読んだ結果
    (液晶、プログラム、変数、マシン語を置いたRAM)と時刻が、ROMのある本体と同じ(PC-1261)"""
    from basic_diff import basic_machine, differences, play

    from sc61box import tape

    lines, name, command = CLOAD_CASES[index]
    out = []
    for m in (boot("1261")[0], basic_machine("1261")):
        play(m, _pc1261_program(lines))
        for a in POKE:
            m.mem[a] = 0
        if name is not None:
            m.tape = tape.TapeIn(pc1261_tapes[name])
        # 液晶を見る時刻は、ROMが>と右端の*を描き替える途中(約50ms)を避ける
        looks = play(m, [("type", command)] + [("wait", 2.2), ("look", None)] * 9)
        m.brk = True  # 待ち続けていれば、BRKで止める
        m.run(CLOCK * 3 // 10)
        m.brk = False
        looks += play(m, [("wait", 0.5), ("look", None)])
        out.append((looks, bytes(m.mem[0x6000:0x6100])))
    (a, ram_a), (b, ram_b) = out
    assert not differences(a, b), "\n".join(differences(a, b))
    assert ram_a == ram_b


def test_merged_programs_like_rom(pc1261_tapes):
    """MERGEで分けたプログラム: LIST・行の登録・RUNはいまのプログラムに、ラベルはすべての
    プログラムから探し、行番号は実行している行のプログラムから探す(PC-1261)"""
    from basic_diff import basic_machine, differences, play

    from sc61box import tape

    steps = [
        ("type", 'GOTO "A"\n'), ("wait", 1.5), ("look", None),
        ("type", "GOTO 10\n"), ("wait", 1.5), ("look", None), ("keys", ["CL"]),
        ("type", "RUN\n"), ("wait", 1.5), ("look", None), ("keys", ["ENTER"]), ("wait", 1),
        ("look", None), ("mode", "PRO"), ("wait", 1.5), ("keys", ["DOWN"]), ("wait", 0.5),
        ("look", None), ("type", "35 Z=9\n"), ("wait", 0.5), ("look", None),
        ("type", "5 Q=1\n"), ("wait", 0.5), ("look", None), ("type", "NEW\n"), ("wait", 0.5),
        ("look", None),
    ]  # fmt: skip
    out = []
    for m in (boot("1261")[0], basic_machine("1261")):
        play(m, _pc1261_program(['10 "A" GOTO 30', "30 PRINT 1"]))
        m.tape = tape.TapeIn(pc1261_tapes["cd"])
        play(m, [("type", "MERGE\n"), ("wait", 14)])
        out.append(play(m, steps))
    a, b = out
    assert not differences(a, b), "\n".join(differences(a, b))


def test_cload_frees_arrays_when_lines_reach_them(tmp_path):
    """CLOADで、行が配列の場所に届くと、配列と2字の名前の変数を消して読み続ける。固定の変数は
    残る(PC-1261。ROMのある本体と同じ)"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    from sc61box import tape

    lines = [f'{10 * k} A$="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"' for k in range(1, 15)]
    src, _t = boot("1261")
    play(src, _pc1261_program(lines))
    path = str(tmp_path / "s.wav")
    tape.write_wav(path, tape.record(src, 'CSAVE "S"'))
    setup = ["A=5\n", "AB=7\n", "DIM B$(111)*80\n"]
    out = []
    for m in (boot("1261")[0], basic_machine("1261")):
        play(
            m,
            _pc1261_program(["10 X=1"]) + [x for c in setup for x in (("type", c), ("wait", 0.5))],
        )
        m.tape = tape.TapeIn(path)
        looks = play(m, [("type", "CLOAD\n")] + [("wait", 5), ("look", None)] * 6)
        looks += play(m, [("keys", ["CL"]), ("type", "A\n"), ("wait", 0.5), ("look", None)])
        looks += play(m, [("keys", ["CL"]), ("type", "AB\n"), ("wait", 0.5), ("look", None)])
        out.append(looks)
    a, b = out
    assert a[-3].lcd.startswith(">")
    assert not differences(a, b), "\n".join(differences(a, b))


LONG_LINES = [f'{n} A$="ABCDEFGHIJKLMNOP":B=12345' for n in range(10, 100, 10)]

# (機種, 命令, BRKを押す時刻, 音が止まる時刻)。時刻は音を出し始めてからのms。止まる時刻は
# ROMのある本体で観察した値。初めの1のあいだは約500msごと(最後の約500msでは見ない)、中身は
# 1バイトごと(120バイトごとのチェックサムと、終わりのFFh・マーク・チェックサムでは見ない)。
# PC-1350は、音を出し始めてから36msはビット4だけで、BRKを見たあと1を9つ送り、ビット4だけを
# 36ms立ててから止める
CSAVE_BRK_CASES_PC1261 = [
    ("1261", 'CSAVE "LONG"', 300, 500),
    ("1261", 'CSAVE "LONG"', 7700, 8346),
    ("1261", 'CSAVE "LONG"', 8360, 8372),
    ("1261", 'CSAVE "LONG"', 11450, 11492),
    ("1261", 'CSAVE "LONG"', 16100, 16178),
    ("1261", "CSAVE M &6000,&6100", 7700, 8634),
    ("1261", "CSAVE M &6000,&6100", 15350, 15426),
    ("1350", 'CSAVE "LONG"', 300, 590),
    ("1350", 'CSAVE "LONG"', 7700, 8436),
    ("1350", 'CSAVE "LONG"', 11490, 11582),
    ("1350", 'CSAVE "LONG"', 16150, 16268),
]


def _csave_brk_stop(m, command: str, at: int) -> tuple[int, int]:
    """mでcommandを打ち、音を出し始めてからat ms後にBRKを押して、音が止まるまで押し続ける。
    (音が止まる時刻, >を出す時刻)。時刻は音を出し始めてからのms"""
    from basic_diff import look, play

    if m.model.family == "1350":
        m.run(CLOCK)
    play(m, _pc1261_program(LONG_LINES))
    start = m.cpu.cycles
    play(m, [("type", command + "\n")])
    while not any(c >= start and v for c, v in m.sound_events):
        m.run(CLOCK // 500)
    first = next(c for c, v in m.sound_events if c >= start and v)
    m.run(first + at * CLOCK // 1000 - m.cpu.cycles)
    press = m.cpu.cycles
    m.brk = True
    for _ in range(1000):  # 音が止まるまで(2秒まで)
        if any(c > press and v == 0 for c, v in m.sound_events):
            break
        m.run(CLOCK // 500)
    m.brk = False
    stop = next(c for c, v in m.sound_events if c > press and v == 0)
    for _ in range(1000):  # >を出すまで(2秒まで)
        if any(row.strip().startswith(">") for row in look(m).lcd.split("\n")):
            break
        m.run(CLOCK // 500)
    return (stop - first) * 1000 // CLOCK, (m.cpu.cycles - first) * 1000 // CLOCK


@pytest.mark.parametrize("index", range(len(CSAVE_BRK_CASES_PC1261)))
def test_csave_checks_brk_at_observed_times(index):
    """PC-1261系とPC-1350のCSAVEがBRKを見て音を止める時刻と、>を出す時刻が、ROMのある本体で
    観察した時刻と同じ(ROMなし)。PC-1261は止めてからも、送り終えたときと同じ約913ms待つ"""
    from basic_diff import basic_machine

    model, command, at, stop = CSAVE_BRK_CASES_PC1261[index]
    own, prompt = _csave_brk_stop(basic_machine(model), command, at)
    assert abs(own - stop) <= 2
    assert abs(prompt - stop - (10 if model == "1350" else 913)) <= 10, prompt - stop


@pytest.mark.parametrize("index", range(len(CSAVE_BRK_CASES_PC1261)))
def test_csave_checks_brk_like_rom_pc1261(index):
    """PC-1261系とPC-1350のCSAVEがBRKを見て音を止める時刻、>を出す時刻と、止めたあとの液晶が、
    ROMのある本体と同じ"""
    from basic_diff import basic_machine, differences, play

    model, command, at, _stop = CSAVE_BRK_CASES_PC1261[index]
    if not (HAVE_ROM_1350 if model == "1350" else HAVE_ROM_1260):
        pytest.skip("ROMがない")
    out = []
    for m in (boot(model)[0], basic_machine(model)):
        times = _csave_brk_stop(m, command, at)
        out.append((times, play(m, [("wait", 0.5), ("look", None)])))
    ((stop_a, prompt_a), a), ((stop_b, prompt_b), b) = out
    assert abs(stop_a - stop_b) <= 3 and abs(prompt_a - prompt_b) <= 15, out
    assert not differences(a, b), "\n".join(differences(a, b))


def test_brk_in_cload_waits_like_observed():
    """CLOADをBRKで止めると、読み終えたときと同じだけ待ってから>を出す(PC-1261は約910ms、
    PC-1350は約62ms。そのあいだPC-1261はBUSYを点けたまま。ROMのある本体で観察。ROMなし)"""
    from basic_diff import basic_machine, look, play

    for model, wait in (("1261", 910), ("1350", 62)):
        m = basic_machine(model)
        if model == "1350":
            m.run(CLOCK)
        play(m, _pc1261_program(["5 X=1"]) + [("type", "CLOAD\n"), ("wait", 0.3)])
        press = m.cpu.cycles
        m.brk = True
        m.run(CLOCK // 50)
        m.brk = False
        if model == "1261":
            assert "BUSY" in look(m).symbols
        for _ in range(1000):  # >を出すまで(2秒まで)
            if any(row.strip().startswith(">") for row in look(m).lcd.split("\n")):
                break
            m.run(CLOCK // 500)
        assert abs((m.cpu.cycles - press) * 1000 // CLOCK - wait) <= 10, model


def _file_wav(path: str, kind: int, data: bytes, place: bytes = b"", flip: int | None = None):
    """PC-1261系の形のファイルを、テープの頭から200ms後に始まる音にしてwavに書く。flipの位置の
    バイトは最下位のビットを変える(チェックサムを合わなくする)"""
    from sc61box import tape
    from sc61box.basic.pc1261 import cassette

    raw = bytearray(cassette.file_bytes(kind, b"QR", data, place))
    if flip is not None:
        raw[flip] ^= 0x01
    events, c, mode = [], CLOCK // 5, -1
    for bit in cassette.bits(bytes(raw)):
        want = cassette.ONE if bit else cassette.ZERO
        if want != mode:
            events.append((c, want))
            mode = want
        c += cassette.BIT
    events.append((c, 0))
    tape.write_wav(path, tape.render(events, 0, c + CLOCK // 3))


def _lines(pairs: list[tuple[int, bytes]]) -> bytes:
    return b"".join(bytes([n >> 8, n & 0xFF, len(b) + 1]) + b + b"\x0d" for n, b in pairs)


BAD_PROGRAM = _lines([(10, b"\xde1"), (20, b"A=5"), (30, b'B$="XYZ"')])  # 10 PRINT 1 …
BAD_SAME = ["10 PRINT 1", "20 A=5", '30 B$="XYZ"']
BAD_MACHINE = bytes((0xFF, 0xEE, 0xF8, 0x8F, i * 37 & 0xFF)[i % 5] for i in range(200))

# (機種, BASICか, データのバイト数(マシン語), 変えるバイトの位置, 行, 命令, 待つ字, 字が出る時刻)。
# 時刻はテープの再生を始めてからのmsで、ROMのある本体で観察した値(Noneなら見ない)。中身の
# チェックサムが合わないときとCLOAD?で違うときも、読み終えたときと同じだけ待ってからERROR 8。
# CLOAD?は違うバイトを読んだところでやめる。CLOAD Mは最後のデータのバイトまでしか読まない
# (そのあとのチェックサムは見ない)
BAD_TAPE_CASES = [
    ("1261", True, 0, None, ["5 X=1"], "CLOAD", ">", 10160),
    ("1261", True, 0, 37, ["5 X=1"], "CLOAD", "ERROR 8", 10166),
    ("1261", True, 0, 14, ["5 X=1", "7 Y=2:Z=3"], "MERGE", "ERROR 8", 10166),
    ("1261", True, 0, 14, BAD_SAME, "CLOAD?", "ERROR 8", 9569),
    ("1261", True, 0, 37, BAD_SAME, "CLOAD?", "ERROR 8", 10166),
    ("1261", True, 0, None, ["10 PRINT 1", "20 A=6", '30 B$="XYZ"'], "CLOAD?", "ERROR 8", 9747),
    ("1261", False, 16, 19, ["5 X=1"], "CLOAD M", ">", 10134),
    ("1261", False, 200, 139, ["5 X=1"], "CLOAD M", "ERROR 8", None),
    ("1261", False, 200, 140, ["5 X=1"], "CLOAD M", ">", 14944),
    ("1261", False, 120, 139, ["5 X=1"], "CLOAD M", ">", None),
    ("1350", True, 0, None, ["5 X=1"], "CLOAD", ">", 9310),
    ("1350", True, 0, 37, ["5 X=1"], "CLOAD", "ERROR 8", 9312),
    ("1350", True, 0, None, ["10 PRINT 1", "20 A=6", '30 B$="XYZ"'], "CLOAD?", "ERROR 8", 8896),
    ("1350", False, 200, 140, ["5 X=1"], "CLOAD M", ">", 14094),
]


def _bad_tape(tmp_path, index: int) -> str:
    from sc61box.basic.pc1261 import cassette

    model, basic, size, flip = BAD_TAPE_CASES[index][:4]
    path = str(tmp_path / f"bad{index}.wav")
    if basic:
        _file_wav(path, cassette.BASIC, BAD_PROGRAM, flip=flip)
    else:
        start = 0x6C00 if model == "1350" else 0x6000
        data = BAD_MACHINE[:size]
        _file_wav(path, cassette.MACHINE, data, cassette.place_field(start, size), flip)
    return path


@pytest.mark.parametrize("index", range(len(BAD_TAPE_CASES)))
def test_bad_tape_like_observed(index, tmp_path):
    """チェックサムの合わないテープとCLOAD?の違い: ERROR 8を出す時刻(読み終えたときと同じだけ
    待つ)と、CLOAD Mが最後のデータのあとのチェックサムを見ないことが、ROMのある本体で観察した
    とおり(ROMなし)"""
    from basic_diff import basic_machine, look, play

    from sc61box import tape

    model, _basic, _size, _flip, lines, command, needle, when = BAD_TAPE_CASES[index]
    m = basic_machine(model)
    if model == "1350":
        m.run(CLOCK)
    play(m, _pc1261_program(lines))
    m.tape = tape.TapeIn(_bad_tape(tmp_path, index))
    play(m, [("type", command + "\n")])
    while m.tape.start is None:
        m.run(CLOCK // 500)
    seen = None
    for _ in range(25 * 250):
        m.run(CLOCK // 250)
        if needle in look(m).lcd:
            seen = (m.cpu.cycles - m.tape.start) * 1000 // CLOCK
            break
    assert seen is not None, look(m).lcd
    assert when is None or abs(seen - when) <= 20, (seen, when)


@pytest.mark.parametrize("index", range(len(BAD_TAPE_CASES)))
def test_bad_tape_like_rom(index, tmp_path):
    """チェックサムの合わないテープとCLOAD?の違いで、液晶とRAM(プログラム、変数、マシン語を
    置いた所)が、ROMのある本体と同じ"""
    from basic_diff import basic_machine, differences, play

    from sc61box import tape

    model, _basic, _size, _flip, lines, command, _needle, _when = BAD_TAPE_CASES[index]
    if not (HAVE_ROM_1350 if model == "1350" else HAVE_ROM_1260):
        pytest.skip("ROMがない")
    path = _bad_tape(tmp_path, index)
    ram = slice(0x6030, 0x6D00) if model == "1350" else slice(0x4080, 0x6100)
    out = []
    for m in (boot(model)[0], basic_machine(model)):
        if model == "1350":
            m.run(CLOCK)
        play(m, _pc1261_program(lines))
        m.tape = tape.TapeIn(path)
        looks = play(m, [("type", command + "\n")] + [("wait", 2.2), ("look", None)] * 8)
        m.brk = True  # 待ち続けていれば、BRKで止める
        m.run(CLOCK * 3 // 10)
        m.brk = False
        looks += play(m, [("wait", 0.5), ("look", None)])
        out.append((looks, bytes(m.mem[ram])))
    (a, ram_a), (b, ram_b) = out
    assert not differences(a[-2:], b[-2:]), "\n".join(differences(a[-2:], b[-2:]))
    assert ram_a == ram_b


# MERGEで2つに分けたプログラム(BLOCKS)をCSAVEしたテープ
MERGE_BLOCKS = (
    _lines([(10, b'"A"X=1'), (30, b"Y=2")])
    + b"\xff"
    + _lines([(30, b"\xde3"), (40, b'B=7:C$="XYZ"')])
)


@pytest.mark.parametrize("model", ["1261", "1350"])
def test_merge_tape_with_blocks_like_observed(model, tmp_path):
    """区切りのあるテープをMERGEすると、読んだ行の最初の行番号がいまのプログラムの最後の行番号
    より大きければ、読んだ行の前の区切りだけを除き、テープの中の区切りは残す。いまのプログラムの
    頭は、読み終えたときは読んだ行の前の区切り、>を出す前にテープの最後の区切りにする(ROMの
    ある本体で観察したRAM。ROMなし)"""
    from basic_diff import basic_machine, play

    from sc61box import tape
    from sc61box.basic.pc1261 import cassette, program
    from sc61box.basic.variables import word

    path = str(tmp_path / "blocks.wav")
    _file_wav(path, cassette.BASIC, MERGE_BLOCKS)
    m = basic_machine(model)
    if model == "1350":
        m.run(CLOCK)
    play(m, _pc1261_program(["5 X=1"]))
    m.tape = tape.TapeIn(path)
    play(m, [("type", "MERGE\n")])
    while m.tape.start is None:
        m.run(CLOCK // 500)
    p = program.PC1350 if model == "1350" else program.PC1261
    base, first = m.model.prog_start, _lines([(5, b"X=1")])
    for _ in range(10000):  # 読み終えて行を置くまで
        if p.end(m) >= base + len(first) + 2:
            break
        m.run(CLOCK // 500)
    # 読み終えたところ: 区切りはまだ除かず、頭は読んだ行の前の区切り
    assert m.mem[base + 1 + len(first)] == 0xFF
    assert word(m, p.START_PTR) == base + 1 + len(first)
    m.run(CLOCK * 3 // 2)
    want = b"\xff" + first + MERGE_BLOCKS + b"\xff"
    assert bytes(m.mem[base : base + len(want)]) == want
    assert word(m, p.START_PTR) == base + 1 + len(first) + MERGE_BLOCKS.index(0xFF)
    assert p.end(m) == base + len(want) - 1


# ---- プリンタ ----

PC1261_PRINTER_CASES = [
    (['10 LPRINT USING "###.##";1.5;2'], ["RUN\n", ("wait", 1), None]),
    (['10 LPRINT 1;"ABCDEFGHIJKLMNOPQRSTUVWXYZ"'], ["RUN\n", ("wait", 1), None]),
    (['10 LPRINT "ABCDEFGHIJKLMNO",1,"XY",-5'], ["RUN\n", ("wait", 1), None]),
    (["10 LPRINT 12345678901;1E-5;-0.5"], ["RUN\n", ("wait", 1), None]),
    (['10 LPRINT "A","B","C":LPRINT 1,2,3,4,5'], ["RUN\n", ("wait", 1), None]),
    (['10 LPRINT "A",1;"B"'], ["RUN\n", ("wait", 1), None]),
    (['10 USING "##.#":LPRINT 1.25;2:LPRINT USING "&&";"ABC";1'], ["RUN\n", ("wait", 1), None]),
    # ;で終わったLPRINTは字をためておき、次のLPRINTやプログラムの終わりで送る
    (['10 LPRINT "A";:PRINT 7:LPRINT 5', '20 LPRINT "ABCDEFGHIJKLMNOPQRSTUVWXYZ";:LPRINT "12"'],
     ["RUN\n", ("wait", 1), None, "\n", ("wait", 1), None]),
    (['10 LPRINT "A";:LPRINT 1,2', '20 LPRINT 5;'], ["RUN\n", ("wait", 1), None]),
    (['10 LPRINT "A";:STOP'], ["RUN\n", ("wait", 1), None, "CONT\n", ("wait", 1), None]),
    (['10 LPRINT "A";:X=1/0', '20 LPRINT "B"'],
     ["RUN\n", ("wait", 1), None, ["CL"], "RUN 20\n", ("wait", 1), None]),
    (["10 FOR I=32 TO 122:LPRINT CHR$ I;:NEXT I", "20 FOR I=161 TO 223:LPRINT CHR$ I;:NEXT I"],
     ["RUN\n", ("wait", 9), None]),
    (["10 FOR I=1 TO 2", "20 LPRINT I", "30 NEXT I", '40 PRINT "AB";"CDEFGHIJKLMNOPQRSTUVWXYZ"',
      "12345 A=1", '65279 B=2:PRINT "ABCDEFGHIJKLMNOPQRSTUVWXYZ"'],
     [("mode", "PRO"), ("wait", 1.5), "LLIST\n", ("wait", 3), None, ("mode", "RUN"), ("wait", 1.5),
      "LLIST 20\n", ("wait", 1), None]),
    (['10 "A" PRINT 1', "20 A=1", "30 B=2"],
     [("mode", "PRO"), ("wait", 1.5), "LLIST 20,\n", ("wait", 1), None, "LLIST 25\n", ("wait", 1),
      None, "LLIST ,\n", None, ["CL"], "LLIST 40\n", None, ["CL"], "LLIST 20,25\n", ("wait", 1),
      None, "LLIST 10,10\n", None, ["CL"], "LLIST 0,10\n", None, ["CL"], "LLIST 10,20,30\n", None,
      ["CL"], 'LLIST "A",20\n', ("wait", 1), None, 'LLIST "B"\n', None, ["CL"], "LLIST ,20\n",
      ("wait", 1), None]),
    (["10 PRINT 1"], [("mode", "PRO"), ("wait", 1.5), 'PASS "A"\n', None, "LLIST\n", ("wait", 1),
                      None]),
]  # fmt: skip


def _pc1261_printer_machine(rom: bool):
    """プリンタをつないだPC-1261"""
    from basic_diff import basic_machine

    m = boot("1261")[0] if rom else basic_machine("1261")
    m.connect_printer()
    m.power_off()
    m.mode = "RUN"
    m.wake()
    m.run(CLOCK)
    return m


def _steps(lines: list[str], actions) -> list[tuple[str, object]]:
    steps = _pc1261_program(lines)
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


@pytest.mark.parametrize("index", range(len(PC1261_PRINTER_CASES)))
def test_printer_like_rom(index):
    """LPRINTとLLISTでプリンタに送るコードと行の分け方、液晶が、ROMのある本体と同じ(PC-1261)"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    from basic_diff import differences, play

    steps = _steps(*PC1261_PRINTER_CASES[index])
    ma, mb = _pc1261_printer_machine(True), _pc1261_printer_machine(False)
    a, b = play(ma, steps), play(mb, steps)
    assert not differences(a, b), "\n".join(differences(a, b))
    assert ma.printer is not None and mb.printer is not None
    assert ma.printer.rows() == mb.printer.rows()


PRINTING_TIMES = [
    (['10 LPRINT "ABCDEFGHIJKLMNOPQRSTUVWXYZ";1', "20 LPRINT 1,2:LPRINT 3"], "RUN\n", "RUN"),
    (['10 LPRINT "ABCDEFGHIJKLMNOPQRSTUVWXYZ";1', "20 LPRINT 1,2:LPRINT 3"], "LLIST\n", "PRO"),
    (["10 FOR I=1 TO 5:LPRINT I;:NEXT I", "20 LPRINT 7"], "RUN\n", "RUN"),
]


@pytest.mark.parametrize(("lines", "command", "mode"), PRINTING_TIMES)
def test_printing_time_like_rom(lines, command, mode):
    """LPRINTとLLISTで送り始めるまでと、送り終わるまでの時間が、ROMのある本体と5%以内
    (PC-1261)"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    from basic_diff import play

    def took(rom: bool) -> tuple[float, float]:
        m = _pc1261_printer_machine(rom)
        play(m, _steps(lines, [("mode", mode), ("wait", 1.5)] if mode == "PRO" else []))
        times: list[int] = []
        printer = m.printer
        assert printer is not None
        orig = printer.put

        def put(code):
            times.append(m.cpu.cycles)
            orig(code)

        printer.put = put
        start = m.cpu.cycles
        play(m, [("type", command), ("wait", 4)])
        return (times[0] - start) / CLOCK, (times[-1] - start) / CLOCK

    (first_a, last_a), (first_b, last_b) = took(True), took(False)
    assert abs(first_b / first_a - 1) < 0.05 and abs(last_b / last_a - 1) < 0.05, (
        (first_a, last_a),
        (first_b, last_b),
    )


@pytest.mark.parametrize("model", ["1260", "1261", "1262"])
def test_app_runs_pc1261_basic_without_rom(model):
    """--noromのPC-1260・1261・1262は、ROMなしのBASICで動く(作業欄だけにならない)。CALLで
    ROMの番地へ入っても、そこでやめてBASICに戻る"""
    from basic_diff import lcd_pc1261
    from helpers import make_app

    app = make_app(model=model, frames=3, norom=True)
    m = app.m
    assert m.basic is not None and not app.bench_only
    app.typer.add_text("1+2\n")
    for _ in range(600):
        app.frame()
        if lcd_pc1261(m).split("\n")[1].strip() == "3.":
            break
    assert lcd_pc1261(m).split("\n")[1].strip() == "3."
    app.typer.add_keys([["CL"]])
    app.typer.add_text("CALL &8000\n")
    for _ in range(600):
        app.frame()
        if lcd_pc1261(m).startswith(">") and m.basic.notice is None:
            break
    assert lcd_pc1261(m).startswith(">")


def _call_entry(m, line: str, prog: str | None) -> bytes:
    """内部RAMの02h〜07hを5Ahにしてから、lineを打って4000h番地を呼び、呼んだ先の頭の内部RAMの
    00h〜0Fhを返す(4000h番地のマシン語が4100h番地からと入れ替える)"""
    from sc61box.autotype import Typer

    t = Typer(m)
    t.add_mode("PRO")
    t.add_text("NEW\n" + (prog or ""))
    finish(m, t)
    m.run(CLOCK // 2)
    if prog:
        t.add_mode("RUN")
        finish(m, t)
        m.run(CLOCK)
    # LIDP 4100h、LP 0、LII 0Fh、EXWD、RTN
    m.mem[0x4000:0x4008] = bytes([0x10, 0x41, 0x00, 0x80, 0x00, 0x0F, 0x19, 0x37])
    m.mem[0x4100:0x4110] = bytes(16)
    m.cpu.ram[2:8] = b"\x5a" * 6
    t.add_text(line + "\n")
    finish(m, t)
    m.run(CLOCK)
    return bytes(m.mem[0x4100:0x4110])


@pytest.mark.parametrize(("line", "prog"), [("CALL &4000", None), ("RUN", "10 CALL &4000\n")])
def test_call_entry_registers_like_rom(line, prog):
    """CALLで呼んだ先の頭のA・B・X・Yが、前のマシン語が残した値によらず、ROMのある本体と同じ
    (PC-1261。LC-3のコンパイラは、このA・Bで動きを変える)"""
    from basic_diff import basic_machine

    got = _call_entry(basic_machine("1261"), line, prog)
    assert got[2:4] == b"\x00\x66" and got[6:8] == b"\xdd\x66", got.hex()
    if HAVE_ROM_1260:
        assert got[2:8] == _call_entry(boot("1261")[0], line, prog)[2:8]


# 液晶に出るはずの字と、それを見るフレーム、そのあと押すキー(フレーム、キー)。キーを押したあとは、
# 押す前と液晶が違うはず
LC3_SAMPLES = {
    "lc3-hello": ("ｱｲｳｴｵ", 399, ()),
    "lc3-chars": ("LC-3", 399, ()),
    "lc3-move": ("", 99, ((100, "6"), (160, None))),
    "lc3-block": ("8:UP 2:DOWN", 99, ((100, "5"), (105, None))),
}


@pytest.mark.parametrize("name", list(LC3_SAMPLES))
def test_lc3_samples_run_without_rom(name):
    """コンパイラLC-3でコンパイルしたサンプルが、ROMなしの本体(PC-1261)で、ROMの番地でやめずに動く"""
    from basic_diff import lcd_pc1261
    from helpers import make_app

    from sc61box import programs

    shown, look, keys = LC3_SAMPLES[name]
    app = make_app("1261", frames=30, norom=True)
    m = app.m
    prog = programs.find(name, "1261")
    assert prog is not None and m.basic is not None
    basic = m.basic
    m.cpu.ram[2:8] = b"\x5a" * 6  # 前に動かしたマシン語が残した値(保存したRAMから戻したときなど)
    app.open_program(prog, run=True)
    before = ""
    for i in range(400):
        for frame, key in keys:
            if frame == i:
                m.held.clear()
                if key:
                    m.held.add(key)
        app.frame()
        assert basic.notice is None, (i, basic.notice)
        if i == look:
            before = lcd_pc1261(m)
            assert shown in before.replace("\n", ""), before
    text = lcd_pc1261(m)
    assert not text.startswith(">"), text  # まだコンパイルしたプログラムの中
    assert not keys or text != before, text
    app.close()


# ---- 状態の保存 ----


def _restored(m, same: bool):
    """mの状態を保存して、同じ本体(same)か新しい本体に戻す"""
    import json

    from basic_diff import basic_machine

    state = json.loads(json.dumps(m.snapshot()))
    if not same:
        m = basic_machine("1261")
        m.connect_printer()
    m.restore(state)
    m.run(CLOCK // 5)
    return m


@pytest.mark.parametrize("same", [False, True])
def test_state_restore_keeps_print_continuation(same):
    """;で終わったPRINTの待ちで保存して戻しても、次のPRINTは続けて書く"""
    from basic_diff import basic_machine, lcd_pc1261, play

    m = basic_machine("1261")
    play(m, _pc1261_program(['10 PRINT "A";', '20 PRINT "B"']) + [("type", "RUN\n"), ("wait", 1)])
    m = _restored(m, same)
    play(m, [("type", "\n"), ("wait", 1)])
    assert lcd_pc1261(m).split("\n")[0].strip() == "AB"


@pytest.mark.parametrize("same", [False, True])
def test_state_restore_keeps_lprint_buffer(same):
    """;で終わったLPRINTのためた字は、保存して戻しても残る"""
    from basic_diff import basic_machine, play

    m = basic_machine("1261")
    m.connect_printer()
    lines = ['10 LPRINT "A";:STOP', '20 LPRINT "B"']
    play(m, _pc1261_program(lines) + [("type", "RUN\n"), ("wait", 1)])
    m = _restored(m, same)
    play(m, [("keys", ["CL"]), ("type", "CONT\n"), ("wait", 1)])
    assert m.printer is not None and m.printer.rows()[-1] == b"AB"


@pytest.mark.parametrize("same", [False, True])
def test_state_restore_keeps_kana_input(same):
    """カナの入力(KANAの記号)は、保存して戻しても続く"""
    from basic_diff import basic_machine, lcd_pc1261, play

    m = basic_machine("1261")
    play(m, _pc1261_program([]) + [("keys", ["SHIFT"]), ("keys", ["8"]), ("wait", 0.3)])
    m = _restored(m, same)
    play(m, [("keys", ["Q"]), ("wait", 0.3)])
    assert "KANA" in m.symbols() and lcd_pc1261(m).startswith("ｱ")


def test_kana_input_survives_power_cycle():
    """電源を入れ直しても、カナの入力は続く(ROMのある本体と同じ)"""
    from basic_diff import basic_machine, lcd_pc1261, play

    m = basic_machine("1261")
    play(m, _pc1261_program([]) + [("keys", ["SHIFT"]), ("keys", ["8"]), ("wait", 0.3)])
    m.power_off()
    m.mode = "RUN"
    m.wake()
    m.run(CLOCK)
    play(m, [("keys", ["Q"]), ("wait", 0.3)])
    assert lcd_pc1261(m).startswith("ｱ")


def test_program_text_stored_like_rom():
    """プログラムの一覧から読み込むとき(basictext.encode_programでRAMに置く)、ROMなしの
    PC-1261もPC-1261系とPC-1350の形で置き、ROMのある本体と同じRAMと実行になる(カナとCURSORの例)"""
    if not HAVE_ROM_1260:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    from sc61box import basictext, keytype

    text = '10 CLS:WAIT 0\n20 CURSOR 1:PRINT "ポケットコンピュータ PC-1261"\n30 END\n'
    out = []
    for m in (boot("1261")[0], basic_machine("1261")):
        play(m, [("mode", "RUN"), ("wait", 1.5)])
        data = basictext.encode_program(keytype.typed_text(text, "1261"), m.mem, True)
        assert data is not None and m.store_program(data)
        out.append(play(m, [("look", None), ("type", "RUN\n"), ("wait", 1), ("look", None)]))
        assert basictext.program_text(m.mem, start=m.program_start(), pc1261=True).startswith(
            "10 CLS:WAIT 0\n"
        )
    a, b = out
    assert not differences(a, b), "\n".join(differences(a, b))


def test_lcd_stays_on_while_running():
    """PC-1261系は、プログラムを実行しているあいだも液晶が消えず、BUSYの記号が見える(ROMの
    ある本体もROMなしも。PC-1251系とは違う)"""
    from basic_diff import basic_machine, play

    machines = [basic_machine("1261")] + ([boot("1261")[0]] if HAVE_ROM_1260 else [])
    for m in machines:
        play(m, _pc1261_program(["10 FOR I=1 TO 300:NEXT I"]) + [("type", "RUN\n")])
        m.run(CLOCK // 5)
        assert "BUSY" in m.symbols() and m.display_on()


# ---- PC-1350 ----

SESSIONS_1350 = {
    # AREADは、打っていた行を読むときに計算する。誤りは打った行のエラーで、←で打っていた行の所に
    # 呼び出す
    "def-typed": [
        "!PRO", '10 "M" AREAD A:PRINT A\n', '20 "N" AREAD A$:PRINT A$\n', "!RUN", "7Z751Z161?",
        "@DEF", "@M", "@LEFT", "@CLS", "12+", "@DEF", "@Q", "@RIGHT", "@CLS", "1+", "@DEF", "@N",
        "\n", "@CLS", "A$", "@DEF", "@M", "@LEFT",
    ],
    # IFの数の条件は正のときだけ成り立つ(液晶の外のPOINTの-1でも成り立たない)
    "if-negative": [
        "!PRO", "10 A=0:B=0:C=0:X=151\n", "20 IF POINT (X,5) LET A=1\n", "30 IF NOT 1 LET B=1\n",
        "40 IF 0.5 LET C=1\n", "50 PRINT A;B;C\n", "!RUN", "RUN\n~",
    ],
    "run": [
        "1+2\n", "@CLS", "1/0\n", "@LEFT", "@CLS", "2\n", "3\n", "4\n", "5\n", '"AB"\n', "A=1\n",
        "@UP", "@DOWN", "@CLS", "DIM C(2)\n", "MEM\n", "AB=3\n", 'B$="XY"\n', "Z\n", "@CLS",
        "SIN 30\n", "RADIAN\n", "SIN 30\n", "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\n",
        '"ABCDEFGHIJKLMNOPQRSTUVWXYZ"\n', "@LEFT", "@LEFT", "X", "\n", "1+2\n", "@LEFT", "X",
        "\n",
    ],
    "program": [
        "!PRO", '10 PRINT 1:PRINT "AB"\n', "20 PRINT 2,3\n", '30 A=5:PRINT A;"X"\n', "2", "0 A=5\n",
        "40 X=1/0\n", "5 REM\n", "LIST\n", "@UP", "@DOWN", "@DOWN", "@CLS", "@UP", "LIST 20\n",
        "!RUN", "RUN\n", "\n", "\n", "\n", "\n", "@CLS", "RUN 40\n", "@LEFT", "@CLS",
        "PRINT 1\n",
    ],
    "input": [
        "!PRO", "10 INPUT A:PRINT A*2\n", '20 B$="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"\n',
        "30 GOTO 30\n", "LIST 20\n", "!RUN", "RUN\n", "7\n", "\n", "BRK", "@CLS", "CONT\n", "BRK",
        "@CLS", "RUN\n", "BRK", "CONT\n",
    ],
    "edit": [
        "!PRO", '10 B$="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"\n', "20 A=1\n", "LIST\n", "@LEFT",
        "@RIGHT", "X", "@DOWN", "@CLS", '10 C$="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"', "@LEFT",
        "\n", "@UP", "@LEFT", "@DEL", "\n", '30 A$="ｱｲｳ abc":PRINT A$\n', "!RUN", "@KANA", "@Q",
        "@W", "@KANA", "@SHIFT,KANA", "@A", "@B", "@SHIFT,KANA", "\n",
    ],
    "cursor": [
        "!PRO", '10 CLS:WAIT 0:CURSOR 5,1:PRINT "AB":PRINT "CD"\n',
        '20 CURSOR 22,3:PRINT "XYZ":PRINT "Q"\n', '30 CURSOR 3:PRINT "R":CURSOR 0,0:PRINT 5;\n',
        '40 PRINT "S":WAIT:PRINT "T":CURSOR 30,0\n', "!RUN", "RUN 10\n~", "\n", "@CLS",
        "RUN 20\n~", "@CLS", "RUN 30\n~", "\n", "\n", "\n",
    ],
    # PRINT・INPUTの待ちでもMODEが効く(実行中は効かない)
    "wait-mode": [
        "!PRO", "10 PRINT 1\n", "20 INPUT A\n", "30 GOTO 30\n", "!RUN", "RUN\n", "@MODE",
        "@MODE", "RUN 20\n", "@MODE", "@MODE", "RUN 30\n", "@MODE", "BRK",
    ],
    # 上へ送ったあとで、打った行を呼び出す
    "recall": [
        "1\n", "2\n", "@LEFT", "X", "\n", "@CLS", "1\n", "2\n", "3\n", "1/0\n", "@LEFT", "X\n",
        "@RIGHT",
    ],
    # INPUTの答えのエラーのあとの←・→、CLS、↑と、打ち込んだCLS
    "input-error": [
        "!PRO", "10 INPUT A:PRINT A\n", '20 INPUT "N=";B\n', "!RUN", "RUN\n", "1/0\n", "@LEFT",
        "X", "\n", "@LEFT", "2\n", "RUN\n", "1/0\n", "@CLS", "5\n", "RUN\n", "12", "@CLS",
        "3\n", "RUN\n", "1/0\n", "@UP", "6\n", "RUN 20\n", "1/0\n", "@RIGHT", "\n", "@CLS",
        "1/0\n", "@CLS", "7\n",
    ],
    # 右上のSHIFT
    "shift2": ["@SHIFT2", "@Q", "@SHIFT2,KANA", "@A", "@SHIFT2,KANA", "@SHIFT2,1", "\n"],
    # SHIFTのあとI・Oで打つπ・√の字。PROモードで打ち始めると液晶を消す
    "pi": [
        "@SHIFT,I", "\n", "@SHIFT,I", "*2\n", "@SHIFT,O", "4\n", "2", "@SHIFT,I", "\n", "@CLS",
        "@SHIFT,I", "2\n", "@CLS", '"', "@SHIFT,I", "@SHIFT,O", '"\n', "!PRO", "10 A=",
        "@SHIFT,I", "+", "@SHIFT,O", "9:PRINT A\n", '20 PRINT "', "@SHIFT,I", '"\n', "LIST\n",
        "!RUN", "RUN\n", "\n", "\n", "!PRO", "@CLS", "3", "0 C=1\n", "@UP", "4", "0 D=2\n",
    ],
    # 何も打たずにENTER(下の行に>)、プリンタがないときのLPRINT・LLIST
    "enter-empty": [
        "\n", "\n", "1\n", "\n", '"A"\n', "\n", "!PRO", "\n", "\n", "10 A=1\n", "\n",
        "LLIST\n", "!RUN", "LLIST\n", "@CLS", "LPRINT 1\n", "\n", "@LEFT", "\n", "2", "@LEFT",
        "@DEL", "\n",
    ],
    # 出すもののないPRINTは何も書かない。LPRINTだけはプリンタがないとERROR 8
    "empty-print": [
        "!PRO", '10 WAIT 0:PRINT "A":PRINT:PRINT "B":END\n',
        '20 WAIT:PRINT "A";:PRINT:PRINT "B":USING "###":PRINT:PRINT 5:END\n',
        '30 LPRINT "A":LPRINT\n', "!RUN", "RUN 10\n~", "@CLS", "RUN 20\n", "\n", "\n", "\n",
        "\n", "RUN 30\n~",
    ],
    # シリアル: OPEN・CLOSE・OPEN$・CONSOLE、開いているあいだのSAVE・LOAD・LLIST・LPRINTは
    # 相手を待ち、BRKで止める
    "sio": [
        "OPEN$\n", "@CLS", 'OPEN "600,O,7,2,A,L,&1B"\n', "@CLS", "OPEN$\n", "@CLS", "OPEN\n",
        "@CLS", "CLOSE\n", "@CLS", "SAVE\n", "LOAD\n", "OPEN\n", "SAVE\n", "@CLS", 'OPEN "2400"\n',
        "@CLS", 'OPEN ",,,,J"\n', "@CLS", "LOAD\n", "BRK", "@CLS", "LLIST\n", "@CLS", "CLOSE\n",
        "CONSOLE 50\n", "@CLS", "CONSOLE 0\n", "@CLS", "!PRO", "10 OPEN:LPRINT 5:CLOSE\n",
        "20 LOAD\n", "30 X$=OPEN$:PRINT X$\n", "!RUN", "RUN 30\n", "\n", "RUN 20\n", "@CLS",
        "RUN 10\n", "BRK", "@CLS", "SAVE\n", "BRK", "@CLS", "LLIST\n", "BRK", "@CLS", "CLOSE\n",
    ],
    # TEXT・BASIC: 行を字の並びにし、中間コードに戻す。TEXTモードの行の登録、出し方、RUN
    "text": [
        "!PRO", '10 A=1:PRINT "X":REM ABC\n', "20 FOR I=1 TO 2:NEXT I:GOTO 10\n",
        '30 B$="IF":C=SIN 30+LEN B$\n', "TEXT\n", "LIST\n", "@CLS", "@UP", "@DOWN", "@LEFT", "@CLS",
        '40 PRINT "AB":GOTO 10\n', "50PRINT\n", "LIST\n", "@CLS", "10\n", "@CLS", "TEXT\n", "@CLS",
        "LIST 20\n", "@LEFT", "@RIGHT", "X", "\n", "!RUN", "TEXT\n", "@CLS", "RUN\n", "@CLS",
        "1+2\n", "!PRO", "BASIC\n", "BASIC\n", "@CLS", "LIST\n",
    ],
    # パスワードで保護しているあいだのTEXT・BASICはERROR 1
    "text-pass": [
        "!PRO", "10 PRINT 1\n", 'PASS "X"\n', "TEXT\n", "@CLS", 'PASS "X"\n', "TEXT\n", "@CLS",
        'PASS "X"\n', "BASIC\n", "@CLS", 'PASS "X"\n', "@CLS", "LIST\n",
    ],
    # SAVE・LOADのあとに何か書くとERROR 1。開いているあいだのLPRINTも、出すものを読んで
    # からエラーにする
    "sio-args": [
        "SAVE 1\n", "@CLS", "LOAD 1\n", "@CLS", 'SAVE "A"\n', "@CLS", "OPEN\n", "SAVE A\n",
        "@CLS", "LOAD ,\n", "@CLS", "!PRO", "10 OPEN:LPRINT 1/0\n", '20 OPEN:LPRINT "A",\n',
        "30 SAVE 1\n", "40 OPEN:LPRINT A$(\n", "!RUN", "RUN\n", "@CLS", "RUN 20\n", "@CLS",
        "RUN 30\n", "@CLS", "RUN 40\n", "@CLS", "CLOSE\n",
    ],
    # RUNとプログラムの終わりでシリアルを閉じる(STOPでは閉じない)
    "sio-run": [
        "!PRO", "50 PRINT PEEK &78B0\n", "60 OPEN:STOP\n", "70 OPEN:GOTO 50\n", "!RUN",
        "OPEN\n", "@CLS", "RUN 50\n", "\n", "@CLS", "RUN 60\n", "@CLS", "PEEK &78B0\n", "@CLS",
        "CONT\n", "\n", "@CLS", "RUN 70\n", "\n", "@CLS", "PEEK &78B0\n",
    ],
    # 打った描く命令は>を出さず、次の行は下から。プログラムの描く命令はPRINTと同じに
    # ENTERを待つ。CLSのあとのメッセージは2行目から
    "graphics": [
        "PSET (100,30)\n", "\n", "PSET (101,30)\n", "A", "\n", "@CLS", "1+2\n", "GPRINT 3\n",
        "@CLS", "LINE (90,28)-(95,31)\n", "@DOWN", "@CLS", "PRESET (100,30)\n", "@LEFT", "\n",
        "@CLS", "GCURSOR (5,5)\n", "@CLS", "POINT (101,30)\n", "PSET (1,1),R\n", "@CLS", "!PRO",
        "PSET (1,1)\n", "@CLS", "10 CLS:PSET (100,30):GPRINT 255:LINE (90,20)-(120,31),X,B\n",
        "20 PRINT POINT (100,30):STOP\n", "30 CLS:LINE (0,0)-(5,5),Q\n", "40 CLS:STOP\n",
        "50 CLS:WAIT 0:GPRINT 1:END\n", "!RUN", "RUN\n", "\n", "\n", "\n", "\n", "@CLS",
        "RUN 30\n", "@CLS", "RUN 40\n", "@CLS", "RUN 50\n", "@CLS", "RUN 10\n", "BRK",
        "@CLS", 'GPRINT "010Z"\n', "@CLS", 'GPRINT "01Z"\n',
    ],
    "substring": [
        'MID$ ("ABC",0,1)\n', "@LEFT", "@CLS", 'MID$ ("ABC",80,1)\n', "@CLS",
        'LEFT$ ("ABC",81)\n', "@CLS", 'RIGHT$ ("ABC",-0.5)\n', "@CLS", 'MID$ ("ABC",1.9,80)\n',
    ],
    # 編集している行の行番号に、INSで空きを入れたり英字を打ったりする
    "edit-number": [
        "!PRO", "10 PRINT 1\n", "20 A=2\n", "LIST 10\n", "@LEFT", "@RIGHT", "@LEFT", "@INS",
        "@RIGHT", "@INS", "X", "@DOWN", "@CLS", "LIST 20\n", "@RIGHT", "@LEFT", "@LEFT", "Q",
        "\n",
    ],
    # DEFのキーで実行すると、>は残し、その下の行から出す
    "def-key": [
        "!PRO", '10 "A" WAIT 0:PRINT 5:END\n', '20 "S" PRINT 6\n', "!RUN", "@DEF", "@A", "@DEF",
        "@S", "\n", "@CLS", "12", "@DEF", "@A", "@DEF", "@B", "@CLS", "@DEF", "@B", "@CLS",
        "1+2\n", "\n", "@DEF", "@A", "@CLS", "1\n", "2\n", "3\n", "\n", "@DEF", "@A", "@CLS",
        "A=1\n", "@DEF", "@A",
    ],
    # LISTと行の編集: 命令は後ろの空白まで行に入らなければ、命令ごと次の行へ送る
    "long-edit": [
        "!PRO", "20 DIM X(500):PRINT MEM\n", "50 PRINT PEEK &78B0:END\n",
        '40 A$="ABCDEFGHIJKLMNOPQRSTUVWXYZ":B=1:GOTO 10\n', "LIST\n", "@DOWN", "@LEFT", "@RIGHT",
        "@CLS", "LIST 40\n", "@RIGHT", "@INS", "@DEL", *["@RIGHT"] * 36, "X", "\n", "LIST 20\n",
        *["@RIGHT"] * 18,
    ],
    # 打った行はLISTと同じ形で出し直す。24字ちょうどの命令のあとは1行空けて>
    "entered": [
        "DEGREE:RADIAN:DEGREE:GRA\n", "@CLS", "WAIT 1:WAIT 2:WAIT 3:WAI\n", "@CLS",
        "ABCDEFGHIJKLMNOPQRSTUVWX\n", "@CLS", 'OPEN "600,O,7,2,A,L,&1B"\n', "CLOSE\n", "@CLS",
        "BEEP 1:BEEP 1:BEEP 1:BEE\n",
    ],
    # CHR$は0〜255(0は空、80h以上は「FEh、字」)
    "chr": [
        "A$=CHR$ 0\n", "@CLS", 'B$=CHR$ 128+CHR$ 254+"Z"\n', "@CLS", "LEN B$\n", "@CLS",
        "CHR$ 256\n", "@CLS", "ASC CHR$ 200\n", "LEN CHR$ 177\n",
    ],
}  # fmt: skip


@pytest.mark.parametrize("name", list(SESSIONS_1350))
def test_basic_like_rom_1350(name):
    """ROMなしのBASIC(PC-1350)が、ROMのある本体と同じ液晶・RAMになる"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    steps: list[tuple[str, object]] = []
    for s in SESSIONS_1350[name]:
        if s.endswith("~"):  # 終わりの~は、打ってから1秒待つ(プログラムが進むのを待つ)
            steps += [("type", s[:-1]), ("wait", 1)]
        elif s.startswith("!"):
            steps += [("mode", s[1:]), ("wait", 1.5)]
        elif s == "BRK":
            steps.append(("brk", None))
        elif s.startswith("@"):
            steps.append(("keys", s[1:].split(",")))
        else:
            steps.append(("type", s))
        steps += [("wait", 0.4), ("look", None)]
    m, _t = boot("1350")
    m.run(CLOCK)
    assert differences(play(m, steps), play(basic_machine("1350"), steps)) == []


LOOP_BODIES_1350 = [
    "", "A=I/3", "WAIT 0:PRINT I", 'WAIT 0:PRINT "A"', 'WAIT 0:CURSOR 3,3:PRINT " >"', "CLS",
    'WAIT 0:PRINT " >";', "WAIT 0:PSET (5,5)", "WAIT 0:GPRINT 255;255", 'WAIT 0:GPRINT "FFFF"',
    "WAIT 0:LINE (0,0)-(50,20)", "WAIT 0:LINE (200,0)-(250,0)", "WAIT 0:LINE (0,0)-(10,3),BF",
    "WAIT 0:A=POINT (5,5)",
]  # fmt: skip


@pytest.mark.parametrize("body", LOOP_BODIES_1350)
def test_loop_time_like_rom_1350(body):
    """FORの繰り返し1回にかかる時間が、ROMのある本体と10%以内(PC-1350)"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine

    def per_loop(make) -> float:
        times = [_loop_time(make(), body, n, marker=0x6B00) for n in (50, 150)]
        return (times[1] - times[0]) / 100

    def rom():
        m = boot("1350")[0]
        m.run(CLOCK)
        return m

    a, b = per_loop(rom), per_loop(lambda: basic_machine("1350"))
    assert abs(b / a - 1) < 0.1, (body, a, b)


def _hold_up_1350(m, lines: list[str], typed: list[str]) -> tuple[str, str]:
    """PROでlinesを入れてRUNし、typedを打ってから、↑を押しているあいだと離したあとの液晶"""
    from basic_diff import lcd_1350, play

    steps: list[tuple[str, object]] = [("mode", "PRO"), ("wait", 1.5)]
    steps += [("type", line + "\n") for line in lines]
    steps += [("mode", "RUN"), ("wait", 1.5), ("type", "RUN\n"), ("wait", 0.4)]
    steps += [("type", t) for t in typed]
    play(m, [*steps, ("wait", 0.4)])
    m.held.add("UP")
    m.run(CLOCK // 2)
    held = lcd_1350(m)
    m.held.discard("UP")
    m.run(CLOCK // 2)
    return held, lcd_1350(m)


@pytest.mark.parametrize(
    "lines, typed",
    [
        (["10 PRINT 1:PRINT 2", '20 B$="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"', "30 A=1"], []),
        (["10 A=1", "20 A=1/0", "30 A=2"], []),
        (["10 INPUT A:PRINT A", '20 INPUT "N=";B'], ["1/0\n"]),
    ],
)
def test_held_up_lists_from_stopped_line_1350(lines, typed):
    """↑を押しているあいだ、液晶を消して止まった行から4行目まで並べる。INPUTの答えの
    エラーなら、離すと答えの行に?を出す(ROMのある本体と同じ。カーソルの点滅は除く)"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import _same_but_blink, basic_machine

    m = boot("1350")[0]
    m.run(CLOCK)
    rom = _hold_up_1350(m, lines, typed)
    ours = _hold_up_1350(basic_machine("1350"), lines, typed)
    assert all(_same_but_blink(a, b) for a, b in zip(rom, ours, strict=True)), (rom, ours)


def test_kana_key_switches_small_letters_overseas_1350():
    """海外向けの本体では、KANAのキーは英小文字の入力(SML)を切り替える(ROMのある本体と
    同じ)"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import differences, play

    from sc61box import norom
    from sc61box.basic import attach

    steps: list[tuple[str, object]] = []
    for keys in (["KANA"], ["Q"], ["KANA"], ["SHIFT", "KANA"], ["Q"], ["SHIFT", "KANA"], ["W"]):
        steps += [("keys", keys), ("wait", 0.4), ("look", None)]
    rom = boot("1350", overseas=True)[0]
    rom.run(CLOCK)
    ours = new_machine("1350", 0, overseas=True, rom=False)
    norom.install(ours)
    attach(ours)
    ours.run(CLOCK // 2)
    assert differences(play(rom, steps), play(ours, steps)) == []


def test_power_on_starts_in_run_mode_1350():
    """PROで電源を切っても、入れ直すとRUNモード。状態を保存して戻すときはPROのまま"""
    import json

    from basic_diff import basic_machine, lcd_1350, play

    m = basic_machine("1350")
    play(m, [("mode", "PRO"), ("wait", 1.5)])
    state = json.loads(json.dumps(m.snapshot()))
    m.mode = "OFF"
    m.run(CLOCK)
    m.mode = "ON"
    m.wake()
    m.run(CLOCK)
    assert "RUN" in m.symbols() and lcd_1350(m).split("\n")[0].strip() == "RUN MODE"
    for target in (m, basic_machine("1350")):
        target.restore(state)
        target.run(CLOCK // 5)
        assert "PRO" in target.symbols()
        assert target.basic is not None and target.basic.mode == "PRO"


def test_stale_dots_cleared_like_rom_1350():
    """字のあいだのあきの列に残った点(マシン語で描いたものなど)は、字を書くと消え、CLSと
    MODEのキーで、行の頭の6列も含めて全部消える(ROMのある本体と同じ)"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, play

    from sc61box.machine import LCD_BANDS_1350, LCD_BLOCKS_1350

    def addr(row: int, col: int) -> int:
        block, c = divmod(col, 30)
        return LCD_BLOCKS_1350[block] + LCD_BANDS_1350[row] + c

    gaps = [6 * (c + 1) + 5 for c in range(24)]

    def dots(m, cols: list[int]) -> list[list[int]]:
        return [[m.mem[addr(r, c)] for c in cols] for r in range(4)]

    def after(m, step) -> list[list[int]]:
        """行の頭の6列とあきの列に点を置いてからstepを与え、点を置いた列の点を返す"""
        cols = [*range(6), *gaps]
        for r in range(4):
            for c in cols:
                m.mem[addr(r, c)] = 0x7F
        play(m, [step, ("wait", 0.6)])
        return dots(m, cols)

    rom = boot("1350")[0]
    rom.run(CLOCK)
    ours = basic_machine("1350")
    for step in [("type", "ABCDEFGHIJKLMNOPQRSTUVWX"), ("type", "1\n")]:
        # ROMが書き直した行(あきの列が消えた行)は、ROMなしでも消えている
        a, b = after(rom, step), after(ours, step)
        rewritten = [r for r in range(4) if not any(a[r][6:])]
        assert rewritten and all(not any(b[r][6:]) for r in rewritten), step
    for step in [("keys", ["CLS"]), ("keys", ["MODE"])]:
        a, b = after(rom, step), after(ours, step)
        assert not any(map(any, a)) and not any(map(any, b)), step


def test_app_runs_1350_basic_without_rom():
    """--noromのPC-1350は、ROMなしのBASICで動く(作業欄だけにならない)"""
    from basic_diff import lcd_1350
    from helpers import make_app

    app = make_app(model="1350", frames=3, norom=True)
    m = app.m
    assert m.basic is not None and not app.bench_only
    app.typer.add_text("1+2\n")
    for _ in range(600):
        app.frame()
        if lcd_1350(m).split("\n")[2].strip() == "3.":
            break
    assert lcd_1350(m).split("\n")[2].strip() == "3."


# ---- 保存したRAM ----


def _stored_without_rom(model: str):
    """ROMなしのBASICで、10 PRINT 123とA=42を入れた本体"""
    from basic_diff import basic_machine, play

    m = basic_machine(model)
    steps: list[tuple[str, object]] = [("mode", "PRO"), ("wait", 1.5), ("type", "10 PRINT 123\n")]
    steps += [("mode", "RUN"), ("wait", 1.5), ("type", "A=42\n"), ("wait", 0.4)]
    play(m, steps)
    return m


@pytest.mark.parametrize(
    "model, have", [("1251", HAVE_ROM), ("1261", HAVE_ROM_1260), ("1350", HAVE_ROM_1350)]
)
def test_rom_reads_ram_saved_without_rom(model, have, tmp_path):
    """ROMなしのBASICで保存したRAMを、ROMのある本体で読んでも、プログラムと変数が残る
    (電源を切ったときのフラグと、ROMが電源を入れたときに見るRAMの値を、ROMと同じに書くため)"""
    if not have:
        pytest.skip("ROMがない")
    from basic_diff import play

    m = _stored_without_rom(model)
    assert m.basic is not None
    m.basic.mark_off()
    path = str(tmp_path / "ram.bin")
    m.save_ram(path)
    rom = new_machine(model)
    assert rom.load_ram(path)
    rom.cpu.reset()
    rom.run(CLOCK)
    looks = play(rom, [("type", "A\n"), ("wait", 0.4), ("look", None)])
    looks += play(rom, [("type", "RUN\n"), ("wait", 0.4), ("look", None)])
    assert "42." in looks[0].lcd and "123." in looks[1].lcd


def test_app_without_rom_marks_power_off_when_closing():
    """ROMなしのBASICで動かしたアプリを閉じると、保存するRAMに電源を切ったときのフラグを書く"""
    from helpers import make_app

    from sc61box import app as app_module

    app = make_app(model="1251", frames=3, norom=True, fresh=False)
    basic = app.m.basic
    assert basic is not None
    app.close()
    data = open(app_module.ram_file("1251", 0, True), "rb").read()
    lo, hi = app.m.model.ram
    a, mark = app.m.off_mark()
    assert data[hi - lo + a : hi - lo + a + len(mark)] == mark


def test_app_says_saved_ram_was_loaded():
    """起動時に前回終了時のRAMを読み込んだら、そのことを出す。プログラムを保護していれば、
    それも出す(初めての起動では出さない)"""
    from helpers import make_app

    plain = "前回終了時のRAMを読み込みました(--freshで初期状態から起動できます)"
    locked = "前回終了時のRAMを読み込みました。プログラムはパスワードで保護されています"
    app = make_app(model="1261", frames=3, norom=True, fresh=False)
    assert "前回終了時" not in app.status
    app.m.mem[0x66D9] |= 0x20
    app.close()
    app = make_app(model="1261", frames=3, norom=True, fresh=False)
    assert locked in app.status
    app.m.mem[0x66D9] &= ~0x20 & 0xFF
    app.close()
    app = make_app(model="1261", frames=3, norom=True, fresh=False)
    assert plain in app.status and "保護" not in app.status
    assert app.status.startswith("ROMがないため") and app.status.endswith("\n" + plain)
    app.close()


# ---- 印字モード(SHIFTのあとENTER)とプリンタ ----

PRINT_MODE_STEPS = [
    ["SHIFT", "ENTER"], "1+2\n", '"AB"\n', "A=5\n", "1/0\n", "CL", "DEGREE\n", "PRINT 5\n", "CL",
    "2*2\n", ["LEFT"], "\n", ["LEFT"], "+1\n", "3\n", "+4\n", "1+2+3+4+5+6+7+8+9+10+11+12+13\n",
    '"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"\n', "1E50*3\n", ["SHIFT", "ENTER"], "4+5\n",
]  # fmt: skip


def _print_mode_rows(m, model: str) -> list[tuple[bool, list[bytes]]]:
    """PRINT_MODE_STEPSを与え、手順1つごとの(印字モードか, 印字した行)を返す"""
    from basic_diff import play

    from sc61box.basic.pc1261 import console

    m.connect_printer()
    a, bit = console.HIDDEN["PRINT"] if model == "1350" else m.model.symbols["PRINT"]
    out = []
    for s in PRINT_MODE_STEPS:
        if s == "CL":
            s = ["CLS" if model == "1350" else "CL"]
        play(m, [("keys", s) if isinstance(s, list) else ("type", s), ("wait", 1.5)])
        out.append((bool(m.mem[a] & bit), list(m.printer.rows())))
    return out


@pytest.mark.parametrize("model, have", [("1261", HAVE_ROM_1260), ("1350", HAVE_ROM_1350)])
def test_print_mode_like_rom(model, have):
    """SHIFTのあとENTERで印字モードにすると、RUNモードで計算した行と答えをプリンタにも
    送る(命令の行とエラーのメッセージは送らない。ROMのある本体と同じ)"""
    if not have:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine

    rom = boot(model)[0]
    rom.run(CLOCK)
    assert _print_mode_rows(rom, model) == _print_mode_rows(basic_machine(model), model)


@pytest.mark.parametrize("model", ["1261", "1350"])
def test_print_mode_needs_printer_and_ends_at_power_off(model):
    """印字モードは、プリンタがなければ入らず、電源を入れ直すとNPに戻る"""
    from basic_diff import basic_machine, play

    m = basic_machine(model)
    b = m.basic
    assert b is not None
    play(m, [("keys", ["SHIFT", "ENTER"]), ("wait", 0.3)])
    assert not b.screen.lit("PRINT")
    m.connect_printer()
    play(m, [("keys", ["SHIFT", "ENTER"]), ("wait", 0.3)])
    assert b.screen.lit("PRINT")
    m.mode = "OFF"
    m.run(CLOCK)
    m.mode = "ON" if model == "1350" else "RUN"
    m.wake()
    m.run(CLOCK)
    assert not b.screen.lit("PRINT")


def test_lprint_codes_like_rom_1350():
    """PC-1350がプリンタに送るコード(数字の0はF0h、英字のOは30hなど)が、ROMのある本体と
    同じ(行の頭の0Eh・0Fhは除く)"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, play

    codes = [0x27, 0x5B, 0x7E, 0x7F, 0x80, 0xA0, 0xB1, 0xE0, 0xF0, 0xFA, 0xFB, 0xFC, 0xFE, 0xFF]
    line = '10 LPRINT "0O";' + ";".join(f"CHR$ {c}" for c in codes)

    def sent(m) -> list[bytes]:
        m.connect_printer()
        assert m.printer is not None
        m.printer.swap, m.printer.lead = {}, frozenset()
        steps: list[tuple[str, object]] = [("mode", "PRO"), ("wait", 1.5), ("type", line + "\n")]
        steps += [("mode", "RUN"), ("wait", 1.5), ("type", "RUN\n"), ("wait", 2)]
        play(m, steps)
        rows = [r.replace(b"\x0e", b"").replace(b"\x0f", b"") for r in m.printer.rows()]
        return [r for r in rows if r]

    rom = boot("1350")[0]
    rom.run(CLOCK)
    assert sent(rom) == sent(basic_machine("1350"))


def test_llist_like_rom_1350():
    """PC-1350のLLIST(PROモードとRUNモード)が、ROMのある本体と同じに印字する"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, play

    def printed(m) -> list[bytes]:
        m.connect_printer()
        steps: list[tuple[str, object]] = [("mode", "PRO"), ("wait", 1.5)]
        steps += [("type", '10 A=10:PRINT "OK";A\n')]
        steps += [("type", '20 B$="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"\n')]
        steps += [("type", "LLIST\n"), ("wait", 3), ("mode", "RUN"), ("wait", 1.5)]
        steps += [("type", "LLIST 20\n"), ("wait", 3)]
        play(m, steps)
        return m.printer.rows()

    rom = boot("1350")[0]
    rom.run(CLOCK)
    assert printed(rom) == printed(basic_machine("1350"))


def test_paper_uses_drawn_glyphs():
    """紙の字のうち液晶にもある字は、ROMのあるなしによらず、エミュレータで描いた液晶の字の形
    (斜線のある0のF0hも0の形、指数のEの60hは小さいEの形)。液晶にない記号は表の形のまま"""
    from helpers import make_app

    from sc61box import charset
    from sc61box.basic.pc1261 import font
    from sc61box.printer import load_font

    drawn = load_font()
    assert drawn[0x30] == drawn[0xF0] == charset.glyph("0")
    assert drawn[0x41] == charset.glyph("A") and drawn[0x61] == font.glyph("a")
    assert drawn[0xB1] == font.glyph("ｱ") and drawn[0x19] == charset.glyph("π")
    assert drawn[0xF1] == font.glyph("年") and drawn[0x60] == charset.glyph("[E]")
    assert drawn[0x01] != bytes(5) and font.glyph("≠") is None  # 液晶にない字も表で描いた形
    app = make_app("1251", frames=2, norom=True)
    assert app.paper.font == drawn
    app.close()
    if HAVE_ROM:
        app = make_app("1251", frames=2)
        assert app.paper.font == drawn
        app.close()


# ---- 待ちの中のSHIFT+ENTER、POKEで描いた点、プリンタがないとき ----


@pytest.mark.parametrize("model, have", [("1261", HAVE_ROM_1260), ("1350", HAVE_ROM_1350)])
def test_print_mode_switch_while_waiting_like_rom(model, have):
    """PRINT・INPUTの待ちでSHIFT+ENTERを押すと、待ったまま印字モードを切り替える。INPUTの
    答えのエラーのあいだは効かない(ROMのある本体と同じ)"""
    if not have:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, look, play

    from sc61box.basic.pc1261 import console

    a, bit = console.HIDDEN["PRINT"] if model == "1350" else (0x203D, 0x02)
    se = ("keys", ["SHIFT", "ENTER"])
    actions = [
        se, ("type", "\n"), se, ("type", "5"), ("type", "\n"), ("type", "RUN 20\n"), se,
        ("type", "3"), se, ("type", "\n"), ("type", "RUN 20\n"), ("type", "1/0\n"), se,
        ("keys", ["LEFT"]), ("type", "X\n"),
    ]  # fmt: skip

    def seen(m) -> list[tuple[str, bool, list[bytes]]]:
        m.connect_printer()
        lines = ["10 PRINT 1:PRINT 2:INPUT A:PRINT A", "20 INPUT A:PRINT A*2"]
        steps: list[tuple[str, object]] = [("mode", "PRO"), ("wait", 1.5)]
        steps += [("type", x + "\n") for x in lines]
        play(m, [*steps, ("mode", "RUN"), ("wait", 1.5), ("type", "RUN\n"), ("wait", 1)])
        out = []
        for step in actions:
            play(m, [step, ("wait", 1)])
            out.append((look(m).lcd, bool(m.mem[a] & bit), list(m.printer.rows())))
        return out

    rom = boot(model)[0]
    rom.run(CLOCK)
    assert seen(rom) == seen(basic_machine(model))


@pytest.mark.parametrize(
    "line",
    [
        '10 CLS:WAIT 0:POKE 28683,85:POKE 28747,85:POKE 28677,85:CURSOR 0,1:PRINT "A"',
        '10 CLS:WAIT 0:POKE 28683,85:POKE 28747,85:CURSOR 3,0:PRINT "A"',
        '10 CLS:WAIT 0:POKE 28713,85:POKE 28677,85:CURSOR 0,3:PRINT "A":PRINT "B"',
    ],
)
def test_poked_dots_kept_like_rom_1350(line):
    """POKEで液晶RAMに描いた点は、字を書かない桁では残り、上へ送ると行ごと上へずれる
    (ROMのある本体と同じ)"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, play

    from sc61box.machine import LCD_BANDS_1350, LCD_BLOCKS_1350

    def dots(m) -> list[list[int]]:
        steps: list[tuple[str, object]] = [("mode", "PRO"), ("wait", 1.5)]
        steps += [("type", line + "\n"), ("type", "20 GOTO 20\n"), ("mode", "RUN"), ("wait", 1.5)]
        play(m, [*steps, ("type", "RUN\n"), ("wait", 2)])
        out = []
        for band in LCD_BANDS_1350:
            row = []
            for col in range(150):
                block, c = divmod(col, 30)
                if m.mem[LCD_BLOCKS_1350[block] + band + c] == 0x55:
                    row.append(col)
            out.append(row)
        return out

    rom = boot("1350")[0]
    rom.run(CLOCK)
    assert dots(rom) == dots(basic_machine("1350"))


@pytest.mark.parametrize("model, have", [("1261", HAVE_ROM_1260), ("1350", HAVE_ROM_1350)])
def test_lprint_without_printer_like_rom(model, have):
    """プリンタがないとき、出すもののないLPRINTだけはERROR 8(PC-1261はプリンタを待つので
    出るまでに時間がかかる)。ほかのLPRINTは何もせずに進む(ROMのある本体と同じ)"""
    if not have:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, look, play

    def until_error(m, line: str) -> float | None:
        m.run(CLOCK)
        steps: list[tuple[str, object]] = [("mode", "PRO"), ("wait", 1.5)]
        steps += [("type", line + "\n"), ("mode", "RUN"), ("wait", 1.5), ("type", "RUN\n")]
        play(m, steps)
        for t in range(200):
            if "ERROR" in look(m).lcd:
                return t * 0.02
            play(m, [("wait", 0.02)])
        return None

    lines = ("10 LPRINT", '10 LPRINT "A":LPRINT 1,2')
    a = [until_error(boot(model)[0], x) for x in lines]
    b = [until_error(basic_machine(model), x) for x in lines]
    assert a[1] is None and b[1] is None
    assert a[0] is not None and b[0] is not None and abs(a[0] - b[0]) <= 0.1 * max(a[0], 1)


def test_sio_settings_like_rom_1350():
    """OPEN$の設定、開いているフラグ(78B0hのビット7)、CONSOLEの字数(78B4h・78B5h)がROMのある
    本体と同じ。電源を入れ直すと閉じて初めの値に戻り、TEXTモードもBASICモードに戻る(設定を
    RAMのどこに置くかは同じにしていない)"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, lcd_1350, play

    lines = ['OPEN "600,O,7,2,A,L,&1B"', "CONSOLE 77", "CLOSE", 'OPEN ",E"', "CONSOLE 300"]

    def seen(m) -> tuple[str, int, int]:
        play(m, [("keys", ["CLS"]), ("type", "OPEN$\n"), ("wait", 0.5)])
        return lcd_1350(m).split("\n")[0].strip(), m.mem[0x78B0] & 0x80, m.mem[0x78B4]

    def state(m) -> list[object]:
        m.run(CLOCK)
        play(m, [("mode", "PRO"), ("wait", 1.5), ("type", "10 A=1\n"), ("type", "TEXT\n")])
        out: list[object] = []
        for line in lines:
            play(m, [("keys", ["CLS"]), ("type", line + "\n"), ("wait", 0.5)])
            out.append(seen(m))
        m.mode = "OFF"
        m.run(CLOCK)
        m.mode = "ON"
        m.wake()
        m.run(CLOCK)
        out += [m.mem[0x6F16] & 0x40, seen(m)]
        return out

    assert state(boot("1350")[0]) == state(basic_machine("1350"))


def test_long_line_text_like_rom_1350():
    """TEXTで字にした行が77バイトを越えると、77バイトで切る(ROMと同じ)"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, play

    from sc61box.basic.pc1261 import program

    p = program.PC1350

    def converted(m) -> list[bytes]:
        m.run(CLOCK)
        play(m, [("mode", "PRO"), ("wait", 1.5), ("type", "NEW\n"), ("wait", 0.5)])
        degrees = bytes([0xC1, 0x3A] * 37)[:-1]  # DEGREEを:で37個(字にすると77バイトを越える)
        p.put(m, p.first(m), p._line(10, degrees) + p._line(20, b"A" * 72 + b"\xc4"))
        play(m, [("type", "TEXT\n"), ("wait", 1)])
        return [p.body(m, a) for _n, a in p.lines(m)]

    rom, norom = converted(boot("1350")[0]), converted(basic_machine("1350"))
    assert rom == norom
    assert [len(b) for b in norom] == [77, 77]


def test_state_restore_keeps_serial_wait_1350():
    """打ったLOAD・SAVEでシリアルの相手を待っているところで保存して戻しても、待ち続け、
    BRKで>に戻る"""
    import json

    from basic_diff import basic_machine, lcd_1350, play

    for line in ("LOAD", "SAVE"):
        m = basic_machine("1350")
        m.run(CLOCK)
        play(m, [("mode", "PRO"), ("wait", 1.5), ("type", "10 A=1\n"), ("mode", "RUN")])
        play(m, [("wait", 1.5), ("type", "OPEN\n"), ("keys", ["CLS"]), ("type", line + "\n")])
        play(m, [("wait", 0.5)])
        shown = lcd_1350(m)
        state = json.loads(json.dumps(m.snapshot()))
        m = basic_machine("1350")
        m.restore(state)
        play(m, [("type", "1"), ("wait", 0.5)])
        assert lcd_1350(m) == shown  # 打ったキーは受け付けない
        play(m, [("brk", None), ("wait", 0.5)])
        assert [r.strip() for r in lcd_1350(m).split("\n")][:2] == [line, ">"]


GRAPHICS_1350 = [
    "PSET (0,0):PSET (149,31):PSET (150,0):PSET (-1,0)",
    "PSET (1.7,2.9):PSET (-0.5,5):PSET (10,10):PRESET (10,10)",
    "PSET (12,10):PSET (12,10),X:PSET (14,10),X",
    "POKE &7001,255:PRESET (1,1):POKE &7002,255:PSET (2,3),X",
    "GPRINT 1;2;3:GPRINT 1,2,3:GPRINT 4",
    'GCURSOR (10,20):GPRINT "0102";"123"',
    "GCURSOR (148,7):GPRINT 1;2;4;8:GCURSOR (-2,3):GPRINT 255,255;",
    "GCURSOR (40,40):GPRINT 255:GCURSOR (40,15):PRINT 1:GPRINT 255",
    "LINE (0,0)-(50,20):LINE (0,20)-(50,0):LINE (60,0)-(70,30)",
    "LINE (0,0)-(2,1):LINE (5,1)-(3,0):LINE (6,0)-(8,1)",
    "LINE (0,6)-(3,0):LINE (7,0)-(4,6):LINE (10,10)-(4,13)",
    "LINE (0,0)-(9,3),&AAAA,B:LINE (20,3)-(29,0),&AAAA,B",
    "LINE (40,0)-(49,3),&AAAA,BF:LINE (0,10)-(9,13),X,B",
    "LINE (20,0)-(25,1),X,B:LINE (40,0)-(45,0),X,B",
    "LINE (50,0)-(50,3),X,B:GPRINT 1,:GPRINT 2",
    "LINE (0,0)-(5,3),X,BF:LINE (0,0)-(5,3),X,B:LINE (10,0)-(15,3),R",
    "LINE (20,0)-(35,0),&F0F0:LINE (-4,9)-(15,9),&F0F0",
    "LINE (145,0)-(160,5):LINE (0,10)-(20,10),1.5",
    "LINE (0,12)-(20,12),0:LINE (0,14)-(20,14),&8000",
    "LINE (2,2)-(5,3):LINE -(8,0):LINE (0,9)-(3,12),X",
    "LINE (0,9)-(3,12),X:LINE -(6,9),X",
    "LINE (2,2)-(5,3):CLS:LINE -(8,8)",
    "P=&F0F0:LINE (0,0)-(15,0),P:B=&F0F0:LINE (0,2)-(15,2),B",
    "LINE (0,4)-(15,4),X,&AAAA:LINE (-10,-10)-(20,40),X,BF",
    'GPRINT "01Z":GPRINT "0102Z";"Q":GPRINT 3',
]


def test_graphics_like_rom_1350():
    """GCURSOR・GPRINT・PSET・PRESET・LINEで描いた点がROMのある本体と同じ"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, play

    from sc61box.machine import LCD_BANDS_1350, LCD_BLOCKS_1350

    def dots(m) -> list[list[int]]:
        return [
            [m.mem[LCD_BLOCKS_1350[x // 30] + band + x % 30] for x in range(150)]
            for band in LCD_BANDS_1350
        ]

    def drawn(m) -> list[list[list[int]]]:
        m.run(CLOCK)
        out = []
        for cmd in GRAPHICS_1350:
            lines = ["NEW", f"10 CLS:WAIT 0:{cmd}", "20 GOTO 20"]
            steps = [("mode", "PRO"), ("wait", 1.5), ("keys", ["CLS"])]
            steps += [("type", x + "\n") for x in lines]
            play(m, [*steps, ("mode", "RUN"), ("wait", 1.5), ("type", "RUN\n"), ("wait", 3)])
            out.append(dots(m))
            play(m, [("brk", None), ("wait", 0.5)])
        return out

    assert all(len(f"10 CLS:WAIT 0:{cmd}") <= 79 for cmd in GRAPHICS_1350)  # 1行に打てる字数
    rom, norom = drawn(boot("1350")[0]), drawn(basic_machine("1350"))
    for cmd, a, b in zip(GRAPHICS_1350, rom, norom, strict=True):
        assert a == b, cmd


def test_state_restore_keeps_graphics_cursor_1350():
    """描く命令のENTERの待ちで保存して戻しても、GPRINTのカーソルは続きから"""
    import json

    from basic_diff import basic_machine, play

    m = basic_machine("1350")
    m.run(CLOCK)
    lines = ["10 CLS:GCURSOR (40,15):GPRINT 1;:GPRINT 2"]
    play(m, [("mode", "PRO"), ("wait", 1.5), *(("type", x + "\n") for x in lines)])
    play(m, [("mode", "RUN"), ("wait", 1.5), ("type", "RUN\n"), ("wait", 1)])
    state = json.loads(json.dumps(m.snapshot()))
    m = basic_machine("1350")
    m.restore(state)
    play(m, [("type", "\n"), ("wait", 1)])
    assert (m.mem[0x7200 + 0x40 + 10], m.mem[0x7200 + 0x40 + 11]) == (1, 2)


CSAVE_CASES_1350 = [
    (["10 PRINT 1", "20 A=5"], 'CSAVE "AB"\n'),
    (["10 PRINT 1"], "CSAVE\n"),
    (["10 PRINT 1"], 'CSAVE M "Q";&6C00,&6C13\n'),
]


@pytest.mark.parametrize("index", range(len(CSAVE_CASES_1350)))
def test_csave_like_rom_1350(index):
    """CSAVEとCSAVE Mでカセットに送るビットの並びと、音を出し始める時刻と終わる時刻が、ROMの
    ある本体と同じ(PC-1350)"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    lines, command = CSAVE_CASES_1350[index]
    out = []
    for m in (boot("1350")[0], basic_machine("1350")):
        m.run(CLOCK)
        play(m, _pc1261_program(lines))
        for i in range(0x20):
            m.mem[0x6C00 + i] = i * 37 & 0xFF
        start = m.cpu.cycles
        looks = play(m, [("type", command), ("wait", 25), ("look", None)])
        sound = [c for c, v in m.sound_events if c >= start and v]
        out.append((_tape_bits(m, start), looks, sound[0] - start, sound[-1] - start))
    (bits_a, a, first_a, end_a), (bits_b, b, first_b, end_b) = out
    assert len(bits_a) > 100 and bits_a == bits_b
    assert not differences(a, b), "\n".join(differences(a, b))
    assert abs(first_a - first_b) < CLOCK // 50 and abs(end_a - end_b) < CLOCK // 50


@pytest.fixture(scope="module")
def tapes_1350(tmp_path_factory):
    """PC-1350のROMのある本体にCSAVEさせたテープ(wav)"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import play

    from sc61box import tape

    d = tmp_path_factory.mktemp("tapes1350")
    out = {}
    for name, lines, command in (
        ("ab", ["10 PRINT 1", "20 A=5"], 'CSAVE "AB"'),
        ("cd", ["30 PRINT 3", '40 B=7:C$="XYZ"'], 'CSAVE "CD"'),
        ("m", ["10 PRINT 1"], 'CSAVE M "Q";&6C00,&6C0F'),
    ):
        m, _t = boot("1350")
        m.run(CLOCK)
        play(m, _pc1261_program(lines))
        for i in range(0x20):
            m.mem[0x6C00 + i] = i * 37 + 5 & 0xFF
        path = str(d / f"{name}.wav")
        tape.write_wav(path, tape.record(m, command))
        out[name] = path
    return out


CLOAD_CASES_1350 = [
    (["5 X=1"], "ab", "CLOAD\n"),
    (["5 X=1"], "ab", 'CLOAD "XY"\n'),
    (["10 PRINT 1", "20 A=6"], "ab", "CLOAD?\n"),
    (["5 X=1"], "m", "CLOAD M\n"),
    (["5 X=1", "30 Y=2"], "cd", "MERGE\n"),
    (['10 CHAIN "AB"', "20 PRINT 7"], "ab", "RUN\n"),
]


@pytest.mark.parametrize("index", range(len(CLOAD_CASES_1350)))
def test_cload_like_rom_1350(index, tapes_1350):
    """CLOAD・CLOAD?・CLOAD M・MERGE・CHAINで、ROMのある本体が録ったテープを読んだ結果と
    時刻が、ROMのある本体と同じ(PC-1350。MERGEしたいまのプログラムの頭は6F05h。RAMの頭の
    コピーは比べない)"""
    from basic_diff import basic_machine, differences, play

    from sc61box import tape

    lines, name, command = CLOAD_CASES_1350[index]
    out = []
    for m in (boot("1350")[0], basic_machine("1350")):
        m.run(CLOCK)
        play(m, _pc1261_program(lines))
        m.tape = tape.TapeIn(tapes_1350[name])
        looks = play(m, [("type", command)] + [("wait", 2.2), ("look", None)] * 9)
        m.brk = True
        m.run(CLOCK * 3 // 10)
        m.brk = False
        looks += play(m, [("wait", 0.5), ("look", None)])
        out.append((looks, bytes(m.mem[0x6030:0x6D00])))
    (a, ram_a), (b, ram_b) = out
    assert not differences(a, b), "\n".join(differences(a, b))
    assert ram_a == ram_b


@pytest.mark.parametrize("body", ["PAUSE 1;2", 'PAUSE "A"'])
def test_pause_time_like_rom_1350(body):
    """PAUSEの繰り返し1回にかかる時間が、ROMのある本体と10%以内(PC-1350。1回が約1秒なので、
    回数を少なくして測る)"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine

    def per_loop(make) -> float:
        times = [_loop_time(make(), body, n, marker=0x6B00) for n in (5, 15)]
        return (times[1] - times[0]) / 10

    def rom():
        m = boot("1350")[0]
        m.run(CLOCK)
        return m

    a, b = per_loop(rom), per_loop(lambda: basic_machine("1350"))
    assert abs(b / a - 1) < 0.1, (body, a, b)


@pytest.mark.parametrize(("model", "marker"), [("1261", 0x4010), ("1350", 0x6B00)])
def test_beep_time_like_rom_pc1261(model, marker):
    """BEEP 1の繰り返し1回にかかる時間が、ROMのある本体と3%以内(PC-1261系とPC-1350の1回は
    PC-1251系より長い)"""
    if not (HAVE_ROM_1350 if model == "1350" else HAVE_ROM_1260):
        pytest.skip("ROMがない")
    from basic_diff import basic_machine

    def per_loop(make) -> float:
        times = [_loop_time(make(), "BEEP 1", n, marker=marker) for n in (2, 6)]
        return (times[1] - times[0]) / 4

    def rom():
        m = boot(model)[0]
        m.run(CLOCK)
        return m

    a, b = per_loop(rom), per_loop(lambda: basic_machine(model))
    assert abs(b / a - 1) < 0.03, (a, b)


def test_file_io_uses_model_keywords_without_rom_1350(tmp_path):
    """ROMなしのPC-1350で、ファイルのBASICはPC-1350の命令の表で中間コードにし、書き出しも
    同じ表で綴りにする(PSETなどPC-1350だけの命令が化けない)"""
    from helpers import make_app

    from sc61box.app import export_program

    app = make_app(model="1350", frames=3, norom=True)
    m = app.m
    data = app._encoded("10 PSET (10,10)\n20 GPRINT 255\n")
    assert data is not None and bytes([0xEA]) in data and bytes([0xE7]) in data
    assert m.store_program(data)
    path = export_program(m, str(tmp_path))
    assert path is not None
    text = open(path, encoding="utf-8").read()
    assert "10 PSET (10,10)" in text and "20 GPRINT 255" in text


def test_brk_stops_drawing_like_rom_1350():
    """長いLINEを描いている途中でもBRKで止まり(描いたところまで残る)、CONTで次の文から続ける"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    steps = _pc1261_program(["10 CLS:WAIT 0:LINE (0,0)-(149,31),BF:PRINT 5"])
    steps += [("type", "RUN\n"), ("wait", 1), ("brk", None), ("wait", 0.5), ("look", None)]
    steps += [("keys", ["CLS"]), ("type", "CONT\n"), ("wait", 1), ("look", None)]
    out = []
    for m in (boot("1350")[0], basic_machine("1350")):
        m.run(CLOCK)
        out.append(play(m, steps))
    assert not differences(*out), "\n".join(differences(*out))


def test_brk_stops_typed_drawing_like_rom_1350():
    """打ったLINEを描いている途中にBRKを押すと、描いたところまで残して>に戻る"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from basic_diff import basic_machine, differences, play

    steps = [("type", "LINE (0,0)-(149,31),BF\n"), ("wait", 1), ("brk", None), ("wait", 0.5)]
    steps += [("look", None), ("type", "1+2\n"), ("wait", 0.5), ("look", None)]
    out = []
    for m in (boot("1350")[0], basic_machine("1350")):
        m.run(CLOCK)
        out.append(play(m, steps))
    assert not differences(*out), "\n".join(differences(*out))


@pytest.mark.parametrize("name", ["lines", "snake"])
def test_graphics_samples_run_1350(name):
    """見本のlines.basとsnake.bas(グラフィックの命令を使う)が、エラーにならずに動く(ROMなしと、
    あればROMのある本体)。snakeは8で上へ向け、上の壁(液晶の外)に当たるまで動かす"""
    import os

    from basic_diff import basic_machine, lcd_1350, play

    path = os.path.join(os.path.dirname(__file__), "..", "programs", "pc1350", f"{name}.bas")
    with open(path, encoding="utf-8") as f:
        lines = [x.rstrip("\n") for x in f if x.strip() and not x.startswith("#")]
    machines = [basic_machine("1350")]
    if HAVE_ROM_1350:
        machines.append(boot("1350")[0])
    for m in machines:
        # ROMなしのRNDの種を決める(えさが、8を押しているあいだにちょうど頭の前に出ると、食べて
        # 次のえさを探すうちに8を離してしまい、上へ向かないことがある)
        m.rnd_seed = 1
        m.run(CLOCK)
        play(m, _pc1261_program(lines) + [("type", "RUN\n"), ("wait", 3)])
        m.held.add("8")
        m.run(CLOCK)
        m.held.discard("8")
        m.run(CLOCK * 8)
        shown = lcd_1350(m)
        assert "ERROR" not in shown, shown
        assert "GAME OVER" in shown if name == "snake" else "BREAK" not in shown


# KEYNUMで得たキーの番号を、キーの表(8403h〜)で文字コードにして6820h番地に置くマシン語
# CALL 0436 / ADIA 3 / LIDP 680B / STD / LIDP 8400 / LDD / LIDP 6820 / STD / RTN
_KEY_TABLE_PROBE = bytes.fromhex("780436740310680B52108400571068205237")
_PROBE_KEYS = ["A", "Z", "5", "0", "(", "*", "=", "SPC", "ENTER", "UP", "DOWN", "LEFT", "RIGHT",
               "CLS", "MODE", "DEF"]  # fmt: skip


def _probe_key(m, key: str) -> int:
    """keyを押したまま_KEY_TABLE_PROBEを呼び、6820h番地の値を返す"""
    cpu = m.cpu
    m.mem[0x6800 : 0x6800 + len(_KEY_TABLE_PROBE)] = _KEY_TABLE_PROBE
    m.held.clear()
    m.held.add(key)
    ret = 0x6FF0
    cpu.r = 0x5C
    cpu.push(ret >> 8)
    cpu.push(ret & 0xFF)
    cpu.pc = 0x6800
    m.halted = False
    guard = bytearray(0x10000)
    guard[ret] = 1
    for _ in range(100):
        if m.run(2000, guard):
            break
    assert cpu.pc == ret
    m.held.clear()
    return m.mem[0x6820]


def test_pc1350_key_table_without_rom():
    """ROMなしのPC-1350でも、BASIC ROMの番地8403hからに、キーの番号から文字コードを引く表を
    置く(漢字表示システムのマシン語モニタなどが、KEYNUMのあとに読む)"""
    from sc61box import norom1350

    m = new_machine("1350", rom=False)
    norom1350.install(m)
    table = norom1350.KEY_TABLE
    for key in _PROBE_KEYS:
        number = norom1350.KEY_NUMBERS[key][0]
        want = norom1350.KEY_CODES.get(key, ord(key) if len(key) == 1 else 0)
        assert m.mem[table + number] == want, key


def test_pc1350_key_table_same_as_rom():
    """キーを押してKEYNUMを呼び、キーの表で文字コードにすると、ROMのある本体とROMなしの表で
    同じ値になる"""
    if not HAVE_ROM_1350:
        pytest.skip("ROMがない")
    from sc61box import norom1350

    rom = new_machine("1350")
    rom.run(CLOCK)
    codes = norom1350.key_codes()
    for key in _PROBE_KEYS:
        assert _probe_key(rom, key) == codes[key], key


def _a_session_1261(m, model: str, lines: list[str]) -> list[tuple[str, int, bytes]]:
    """配列の場所の上の96バイトに前の中身を置いてから、RUNモードで行を打つ(CLはCLのキー)。行ごとに
    (液晶, 配列の下端, 配列の場所の上の384バイトと固定の変数のRAM)を返す"""
    from basic_diff import lcd_1350, lcd_pc1261

    from sc61box.autotype import Typer
    from sc61box.basic.pc1261 import variables

    v = variables.PC1350 if model == "1350" else variables.PC1261
    t = Typer(m)
    t.add_mode("RUN")
    finish(m, t)
    m.run(CLOCK * 3 // 2)
    m.mem[v.ARRAY_TOP - 96 : v.ARRAY_TOP] = bytes(range(0xA0, 0x100))
    out = []
    for line in lines:
        if line == "CL":
            t.add_keys([["CL"]])
        else:
            t.add_text(line + "\n")
        finish(m, t)
        m.run(CLOCK)
        text = lcd_1350(m) if model == "1350" else lcd_pc1261(m)
        ram = bytes(m.mem[v.ARRAY_TOP - 384 : v.FIXED_TOP])
        out.append((text, v.word(m, v.ARRAY_PTR), ram))
    return out


# A(n)の続きの配列、DIM A、A(i,j)、CLEAR(観察: どの行のあとも、液晶と配列の下端とRAMがROMの
# ある本体と同じ)
A_SESSIONS_1261 = [
    ["A(27)", "A(29)", "CL", "A(29)=6", "DIM B(0)", "A(30)", "CL", "A(30)=1", "CL", "CLEAR",
     "A$(28)", "DIM A(30)", "CL", "A(256)=1", "CL", "A(255)"],
    ["A(27)", "DIM A(2)", "CL", "DIM A$(2)", "CL", "A(1,2)=3", "B=A(0,0)", "CL", "A(1,28)=5",
     "CL", "A(1,28)", "CL", "A(1,0)=5", "CL", "CLEAR", "DIM A(2,3)", "A(1,2)=4", "B=A(1,2)"],
]  # fmt: skip


@pytest.mark.parametrize("index", range(len(A_SESSIONS_1261)))
@pytest.mark.parametrize(("model", "have"), [("1261", HAVE_ROM_1260), ("1350", HAVE_ROM_1350)])
def test_extra_a_like_rom(model, have, index):
    if not have:
        pytest.skip("ROMがない")
    from basic_diff import _same_but_blink, basic_machine

    lines = A_SESSIONS_1261[index]
    want = _a_session_1261(boot(model)[0], model, lines)
    got = _a_session_1261(basic_machine(model), model, lines)
    for line, (a, b) in zip(lines, zip(want, got, strict=True), strict=True):
        assert _same_but_blink(a[0], b[0]), (line, a[0], b[0])
        assert a[1:] == b[1:], (line, hex(a[1]), hex(b[1]))


def test_reading_extra_a_makes_array_1261():
    """PC-1261系も、A(27)を読むだけで続きの配列(名前40h)を作り、見出しの添字の最大の2バイトは
    前の中身のまま。A(i,j)は、入れるときはA(j)、式の中ではERROR 1。続きの配列があればDIM Aは
    ERROR 3(ROMのある本体で観察した値)"""
    from basic_diff import basic_machine

    lines = ["A(27)", "A(1,2)=5", "B=A(1,2)", "CL", "DIM A(2)"]
    seen = _a_session_1261(basic_machine("1261"), "1261", lines)
    at = 0x64F1 - (0x6500 - 384)
    assert seen[0][1] == 0x64F1
    assert seen[0][2][at : at + 15] == bytes.fromhex("4000000bf5f608") + bytes(8)
    assert seen[1][2][0x65C2 - (0x6500 - 384)] == 0x50  # Bの仮数
    assert "ERROR 1" in seen[2][0]
    assert "ERROR 3" in seen[4][0] and seen[4][1] == 0x64F1

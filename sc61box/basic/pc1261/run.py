"""PC-1261系とPC-1350のプログラムの実行。文のふるまいはPC-1251系と同じで、字のコードと中間コードの番号、
式の読み方、プログラムと変数の置き方を差し替える"""

from decimal import Decimal

from .. import run, timing
from ..errors import BasicError
from ..evaluate import by_code
from . import evaluate, program, tokens, variables

_CODE = {name: code for code, name in tokens.KEYWORDS.items()}
# CLSとCURSORにかかる時間。文を始める時間と、CURSORの数を読む時間は含めない(観察: 繰り返しの
# 1回が、CLSで58.7ms、CURSOR 0で15.2ms長い)
CLS_TIME = timing.ms(54.8)
CURSOR_TIME = timing.ms(11.3)


class Runner(run.Runner):
    COLON, SEMICOLON, DOLLAR, COMMA, EQ = 0x3A, 0x3B, 0x24, 0x2C, 0x3D
    LPAREN, RPAREN, MUL, QUOTE = 0x28, 0x29, 0x2A, 0x22
    T_TO, T_STEP, T_THEN = _CODE["TO"], _CODE["STEP"], _CODE["THEN"]
    T_GOTO, T_GOSUB, T_DATA, T_USING = _CODE["GOTO"], _CODE["GOSUB"], _CODE["DATA"], _CODE["USING"]
    # 文の頭に来るとERROR 9になる中間コード(関数と演算子、NEW。PC-1251系にならう)
    NOT_STATEMENTS = frozenset([*range(0x91, 0xB0), _CODE["NEW"]])
    TOKEN = 0x80
    NEXT_ADDS_FIRST = True  # FOR I=1 TO 2のあとIは3(観察)
    TRAILING_SEMICOLON = True  # PRINT "A";のあとのPRINTは、同じ行に続けて出す(観察)
    FOR_INTEGERS = False  # FOR I=0 TO 1 STEP .5、FOR I=40000 TO 40001、STEP 0(観察)
    COMMA_ITEMS = 4  # PRINT "A","B","C","D"(観察。液晶の2行ぶん)
    BACK_FROM_TOP = True  # 前の行へ跳ぶ先は、プログラムの頭から探す(観察)
    # PRINT・PAUSEだけは何も書かずに待つ。LPRINTだけは空の行を送る(観察)
    EMPTY_PRINT: list[Decimal | bytes] | None = []
    NO_PRINTER_TIME = timing.ms(2860)  # プリンタがないときのLPRINTだけで、ERROR 8までの時間
    EVALUATOR = evaluate.Evaluator
    TIMES = evaluate.Evaluator.TIMES
    PROGRAM, VARS = program.PC1261, variables.PC1261

    def _cls(self) -> None:
        self.meter.add(CLS_TIME)
        self.basic.cls()

    def _cursor(self) -> None:
        """CURSOR n(0〜47。ほかはERROR 3とする)"""
        n = self._integer()
        if not 0 <= n < self.basic.screen.cells:
            raise BasicError(3)
        self.meter.add(CURSOR_TIME)
        self.basic.cursor(n)

    def _lprint(self) -> run.Steps:
        """プリンタがないとき、出すもののないLPRINTだけはERROR 8(観察。ほかは何もせずに
        次へ進む)"""
        if self.m.printer is None and self._at_end():
            if self.NO_PRINTER_TIME:
                yield self.NO_PRINTER_TIME
            raise BasicError(8)
        yield from super()._lprint()


Runner.STATEMENTS = by_code(
    tokens.KEYWORDS_1261,
    run.STATEMENTS_BY_NAME
    | {"CLS": Runner._cls, "CURSOR": Runner._cursor, "LPRINT": Runner._lprint},
)

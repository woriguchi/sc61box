"""PC-1251系のプログラムの実行: 字のコードと中間コードの番号、文の表"""

from .. import run
from ..evaluate import by_code
from . import evaluate, program, tokens, variables

COLON, SEMICOLON = 0x1D, 0x1C
T_TO, T_STEP, T_THEN = 0x90, 0x91, 0x92
T_GOTO, T_GOSUB, T_DATA, T_USING = 0xD7, 0xD8, 0xCB, 0xDD


class Runner(run.Runner):
    COLON, SEMICOLON = COLON, SEMICOLON
    DOLLAR, COMMA, EQ, QUOTE = evaluate.DOLLAR, evaluate.COMMA, evaluate.EQ, evaluate.QUOTE
    LPAREN, RPAREN, MUL = evaluate.LPAREN, evaluate.RPAREN, evaluate.MUL
    T_TO, T_STEP, T_THEN, T_GOTO, T_GOSUB, T_DATA, T_USING = (
        T_TO, T_STEP, T_THEN, T_GOTO, T_GOSUB, T_DATA, T_USING
    )  # fmt: skip
    TOKEN = 0x7D
    WAIT_AT = 0xC6E5
    # 文の頭に来るとERROR 9になる中間コード(関数、演算子、NEW。観察)
    NOT_STATEMENTS = frozenset([*range(0x7D, 0x8F), *range(0xA0, 0xB0), 0xB1, 0xB2, 0xBD])
    STATEMENTS = by_code(tokens.KEYWORDS_1251, run.STATEMENTS_BY_NAME)
    EVALUATOR = evaluate.Evaluator
    TIMES = evaluate.Evaluator.TIMES
    PROGRAM, VARS = program.PC1251, variables.PC1251

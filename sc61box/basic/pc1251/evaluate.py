"""PC-1251系の式の計算: 本体の文字コードと中間コードの番号、数の字の読み書き"""

from decimal import Decimal

from ... import charset, number
from .. import dialect, evaluate, timing, workarea
from ..evaluate import by_code
from . import tokens, variables

# 本体の文字コード
QUOTE, DOLLAR, COMMA = 0x12, 0x18, 0x1B
LPAREN, RPAREN, GT, LT, EQ = 0x30, 0x31, 0x32, 0x33, 0x34
PLUS, MINUS, MUL, DIV, POW = 0x35, 0x36, 0x37, 0x38, 0x39
DOT, EXP = 0x4A, 0x4B  # EXPは指数のE(英字のEとは別の字)
AMP = charset.CODES["&"]
PI_CHAR, ROOT_CHAR = 0x19, 0x1A  # π・√のキーで打つ字(中間コードにならない)
# 中間コード
T_AND, T_GE, T_LE, T_NE, T_OR, T_NOT = 0x81, 0x82, 0x83, 0x84, 0x85, 0x86
T_PI, T_MEM, T_INKEY, T_SQR = 0xBD, 0xB2, 0x8A, 0x87
T_LEFT, T_RIGHT, T_MID = 0x8C, 0x8D, 0x8E


def is_digit(c: int) -> bool:
    return 0x40 <= c <= 0x49


def is_letter(c: int) -> bool:
    return 0x51 <= c <= 0x6A


def display_number(v: Decimal) -> bytes:
    """RUNモードで答えとして出す字。10桁に丸め、小数点のない数には小数点を付ける"""
    return bytes(charset.CODES[ch] for ch in evaluate.answer_text(v))


class Evaluator(evaluate.Evaluator):
    QUOTE, DOLLAR, COMMA, LPAREN, RPAREN = QUOTE, DOLLAR, COMMA, LPAREN, RPAREN
    PLUS, MINUS, MUL, DIV, POW, DOT, EXP, AMP = PLUS, MINUS, MUL, DIV, POW, DOT, EXP, AMP
    PI_CHAR, ROOT_CHAR = PI_CHAR, ROOT_CHAR
    DIGIT_BASE, LETTER_BASE = 0x40, 0x50
    CODES = charset.CODES
    T_AND, T_OR, T_NOT, T_PI, T_MEM, T_INKEY = T_AND, T_OR, T_NOT, T_PI, T_MEM, T_INKEY
    T_SQR, T_LEFT, T_RIGHT, T_MID = T_SQR, T_LEFT, T_RIGHT, T_MID
    RELATIONS = {EQ: "=", LT: "<", GT: ">", T_GE: ">=", T_LE: "<=", T_NE: "<>"}
    FUNCTIONS = by_code(tokens.KEYWORDS_1251, evaluate.FUNCTIONS_BY_NAME)
    TIMES = timing.PC1251
    FUNCTION_TIME = by_code(tokens.KEYWORDS_1251, evaluate.function_times(TIMES))
    VARS = variables.PC1251
    # 計算に使うRAM(観察)。STR$の跡のうち、F800〜F80Fは計算の積み場所で、あとで戻す
    WORK = workarea.Layout(
        ops=0xF800, ops_size=16, ops_count=0xC6F6, values=0xF840, values_size=8,
        values_top=0xC6F5, strings=0xC760, strings_end=0xC7B0, strings_next=0xC6F7,
        copy=0xC6C6, copy_number=None, target=0xC6EB, call=0xC6DC, number_work=0xF800,
        number_first=0x10, number_text=0xF820, unary_minus=0x3A, string_array=0x80,
        array_kinds=False, dim_pushes=False, colon=0x1D,
        for_at=0xC710, for_top=0xC6F3, gosub_at=0xF880, gosub_top=0xC6F4, int_limit=True,
        last=0xC6FE, line_numbers=True, data=0xC70E, reading=None, program_head=None,
        flags=0xC6D8, print_end=0xC6E7, print_item=0xC6A2, print_token=0xC6B5, using=0xC6F9,
        print_copies=True, print_page=None,
    )  # fmt: skip
    is_digit = staticmethod(is_digit)
    is_letter = staticmethod(is_letter)
    display_number = staticmethod(display_number)

    @staticmethod
    def ascii(c: int) -> int:
        return charset.ASCII.get(c, 0)

    @staticmethod
    def from_ascii(n: int) -> int | None:
        return charset.FROM_ASCII.get(n)

    @staticmethod
    def number_text(v: Decimal) -> bytes:
        return bytes(charset.CODES[ch] for ch in number.number_text(v))

    def literal(self, s: bytes) -> Decimal:
        return number.leading_number(s)

    def val(self, s: bytes) -> Decimal:
        return number.leading_number(s, dialect.of(self.m).val_exp_spaces)

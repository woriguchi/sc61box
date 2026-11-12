"""PC-1261系とPC-1350の式の計算。演算子の優先順位と関数はPC-1251系と同じで、違うところだけを
差し替える(観察)

- 字はASCII。比較の>=・<=・<>は2字で書く(=<や=>はERROR 1)
- 変数の名前は2字まで(英字のあとに英字か数字)。3字目からの英字と数字は名前に入れない
- 2A・2PIのように、掛け算の記号なしに並べることはできない(ERROR 1)
- 数の指数は英字のE。Eのあとの符号はいくつ続いてもよく、指数の数字のあいだのEは飛ばす
- &に続く16進表記は、4桁を越えてもよい
"""

from decimal import Decimal
from typing import cast

from ... import number
from .. import evaluate, workarea
from ..evaluate import Target, by_code
from . import editor, timing, tokens, variables

_CODE = {name: code for code, name in tokens.KEYWORDS.items()}
E = 0x45


def is_digit(c: int) -> bool:
    return 0x30 <= c <= 0x39


def is_letter(c: int) -> bool:
    return 0x41 <= c <= 0x5A


def _chars(s: bytes) -> list[str]:
    """ASCIIの並びを、leading_textの字の並びにする(Eは指数のE)"""
    return ["[E]" if c == E else chr(c) if c < 0x80 else "?" for c in s]


def number_text(v: Decimal) -> bytes:
    """STR$の字(ASCII)"""
    return "".join("E" if ch == "[E]" else ch for ch in number.number_text(v)).encode("ascii")


def display_number(v: Decimal) -> bytes:
    """RUNモードで答えとして出す字。10桁に丸め、小数点のない数には小数点を付ける"""
    return "".join("E" if ch == "[E]" else ch for ch in evaluate.answer_text(v)).encode("ascii")


def leading_number(s: bytes) -> Decimal:
    """文字列の頭の数(VALと、式の中の数の字の並び。指数の中の空白も飛ばす。観察)"""
    return number.leading_text(_chars(s), exp_spaces=True, loose_exp=True)


class Evaluator(evaluate.Evaluator):
    QUOTE, DOLLAR, COMMA, LPAREN, RPAREN = 0x22, 0x24, 0x2C, 0x28, 0x29
    PLUS, MINUS, MUL, DIV, POW, DOT, EXP, AMP = 0x2B, 0x2D, 0x2A, 0x2F, 0x5E, 0x2E, E, 0x26
    PI_CHAR = ROOT_CHAR = -1  # πと√の字はない
    DIGIT_BASE, LETTER_BASE = 0x30, 0x40
    CODES = {chr(c): c for c in range(0x20, 0x7F)}
    T_AND, T_OR, T_NOT = _CODE["AND"], _CODE["OR"], _CODE["NOT"]
    T_PI, T_MEM, T_INKEY, T_SQR = _CODE["PI"], _CODE["MEM"], _CODE["INKEY$"], _CODE["SQR"]
    T_LEFT, T_RIGHT, T_MID = _CODE["LEFT$"], _CODE["RIGHT$"], _CODE["MID$"]
    EQ, LT, GT = 0x3D, 0x3C, 0x3E
    VARS = variables.PC1261
    WORK = workarea.Layout(
        ops=0x2880, ops_size=16, ops_count=0x66F6, values=0x2080, values_size=8,
        values_top=0x66F5, strings=0x6760, strings_end=0x67B0, strings_next=0x66F7,
        copy=0x6648, copy_number=0x66B0, target=0x66EB, call=0x66DC, number_work=0x6694,
        number_first=3, number_text=0x28A0, unary_minus=0x65, string_array=0,
        array_kinds=True, dim_pushes=True, colon=0x3A,
        for_at=0x6706, for_top=0x66F3, gosub_at=0x6683, gosub_top=0x66F4, int_limit=False,
        last=0x6700, line_numbers=False, data=0x66FE, reading=0x6635, program_head=None,
        flags=0x66D8, print_end=0x66E7, print_item=None, print_token=None, using=0x66F9,
        print_copies=False, print_page=0x6650,
    )  # 計算に使うRAM(観察)  # fmt: skip
    ZERO_DIVISOR_BACK = 1  # 0で割ったエラーは、割る数の最後の字の位置(観察: 1/0は0の上)
    FUNCTIONS = by_code(tokens.KEYWORDS, evaluate.FUNCTIONS_BY_NAME)
    TIMES = timing.PC1261
    FUNCTION_TIME = by_code(tokens.KEYWORDS, evaluate.function_times(TIMES))
    is_digit = staticmethod(is_digit)
    is_letter = staticmethod(is_letter)
    number_text = staticmethod(number_text)
    display_number = staticmethod(display_number)

    @staticmethod
    def ascii(c: int) -> int:
        return c

    @staticmethod
    def from_ascii(n: int) -> int | None:
        """CHR$の字。20h〜7Ahとカナ(A1h〜DFh)だけで、ほかはERROR 9(観察)"""
        return n if 0x20 <= n <= 0x7A or 0xA1 <= n <= 0xDF else None

    @staticmethod
    def chars(s: bytes) -> list[bytes]:
        """カナは「FEh、字」の2バイトで1字(LEN・MID$などで1字に数える。観察)"""
        out: list[bytes] = []
        i = 0
        while i < len(s):
            n = 2 if s[i] == editor.KANA_MARK else 1
            out.append(s[i : i + n])
            i += n
        return out

    @staticmethod
    def char_bytes(c: int) -> bytes:
        """カナ(A1h〜DFh)は「FEh、字」にする(観察: CHR$ 177はｱ)"""
        return bytes([editor.KANA_MARK, c]) if 0xA1 <= c <= 0xDF else bytes([c])

    def literal(self, s: bytes) -> Decimal:
        return leading_number(s)

    def val(self, s: bytes) -> Decimal:
        return leading_number(s)

    def _relation_op(self) -> str | None:
        c = self.peek()
        if c == self.EQ:
            self.pos += 1
            return "="
        if c not in (self.LT, self.GT):
            return None
        self.pos += 1
        if self.take(self.EQ):
            return "<=" if c == self.LT else ">="
        if c == self.LT and self.take(self.GT):
            return "<>"
        return "<" if c == self.LT else ">"

    def _implicit(self) -> bool:
        return False

    def _operand(self):
        c = self.peek()
        if c == self.EXP:  # 頭のEは変数の名前
            return self._variable()
        return super()._operand()

    def _number(self) -> Decimal:
        start, code = self.pos, self.code

        def run(ok) -> None:
            while self.pos < len(code) and ok(code[self.pos]):
                self.pos += 1

        run(lambda c: is_digit(c) or c == self.DOT)
        if self.take(self.EXP):
            run(lambda c: c in (self.PLUS, self.MINUS))
            run(lambda c: is_digit(c) or c in (self.DOT, self.EXP))
        self.spend(self.TIMES.DIGIT * (self.pos - start - 1))
        return evaluate.in_range(self.literal(code[start : self.pos]))

    def _hex(self) -> Decimal:
        """&に続く16進表記の数(桁の数は限らない。&だけなら0。観察)"""
        self.pos += 1
        n = digits = 0
        while (c := self.peek()) is not None:
            if is_digit(c):
                d = c - self.DIGIT_BASE
            elif 0x41 <= c <= 0x46:  # A〜F
                d = c - 0x41 + 10
            else:
                break
            n, digits = n * 16 + d, digits + 1
            self.pos += 1
        self.spend(self.TIMES.DIGIT * digits)
        return Decimal(n)

    def name(self) -> int:
        """変数の名前を読む。2字目が英字か数字なら2字の名前で、そのあとの英字と数字は
        飛ばす(ABCはAB。観察)"""
        c = super().name()
        c2 = self.peek()
        if c2 is not None and (is_letter(c2) or is_digit(c2)):
            c |= c2 << 8
            self.pos += 1
            while (c3 := self.peek()) is not None and (is_letter(c3) or is_digit(c3)):
                self.pos += 1
        return c

    def _array_name(self, name: int, string: bool) -> tuple[int, int | None]:
        """名前の1字目(A(n)の続きの配列は@)と、変数の領域に置く名前の2バイト目(観察)"""
        if name > 0xFF:
            return name & 0xFF, (name >> 8) + variables.ADD[(string, False)] & 0xFF
        if name == self.VARS.EXTRA:
            return variables.EXTRA_MARK, variables.KINDS[string]
        return name, variables.KINDS[string]

    @property
    def pc1261_vars(self) -> variables.Variables:
        """2字の名前の変数を持つ、PC-1261系とPC-1350の変数の置き方(子クラスが差し替えたVARS)"""
        return cast(variables.Variables, self.VARS)

    def claim(self, target: Target) -> None:
        """文の頭に書いた2字の名前の変数は、=がなくても作る(観察: Z1だけの文はERROR 9に
        なるが、Z1はできる)"""
        if target.subs is None and target.name > 0xFF:
            self.pc1261_vars.simple(self.m, target.name, target.string)

    def resolve(self, target: Target, create: bool = False):
        if target.subs is None and target.name > 0xFF:
            return self.pc1261_vars.simple(self.m, target.name, target.string)
        return super().resolve(target, create)

    def _variable(self):
        """式の中で読む2字の名前の変数は、なければ作らずに0か空にする(観察)。文字列は
        作業場所に写す(観察)"""
        target = self.target(reading=True)
        if target.subs is None and target.name > 0xFF:
            ref = self.pc1261_vars.simple(self.m, target.name, target.string, create=False)
            if ref is None:
                return self._place(b"") if target.string else Decimal(0)
            v = self.VARS.read(self.m, ref)
        else:
            v = self.VARS.read(self.m, self.resolve(target))
        return self._place(v) if isinstance(v, bytes) else v

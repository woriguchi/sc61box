"""式の計算(系統によらない部分)

数はDecimal、文字列は本体の文字コードの並び(bytes)で扱う。字のコードと中間コードの番号、
数の字の読み書きは、系統ごとの子クラス(pc1251/evaluate.py、pc1261/evaluate.py)が決める。
"""

import math
from dataclasses import dataclass
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import TypeVar

from ..number import (
    angle_turn,
    arc_value,
    compute,
    cut,
    number_text,
    power,
    random_value,
    to_degrees,
    to_dms,
    trig_value,
)
from . import dialect, timing, variables
from .errors import BasicError
from .timing import Meter

Value = Decimal | bytes
_T = TypeVar("_T")

PI = Decimal("3.14159265359")


def number(v: Value) -> Decimal:
    if not isinstance(v, Decimal):
        raise BasicError(9)
    return v


def string(v: Value) -> bytes:
    if not isinstance(v, bytes):
        raise BasicError(9)
    return v


def calc(f, *args) -> Decimal:
    """computeで計算し、答えがなければエラー2"""
    v = compute(f, *args)
    if v is None:
        raise BasicError(2)
    return v


def int16(v: Value) -> int:
    """AND・OR・NOTに使う16ビットの整数(−32768〜65535の外はエラー3)"""
    n = int(number(v))
    if not -0x8000 <= n <= 0xFFFF:
        raise BasicError(3)
    return n & 0xFFFF


def signed16(n: int) -> Decimal:
    return Decimal(n - 0x10000 if n & 0x8000 else n)


def expect_end(e: "Evaluator") -> None:
    """行の終わりまで読んだか。余計なものがあればERROR 1"""
    if e.pos != len(e.code):
        raise BasicError(1, e.pos)


def answer_text(v: Decimal) -> list[str]:
    """RUNモードで答えとして出す字(指数のEは"[E]")。10桁に丸め、小数点のない数には小数点を
    付ける"""
    text = number_text(cut(v, 10, ROUND_HALF_UP))
    return text if "." in text else [*text, "."]


def _compare(op: str, a: Value, b: Value) -> bool:
    if isinstance(a, Decimal) and isinstance(b, Decimal):
        order = (a > b) - (a < b)
    elif isinstance(a, bytes) and isinstance(b, bytes):
        order = (a > b) - (a < b)
    else:
        raise BasicError(9)
    return {"=": order == 0, "<>": order != 0, "<": order < 0, ">": order > 0,
            "<=": order <= 0, ">=": order >= 0}[op]  # fmt: skip


@dataclass(frozen=True)
class Target:
    """変数の名前。subsは添字(配列の要素でなければNone)、endは添字の閉じ括弧の位置。
    quirkは、PC-1251で入れるときに1つ目の添字を0にするか(Evaluator.target)"""

    name: int
    string: bool
    subs: list[int] | None = None
    end: int = 0
    quirk: bool = False


class Evaluator:
    """中間コードの並びcodeの位置posから式を読んで計算する。字のコードと中間コードの番号、
    変数の置き方は、系統ごとの子クラスがクラスの属性に入れる"""

    # 字のコード
    QUOTE: int
    DOLLAR: int
    COMMA: int
    LPAREN: int
    RPAREN: int
    PLUS: int
    MINUS: int
    MUL: int
    DIV: int
    POW: int
    DOT: int
    EXP: int  # 指数のE
    AMP: int
    PI_CHAR: int  # πのキーで打つ字(なければ−1)
    ROOT_CHAR: int  # √のキーで打つ字(なければ−1)
    DIGIT_BASE: int  # 「0」の字
    LETTER_BASE: int  # 「A」の字の1つ前
    CODES: dict[str, int]  # 字から本体の文字コードへ
    # 中間コード
    T_AND: int
    T_OR: int
    T_NOT: int
    T_PI: int
    T_MEM: int
    T_INKEY: int
    T_SQR: int
    T_LEFT: int
    T_RIGHT: int
    T_MID: int
    RELATIONS: dict[int, str] = {}  # 1つの単位で書く比較の演算子
    FUNCTIONS: dict = {}  # 関数(中間コードで引く)
    FUNCTION_TIME: dict = {}
    VARS: variables.Variables  # 変数の置き方
    TIMES: timing.Timing  # かかる時間
    ZERO_DIVISOR_BACK = 0  # 0で割ったエラーの位置を、割る数の終わりから戻す字の数

    @staticmethod
    def is_digit(c: int) -> bool:
        raise NotImplementedError

    @staticmethod
    def is_letter(c: int) -> bool:
        raise NotImplementedError

    @staticmethod
    def ascii(c: int) -> int:
        """ASCの値(本体の文字コードからASCIIへ)"""
        raise NotImplementedError

    @staticmethod
    def from_ascii(n: int) -> int | None:
        """CHR$の字(ASCIIから本体の文字コードへ。なければNone)"""
        raise NotImplementedError

    @staticmethod
    def number_text(v: Decimal) -> bytes:
        """STR$の字"""
        raise NotImplementedError

    @staticmethod
    def display_number(v: Decimal) -> bytes:
        """RUNモードで答えとして出す字"""
        raise NotImplementedError

    @staticmethod
    def chars(s: bytes) -> list[bytes]:
        """文字列を1字ずつに分ける(2バイトで持つ字はPC-1261系とPC-1350のカナ)"""
        return [s[i : i + 1] for i in range(len(s))]

    @staticmethod
    def char_bytes(c: int) -> bytes:
        """文字コードcの字を文字列に入れるときのバイトの並び"""
        return bytes([c])

    def literal(self, s: bytes) -> Decimal:
        """式の中の数の字の並びの値"""
        raise NotImplementedError

    def val(self, s: bytes) -> Decimal:
        """VALで読む、文字列の頭の数"""
        raise NotImplementedError

    def _relation_op(self) -> str | None:
        """比較の演算子を読む(なければNone)"""
        op = self.RELATIONS.get(self.peek() or -1)
        if op is not None:
            self.pos += 1
        return op

    def __init__(self, m, code: bytes, pos: int = 0, meter: Meter | None = None) -> None:
        self.m = m
        self.code = code
        self.pos = pos
        self.meter = Meter() if meter is None else meter  # 計算にかかった時間をためる
        self.array_refs = 0  # 読んだ配列の要素(A(n)を除く)の数

    def spend(self, cycles: int) -> None:
        self.meter.add(cycles)

    def peek(self) -> int | None:
        return self.code[self.pos] if self.pos < len(self.code) else None

    def take(self, c: int) -> bool:
        if self.peek() == c:
            self.pos += 1
            return True
        return False

    def expect(self, c: int) -> None:
        if not self.take(c):
            raise BasicError(1)

    def expression(self) -> Value:
        """式を読んで計算する。エラーの位置は、エラーになったときに読んでいた所(観察)"""
        try:
            return self._or()
        except BasicError as e:
            e.at(self.pos)
            raise

    # ---- 演算(優先順位の低いものから) ----
    def _or(self) -> Value:
        v = self._and()
        while self.take(self.T_OR):
            v = signed16(int16(v) | int16(self._and()))
            self.spend(self._logic_time())
        return v

    def _and(self) -> Value:
        v = self._relation()
        while self.take(self.T_AND):
            v = signed16(int16(v) & int16(self._relation()))
            self.spend(self._logic_time())
        return v

    def _logic_time(self) -> int:
        """AND・ORの時間(16ビットの整数にして戻す)"""
        t = self.TIMES
        return t.OPERATOR + 2 * t.routine("F2I") + t.routine("I2F")

    def _relation(self) -> Value:
        v = self._add()
        while (op := self._relation_op()) is not None:
            w = self._add()
            self.spend(self.TIMES.RELATION + self.TIMES.routine(COMPARE[op][isinstance(w, bytes)]))
            v = Decimal(int(_compare(op, v, w)))
        return v

    def _add(self) -> Value:
        v = self._mul()
        while (op := self.peek()) in (self.PLUS, self.MINUS):
            self.pos += 1
            w = self._mul()
            if op == self.PLUS and isinstance(v, bytes):
                v = v + string(w)
                self.spend(self.TIMES.OPERATOR)
            elif op == self.PLUS:
                v = calc(lambda a, b: a + b, number(v), number(w))
                self.spend(self.TIMES.OPERATOR + self.TIMES.routine("FADD"))
            else:
                v = calc(lambda a, b: a - b, number(v), number(w))
                self.spend(self.TIMES.OPERATOR + self.TIMES.routine("FSUB"))
        return v

    def _mul(self) -> Value:
        v = self._unary()
        while True:
            op = self.peek()
            if op not in (self.MUL, self.DIV):
                return v
            self.pos += 1
            w = number(self._unary())
            f = (lambda a, b: a / b) if op == self.DIV else (lambda a, b: a * b)
            try:
                v = calc(f, number(v), w)
            except BasicError as e:
                if op == self.DIV and not w:
                    e.at(self.pos - self.ZERO_DIVISOR_BACK)
                raise
            if op == self.DIV:
                self.spend(self.TIMES.DIV + self.TIMES.DIV_PER_DIGIT * timing.digit_sum(v))
            else:
                self.spend(self.TIMES.MUL + self.TIMES.MUL_PER_DIGIT * timing.digit_sum(w))

    def _unary(self) -> Value:
        if self.take(self.MINUS):
            self.spend(self.TIMES.MINUS)
            return calc(lambda a: -a, number(self._unary()))
        if self.take(self.PLUS):
            return number(self._unary())
        v = self._power()
        while self._implicit():
            # 2A・2πのように並べた変数とπは掛け算で、*・/より先に計算する(6/2Aは
            # 6/(2*A)。観察)
            w = number(self._power())
            v = calc(lambda a, b: a * b, number(v), w)
            self.spend(self.TIMES.MUL + self.TIMES.MUL_PER_DIGIT * timing.digit_sum(w))
        return v

    def _power(self) -> Value:
        v = self._operand()
        if self.take(self.POW):
            v = calc(power, number(v), number(self._exponent()))
            self.spend(self.TIMES.OPERATOR + self.TIMES.routine("FPOW"))
        return v

    def _exponent(self) -> Value:
        """^の右(右から順に計算する。符号を付けられる。並べた変数とπは、指数の中で掛ける:
        2^2Aは2^(2*A)。観察)"""
        if self.take(self.MINUS):
            return calc(lambda a: -a, number(self._exponent()))
        if self.take(self.PLUS):
            return number(self._exponent())
        v = self._product()
        if self.take(self.POW):
            v = calc(power, number(v), number(self._exponent()))
            self.spend(self.TIMES.OPERATOR + self.TIMES.routine("FPOW"))
        return v

    # ---- 項 ----
    def _argument(self) -> Value:
        """関数の引数。符号を付けた項(^を含まない)。2A・2πのように並べた変数とπは、
        引数の中で掛ける(SIN 30AはSIN(30*A)。観察)"""
        if self.take(self.MINUS):
            return calc(lambda a: -a, number(self._argument()))
        if self.take(self.PLUS):
            return number(self._argument())
        return self._product()

    def _product(self) -> Value:
        """項と、そのあとに掛け算の記号なしに並べた変数とπ"""
        v = self._operand()
        while self._implicit():
            w = number(self._power())  # 並べた変数には^が付けられる(SIN 2A^2はSIN(2*A^2)。観察)
            v = calc(lambda a, b: a * b, number(v), w)
            self.spend(self.TIMES.MUL + self.TIMES.MUL_PER_DIGIT * timing.digit_sum(w))
        return v

    def _implicit(self) -> bool:
        """次が、掛け算の記号なしに並べた変数かπか(πは)のあとには並べられない。観察)"""
        op = self.peek()
        return op is not None and (
            self.is_letter(op) or op == self.PI_CHAR and self.code[self.pos - 1] != self.RPAREN
        )

    def _operand(self) -> Value:
        c = self.peek()
        if c is None:
            raise BasicError(1)
        if self.is_digit(c) or c in (self.DOT, self.EXP):
            return self._number()
        if c == self.AMP:
            return self._hex()
        if c == self.QUOTE:
            return self.string_literal()
        if self.is_letter(c):
            return self._variable()
        if c == self.LPAREN:
            self.pos += 1
            v = self.expression()
            self.expect(self.RPAREN)
            self.spend(self.TIMES.PAREN)
            return v
        self.pos += 1
        if c in (self.T_PI, self.PI_CHAR):  # πの字もPIと同じ(観察)
            return PI
        if c == self.T_INKEY:
            return self._inkey()
        if c == self.T_MEM:
            return Decimal(self._mem())
        if c in (self.T_LEFT, self.T_RIGHT, self.T_MID):
            return self._substring(c)
        if c == self.ROOT_CHAR:  # √の字はSQRと同じ(観察)
            c = self.T_SQR
        f = self.FUNCTIONS.get(c)
        if f is None:
            raise BasicError(1)
        v = f(self, self._argument())
        self.spend(self.TIMES.FUNCTION + self.FUNCTION_TIME.get(c, 0))
        return v

    def _number(self) -> Decimal:
        """数の字の並び。読み方はVALと同じ(仮数は10桁まで、指数は下の2桁、2つ目からの
        小数点は飛ばす)。1E100以上ならERROR 9、1E-99より小さければ0(観察)"""
        start, code = self.pos, self.code
        while self.pos < len(code) and (
            self.is_digit(code[self.pos]) or code[self.pos] == self.DOT
        ):
            self.pos += 1
        if self.take(self.EXP):
            if not self.take(self.MINUS):
                self.take(self.PLUS)
            while self.pos < len(code) and (
                self.is_digit(code[self.pos]) or code[self.pos] == self.DOT
            ):
                self.pos += 1
        self.spend(self.TIMES.DIGIT * (self.pos - start - 1))
        return in_range(self.literal(code[start : self.pos]))

    def _hex(self) -> Decimal:
        """&に続く16進表記の数(4桁まで。5桁目からは続きの式として読む。&だけなら0。観察)"""
        self.pos += 1
        n = digits = 0
        while digits < 4 and (c := self.peek()) is not None:
            if self.is_digit(c):
                d = c - self.DIGIT_BASE
            elif self.LETTER_BASE + 1 <= c <= self.LETTER_BASE + 6:  # A〜F
                d = c - self.LETTER_BASE - 1 + 10
            else:
                break
            n, digits = n * 16 + d, digits + 1
            self.pos += 1
        self.spend(self.TIMES.DIGIT * digits)
        return Decimal(n)

    def skip_string(self) -> int:
        """文字列を読み飛ばし、そのあとの位置を返す"""
        self.string_literal()
        return self.pos

    def string_literal(self) -> bytes:
        self.pos += 1
        end = self.code.find(self.QUOTE, self.pos)
        if end < 0:
            end = len(self.code)
        s = self.code[self.pos : end]
        self.pos = min(end + 1, len(self.code))
        return s

    def _variable(self) -> Value:
        return self.VARS.read(self.m, self.reference())

    def name(self) -> int:
        """変数の名前の字(PC-1251系は英字1字)を読む"""
        c = self.peek()
        if c is None or not self.is_letter(c):
            raise BasicError(1, self.pos)
        self.pos += 1
        return c

    def target(self) -> Target:
        """変数の名前(A、A$、B(1)、C$(1,2)など)を読む"""
        c = self.name()
        string = self.take(self.DOLLAR)
        if not self.take(self.LPAREN):
            return Target(c, string)
        subs = [self.integer()]
        quirk = False
        if self.take(self.COMMA):
            before = self.array_refs
            subs.append(self.integer())
            # PC-1251: 2つ目の添字に配列の要素があると、入れるときは1つ目の添字が0になる
            # (読むときはならない。観察)
            quirk = self.array_refs != before and dialect.of(self.m).subscript_quirk
        self.expect(self.RPAREN)
        if not (c == self.VARS.EXTRA and len(subs) == 1):
            self.array_refs += 1
        return Target(c, string, subs, self.pos - 1, quirk)

    def claim(self, target: "Target") -> None:
        """文の頭(代入の左辺の場所)で読んだ変数の名前。PC-1251系は何もしない"""

    def resolve(self, target: "Target", create: bool = False) -> variables.Ref:
        """targetの場所。createなら、A(n)の続きの場所を作ってよい(代入の左辺)。添字の
        エラーの位置は閉じ括弧(観察)"""
        if target.subs is None:
            return self.VARS.Ref(
                self.VARS.fixed_addr(target.name - self.LETTER_BASE), target.string
            )
        subs = [0, target.subs[1]] if create and target.quirk else target.subs
        try:
            return self.VARS.element(self.m, target.name, target.string, subs, create)
        except BasicError as e:
            e.at(target.end)
            raise

    def reference(self, create: bool = False) -> variables.Ref:
        return self.resolve(self.target(), create)

    def integer(self) -> int:
        """式を計算して、小数を切り捨てた整数にする"""
        v = self.expression()
        try:
            return int(number(v))
        except BasicError as e:
            e.at(self.pos)
            raise

    def _inkey(self) -> bytes:
        """INKEY$: いま押している字のキーの字(SHIFTは見ない)。字のキーでなければ空(観察)"""
        for k in sorted(self.m.held):
            ch = " " if k == "SPC" else k
            if len(ch) == 1 and ch in self.CODES:
                return bytes([self.CODES[ch]])
        return b""

    def _mem(self) -> int:
        m = self.m
        word = lambda a: m.mem[a] | m.mem[a + 1] << 8  # noqa: E731
        return word(self.VARS.ARRAY_PTR) - word(m.model.prog_end_ptr) - 1

    def _substring(self, which: int) -> bytes:
        """LEFT$・RIGHT$の字数は0〜80、MID$の始めは1〜80、字数は0〜80。小数は下の整数にして
        から見て、外れればERROR 3(観察)"""
        self.expect(self.LPAREN)
        s = string(self.expression())
        self.expect(self.COMMA)
        a = _floor(self.expression())
        b = None
        if which == self.T_MID:
            self.expect(self.COMMA)
            b = _floor(self.expression())
        low = 1 if which == self.T_MID else 0
        if not low <= a <= SUBSTRING_MAX or b is not None and not 0 <= b <= SUBSTRING_MAX:
            raise BasicError(3)  # 位置は閉じる括弧(観察)
        self.expect(self.RPAREN)
        c = self.chars(s)
        if which == self.T_LEFT:
            return b"".join(c[: max(a, 0)])
        if which == self.T_RIGHT:
            return b"".join(c[len(c) - a :]) if a > 0 else b""
        assert b is not None
        return b"".join(c[max(a - 1, 0) : max(a - 1, 0) + max(b, 0)])


SUBSTRING_MAX = 80  # LEFT$・RIGHT$・MID$の字数と位置の上限(観察)


def _floor(v: Value) -> int:
    return int(number(v).to_integral_value(rounding=ROUND_FLOOR))


def in_range(v: Decimal) -> Decimal:
    """読んだ数: 1E100以上ならERROR 9、1E-99より小さければ0(観察)"""
    if abs(v) >= Decimal("1E100"):
        raise BasicError(9)
    return v if abs(v) >= Decimal("1E-99") else Decimal(0)


def _trig(fn, exact):
    def f(e: Evaluator, v: Value) -> Decimal:
        turn = angle_turn(e.m)
        return calc(lambda x: trig_value(fn, exact, x, turn), number(v))

    return f


def _arc(fn):
    return lambda e, v: calc(lambda x: arc_value(fn, x, angle_turn(e.m)), number(v))


def _num(f):
    return lambda e, v: calc(f, number(v))


def _peek(e: Evaluator, v: Value) -> Decimal:
    a = int(number(v))
    if not 0 <= a <= 0xFFFF:
        raise BasicError(3)
    return Decimal(e.m.read(a))


def _chr(e: Evaluator, v: Value) -> bytes:
    n = int(number(v))
    if n == 0:
        return b""
    c = e.from_ascii(n)
    if c is None:
        raise BasicError(9)
    return e.char_bytes(c)


FUNCTIONS_BY_NAME = {
    "SIN": _trig(math.sin, (0, 1, 0, -1)),
    "COS": _trig(math.cos, (1, 0, -1, 0)),
    "TAN": _trig(math.tan, (0, None, 0, None)),
    "ASN": _arc(math.asin),
    "ACS": _arc(math.acos),
    "ATN": _arc(math.atan),
    "EXP": _num(lambda x: x.exp()),
    "LN": _num(lambda x: x.ln()),
    "LOG": _num(lambda x: x.log10()),
    "INT": _num(lambda x: x.to_integral_value(rounding=ROUND_FLOOR)),
    "ABS": _num(abs),
    "SGN": _num(lambda x: Decimal((x > 0) - (x < 0))),
    "DEG": _num(to_degrees),
    "DMS": _num(to_dms),
    "RND": lambda e, v: calc(lambda x: random_value(e.m, x), number(v)),
    "PEEK": _peek,
    "SQR": _num(lambda x: x.sqrt()),
    "NOT": lambda e, v: signed16(~int16(v) & 0xFFFF),
    "ASC": lambda e, v: Decimal(e.ascii(e.chars(string(v))[0][-1]) if string(v) else 0),
    "VAL": lambda e, v: in_range(e.val(string(v))),
    "LEN": lambda e, v: Decimal(len(e.chars(string(v)))),
    "CHR$": _chr,
    "STR$": lambda e, v: e.number_text(number(v)),
}


def function_times(t: timing.Timing) -> dict[str, int]:
    """関数の、計算のルーチンにかかる時間(サイクル)"""
    r = t.routine
    return {
        "SIN": r("FSIN"), "COS": r("FCOS"), "TAN": r("FTAN"), "ASN": r("FASN"),
        "ACS": r("FACS"), "ATN": r("FATN"), "EXP": r("FEXP"), "LN": r("FLN"), "LOG": r("FLOG"),
        "INT": r("FINT"), "ABS": r("FABS"), "SGN": r("FSGN"), "DEG": r("FDEG"),
        "DMS": r("FDMS"), "RND": r("FRND"), "PEEK": r("I2F") + r("F2I"), "SQR": r("FSQR"),
        "ASC": r("FASC"), "VAL": r("FVAL"), "CHR$": r("FCHRS"), "STR$": r("FSTRS"),
        "NOT": t.NOT + r("F2I") + r("I2F"),
    }  # fmt: skip


# 比較の演算子の、比べるルーチンの名前: (数のとき, 文字列のとき)
COMPARE = {
    "=": ("FEQ", "SEQ"), "<>": ("FNE", "SNE"), "<": ("FLT", "SLT"),
    ">": ("FGT", "SGT"), "<=": ("FLE", "SLE"), ">=": ("FGE", "SGE"),
}  # fmt: skip


def by_code(keywords: dict[int, str], table: dict[str, _T]) -> dict[int, _T]:
    """命令の綴りで引く表を、中間コードで引く表にする"""
    return {code: table[name] for code, name in keywords.items() if name in table}

"""USINGの書式(書式の形と出し方は、ROMのある本体で観察した)

書式は、数の書式「#の並び[.[#の並び]][^の並び]」と、文字列の書式「&の並び」を、どちらか
一方か両方(順はどちらでもよい)並べたもの。数の書式と文字列の書式は別々に覚えていて、
片方だけを書いたUSINGは、もう片方を変えない。
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, localcontext

from .errors import BasicError

# 字の並びは、字から本体の文字コードへの表codes(系統ごとに違う。指数のEは"[E]")で作る


def _codes(text: str, codes: dict[str, int]) -> bytes:
    return bytes(codes[ch] for ch in text)


@dataclass(frozen=True)
class NumberFormat:
    """width: 小数点より前の#の数(符号の場所を含む)。decimals: 小数点より後ろの#の数。
    dot: 小数点があるか。exponent: ^があるか"""

    width: int
    decimals: int = 0
    dot: bool = False
    exponent: bool = False

    def field(
        self, v: Decimal, codes: dict[str, int], zero_quirk: bool = True, limit: int | None = None
    ) -> bytes:
        """数の欄(幅に満たなければ左に空白)。数は10桁に丸めてから、桁を切り捨てる。小数の
        桁は12桁まで(指数の形では9桁まで)。整数の部分が#の数より1つ少ない桁に入らなければ
        ERROR 7。limitがあれば、整数の桁(10桁まで)と小数の桁の和がlimitを越えるとERROR 7
        (PC-1245)。zero_quirkは下に書くPC-1251の出し方(観察)"""
        space = codes[" "]
        sign = "-" if v < 0 else ""
        with localcontext() as ctx:
            ctx.prec = 10
            ctx.rounding = ROUND_HALF_UP
            a = +abs(v)
        decimals = min(self.decimals, 9 if self.exponent else 12)
        if limit is not None and min(self.width - 1, 10) + decimals > limit:
            raise BasicError(7)
        q = Decimal(1).scaleb(-decimals)
        width = self.width + (1 + decimals if self.dot else 0)
        if self.exponent:
            e = a.adjusted() if a else 0
            mant = (a.scaleb(-e) if a else Decimal(0)).quantize(q, rounding=ROUND_DOWN)
            digits = f"{mant:.{decimals}f}" + ("." if self.dot and not decimals else "")
            tail = ("-" if e < 0 else " ") + f"{abs(e):02d}"
            text = _codes(sign + digits, codes) + bytes([codes["[E]"]]) + _codes(tail, codes)
            return bytes([space]) * (width + 4 - len(text)) + text
        if a and a.adjusted() + 1 > self.width - 1:
            raise BasicError(7)  # 整数の部分が入らない(大きな数で桁を切る前に調べる)
        with localcontext() as ctx:
            ctx.prec = 200  # #を多く並べた書式でも、切り捨てで桁が足りなくならないように
            t = a.quantize(q, rounding=ROUND_DOWN)
        whole = str(int(t))
        if len(whole) > self.width - 1:
            raise BasicError(7)
        if zero_quirk and v and not t and decimals:
            # PC-1251: 0でない数が小数の桁に入らず0になるときは、小数の最後の桁が出ず、
            # 欄も1つ短い(観察)
            out = _codes(sign + "0." + "0" * (decimals - 1), codes)
            width -= 1
        else:
            frac = f"{t:.{decimals}f}".split(".")[1] if decimals else ""
            out = _codes(sign + whole + ("." + frac if self.dot else ""), codes)
        return bytes([space]) * (width - len(out)) + out


@dataclass(frozen=True)
class Format:
    """USINGの書式。numberは数の書式、textは文字列の書式の幅(&の数)。Noneはその書式がない"""

    number: NumberFormat | None = None
    text: int | None = None

    @staticmethod
    def parse(s: bytes, codes: dict[str, int], dot_first: bool = False) -> "Format":
        """書式の字の並びを読む。形が違えばERROR 1。dot_firstなら、数の書式を「.」で
        始めてよい(PC-1245。観察)"""
        amp, sharp, dot_c, hat = codes["&"], codes["#"], codes["."], codes["^"]
        number: NumberFormat | None = None
        text: int | None = None
        i = 0
        while i < len(s):
            start = i
            if s[i] == amp and text is None:
                while i < len(s) and s[i] == amp:
                    i += 1
                text = i - start
                continue
            if not (s[i] == sharp or s[i] == dot_c and dot_first) or number is not None:
                raise BasicError(1)
            while i < len(s) and s[i] == sharp:
                i += 1
            width = i - start
            dot = i < len(s) and s[i] == dot_c
            decimals = 0
            if dot:
                i += 1
                while i < len(s) and s[i] == sharp:
                    i += 1
                    decimals += 1
            exponent = i < len(s) and s[i] == hat
            while i < len(s) and s[i] == hat:
                i += 1
            number = NumberFormat(width, decimals, dot, exponent)
        return Format(number, text)

    def merged(self, new: "Format") -> "Format":
        """newで書いた書式だけを置き換えた書式"""
        return Format(new.number or self.number, new.text or self.text)

    def show_number(
        self,
        v: Decimal,
        plain: Callable[[Decimal], bytes],
        codes: dict[str, int],
        zero_quirk: bool = True,
        limit: int | None = None,
    ) -> bytes:
        """数の出し方。数の書式がなければ、ふつうの出し方plain。codes・zero_quirk・limitは
        fieldのもの"""
        if self.number is None:
            return plain(v)
        return self.number.field(v, codes, zero_quirk, limit)

    def show_string(self, s: bytes, space: int) -> bytes:
        """文字列の出し方。文字列の書式があれば、幅に切って右を空白で埋める"""
        if self.text is None:
            return s
        s = s[: self.text]
        return s + bytes([space]) * (self.text - len(s))

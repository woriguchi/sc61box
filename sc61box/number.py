"""数の読み書きと計算

BASICの変数と同じ8バイトの形の数の読み書き、桁の切り捨て、計算と範囲の検査、三角関数と角度、
乱数、数と字の並びの変換。代替ROMルーチンとROMなしのBASICが使う。
"""

from __future__ import annotations

import hashlib
import math
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, localcontext

from .basictext import CHARS

ANGLE_LIMIT = Decimal("1E10")  # 三角関数の角度(度にしたもの)の大きさの上限
PI = Decimal("3.14159265358979323846264338")


def get_num(ram, at: int) -> Decimal:
    """内部RAMのatからの8バイトの数。BASICの変数と同じ形(指数3桁の10の補数、符号、仮数12桁)"""
    b = ram[at : at + 8]
    digits = "".join(f"{v:02X}" for v in b[2:8])
    if not digits.isdigit() or int(digits) == 0:
        return Decimal(0)
    e = (b[0] >> 4) * 100 + (b[0] & 0x0F) * 10 + (b[1] >> 4)
    if e >= 500:
        e -= 1000
    return Decimal(f"{'-' if b[1] & 0x08 else ''}{digits[0]}.{digits[1:]}E{e}")


def put_num(ram, at: int, v: Decimal) -> None:
    """vを12桁で切り捨てて、内部RAMのatから書く。指数が−99より小さければ0にする"""
    v = cut(v)
    if v == 0 or v.adjusted() < -99:
        ram[at : at + 8] = bytes(8)
        return
    sign, digits, _ = v.as_tuple()
    d = (list(digits) + [0] * 12)[:12]
    e = v.adjusted() % 1000
    ram[at] = (e // 100) << 4 | e // 10 % 10
    ram[at + 1] = (e % 10) << 4 | (0x08 if sign else 0)
    for i in range(6):
        ram[at + 2 + i] = d[2 * i] << 4 | d[2 * i + 1]


def cut(v: Decimal, digits: int = 12, rounding: str = ROUND_DOWN) -> Decimal:
    with localcontext() as c:
        c.prec, c.rounding = digits, rounding
        return +v


def compute(f, *args) -> Decimal | None:
    """f(*args)を12桁で切り捨てた数。答えがない(fがNone)か、計算できないか、1E100以上なら
    None。1E−99より小さければ0"""
    v: Decimal | None
    try:
        with localcontext() as c:
            c.prec, c.Emax, c.Emin = 24, 999_999, -999_999
            v = f(*args)
    except (ArithmeticError, ValueError):
        return None
    if v is None or not v.is_finite():
        return None
    v = cut(v)
    if v != 0 and v.adjusted() >= 100:
        return None
    return Decimal(0) if v != 0 and v.adjusted() < -99 else v


def power(y: Decimal, x: Decimal) -> Decimal | None:
    if (y == 0 and x <= 0) or (y < 0 and x != x.to_integral_value()):
        return None
    return y**x


def angle_turn(m) -> Decimal | None:
    """1回りの角度(液晶のDEG・GRADの記号で決まる)。RADならNone"""
    if m.model.lines == 2 or m.model.family == "1350":
        # PC-1261系: 207Cのビット1がRAD、ビット2がGRAD。PC-1350は787Chの同じビット
        flags = m.mem[0x787C if m.model.family == "1350" else 0x207C]
        return None if flags & 0x02 else Decimal(400) if flags & 0x04 else Decimal(360)
    if not m.mem[0xF83D] & 0x04:
        return Decimal(360)
    return Decimal(400) if m.mem[0xF83C] & 0x04 else None


def _float(f: float) -> Decimal:
    """floatの答えを15桁に丸めてDecimalにする(0.49999999999999994を0.5に)"""
    return Decimal(f"{f:.15g}")


def trig_value(
    fn, exact: tuple[int | None, ...], x: Decimal, turn: Decimal | None
) -> Decimal | None:
    """角度xのfnの値。turnは1回りの角度(RADならNone)"""
    deg = x * 360 / turn if turn is not None else x * 180 / PI
    if abs(deg) >= ANGLE_LIMIT:
        return None
    # 直角の倍数かは、度を12桁(RADでは10桁)に丸めて見る(ROMのある本体で確かめた)
    q, rest = divmod(cut(deg, 10 if turn is None else 12, ROUND_HALF_UP) % 360 + 360, 90)
    if rest == 0:
        v = exact[int(q) % 4]
        return None if v is None else Decimal(v)
    if turn is None:
        return _float(fn(float(x)))
    return _float(fn(float(x % turn) * 2 * math.pi / float(turn)))


def arc_value(fn, x: Decimal, turn: Decimal | None) -> Decimal:
    """fnの答えのラジアンを、turnを1回りとする角度にする(turnがNoneならラジアンのまま)"""
    scale = 1.0 if turn is None else float(turn) / (2 * math.pi)
    return _float(fn(float(x)) * scale)


def to_degrees(x: Decimal) -> Decimal:
    """度・分・秒(12.3456は12度34分56秒)を度にする"""
    a = abs(x)
    d = int(a)
    minutes = (a - d) * 100
    mi = int(minutes)
    v = d + mi / Decimal(60) + (minutes - mi) * 100 / 3600
    return -v if x < 0 else v


def to_dms(x: Decimal) -> Decimal:
    """度を度・分・秒にする"""
    a = abs(x)
    d = int(a)
    minutes = (a - d) * 60
    mi = int(minutes)
    v = d + mi / Decimal(100) + (minutes - mi) * 60 / 10000
    return -v if x < 0 else v


MASK64 = (1 << 64) - 1


def _random(m) -> int:
    """乱数の種(本体のrnd_seed。どこでもセーブに入る)を進めて、64ビットの乱数を返す
    (xorshift64*)"""
    x = m.rnd_seed or 1
    x ^= x >> 12
    x ^= (x << 25) & MASK64
    x ^= x >> 27
    m.rnd_seed = x
    return (x * 0x2545F4914F6CDD1D) & MASK64


def _below(m, n: int) -> int:
    """0以上n未満の乱数"""
    v = 0
    for _ in range(n.bit_length() // 64 + 2):
        v = v << 64 | _random(m)
    return v % n


def random_value(m, x: Decimal) -> Decimal:
    """RND xの値。1以上なら1〜その数の整数、0以上1未満なら0と1のあいだの数。負なら、その数で
    乱数の種を決めてから0と1のあいだの数(乱数の並びはROMと違う)"""
    if x < 0:
        m.rnd_seed = int.from_bytes(hashlib.sha256(str(x).encode()).digest()[:8]) or 1
    if x >= 1:
        return Decimal(1 + _below(m, int(x)))
    return Decimal(1 + _below(m, 10**12 - 1)).scaleb(-12)


def number_text(v: Decimal) -> list[str]:
    """STR$の字の並び。10桁で切り捨て、整数部と小数部の桁が合わせて10桁までなら小数で、
    越えれば指数で書く(指数は空白か−のあとに2桁)。書き方はROMのある本体で確かめたもの"""
    v = cut(v, 10)
    if v == 0:
        return ["0"]
    sign, digits, _ = v.normalize().as_tuple()
    ds = "".join(map(str, digits))
    e = v.adjusted()
    if (max(e + 1, len(ds)) if e >= 0 else len(ds) - e) <= 10:
        body = list(format(abs(v).normalize(), "f"))
    else:
        body = [ds[0], ".", *ds[1:], "[E]", "-" if e < 0 else " ", *f"{abs(e):02d}"]
    return ["-", *body] if sign else body


def leading_number(s: bytes, exp_spaces: bool = False) -> Decimal:
    """文字列の頭の数。読み方はROMのある本体で確かめたもの: 空白は飛ばす。頭の+と−は
    いくつ続いてもよい。2つ目からの小数点は飛ばす。仮数は10桁まで。指数は指数のE(4Bh)の
    すぐあとの符号と数字で、数字のあいだの小数点は飛ばし、3桁以上なら下の2桁を使う。仮数の
    字がなく指数のEがあれば、仮数は1(小数点だけなら0)。exp_spacesなら、指数の中の空白も
    飛ばす(PC-1245)"""
    return leading_text([CHARS.get(b, "?") for b in s], exp_spaces)


def leading_text(chars: list[str], exp_spaces: bool = False, loose_exp: bool = False) -> Decimal:
    """leading_numberの読み方で、字の並び(指数のEは"[E]")の頭の数を読む。loose_expなら、
    指数の符号はいくつ続いてもよく(−の数で決まる)、指数の数字のあいだのEも飛ばす(PC-1261系とPC-1350。
    観察)"""
    text = [*chars, ""]
    i, neg = 0, False
    while text[i] in (" ", "+", "-"):
        neg ^= text[i] == "-"
        i += 1
    digits, point = "", -1
    while text[i] == " " or text[i].isdigit() or text[i] == ".":
        if text[i] == "." and point < 0:
            point = len(digits)
        elif text[i].isdigit():
            digits += text[i]
        i += 1
    if not digits and (point >= 0 or text[i] != "[E]"):
        return Decimal(0)
    if digits:
        # 桁の多い数でも丸めずに作ってから、10桁に切り捨てる
        exp = (point if point >= 0 else len(digits)) - len(digits)
        v = cut(Decimal((0, tuple(int(d) for d in digits), exp)), 10)
    else:
        v = Decimal(1)
    if text[i] == "[E]":
        j, sign = i + 1, 1

        def skip() -> None:
            nonlocal j
            while exp_spaces and text[j] == " ":
                j += 1

        skip()
        while text[j] in ("+", "-"):
            sign = -sign if text[j] == "-" else sign
            j += 1
            if not loose_exp:
                break
        exp = ""
        skip()
        while text[j].isdigit() or text[j] == "." or loose_exp and text[j] == "[E]":
            exp += text[j] if text[j].isdigit() else ""
            j += 1
            skip()
        if exp:
            v = v.scaleb(sign * int(exp[-2:]))
    return -v if neg else v

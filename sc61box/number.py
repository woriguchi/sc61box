"""数の読み書きと計算

BASICの変数と同じ8バイトの形の数の読み書き、桁の切り捨て、計算と範囲の検査、三角関数と角度、
乱数、数と字の並びの変換。代替ROMルーチンとROMなしのBASICが使う。
"""

from __future__ import annotations

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


# 乱数の種を置く番地と、電源を入れたときの種(観察。PC-1251系はπ、PC-1261系とPC-1350は180/π)
SEED_1251 = (0xF8B0, bytes.fromhex("0000314159265359"))
SEED_1261 = (0x28B8, bytes.fromhex("0010572957795131"))
SEED_1350 = (0x7298, bytes.fromhex("0010572957795131"))


def _seed_place(m) -> tuple[int, bytes]:
    if m.model.family == "1350":
        return SEED_1350
    return SEED_1261 if m.model.lines == 2 else SEED_1251


def _digits(b: bytes) -> int | None:
    """8バイトの数の仮数の12桁(BCDでなければNone)"""
    text = "".join(f"{v:02X}" for v in b[2:8])
    return int(text) if text.isdigit() else None


def reset_seed(m) -> None:
    """電源を入れたときの種を置く(観察)"""
    at, init = _seed_place(m)
    m.mem[at : at + 8] = init


def _seed(m) -> Decimal:
    """いまの乱数の種(0〜1)。仮数の12桁を0.の後ろに並べた数とみる。指数の欄は見ない(観察)。
    仮数がBCDでなければ、電源を入れたときの種とみる"""
    at, init = _seed_place(m)
    d = _digits(bytes(m.mem[at : at + 8]))
    return Decimal(d if d is not None else _digits(init) or 0).scaleb(-12)


def _advance(m, s: Decimal) -> None:
    """種sから次の種を求めてRAMに置く(観察)。p=230sを12桁で切り捨て、pが1以上か0なら
    (pを10で割った余り)を10^-10の桁で切り捨てて10^-11を足し、10で割る(指数は−1のまま、仮数の
    頭の0は詰めない)。pが1より小さければ、pを10^-10の桁で切り捨てて12桁目に1を足し、10で割る。
    指数の欄の下位4ビットにはpの十の位を置く"""
    with localcontext() as c:
        c.prec = 40
        p = s * 230
        if p:
            p = p.quantize(Decimal(1).scaleb(p.adjusted() - 11), rounding=ROUND_DOWN)
        tens = int(p // 10) % 10
        buf = bytearray(8)
        if p >= 1 or p == 0:
            y = (p % 10).quantize(Decimal("1E-10"), rounding=ROUND_DOWN) + Decimal("1E-11")
            new = y / 10
            d = f"{int(new.scaleb(12)):012d}"
            buf[:2] = b"\x99\x90"
            buf[2:] = bytes(int(d[i : i + 2], 16) for i in range(0, 12, 2))
        else:
            y = p.quantize(Decimal("1E-10"), rounding=ROUND_DOWN)
            y += Decimal(1).scaleb((y.adjusted() if y else -10) - 11)
            new = y / 10
            put_num(buf, 0, new)
        buf[1] |= tens
    at, _ = _seed_place(m)
    m.mem[at : at + 8] = buf


LOG10_E = Decimal("0.434294481903")


def random_value(m, x: Decimal) -> Decimal:
    """RND x(観察)。種を進め、xが1以上ならINT(種×x)+1、0以上1未満なら種そのもの(種は_seedの
    読み方で読む)。負なら、xの仮数の12桁(PC-1261系とPC-1350は|x|×log10(e)の仮数の12桁)を0.の
    後ろに並べた数を種にしてから進め、種そのもの"""
    if x < 0:
        y = x if _seed_place(m) == SEED_1251 else cut(-x * LOG10_E)
        buf = bytearray(8)
        put_num(buf, 0, y)
        s = Decimal(_digits(bytes(buf)) or 0).scaleb(-12)
    else:
        s = _seed(m)
    _advance(m, s)
    new = _seed(m)
    if x >= 1:
        return Decimal(int(new * x) + 1)
    return new


def randomize(m) -> None:
    """RANDOM: 種を新しくする(ROMのある本体は時刻から作る。ここではrnd_seedから作る)"""
    _advance(m, Decimal(_random(m) % 10**12).scaleb(-12))


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


def put_str_work(
    m, base: int, first: int, text_at: int | None, text: bytes, codes: dict[str, int]
) -> None:
    """STR$が数を字にするのに使ったRAMの跡(観察)。textはSTR$の字の並び、codesは字の文字コード。
    baseからの28バイトを空白で埋め、15〜23バイト目を0で埋め、小数点が14バイト目に来るように
    字を置いた形のうち、first(バイト数)から後ろを書く。text_atには、小数点のない数に小数点を
    足した字の並びと、24バイトまでの残りのFFhを書く"""
    dot = codes["."]
    shown = text if dot in text else text + bytes([dot])
    buf = bytearray([codes[" "]] * 28)
    buf[15:24] = bytes([codes["0"]] * 9)
    start = 14 - shown.index(dot)
    for i, c in enumerate(shown):
        if 0 <= start + i < 28:
            buf[start + i] = c
    m.mem[base + first : base + 28] = buf[first:]
    if text_at is not None:
        m.mem[text_at : text_at + 24] = shown[:24].ljust(24, b"\xff")
    m.lcd_dirty = True


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

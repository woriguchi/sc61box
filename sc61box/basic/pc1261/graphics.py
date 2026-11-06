"""PC-1350のグラフィック: GCURSOR・GPRINT・PSET・PRESET・LINE・POINT(観察)

- 点は液晶の150×32ドット。xは左から0〜149、yは上から0〜31。座標は小数を切り捨て(下の
  整数)、-32768〜32767を越えるとERROR 3。液晶の外の点は描かない(POINTは-1)
- GPRINTは、グラフィックのカーソル(GCURSORで決める。初めとCLSのあとは(0,7))の列に、
  1列8ドットを、カーソルのyを下端(ビット7)として書き、列ごとに右へ進む。数は0〜255
  の1列、文字列は16進表記の2字ずつが1列(大文字。余った1字は見ない)。;は続けて、,は
  空の列を1つ書いてから書く。終わりに;か,がなければ、カーソルのxを0に戻す
- LINE [(x1,y1)]-(x2,y2)[,S|R|X][,線の形][,B|BF]。始めを省くと前のLINEの終わり(初めと
  CLSのあとは(0,0))から。線は長い方の軸に1ドットずつ進め、短い方の軸は始めからの比で
  決め、ちょうど半分のときは始めの側に寄せる。線の形は16ドットの繰り返しで、下位バイト、
  上位バイトの順に、それぞれ上位ビットから使う(液晶の外の点も数える)
- Bは、xの小さい方の角から横、縦、横、縦の順に囲む(線の形は続けて数え、始めの角は2度
  描く)。幅か高さが0なら1本の線。BFは各行を左から塗る
- 描く命令(GPRINT・PSET・PRESET・LINE)は、PRINTと同じように、WAITがなければENTERを
  待ち、WAIT nならその時間待つ
"""

from collections.abc import Iterator

from ...machine import LCD_BANDS_1350, LCD_BLOCKS_1350
from ..errors import BasicError

WIDTH, HEIGHT = 150, 32
LOWEST, HIGHEST = -32768, 32767
START = (0, 7)  # GPRINTのカーソルの初め


def check(n: int) -> int:
    if not LOWEST <= n <= HIGHEST:
        raise BasicError(3)
    return n


def _where(x: int, y: int) -> tuple[int, int]:
    """点(x,y)の液晶RAMの番地とビット"""
    block, col = divmod(x, 30)
    return LCD_BLOCKS_1350[block] + LCD_BANDS_1350[y >> 3] + col, 1 << (y & 7)


def point(m, x: int, y: int) -> int:
    """POINT: 点いていれば1、消えていれば0、液晶の外なら-1"""
    if not (0 <= x < WIDTH and 0 <= y < HEIGHT):
        return -1
    a, bit = _where(x, y)
    return 1 if m.mem[a] & bit else 0


def plot(m, x: int, y: int, how: str) -> None:
    """S(点ける)・R(消す)・X(反転)"""
    if not (0 <= x < WIDTH and 0 <= y < HEIGHT):
        return
    a, bit = _where(x, y)
    v = m.mem[a]
    m.write(a, v | bit if how == "S" else v & ~bit if how == "R" else v ^ bit)


def column(m, x: int, bottom: int, byte: int) -> None:
    """GPRINTの1列: yがbottom-7〜bottomの8ドットを書き換える"""
    if not 0 <= x < WIDTH:
        return
    for k in range(8):
        y = bottom - 7 + k
        if 0 <= y < HEIGHT:
            plot(m, x, y, "S" if byte >> k & 1 else "R")


def hex_columns(text: bytes) -> Iterator[int]:
    """GPRINTの文字列: 16進表記の2字ずつの列を順に返す。2字の中に大文字の0〜9・A〜Fで
    ないものがあれば、その前の列までを返してからERROR 1。余った1字は見ない(観察)"""
    digits = b"0123456789ABCDEF"
    for i in range(0, len(text) - 1, 2):
        pair = text[i : i + 2]
        if any(c not in digits for c in pair):
            raise BasicError(1)
        yield int(pair, 16)


def segment(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """(x0,y0)から(x1,y1)までの線の点を、始めから順に"""
    dx, dy = x1 - x0, y1 - y0
    n = max(abs(dx), abs(dy))
    if n == 0:
        return [(x0, y0)]
    major, minor = (abs(dx), abs(dy)) if abs(dx) >= abs(dy) else (abs(dy), abs(dx))
    sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
    out = []
    for i in range(n + 1):
        # 短い方の軸の進み: minor*i/majorを、ちょうど半分なら切り捨てて丸める
        off = -((major - 2 * minor * i) // (2 * major))
        if abs(dx) >= abs(dy):
            out.append((x0 + sx * i, y0 + sy * off))
        else:
            out.append((x0 + sx * off, y0 + sy * i))
    return out


def box(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """Bで囲む点を描く順に"""
    if x0 > x1:
        x0, y0, x1, y1 = x1, y1, x0, y0
    if x0 == x1 or y0 == y1:
        return segment(x0, y0, x1, y1)
    s = 1 if y1 > y0 else -1
    pts = [(x, y0) for x in range(x0, x1 + 1)]
    pts += [(x1, y) for y in range(y0 + s, y1 + s, s)]
    pts += [(x, y1) for x in range(x1 - 1, x0 - 1, -1)]
    pts += [(x0, y) for y in range(y1 - s, y0 - s, -s)]
    return pts


def _bits(pattern: int) -> list[int]:
    """線の形の16ドット: 下位バイト、上位バイトの順に、それぞれ上位ビットから"""
    return [pattern >> (7 - k) & 1 for k in range(8)] + [pattern >> (15 - k) & 1 for k in range(8)]


def draw(m, pts: list[tuple[int, int]], how: str, pattern: int) -> Iterator[bool]:
    """点の並びを、線の形に合わせて1点ずつ描く。点ごとに、液晶の中の点だったかを返す
    (描く側が点ごとの時間を進め、途中でBRKを見る)"""
    bits = _bits(pattern)
    for i, (x, y) in enumerate(pts):
        if bits[i & 15]:
            plot(m, x, y, how)
        yield 0 <= x < WIDTH and 0 <= y < HEIGHT


def fill(
    m, x0: int, y0: int, x1: int, y1: int, how: str, pattern: int
) -> Iterator[tuple[int, int]]:
    """BF: 各行を左から塗る(線の形は行ごとに左端から数える)。(液晶の中の点の数, 外の点の
    数)を、行の左の外、中の1点ずつ、右の外の順に返す"""
    bits = _bits(pattern)
    xa, xb = sorted((x0, x1))
    ya, yb = sorted((y0, y1))
    left, right = max(xa, 0), min(xb, WIDTH - 1)
    for y in range(ya, yb + 1):
        if not (0 <= y < HEIGHT and left <= right):
            yield 0, xb - xa + 1
            continue
        yield 0, left - xa
        for x in range(left, right + 1):
            if bits[(x - xa) & 15]:
                plot(m, x, y, how)
            yield 1, 0
        yield 0, xb - right


class Graphics:
    """GPRINTのカーソルと、LINEの前の終わり(RAMの外に持つ)"""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """初めと、CLS・RUNのあと"""
        self.gx, self.gy = START
        self.last: tuple[int, int] = (0, 0)

    def save(self) -> list[int]:
        return [self.gx, self.gy, *self.last]

    def parse(self, d: object) -> tuple[int, int, tuple[int, int]] | None:
        """saveで書いたもの。読めないか、座標の範囲の外ならNone(壊れた状態のファイルで、
        LINEがいつまでも点を打ち続けないように)"""
        if not isinstance(d, list) or len(d) != 4:
            return None
        try:
            gx, gy, lx, ly = (int(v) for v in d)
        except (TypeError, ValueError, OverflowError):
            return None
        if not all(LOWEST <= v <= HIGHEST for v in (gx, gy, lx, ly)):
            return None
        return gx, gy, (lx, ly)

    def place(self, saved: tuple[int, int, tuple[int, int]] | None) -> None:
        """parseで読んだものに戻す(Noneなら初めの位置)"""
        if saved is None:
            self.reset()
        else:
            self.gx, self.gy, self.last = saved

"""PC-1261系の2行の液晶。字はASCII(5Chは¥)。PC-1350の4行の液晶(console.py)は、この
Screenと字の形を受け継ぐ"""

from ... import charset
from .. import editor, screen
from ..screen import INSERT_MARK, UNDERLINE
from . import font

# 液晶にない記号(ビットだけを立てる。GRADは207Cのビット2。machine.SYMBOLS_1261の註釈も参照)
HIDDEN = {"GRAD": (0x207C, 0x04)}
BLANK = frozenset({0x60})  # 液晶に何も描かない字(観察。PC-1350では`の形)
# 打っている行の挿入マークを液晶に出すときの番号。文字列の01h(PC-1350のCHR$ 1など)は空白で
# 出す(観察)
INSERT_CODE = 0x100


def marked(codes: list[int]) -> list[int]:
    """打っている行の液晶の字の並びの挿入マーク(01h)を、INSERT_CODEにする"""
    return [INSERT_CODE if c == editor.INSERT_MARK else c for c in codes]


def char(code: int) -> str:
    """文字コードの字(ASCIIと半角カナ。5Chは¥)。字でなければ空"""
    if code == 0x5C:
        return "¥"
    if 0x20 < code < 0x7F:
        return chr(code)
    if 0xA1 <= code <= 0xDF:
        return bytes([code]).decode("cp932")
    return ""


def glyph(code: int) -> bytes:
    """字の形(5列)。形のない字は空白"""
    if code == INSERT_CODE:
        return INSERT_MARK
    if code in BLANK:
        return bytes(5)
    ch = font.SAME.get(char(code), char(code))
    return font.glyph(ch) or charset.glyph(ch) if ch else bytes(5)


class Screen(screen.Screen):
    """2行の液晶。字は1行目の左から2行目の右へ並べる"""

    def __init__(self, m) -> None:
        super().__init__(m)
        self.width = m.model.cells
        self.cells = self.width * m.model.lines
        self.text = [0x20] * self.cells  # 出している字(カーソルを除く)

    def show(self, codes: list[int], cursor: int | None = None, shape: bytes = UNDERLINE) -> None:
        self.text = [codes[i] if i < len(codes) else 0x20 for i in range(self.cells)]
        for i in range(self.cells):
            self.put(i, shape if i == cursor else glyph(self.text[i]))
        self.m.lcd_dirty = True

    def lines(self, *rows: list[int] | bytes) -> None:
        """1行ずつ(rows[0]が1行目)出す。行の幅を越えた字は捨てる"""
        codes: list[int] = []
        for row in rows:
            codes += list(row[: self.width]) + [0x20] * (self.width - len(row[: self.width]))
        self.show(codes)

    def _where(self, name: str) -> tuple[int, int] | None:
        return HIDDEN.get(name) or super()._where(name)

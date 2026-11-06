"""PC-1251系の1行の液晶。字は本体の文字コードの並びで渡す"""

from ... import charset
from ...basictext import CHARS
from .. import screen
from ..screen import INSERT_MARK, UNDERLINE

# 文字コードの表(basictext.CHARS)にない字
EXTRA_CHARS = {0x10: "'", 0x4E: "_"}


def glyph(code: int) -> bytes:
    """本体の文字コードの字の形(5列)。形のない字は空白"""
    if code == 0x01:
        return INSERT_MARK
    ch = CHARS.get(code) or EXTRA_CHARS.get(code)
    return charset.glyph(ch) if ch else bytes(5)


class Screen(screen.Screen):
    def __init__(self, m) -> None:
        super().__init__(m)
        self.cells = self.width = m.model.cells

    def show(self, codes: list[int], cursor: int | None = None, shape: bytes = UNDERLINE) -> None:
        for i in range(self.cells):
            self.put(i, shape if i == cursor else glyph(codes[i]) if i < len(codes) else bytes(5))
        self.m.lcd_dirty = True

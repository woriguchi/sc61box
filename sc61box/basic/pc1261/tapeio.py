"""PC-1261系とPC-1350のカセットの命令。テープの形はcassette.py"""

from .. import tapeio, timing
from . import cassette, tokens
from .screen import glyph

_CODE = {name: code for code, name in tokens.KEYWORDS.items()}


class TapeIO(tapeio.TapeIO):
    FORMAT = cassette
    T_CHAIN = _CODE["CHAIN"]

    def _show_found(self) -> None:
        """2行目の右端に*を出す(1行目は打った行とカーソルのまま。観察)"""
        screen = self.basic.lcd
        screen.text[-1] = self.basic.CODES["*"]
        screen.put(screen.cells - 1, glyph(screen.text[-1]))
        self.m.lcd_dirty = True


class TapeIO1350(TapeIO):
    TAIL_ONES = 9  # 最後のバイトのあと(BRKで止めたときも)の1が、PC-1261より9つ多い(観察)
    M_START = timing.ms(130.0)  # CSAVE Mで、音を出し始めるまでに余分にかかる(観察)
    # 送り始め(初めの1の前)と送り終えたあと(BRKで止めたときも)に、Cポートのビット4だけを
    # 36ms立てる(観察)
    START_HOLD = END_HOLD = (1, timing.ms(36.0))

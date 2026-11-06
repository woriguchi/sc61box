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
    TAIL_ONES = 9  # 最後のバイトのあとの1が、PC-1261より9つ多い(観察)
    M_START = timing.ms(130.0)  # CSAVE Mで、音を出し始めるまでに余分にかかる(観察)
    END_HOLD = (1, timing.ms(36.0))  # 送り終えると、Cポートのビット4だけを36ms立てる(観察)
    BIT_PERIOD = cassette.BIT * 1.0042  # 1ビットがPC-1261より0.4%長い(観察)

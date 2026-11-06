"""PC-1261系とPC-1350の打っている行。字はASCIIで、比較の演算子は字のまま並ぶ。カナはRAMでは
FEhのあとに字のコードを置く2バイトで持ち(観察: ｱは「FE B1」)、単位では100h+字のコードにする"""

from .. import editor
from ..editor import WIDE

KANA_MARK = 0xFE


def units_of(data) -> list[int]:
    out: list[int] = []
    it = iter(data)
    for c in it:
        if c == KANA_MARK:
            c = WIDE + next(it, 0x20)
        out.append(c)
    return out


def bytes_of(units) -> bytes:
    out = bytearray()
    for u in units:
        out += bytes([KANA_MARK, u - WIDE]) if u >= WIDE else bytes([u])
    return bytes(out)


class Editor(editor.Editor):
    SPACE, TIGHT, TOKEN = 0x20, (), 0x80
    units_of = staticmethod(units_of)
    bytes_of = staticmethod(bytes_of)

    def __init__(self, units=(), cur=None, head=0, sep=None, glued=False) -> None:
        units = list(units)
        if cur is not None:  # バイトの位置を単位の位置にする
            cur = len(units_of(units[:cur]))
        super().__init__(units_of(units), cur, head, sep, glued)

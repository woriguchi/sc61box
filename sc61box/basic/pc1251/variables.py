"""PC-1251系のRAMの中の変数"""

from .. import variables
from ..variables import Array


class Variables(variables.Variables):
    """プログラムの頭の番地を、プログラムの終わりのポインタの前(C6E1h)にも置く。ROMのある
    本体は、この番地が違うとRAMを初めの形にする(観察)"""

    FIXED_TOP = 0xC6A0
    ARRAY_PTR = 0xC6FC
    ARRAY_TOP = 0xC6A0 - 8 * 26
    EXTRA = 0x51
    EXTRA_KEY = 0x51
    HEAD = 6
    DIM_FIXED = True

    def initialize(self, m) -> None:
        super().initialize(m)
        variables.set_word(m, m.model.prog_end_ptr - 2, m.model.prog_start)

    def _header(
        self, name: int, string: bool, length: int, last: int, first: int, size: int
    ) -> bytes:
        """名前の文字コード(文字列なら+80h)、残りのバイト数(上位、下位)、添字の最大2つ、
        1要素のバイト数"""
        return bytes(
            [name | (0x80 if string else 0), length >> 8, length & 0xFF, last, first, size]
        )

    def _array_at(self, mem, a: int) -> Array:
        length = mem[a + 1] << 8 | mem[a + 2]
        return Array(
            a, mem[a] & 0x7F, bool(mem[a] & 0x80), mem[a + 3], mem[a + 4], mem[a + 5], length
        )


# PC-1251系の置き方と、そのメソッドをモジュールの関数として使う名前
PC1251 = Variables()
FIXED_TOP, ARRAY_PTR, ARRAY_TOP, EXTRA = (
    PC1251.FIXED_TOP, PC1251.ARRAY_PTR, PC1251.ARRAY_TOP, PC1251.EXTRA
)  # fmt: skip
fixed_addr = PC1251.fixed_addr
initialize = PC1251.initialize
read = PC1251.read
write = PC1251.write
clear = PC1251.clear
clear_arrays = PC1251.clear_arrays
arrays = PC1251.arrays
find = PC1251.find
dim = PC1251.dim
element = PC1251.element

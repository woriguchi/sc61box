"""PC-1251系のRAMの中のプログラム

行は「E0h+百の位、十と一の位のBCD、中身、00h」で、行番号の順に並ぶ。
"""

from .. import program
from . import variables


class Program(program.Program):
    LAST_LINE = 999
    VARS = variables.PC1251

    def number_at(self, m, a: int) -> int | None:
        hi = m.mem[a]
        if not 0xE0 <= hi <= 0xE9:
            return None
        lo = m.mem[a + 1]
        return (hi & 0x0F) * 100 + (lo >> 4) * 10 + (lo & 0x0F)

    def next_line(self, m, a: int) -> int:
        a += 2
        while m.mem[a] != 0x00:
            a += 1
        return a + 1

    def body(self, m, a: int) -> bytes:
        return bytes(m.mem[a + 2 : self.next_line(m, a) - 1])

    def _line(self, n: int, content: bytes) -> bytes:
        return bytes([0xE0 | n // 100, (n // 10 % 10) << 4 | n % 10]) + content + b"\x00"


# PC-1251系の置き方と、そのメソッドをモジュールの関数として使う名前
PC1251 = Program()
LAST_LINE = PC1251.LAST_LINE
first = PC1251.first
end = PC1251.end
number_at = PC1251.number_at
next_line = PC1251.next_line
lines = PC1251.lines
body = PC1251.body
at_or_after = PC1251.at_or_after
store = PC1251.store
clear = PC1251.clear
put = PC1251.put

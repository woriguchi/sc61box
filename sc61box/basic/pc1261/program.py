"""PC-1261系とPC-1350のRAMの中のプログラム

行は「行番号の上位、下位、長さ、中身、0Dh」で、行番号の順に並ぶ。長さは中身と0Dhのバイト数。

MERGEは、いまのプログラムの終わりのFFを区切りとして残し、そのあとに読んだ行を置いて、新しい
プログラムにする。6619h(PC-1350は6F05h)に、いまのプログラムの頭(区切りのFF)の番地を置く。
読んだ行の最初の行番号が前のプログラムの最後の行番号より大きければ、>を出す前に区切りを
除いて1つにする。LIST、行の登録、RUNなどはいまのプログラムに対して行い、ラベルはすべての
プログラムから探す。行番号は、実行している行のプログラムから探す。CSAVEはすべてのプログラムを
区切りごと送り、CLOADは区切りごと戻して、最後の区切りをいまのプログラムの頭にする(観察)
"""

from .. import program
from ..variables import word
from . import variables


class Program(program.Program):
    START_PTR = 0x6619  # いまのプログラムの頭のFFの番地
    LAST_LINE = 65279  # 65280からはERROR 4(観察)
    VARS = variables.PC1261

    def start(self, m) -> int:
        """いまのプログラムの頭のFFの番地"""
        a, base = word(m, self.START_PTR), m.prog_base()
        return a if base <= a <= self.end(m) and m.mem[a] == 0xFF else base

    def set_start(self, m, a: int) -> None:
        self.VARS.set_pointer(m, self.START_PTR, a)

    def set_base(self, m, a: int) -> None:
        """プログラムの場所の頭をaにして、プログラムを空にする(EQU#)。ROMは頭の番地を
        661Bhと66E1hにも置く(観察)"""
        m.mem[a] = m.mem[a + 1] = 0xFF
        for ptr in (self.START_PTR, 0x661B, *variables.PC1261.BASE_PTRS):
            self.VARS.set_pointer(m, ptr, a)
        self.VARS.set_end(m, a + 1)

    def first(self, m) -> int:
        return self.start(m) + 1

    def heads(self, m) -> list[int]:
        """それぞれのプログラムの最初の行の番地"""
        out = [self.top(m)]
        a, stop = self.top(m), self.end(m)
        while a < stop:
            if m.mem[a] == 0xFF:
                a += 1
                out.append(a)
            else:
                a = self.next_line(m, a)
        return out

    def block_first(self, m, a: int) -> int:
        if not self.top(m) <= a <= self.end(m):
            return self.first(m)
        return max(h for h in self.heads(m) if h <= a)

    def all_lines(self, m) -> list[tuple[int, int]]:
        return [line for h in self.heads(m) for line in self.lines(m, h)]

    def clear(self, m) -> None:
        super().clear(m)
        self.set_start(m, m.prog_base())

    def merge_at(self, m) -> int:
        """区切りのFFを残し、そのあとに置く(いまのプログラムに行がなければ、終わりのFFから)"""
        return self.end(m) + (1 if self.lines(m) else 0)

    def loaded(self, m, at: int, data: bytes) -> None:
        """CLOADなら初めの区切りを、MERGEなら読んだ行の前の区切りを頭にする。読んだ行に区切りが
        あれば、最後の区切りを頭にする"""
        self.set_start(m, m.prog_base() if at == self.top(m) else at - 1)
        i = 0
        while i + 2 < len(data) or i < len(data) and data[i] == 0xFF:
            if data[i] == 0xFF:
                self.set_start(m, at + i)
                i += 1
            else:
                i += 3 + data[i + 2]

    def merged(self, m) -> None:
        """読んだ行の最初の行番号が、前のプログラムの最後の行番号より大きければ(前のプログラムに
        行がなくても)、区切りを除いて1つのプログラムにする"""
        sep = self.start(m)
        if sep < self.top(m):
            return
        head = self.block_first(m, sep)
        before, after = self.lines(m, head), self.lines(m)
        if after and before and after[0][0] <= before[-1][0]:
            return
        end = self.end(m)
        m.mem[sep:end] = m.mem[sep + 1 : end + 1]
        self.VARS.set_end(m, end - 1)
        self.set_start(m, head - 1)

    def number_at(self, m, a: int) -> int | None:
        hi = m.mem[a]
        if hi == 0xFF:
            return None
        return hi << 8 | m.mem[a + 1]

    def next_line(self, m, a: int) -> int:
        return a + 3 + m.mem[a + 2]

    def body(self, m, a: int) -> bytes:
        return bytes(m.mem[a + 3 : a + 2 + m.mem[a + 2]])

    def _line(self, n: int, content: bytes) -> bytes:
        return bytes([n >> 8, n & 0xFF, len(content) + 1]) + content + b"\x0d"


class Program1350(Program):
    """PC-1350。いまのプログラムの頭は6F05h。6F01hはいつもプログラムの領域の頭で、MERGEでも
    変わらない(観察)"""

    START_PTR = 0x6F05
    VARS = variables.PC1350


PC1261 = Program()
PC1350 = Program1350()

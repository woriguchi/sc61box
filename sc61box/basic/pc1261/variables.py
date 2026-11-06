"""PC-1261系とPC-1350のRAMの中の変数(番地はPC-1261系。PC-1350はVariables1350)

固定の変数(1字の名前)はPC-1251系と同じ8バイトの形。配列のヘッダは7バイトで、名前の字、
2つ目のバイト、残りのバイト数(上位、下位)、添字の最大2つ、1要素のバイト数。2つ目のバイトは、
名前が1字の配列なら種類(数の配列は80h、文字列の配列はA0h)、2字の名前なら2字目に、数の
変数は0、文字列の変数は40h、数の配列は80h、文字列の配列はC0hを足したもの。2字の名前の変数は、
添字の最大を0と0にしたヘッダを付けて配列と同じ所に置き、数は8バイト、文字列は16字(頭に
マークF5hは置かない)。添字が26を越えるA(n)の続きは、名前40h・2つ目のバイト00hの配列にする。
DIMで作ったAの配列があれば、A(n)はその要素になる。

名前は、1字目の文字コードと、2字目の文字コード×100h(1字なら0)を足した数で持つ。
"""

from decimal import Decimal
from typing import overload

from ...machine import PC1251
from .. import variables
from ..errors import BasicError
from ..variables import Array, Ref

KINDS = {False: 0x80, True: 0xA0}  # 名前が1字の配列の種類
ADD = {(False, True): 0x00, (True, True): 0x40, (False, False): 0x80, (True, False): 0xC0}
EXTRA_MARK = 0x40  # A(n)の続きの配列の名前の字(観察)
STRING_SIZE = 16  # 2字の名前の文字列の変数に入る字の数(観察)


def _second(b: int) -> tuple[int, bool, bool] | None:
    """2つ目のバイトから(2字目, 文字列か, 2字の名前の変数か)。名前が1字ならNone"""
    for (string, simple), add in ADD.items():
        c = (b - add) & 0xFF
        if 0x30 <= c <= 0x39 or 0x41 <= c <= 0x5A:
            return c, string, simple
    return None


class Variables(variables.Variables):
    FIXED_TOP = 0x65D0  # Aは65C8h(観察)
    ARRAY_PTR = 0x66FC
    ARRAY_TOP = 0x65D0 - 8 * 26
    EXTRA = 0x41
    EXTRA_KEY = 0x140  # 続きの配列は、どの名前とも重ならない名前で探す
    HEAD = 7
    # プログラムの場所の頭(EQU#で動く)を置くポインタ(観察)
    BASE_PTRS: tuple[int, ...] = (PC1251.PROG_BASE_PTR,)

    def initialize(self, m) -> None:
        """RAMがおかしくて作り直すときは、プログラムの場所の頭も機種の既定に戻す(EQU#0)"""
        start = m.prog_base()
        end, bottom = variables.word(m, m.model.prog_end_ptr), variables.word(m, self.ARRAY_PTR)
        intact = start < end < bottom <= self.ARRAY_TOP and m.mem[end] == 0xFF
        if not intact:
            for ptr in self.BASE_PTRS:
                self.set_pointer(m, ptr, m.model.prog_start)
        super().initialize(m)
        for ptr in self.BASE_PTRS:
            self.set_pointer(m, ptr, m.prog_base())

    def _header(self, name: int, string: bool, length: int, last: int, first: int, size: int):
        return self._head(name, string, False, length, last, first, size)

    def _head(self, name, string, simple, length, last, first, size) -> bytes:
        c1, c2 = name & 0xFF, name >> 8
        if name == self.EXTRA_KEY:
            head = [EXTRA_MARK, 0]
        elif c2:
            head = [c1, (c2 + ADD[string, simple]) & 0xFF]
        else:
            head = [c1, KINDS[string]]
        return bytes(head + [length >> 8, length & 0xFF, last, first, size])

    def _array_at(self, mem, a: int) -> Array:
        name, kind = mem[a], mem[a + 1]
        string, simple = kind == KINDS[True], False
        if name == EXTRA_MARK and kind == 0:
            name = self.EXTRA_KEY
        elif (second := _second(kind)) is not None:
            c2, string, simple = second
            name |= c2 << 8
        length = mem[a + 2] << 8 | mem[a + 3]
        return Array(a, name, string, mem[a + 4], mem[a + 5], mem[a + 6], length, 7, simple)

    def _fixed_a(self, m, string: bool) -> bool:
        return self.find(m, self.EXTRA, string) is None

    def clear(self, m) -> None:
        """固定の変数を0にし、配列と2字の名前の変数をなくす(配列の場所の中身は残る。観察)"""
        m.mem[self.ARRAY_TOP : self.FIXED_TOP] = bytes(self.FIXED_TOP - self.ARRAY_TOP)
        self.set_bottom(m, self.ARRAY_TOP)

    def write(self, m, ref: Ref, value: Decimal | bytes) -> Decimal | bytes:
        """文字列は、入る字の数までと、短ければ終わりの00hだけを書く(その先は前のまま。観察)"""
        if not ref.string:
            return super().write(m, ref, value)
        if not isinstance(value, bytes):
            raise BasicError(9)
        size = variables.STRING_MAX if ref.fixed else ref.size
        s = value[:size]
        if s[-1:] == b"\xfe":
            s = s[:-1]  # カナの2バイトの途中では切らない
        at = ref.addr + 1 if ref.fixed else ref.addr
        if ref.fixed:
            m.mem[ref.addr] = variables.STRING_MARK
        m.mem[at : at + len(s)] = s
        if len(s) < size:
            m.mem[at + len(s)] = 0
        return s

    @overload
    def simple(self, m, name: int, string: bool) -> Ref: ...
    @overload
    def simple(self, m, name: int, string: bool, create: bool) -> Ref | None: ...

    def simple(self, m, name: int, string: bool, create: bool = True) -> Ref | None:
        """2字の名前の変数の場所。なければ、createならいちばん下に作る(なければNone)"""
        for arr in self.arrays(m):
            if arr.simple and arr.name == name and arr.string == string:
                return Ref(arr.data, string, False, arr.size)
        if not create:
            return None
        size = STRING_SIZE if string else 8
        length = 3 + size
        bottom = variables.word(m, self.ARRAY_PTR) - (self.HEAD - 3) - length
        if bottom <= variables.word(m, m.model.prog_end_ptr):
            raise BasicError(6)
        head = self._head(name, string, True, length, 0, 0, size)
        m.mem[bottom : bottom + self.HEAD + size] = head + bytes(size)
        self.set_bottom(m, bottom)
        return Ref(bottom + self.HEAD, string, False, size)


class Variables1350(Variables):
    """PC-1350。ポインタは6F00hからの9バイト(RAMの大きさを示すバイト、プログラムの領域の頭、
    終わり、いまのプログラムの頭、配列の下端)で、続いてパスワード(6F09h)と、プログラムを
    保護のフラグ(6F14h)がある。6F00h〜6F29hのコピーをRAMの頭+6にも置く(RAMカードを
    差すとRAMの頭は4000hか2000h)。RAMの頭の6バイトは10h〜15hで、ROMのある本体は、この6バイトが
    違うとRAMを初期化する。固定の変数と配列の場所はRAMカードによらない(観察)"""

    BASE_PTRS = ()  # PC-1350にEQU#はない(頭はPOINTERSの中)

    FIXED_TOP = 0x6D00  # Aは6CF8h(観察)
    ARRAY_PTR = 0x6F07
    ARRAY_TOP = 0x6D00 - 8 * 26
    POINTERS = 0x6F00
    SIZE_MARK = {0x6000: 0x08, 0x4000: 0x04, 0x2000: 0x02}  # RAMの頭ごとの、6F00hの値(観察)
    HEAD_MARK = bytes(range(0x10, 0x16))

    def copy_of(self, m, a: int) -> int | None:
        if self.POINTERS <= a < self.POINTERS + 0x2A:
            return m.model.ram[0] + 6 + a - self.POINTERS
        return None

    def initialize(self, m) -> None:
        super().initialize(m)
        top = m.model.ram[0]
        m.mem[top : top + len(self.HEAD_MARK)] = self.HEAD_MARK
        mark = self.SIZE_MARK.get(top, 0)
        m.mem[self.POINTERS] = m.mem[top + 6] = mark
        for a in (self.POINTERS + 1, self.POINTERS + 5):
            if variables.word(m, a) != m.model.prog_start:
                self.set_pointer(m, a, m.model.prog_start)


PC1261 = Variables()
PC1350 = Variables1350()

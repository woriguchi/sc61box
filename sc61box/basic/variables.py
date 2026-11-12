"""RAMの中の変数(系統によらない部分)

固定の変数(A〜Z)は8バイトずつ並び、配列はその下へ取る。番地と配列のヘッダの形は、系統ごとの
子クラス(pc1251/variables.py、pc1261/variables.py)が決める。
"""

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from ..number import compute, cut, get_num, put_num
from .errors import BasicError

STRING_MARK = 0xF5
STRING_MAX = 7  # 固定の変数に入る字の数


def _put(m, at: int, data: bytes) -> None:
    """変数の値を、本体の番地の割り当て(ミラーなど)のとおりに書く"""
    for i, v in enumerate(data):
        m.write(at + i & 0xFFFF, v)


def word(m, a: int) -> int:
    return m.mem[a] | m.mem[a + 1] << 8


def set_word(m, a: int, v: int) -> None:
    m.mem[a], m.mem[a + 1] = v & 0xFF, v >> 8


@dataclass(frozen=True)
class Ref:
    """変数の場所。fixedは固定の変数の形(文字列はマークF5hのあとに7字)。sizeは配列の文字列の
    字の数"""

    addr: int
    string: bool
    fixed: bool = True
    size: int = 8


@dataclass(frozen=True)
class Array:
    addr: int  # ヘッダの番地
    name: int
    string: bool
    last: int  # ヘッダの3バイト目(1次元の添字の最大、2次元なら2つ目の添字の最大)
    first: int  # ヘッダの4バイト目(2次元の1つ目の添字の最大。1次元なら0)
    size: int
    length: int = 0  # ヘッダの残りのバイト数(添字の最大の所から配列の終わりまで)
    head: int = 6  # ヘッダのバイト数
    simple: bool = False  # 配列ではなく、2字の名前の変数(PC-1261系とPC-1350)

    @property
    def data(self) -> int:
        return self.addr + self.head

    @property
    def end(self) -> int:
        """配列の次の番地"""
        return self.addr + self.head - 3 + self.length


class Variables:
    """変数の置き方。番地と配列のヘッダの形は子クラスのクラスの属性とメソッドに持つ"""

    FIXED_TOP: int  # 固定の変数のn番目(A=1)はFIXED_TOP−8n
    ARRAY_PTR: int  # いちばん下の配列の先頭の番地(下位、上位)
    ARRAY_TOP: int  # 配列はここから下へ取る
    EXTRA: int  # 添字が26を越えるA(n)の場所は、名前Aの配列として持つ
    EXTRA_KEY: int  # A(n)の続きの配列を探すときの名前
    HEAD: int  # 配列のヘッダのバイト数
    Ref = Ref
    word = staticmethod(word)
    set_word = staticmethod(set_word)

    def fixed_addr(self, n: int) -> int:
        return self.FIXED_TOP - 8 * n

    def copy_of(self, m, a: int) -> int | None:
        """番地aに置くポインタのコピーを置く番地(なければNone。PC-1350はRAMの頭にも置く)"""
        return None

    def set_pointer(self, m, a: int, v: int) -> None:
        """番地aのポインタ(下位、上位)をvにする。コピーがあればコピーも"""
        set_word(m, a, v)
        copy = self.copy_of(m, a)
        if copy is not None:
            set_word(m, copy, v)

    def set_bottom(self, m, a: int) -> None:
        """配列のいちばん下の番地"""
        self.set_pointer(m, self.ARRAY_PTR, a)

    def set_end(self, m, a: int) -> None:
        """プログラムの終わりのFFの番地"""
        self.set_pointer(m, m.model.prog_end_ptr, a)

    def _header(
        self, name: int, string: bool, length: int, last: int, first: int, size: int
    ) -> bytes:
        """配列のヘッダ。lengthは残りのバイト数、last・firstは添字の最大(1次元なら最大と0、
        2次元なら2つ目の最大と1つ目の最大)、sizeは1要素のバイト数"""
        raise NotImplementedError

    def _array_at(self, mem, a: int) -> "Array":
        """番地aのヘッダの配列"""
        raise NotImplementedError

    def initialize(self, m) -> None:
        """プログラムと変数の場所を、何もない形にする。RAMに前の内容が正しく
        残っていれば(終わりのFFと配列の下端が範囲にあれば)何もしない"""
        start = m.prog_base()
        end, bottom = word(m, m.model.prog_end_ptr), word(m, self.ARRAY_PTR)
        if m.mem[start] == 0xFF and start < end < bottom <= self.ARRAY_TOP and m.mem[end] == 0xFF:
            return
        m.mem[start] = m.mem[start + 1] = 0xFF
        self.set_end(m, start + 1)
        self.set_bottom(m, self.ARRAY_TOP)

    def read(self, m, ref: Ref) -> Decimal | bytes:
        """変数の値。数の場所の文字列や、文字列の場所の数はエラー9(8バイトとも0なら0か空)"""
        data = bytes(m.read(ref.addr + i & 0xFFFF) for i in range(ref.size))
        if not ref.fixed:
            return data.split(b"\0", 1)[0] if ref.string else get_num(data, 0)
        if ref.string:
            if data[0] != STRING_MARK:
                if any(data):
                    raise BasicError(9)
                return b""
            return data[1:].split(b"\0", 1)[0]
        if data[0] == STRING_MARK:
            raise BasicError(9)
        return get_num(data, 0)

    def write(self, m, ref: Ref, value: Decimal | bytes) -> Decimal | bytes:
        """変数に入れ、入れた値を返す(数は10桁に四捨五入、文字列は入る字の数まで)"""
        if ref.string:
            if not isinstance(value, bytes):
                raise BasicError(9)
            if ref.fixed:
                s = value[:STRING_MAX]
                _put(m, ref.addr, bytes([STRING_MARK]) + s + bytes(STRING_MAX - len(s)))
            else:
                s = value[: ref.size]
                _put(m, ref.addr, s + bytes(ref.size - len(s)))
            return s
        if not isinstance(value, Decimal):
            raise BasicError(9)
        stored = compute(lambda: cut(value, 10, ROUND_HALF_UP))
        if stored is None:
            raise BasicError(2)
        buf = bytearray(8)
        put_num(buf, 0, stored)
        _put(m, ref.addr, bytes(buf))
        return stored

    def clear(self, m) -> None:
        """固定の変数を0にし、配列を消す"""
        lo = min(word(m, self.ARRAY_PTR), self.ARRAY_TOP)
        m.mem[lo : self.FIXED_TOP] = bytes(self.FIXED_TOP - lo)
        self.set_bottom(m, self.ARRAY_TOP)

    def clear_arrays(self, m) -> None:
        """配列だけを消す(RUN)"""
        lo = word(m, self.ARRAY_PTR)
        if lo < self.ARRAY_TOP:
            m.mem[lo : self.ARRAY_TOP] = bytes(self.ARRAY_TOP - lo)
        self.set_bottom(m, self.ARRAY_TOP)

    def arrays(self, m) -> Iterator[Array]:
        a = word(m, self.ARRAY_PTR)
        while a < self.ARRAY_TOP:
            arr = self._array_at(m.mem, a)
            yield arr
            a = arr.end

    def find(self, m, name: int, string: bool) -> Array | None:
        for arr in self.arrays(m):
            if arr.name == name and arr.string == string and not arr.simple:
                return arr
        return None

    def dim(self, m, name: int, string: bool, dims: list[int], size: int) -> None:
        """DIM。作ってある配列、添字の最大が255を越える、文字列の長さが80を越えるとERROR 3、
        場所が足りなければERROR 6(観察)"""
        if (
            self.find(m, name, string)
            or any(not 0 <= d <= 255 for d in dims)
            or not 1 <= size <= 80
        ):
            raise BasicError(3)
        count = (dims[0] + 1) * (dims[1] + 1 if len(dims) == 2 else 1)
        length = 3 + count * size
        bottom = word(m, self.ARRAY_PTR) - (self.HEAD - 3) - length
        if bottom <= word(m, m.model.prog_end_ptr):
            raise BasicError(6)
        last, first = (dims[1], dims[0]) if len(dims) == 2 else (dims[0], 0)
        head = self._header(name, string, length, last, first, size)
        m.mem[bottom : bottom + self.HEAD - 3 + length] = head + bytes(length - 3)
        self.set_bottom(m, bottom)

    def fixed(self, m, name: int, string: bool, subs: list[int]) -> bool:
        """A(n)・A$(n)の固定の変数の続きか"""
        return name == self.EXTRA and len(subs) == 1 and self._fixed_a(m, string)

    def element(self, m, name: int, string: bool, subs: list[int], create: bool) -> Ref:
        """配列の要素の場所。A(n)・A$(n)は固定の変数の続き"""
        if self.fixed(m, name, string, subs):
            return self._fixed_element(m, subs[0], string, create)
        arr = self.find(m, name, string)
        if arr is None:
            raise BasicError(3)
        if len(subs) == 1:
            i, j = 0, subs[0]
            if arr.first:
                raise BasicError(3)
        else:
            i, j = subs
        if not (0 <= i <= arr.first and 0 <= j <= arr.last):
            raise BasicError(3)
        index = i * (arr.last + 1) + j
        return Ref(arr.data + index * arr.size, string, False, arr.size)

    def _fixed_a(self, m, string: bool) -> bool:
        """A(n)を固定の変数の続きとして扱うか"""
        return True

    def _fixed_element(self, m, n: int, string: bool, create: bool) -> Ref:
        """A(n)・A$(n)の場所。nが26を越えるときは、名前Aの配列(ヘッダの添字の最大は0と0)を
        いちばん下に作って続きにする。A(27)が配列の上端の8バイトで、そこから下へ並ぶ。配列が
        いちばん下にあれば下へ広げ、ほかの配列がその下にあればERROR 3(観察)"""
        if n < 1:
            raise BasicError(3)
        if n <= 26:
            return Ref(self.fixed_addr(n), string)
        extra = self.find(m, self.EXTRA_KEY, False)
        bottom_now = word(m, self.ARRAY_PTR)
        top = extra.end if extra else bottom_now
        have = (extra.length - 3) // 8 if extra else 0
        if n - 26 > have:
            if not create or (extra is not None and extra.addr != bottom_now):
                raise BasicError(3)
            length = 3 + (n - 26) * 8
            bottom = top - (self.HEAD - 3) - length
            if bottom <= word(m, m.model.prog_end_ptr):
                raise BasicError(6)
            head = self._header(self.EXTRA_KEY, False, length, 0, 0, 8)
            m.mem[bottom : top - 8 * have] = head + bytes(top - 8 * have - bottom - self.HEAD)
            self.set_bottom(m, bottom)
        return Ref(top - 8 * (n - 26), string)

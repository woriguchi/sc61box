"""RAMの中のプログラム(系統によらない部分)

行は行番号の順に並び、終わりにFFを置く。1行の形(行番号と終わりのマーカー)は、系統ごとの子クラス
(pc1251/program.py、pc1261/program.py)が決める。PC-1261系とPC-1350は、MERGEで読んだ行をFFで区切って別の
プログラムとして置くことがある(pc1261/program.py)。
"""

from . import variables
from .errors import BasicError
from .variables import word


class Program:
    """プログラムの置き方。行の形は子クラスのメソッドに持つ"""

    LAST_LINE: int  # いちばん大きい行番号
    VARS: variables.Variables  # 変数の置き方(場所が足りるかを見るのに使う)

    def top(self, m) -> int:
        """RAMのプログラムの場所の、最初の行の番地(CLOADはここから置く)"""
        return m.prog_base() + 1

    def first(self, m) -> int:
        """いまのプログラムの最初の行の番地(行がなければ終わりのFFの番地)"""
        return self.top(m)

    def block_first(self, m, a: int) -> int:
        """番地aの行を含むプログラムの最初の行の番地"""
        return self.first(m)

    def end(self, m) -> int:
        """終わりのFFの番地"""
        return word(m, m.model.prog_end_ptr)

    def number_at(self, m, a: int) -> int | None:
        """番地aの行の番号(aが終わりのFFならNone)"""
        raise NotImplementedError

    def next_line(self, m, a: int) -> int:
        """番地aの行の次の行の番地"""
        raise NotImplementedError

    def lines(self, m, first: int | None = None) -> list[tuple[int, int]]:
        """いまのプログラム(firstを書けば、その番地から始まるプログラム)の(行番号, 番地)の
        並び"""
        out = []
        a, stop = self.first(m) if first is None else first, self.end(m)
        while a < stop:
            n = self.number_at(m, a)
            if n is None:
                break
            out.append((n, a))
            a = self.next_line(m, a)
        return out

    def all_lines(self, m) -> list[tuple[int, int]]:
        """RAMのすべてのプログラムの(行番号, 番地)の並び"""
        return self.lines(m)

    def find_label(self, m, mark: bytes) -> tuple[int, int] | None:
        """中身がmark(「"ラベル"」)で始まる最初の行の(行番号, 番地)。すべてのプログラムから
        探す"""
        for n, a in self.all_lines(m):
            if self.body(m, a).startswith(mark):
                return n, a
        return None

    def loaded(self, m, at: int, data: bytes) -> None:
        """CLOADとMERGEで、番地atから行の並びdataを置いたあと"""

    def separated(self, m, at: int, data: bytes) -> None:
        """CLOADとMERGEを終えて、>を出す前(読んだ行の並びdataを番地atから置いた)"""

    def merge_at(self, m) -> int:
        """MERGEで、読んだ行を置き始める番地"""
        return self.end(m)

    def merged(self, m, at: int) -> None:
        """MERGEを終えて、>を出す前(atは読んだ行を置き始めた番地)"""

    def body(self, m, a: int) -> bytes:
        """番地aの行の中身(行番号と終わりのマーカーを除く)"""
        raise NotImplementedError

    def at_or_after(self, m, n: int) -> tuple[int, int] | None:
        """番号n以上の最初の行の(番号, 番地)"""
        for number, a in self.lines(m):
            if number >= n:
                return number, a
        return None

    def _move(self, m, at: int, delta: int) -> None:
        """番地atから終わりのFFまでをdeltaバイトずらし、終わりの番地を直す"""
        stop = self.end(m)
        data = bytes(m.mem[at : stop + 1])
        m.mem[at + delta : at + delta + len(data)] = data
        self.VARS.set_end(m, stop + delta)

    def _line(self, n: int, content: bytes) -> bytes:
        """行番号nと中身contentの行のバイトの並び"""
        raise NotImplementedError

    def store(self, m, n: int, content: bytes) -> None:
        """行nを中身contentで登録する(同じ番号があれば置き換える)。contentが空なら消す"""
        if not 1 <= n <= self.LAST_LINE:
            raise BasicError(4)
        found = self.at_or_after(m, n)
        at = found[1] if found else self.end(m)
        old = self.next_line(m, at) - at if found and found[0] == n else 0
        if not content:
            if old:
                self._move(m, at + old, -old)
            return
        data = self._line(n, content)
        delta = len(data) - old
        if self.end(m) + delta >= word(m, self.VARS.ARRAY_PTR):
            raise BasicError(6)
        self._move(m, at + old, delta)
        m.mem[at : at + len(data)] = data

    def clear(self, m) -> None:
        """NEW: プログラムと変数を消す"""
        start = m.prog_base()
        m.mem[start] = m.mem[start + 1] = 0xFF
        self.VARS.set_end(m, start + 1)
        self.VARS.clear(m)

    def put(self, m, at: int, data: bytes) -> None:
        """CLOADとMERGE: 番地atから行の並びdataを置き、終わりにFFを置く。入りきらなければ
        ERROR 6"""
        stop = at + len(data)
        if stop >= word(m, self.VARS.ARRAY_PTR):
            raise BasicError(6)
        m.mem[at:stop] = data
        m.mem[stop] = 0xFF
        self.VARS.set_end(m, stop)

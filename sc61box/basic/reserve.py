"""リザーブ(RSVモードで、SHIFTのあとのキーに登録する字の並び)の置き方(系統によらない部分)

決まった48バイトに、登録した順に「マーク、中身」を並べ、残りを00hで埋める。マークはキーごとに
決まった1バイト。中身は、打った行を中間コードにしたもの。置く領域とマークは系統ごとに違う
(pc1251/reserve.py、pc1261/reserve.py)。
"""

from collections.abc import Callable
from typing import Any

from .errors import BasicError

SIZE = 0x30
KEYS = "ASDFGHJKL=ZXCVBNM"  # リザーブのキー(machine.KEYSの名前。ほかにSPC)


class Reserve:
    """start(m)は置く領域の頭の番地、marksはキーの名前とマーク"""

    KEYS = KEYS

    def __init__(self, start: Callable[[Any], int], marks: dict[str, int]) -> None:
        self.start = start
        self.MARKS = marks

    def area(self, m) -> tuple[int, int]:
        start = self.start(m)
        return start, start + SIZE

    def entries(self, m) -> list[tuple[str, bytes]]:
        """登録してある(キー, 中身)を、置いてある順に"""
        lo, hi = self.area(m)
        keys = {mark: k for k, mark in self.MARKS.items()}
        out: list[tuple[str, bytes]] = []
        a = lo
        while a < hi and m.mem[a] in keys:
            b = a + 1
            while b < hi and m.mem[b] and m.mem[b] not in keys:
                b += 1
            out.append((keys[m.mem[a]], bytes(m.mem[a + 1 : b])))
            a = b
        return out

    def get(self, m, key: str) -> bytes | None:
        return dict(self.entries(m)).get(key)

    def store(self, m, key: str, content: bytes) -> None:
        """keyに中身を登録する(前の中身は消し、終わりに足す)。中身が空なら消すだけ。
        入りきらなければERROR 6で、前のまま(観察)"""
        rest = [(k, c) for k, c in self.entries(m) if k != key]
        if content:
            rest.append((key, content))
        data = b"".join(bytes([self.MARKS[k]]) + c for k, c in rest)
        if len(data) > SIZE:
            raise BasicError(6)
        lo, hi = self.area(m)
        m.mem[lo:hi] = data + bytes(SIZE - len(data))

"""パスワード(PASS)の置き方(系統によらない部分)

パスワードは、決まった番地にマークF5hを置き、続けて字を7字まで並べる(7字より短ければ、あとに
00h)。プログラムを保護しているかは、決まった番地のビット5のフラグで表す。番地は系統ごとに違う
(pc1251/password.py、pc1261/password.py)。
"""

from . import program
from .errors import BasicError

MARK = 0xF5
LOCK = 0x20
SIZE = 7


class Password:
    """STOREはパスワードの番地、FLAGSは保護のフラグのある番地、programはプログラムの置き方"""

    SIZE = SIZE

    def __init__(self, store: int, flags: int, prog: program.Program) -> None:
        self.STORE = store
        self.FLAGS = flags
        self.program = prog

    def locked(self, m) -> bool:
        return bool(m.mem[self.FLAGS] & LOCK)

    def unlock(self, m) -> None:
        m.mem[self.FLAGS] &= ~LOCK & 0xFF
        self._mirror(m, self.FLAGS, 1)

    def _mirror(self, m, a: int, n: int) -> None:
        """番地aからnバイトを、コピーの番地にも書く(PC-1350はRAMの頭にも置く)"""
        for i in range(n):
            copy = self.program.VARS.copy_of(m, a + i)
            if copy is not None:
                m.mem[copy] = m.mem[a + i]

    def stored(self, m) -> bytes:
        if m.mem[self.STORE] != MARK:
            return b""
        out = bytes(m.mem[self.STORE + 1 : self.STORE + 1 + SIZE])
        return out.split(b"\x00")[0]

    def apply(self, m, word: bytes, exact: bool = False) -> None:
        """PASS "word": 保護していなければ、wordをパスワードにして保護する。保護していれば、wordの
        頭がパスワードと同じなら保護を解き、違えばERROR 9。exactなら、wordの7字までがパスワードと
        同じでなければ解かない(PC-1245、PC-1261系)。プログラムがなければERROR 1(観察)"""
        if not self.program.lines(m):
            raise BasicError(1)
        if self.locked(m):
            if (word[:SIZE] if exact else word[: len(self.stored(m))]) != self.stored(m):
                raise BasicError(9)
            self.unlock(m)
            return
        word = word[:SIZE]
        data = bytes([MARK]) + word + (b"\x00" if len(word) < SIZE else b"")
        m.mem[self.STORE : self.STORE + len(data)] = data
        m.mem[self.FLAGS] |= LOCK
        self._mirror(m, self.STORE, len(data))
        self._mirror(m, self.FLAGS, 1)

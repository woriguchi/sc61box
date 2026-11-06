"""液晶に字と表示記号を書く(系統によらない部分)。字の形と並べ方は系統ごとの子クラス
(pc1251/screen.py、pc1261/screen.py)が決める"""

INSERT_MARK = bytes([0x63, 0x41, 0x41, 0x41, 0x63])  # 挿入マークの形(観察)
UNDERLINE = bytes([0x40] * 5)  # 行の終わりにいるカーソル
BLOCK = bytes([0x7F] * 5)  # 字の上にいるカーソル(字と交互に出す)


class Screen:
    """液晶。cellsは出せる字の数、widthは1行の字の数"""

    cells: int
    width: int

    def __init__(self, m) -> None:
        self.m = m
        self.addrs = m.column_addrs()

    def show(self, codes: list[int], cursor: int | None = None, shape: bytes = UNDERLINE) -> None:
        """左からcodesを並べ、残りを空白にする。cursorの桁にはshapeを出す"""
        raise NotImplementedError

    def put(self, i: int, g: bytes) -> None:
        """i桁目に字の形g(5列)を書く"""
        mem, addrs = self.m.mem, self.addrs
        for j in range(5):
            mem[addrs[5 * i + j]] = g[j]

    def _where(self, name: str) -> tuple[int, int] | None:
        """表示記号の(番地, ビット)。その機種になければNone"""
        return self.m.model.symbols.get(name)

    def symbol(self, name: str, on: bool) -> None:
        where = self._where(name)
        if where is None:
            return
        a, bit = where
        self.m.mem[a] = self.m.mem[a] | bit if on else self.m.mem[a] & ~bit
        self.m.lcd_dirty = True

    def lit(self, name: str) -> bool:
        """表示記号が点いているか"""
        where = self._where(name)
        return where is not None and bool(self.m.mem[where[0]] & where[1])

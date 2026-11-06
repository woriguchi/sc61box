"""PC-1350の4行の液晶。24字×4行で、1字は6列(5列の形と1列のあき)。液晶RAMの1行(150列)の
頭の6列は字に使わない。字を書くときは、あきの列も0にする。液晶を消すときは、頭の6列も
含めて全部を0にする。書くのは字が変わる桁と、書いた桁(PRINTでは、書いた行より下の行の桁も)
だけで、ほかの桁にPOKEやマシン語で描いた点は残る。スクロールするときは、液晶RAMの行(150列)
ごと上へずらす(観察)

打った行、答え、PRINTの字、メッセージは、上から順に1つずつ表示のまとまりとして並べる。
いまの表示は書き直せ(打っている行、>、INPUTの?)、確定した(commit)表示は残る。次の表示は
その下の行から書き、4行目を越えると全体をスクロールする(観察)
"""

from ... import charset
from ...machine import SYMBOLS_1350
from ..screen import UNDERLINE
from . import screen
from .screen import Screen

ROWS = 4
# 液晶にない記号(ビットだけを立てる。DEGREE・RADIAN・GRADは787Chのビット0〜2、印字モードは
# 783Chのビット2。観察)
HIDDEN = {
    "DEG": (0x787C, 0x01), "RAD": (0x787C, 0x02), "GRAD": (0x787C, 0x04),
    "PRINT": (0x783C, 0x04),
}  # fmt: skip


CHARS = {0xFB: "π", 0xFC: "√"}  # PC-1261系にない字(観察)


def glyph(code: int) -> bytes:
    ch = CHARS.get(code)
    return charset.glyph(ch) if ch else screen.glyph(code)


class Console(Screen):
    def __init__(self, m) -> None:
        super().__init__(m)
        self.width = m.model.cells
        self.cells = self.width * ROWS
        self.text = [0x20] * self.cells
        self.row = 0  # いまの表示の頭の行
        self.used = 0  # いまの表示が使っている行の数
        self.kept = False  # いまの表示を確定した(次の表示はその下から)
        self.scrolls = 0  # スクロールした回数(時間を数えるのに使う)
        # 液晶RAMに書いてある字(カーソルを書いた桁はNone)
        self.drawn: list[int | None] = [None] * self.cells
        self.below = False  # 次のshowで、いまの表示より下の行も書き直す

    def put(self, i: int, g: bytes) -> None:
        row, col = divmod(i, self.width)
        base = row * 150 + 6 * (col + 1)
        for j in range(5):
            self.m.mem[self.addrs[base + j]] = g[j]
        self.m.mem[self.addrs[base + 5]] = 0

    def _draw(self, force: range = range(0)) -> None:
        """字が変わった桁と、forceの桁を書く"""
        for i, c in enumerate(self.text):
            if i in force or self.drawn[i] != c:
                self.put(i, glyph(c))
                self.drawn[i] = c
        self.m.lcd_dirty = True

    def clear(self) -> None:
        """液晶を消し、次の表示を1行目から書く"""
        self.text = [0x20] * self.cells
        self.row, self.used, self.kept = 0, 0, False
        for a in self.addrs:
            self.m.mem[a] = 0
        self.drawn = [0x20] * self.cells
        self.m.lcd_dirty = True

    def commit(self) -> None:
        """いまの表示を確定して残す"""
        if self.used:
            self.kept = True

    def back(self, row: int) -> None:
        """行rowから下を消し、そこをいまの表示にする(打った行を呼び出すとき)"""
        w = self.width
        self.text[row * w :] = [0x20] * (self.cells - row * w)
        self.row, self.used, self.kept = row, 0, False
        self._draw()

    def show(self, codes: list[int], cursor: int | None = None, shape: bytes = UNDERLINE) -> None:
        """いまの表示を、codes(行をまたいで続ける)にする。前の表示を確定していれば、その下の
        行から書く。入りきらなければ全体をスクロールする"""
        w = self.width
        if self.kept:
            self.row, self.used, self.kept = self.row + self.used, 0, False
        codes = list(codes[: self.cells])
        need = max(1, -(-len(codes) // w), (cursor // w + 1) if cursor is not None else 0)
        start = self.row * w
        self.text[start : start + self.used * w] = [0x20] * (self.used * w)
        while self.row + need > ROWS:
            self._scroll()
        start = self.row * w
        self.text[start : start + need * w] = codes + [0x20] * (need * w - len(codes))
        self.used = need
        self._draw(range(start, self.cells if self.below else start + need * w))
        self.below = False
        if cursor is not None and start + cursor < self.cells:
            self.put(start + cursor, shape)
            self.drawn[start + cursor] = None

    def fill_below(self, rows: list[list[int]]) -> None:
        """いまの表示より下の行に、rowsを上から並べる(いまの表示には含めない)"""
        w, first = self.width, self.row + self.used
        for k, r in enumerate(range(first, ROWS)):
            line = list(rows[k][:w]) if k < len(rows) else []
            self.text[r * w : (r + 1) * w] = line + [0x20] * (w - len(line))
        for i in range(first * w, self.cells):  # カーソルを書いた桁は書き直さない
            if self.drawn[i] != self.text[i]:
                self.put(i, glyph(self.text[i]))
                self.drawn[i] = self.text[i]
        self.m.lcd_dirty = True

    def next_start(self) -> int:
        """次の表示を書き始める桁(行の頭。4行目の下ならスクロールしてから)"""
        row = self.row + self.used if self.kept else self.row
        while row >= ROWS:
            self._scroll()
            row -= 1
        return row * self.width

    def write(self, at: int, codes: list[int]) -> int:
        """桁atから字を上書きする(行の残りは消さない)。4行目を越えるとスクロールする。書き
        終えた次の桁を返す。書いた字の最後の行を、確定した表示にする(PRINT。観察)"""
        last = at
        for c in codes:
            while at >= self.cells:
                self._scroll()
                at -= self.width
            self.text[at] = c
            self.put(at, glyph(c))
            self.drawn[at] = c
            last = at
            at += 1
        self.row, self.used, self.kept = min(last // self.width, ROWS - 1), 1, True
        # 書いた行より下の行は、字を書き直す(POKEで描いた点は消える。観察)
        self._draw(range((self.row + 1) * self.width, self.cells))
        return at

    def _scroll(self) -> None:
        self.scrolls += 1
        w = self.width
        self.text = self.text[w:] + [0x20] * w
        self.drawn = self.drawn[w:] + [0x20] * w
        mem, addrs = self.m.mem, self.addrs
        for i in range(150 * (ROWS - 1)):
            mem[addrs[i]] = mem[addrs[i + 150]]
        for i in range(150 * (ROWS - 1), 150 * ROWS):
            mem[addrs[i]] = 0
        self.m.lcd_dirty = True
        self.row -= 1

    def lines(self, *rows: list[int] | bytes) -> None:
        """1行ずつ(rows[0]が1行目)、液晶を消して上から出す"""
        self.clear()
        w = self.width
        for k, r in enumerate(rows[:ROWS]):
            self.text[k * w : k * w + len(r[:w])] = list(r[:w])
        self.row, self.used, self.kept = 0, min(len(rows), ROWS), True
        self._draw()

    def _where(self, name: str) -> tuple[int, int] | None:
        return HIDDEN.get(name) or SYMBOLS_1350.get(name)

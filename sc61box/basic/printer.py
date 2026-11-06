"""プリンタへの印字: LPRINTとLLIST(系統によらない部分)

字の並びを24字ずつの行にし、字をプリンタのコードにして1バイトずつ送り、行の終わりに0Dhを
送る。字のコードの置き換え、LLISTの範囲の書き方、送る時間は系統ごとの子クラス
(pc1251/printer.py、pc1261/printer.py)が決める。
"""

from collections.abc import Generator
from decimal import Decimal

from .using import Format

Steps = Generator[int, None, None]

ROW_BREAK = -1  # send_rowsの並びの、行を変える所のマーカー


class PrintOut:
    WIDTH = 24  # プリンタの1行の字の数
    BYTE: int  # 1バイトを送る時間
    ROW: int  # 1つの印字で、24字の行を変える時間
    LLIST_START: int  # LLISTで最初の行を送り始めるまで
    LLIST_LINE: int  # LLISTで次の行へ移る時間
    LLIST_ROW: int | None = None  # LLISTで、1つの行の中で24字の行を変える時間(NoneならROW)
    LINE_TAIL = b""  # LLISTで、行ごとに最後の0Dhのあとに送るもの

    def __init__(self, basic) -> None:
        self.basic = basic
        self.m = basic.m

    def printer_code(self, unit: int) -> int:
        """本体の字(単位)を、プリンタのコードにする"""
        raise NotImplementedError

    # ---- LPRINT ----
    def lprint(self, items: list[Decimal | bytes], comma: bool, fmt: Format) -> Steps:
        """LPRINT: PRINTと同じ形の字を24字ずつの行にして送る(最後の行の右は空白で埋める)"""
        text = self.basic.print_text(items, comma, fmt, self.WIDTH)
        yield from self.send_rows(self.rows(self.units(text), 0))

    def program_started(self) -> None:
        """RUN・GOTOでプログラムを始めたとき"""

    def program_ended(self) -> Steps:
        """プログラムが終わったとき"""
        yield from ()

    # ---- 状態の保存 ----
    def save(self) -> dict:
        """RAMの外にある、印字の途中の状態"""
        return {}

    def parse(self, d: dict) -> dict:
        """saveで書いたものを読み、戻す属性の値を返す(何も変えない)"""
        return {}

    # ---- 行と送り方 ----
    def units(self, text: bytes) -> list[int]:
        return self.basic.EDITOR.units_of(text)

    def rows(self, units: list[int], indent: int) -> list[list[int]]:
        """字の並びを24字ずつの行にする。2行目からは頭にindent字の空白を置き、最後の行の右を
        空白で埋める(観察)"""
        space = self.basic.SPACE
        width = self.WIDTH
        out = [list(units[:width])]
        rest = units[width:]
        while rest:
            n = width - indent
            out.append([space] * indent + list(rest[:n]))
            rest = rest[n:]
        return [r + [space] * (width - len(r)) for r in out]

    def send_rows(self, rows: list[list[int]], tail: bytes = b"", row: int | None = None) -> Steps:
        """行をプリンタに送る。行の終わりに0Dhを送り、tailは最後の0Dhのあとに送る。rowは
        行を変える時間(NoneならROW)"""
        codes: list[int] = []
        for i, units in enumerate(rows):
            if i:
                codes.append(ROW_BREAK)
            codes += [*(self.printer_code(u) for u in units), 0x0D]
        yield from self.send(codes + list(tail), self.ROW if row is None else row)

    def send(self, codes: list[int], row: int) -> Steps:
        printer = self.m.printer
        for code in codes:
            if code == ROW_BREAK:
                yield row
                continue
            if printer is not None:
                printer.put(code)
            yield self.BYTE

    # ---- LLIST ----
    def llist(self, code: bytes) -> Steps:
        """LLIST: 登録した行を「行番号:中身」の形でプリンタに送る。行番号は3桁に右寄せし、
        続きの行は頭に「行番号:」の幅の空白を置く。プリンタがないときと、パスワードで
        保護しているときは何もしない(観察)"""
        basic = self.basic
        if self.m.printer is None or basic.PASSWORD.locked(self.m):
            basic._prompt()
            return
        lines = self.llist_lines(code)
        self.program_started()
        yield self.LLIST_START
        for i, (n, at) in enumerate(lines):
            if i:
                yield self.LLIST_LINE
            body, _ = basic._layout(basic.PROGRAM.body(self.m, at))
            head = list(basic._codes(f"{n:>3}:"))
            rows = self.rows(head + body, len(head))
            yield from self.send_rows(rows, self.LINE_TAIL, self.LLIST_ROW)
        basic._prompt()

    def llist_lines(self, code: bytes) -> list[tuple[int, int]]:
        """LLISTのあとに書いた範囲の(行番号, 番地)の並び。code[0]はLLIST"""
        raise NotImplementedError

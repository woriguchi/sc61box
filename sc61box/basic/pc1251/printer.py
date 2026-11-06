"""PC-1251系のプリンタ(CE-125)への印字: LPRINTとLLIST。共通の部分は..printer"""

from ... import charset
from .. import printer, timing
from ..errors import BasicError
from ..evaluate import expect_end
from . import program
from .evaluate import COMMA, Evaluator


class PrintOut(printer.PrintOut):
    # プリンタに送る時間(観察): 1バイトごと、24字の行を変えるごと、LLISTの始めと1行ごと
    BYTE = timing.ms(8.75)
    ROW = timing.ms(12.25)
    LLIST_START = timing.ms(8.7)
    LLIST_LINE = timing.ms(37.0)
    LINE_TAIL = b"\x03"  # LLISTで、行ごとに0Dhのあとに03hを送る(観察)

    def printer_code(self, unit: int) -> int:
        """本体の字のコードをASCIIにする(ないものは空白)"""
        return charset.ASCII.get(unit, 0x20)

    def llist_lines(self, code: bytes) -> list[tuple[int, int]]:
        """LLIST [n,m]: n,mなら、n以上の最初の行からm以上の最初の行まで(両方を含み、前の行が
        後の行より前でなければERROR 1)。行番号を1つだけ書くとERROR 1(観察)"""
        lines = program.lines(self.m)
        if len(code) <= 1:
            return lines
        if code[1] == COMMA:
            raise BasicError(1, 1)
        e = Evaluator(self.m, code, 1)
        first = e.integer()
        if not e.take(COMMA):
            raise BasicError(1, e.pos)
        last = e.integer()
        expect_end(e)
        if first <= 0:
            raise BasicError(1, 0)
        a = program.at_or_after(self.m, first)
        b = program.at_or_after(self.m, last)
        if a is None or b is None:
            raise BasicError(4)
        if a[0] >= b[0]:
            raise BasicError(1, 0)
        return [(n, at) for n, at in lines if a[0] <= n <= b[0]]

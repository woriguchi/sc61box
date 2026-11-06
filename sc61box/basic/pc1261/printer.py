"""PC-1261系とPC-1350のプリンタ(CE-126P)への印字: LPRINTとLLIST(観察)。共通の部分は..printer

- PC-1261系は、字をそのままのコードで送る。カナ(FEh、字)は字だけを送り、'、[、]、`は空白に
  する。PC-1350の送るコードはCODES_1350
- LPRINTは、字を本体の1行ぶん(24字)ためてから送る。;で終わったLPRINTの字は送らずに
  ためておき、次のLPRINTが続けて書く。プログラムが終わると、ためた字を送る。RUN・GOTOで
  始めると、ためた字は捨てる。,で分けたLPRINTは、ためた字を送ってから書く
- LLISTは、RUN・PROモードで打つ。LLIST n(その行だけ)、LLIST n,(そこから終わりまで)、
  LLIST ,m、LLIST n,mと書け、nとmにはラベルも書ける
"""

from decimal import Decimal

from .. import printer, timing
from ..editor import WIDE
from ..errors import BasicError
from ..evaluate import expect_end
from ..printer import Steps
from ..using import Format

BLANKS = frozenset([0x27, 0x5B, 0x5D, 0x60])  # プリンタで空白にする字


class PrintOut(printer.PrintOut):
    # プリンタに送る時間(観察): 1バイトごと、1つのLPRINTで24字の行を変えるごと、LPRINTの
    # 送り始め、LLISTの始め、1行ごと、1つの行の中で24字の行を変えるごと
    BYTE = timing.ms(6.48)
    ROW = timing.ms(7.5)
    SEND_START = timing.ms(17.0)  # LPRINTで送り始めるまで
    LLIST_START = timing.ms(38.0)
    LLIST_LINE = timing.ms(34.7)
    LLIST_ROW = timing.ms(12.5)

    def __init__(self, basic) -> None:
        super().__init__(basic)
        self.line: list[int] = []  # ためていて、まだ送っていない字

    def save(self) -> dict:
        return {"line": list(self.line)}

    def parse(self, d: dict) -> dict:
        """ためていた字(なければ空)"""
        return {"line": [int(u) for u in d.get("line", [])]}

    def printer_code(self, unit: int) -> int:
        if unit >= WIDE:
            return unit - WIDE  # カナ
        return 0x20 if unit in BLANKS else unit

    def lprint(self, items: list[Decimal | bytes], comma: bool, fmt: Format) -> Steps:
        trailing = self.basic.runner.trailing
        if comma and self.line:
            yield from self._flush()
        joined = bool(self.line) or trailing
        text = self.basic.print_text(items, comma, fmt, self.WIDTH, joined=joined and not comma)
        units = self.line + self.units(text)
        width = self.WIDTH
        full = len(units) // width
        rows = [units[i * width : (i + 1) * width] for i in range(full)]
        self.line = units[full * width :]
        if not trailing and (self.line or not rows):
            rows.append(self.line + [self.basic.SPACE] * (width - len(self.line)))
            self.line = []
        if rows:
            yield self.SEND_START
            yield from self.send_rows(rows)

    def echo(self, units: list[int], right: bool = False) -> Steps:
        """印字モードで、打った行か答えを24字ずつの行にして送る(続きの行は頭を空けない)。
        rightなら右に寄せる(観察)"""
        if right:
            units = [self.basic.SPACE] * (self.WIDTH - len(units)) + units
        yield self.SEND_START
        yield from self.send_rows(self.rows(units, 0))

    def _flush(self) -> Steps:
        if self.line:
            row = self.line + [self.basic.SPACE] * (self.WIDTH - len(self.line))
            self.line = []
            yield self.SEND_START
            yield from self.send_rows([row])

    def program_started(self) -> None:
        self.line = []

    def program_ended(self) -> Steps:
        yield from self._flush()

    def llist_lines(self, code: bytes) -> list[tuple[int, int]]:
        """LLIST [n][,[m]]: nだけならn以上の最初の行だけ、n,ならそこから終わりまで、,mなら
        初めからm以上の最初の行まで、n,mならn以上の最初の行からm以上の最初の行まで(前の行が
        後の行より前でなければERROR 1)。行がなければERROR 4(観察)"""
        basic = self.basic
        lines = basic.PROGRAM.lines(self.m)
        e = basic.EVALUATOR(self.m, code, 1)
        if e.pos >= len(code):
            return lines
        first = None if e.peek() == basic.COMMA else self._line_at(e.expression(), lines)
        if not e.take(basic.COMMA):
            expect_end(e)
            assert first is not None
            return [first]
        if e.pos >= len(code):
            if first is None:
                raise BasicError(1, e.pos)
            return lines[lines.index(first) :]
        last = self._line_at(e.expression(), lines)
        expect_end(e)
        start = lines.index(first) if first is not None else 0
        stop = lines.index(last)
        if first is not None and start >= stop:
            raise BasicError(1, 0)
        return lines[start : stop + 1]

    def _line_at(self, v: Decimal | bytes, lines: list[tuple[int, int]]) -> tuple[int, int]:
        """行番号か(番号以上の最初の行)、ラベルの行。なければERROR 4"""
        if isinstance(v, bytes):
            quote = bytes([self.basic.QUOTE])
            found = self.basic.PROGRAM.find_label(self.m, quote + v + quote) if v else None
        else:
            n = int(v)
            found = None if n < 1 else next(((k, a) for k, a in lines if k >= n), None)
        if found is None or found not in lines:
            raise BasicError(4)
        return found


# PC-1350が字のコードの代わりにプリンタに送るコード(観察: 数字の0は斜線のある0、英字のOは
# 30h、πと√はプリンタの19h・18h。ないものと01h〜1Fh(0Dhも)は空白で、FAhは00h)
CODES_1350 = (
    {0x30: 0xF0, 0x4F: 0x30, 0x7E: 0x9F, 0xFA: 0x00, 0xFB: 0x19, 0xFC: 0x18}
    | {c: 0x20 for c in [*range(0x01, 0x20), *range(0x7F, 0xA0), *range(0xE0, 0xF0)]}
    | {c: 0x20 for c in (0xF9, 0xFD, 0xFE, 0xFF)}
)


class PrintOut1350(PrintOut):
    """PC-1350。'、[、]、`もそのまま送る(観察)"""

    def units(self, text: bytes) -> list[int]:
        """PRINTと同じ形にした字は1バイトが1字(FEhもCHR$ 254の字)"""
        return list(text)

    def printer_code(self, unit: int) -> int:
        code = unit - WIDE if unit >= WIDE else unit
        return CODES_1350.get(code, code)

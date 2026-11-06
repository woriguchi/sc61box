"""PC-1350のROMなしのBASIC。BASICの形(中間コード、行と変数の置き方)はPC-1261系と同じで、
4行の液晶への出し方、モードの切り替え、キーが違う(観察)

- モードはMODEのキーでRUNとPROを切り替え(スイッチは電源だけ)、液晶を消して1行目に
  「RUN MODE」か「PROGRAM MODE」、2行目に>を出す
- RUNモードで打った行は残し、答えはその下の行の右に、文字列の答えは液晶を消して1行目に
  出す。エラーは下の行に「ERROR n」。命令のあとは下の行に>。次に打つ行は下の行から書き、
  4行目を越えるとスクロールする
- PROモードで行を登録したり、LIST・↑・↓で出したりすると、液晶を消し、その行から4行に
  並べる。続きの行は「行番号:」の幅だけ空ける
- CLSのキーで液晶を消して1行目に>。INPUTの打ち込みでは消さず、CLと同じに打ち直させる
- プログラムのPRINT、INPUTの?、メッセージ(ERROR n IN 行番号など)も下の行へ順に出す
- 電源を入れるとRUNモード
"""

from collections.abc import Callable, Generator, Iterable
from dataclasses import replace
from decimal import ROUND_FLOOR, Decimal
from typing import cast

from ...machine import TICK_2MS
from ..editor import NO_SEP, spans
from ..errors import BasicError
from ..evaluate import by_code
from ..evaluate import number as as_number
from ..run import STATEMENTS_BY_NAME, End, Steps
from ..timing import ms
from ..using import Format
from . import (
    editor,
    evaluate,
    graphics,
    password,
    printer,
    program,
    run,
    sio,
    system,
    tapeio,
    textmode,
    tokens,
    variables,
)
from .console import ROWS, Console
from .keyboard import CODES_1350, Keyboard1350
from .run import CURSOR_TIME
from .timing import PC1261

BANNERS = {"RUN": "RUN MODE", "PRO": "PROGRAM MODE"}
# 時間(観察: 繰り返しの1回が、CLSで110ms、CURSORの行を書くと11.5ms、スクロール1回で86ms長い)
CLS_TIME_1350 = ms(106.0)
CURSOR_ROW_TIME = ms(11.5)
SCROLL_TIME = ms(86.0)
# グラフィックの時間(観察: WAIT 0のあとの繰り返しの1回で測った)。(x,y)を1つ読むのに20ms
# かかる。LINEの時間は点ごとに足す(液晶の外の点も数える)
XY_TIME = ms(20.2)
PSET_TIME, GCURSOR_TIME, POINT_TIME = ms(7.6), ms(5.7), ms(8.3)
GPRINT_TIME, GPRINT_NUMBER, GPRINT_STRING, GPRINT_COLUMN = ms(4.0), ms(12.0), ms(1.5), ms(2.6)
LINE_TIME, LINE_DOT, LINE_OUTSIDE, LINE_SIDEWAYS = ms(8.2), ms(1.90), ms(1.06), ms(0.44)
PATTERN_DOT, BOX_DOT, FILL_DOT = ms(0.79), ms(1.72), ms(1.62)
DRAW_STEP = ms(10.0)  # LINEを描くあいだ、BRKを見る間隔


_CODE = {name: code for code, name in tokens.KEYWORDS_1350.items()}
# 描く命令。打った行でも使える(GCURSORは打った行ではERROR 1。観察)
DRAWING = tuple(_CODE[n] for n in ("GPRINT", "PSET", "PRESET", "LINE"))
LETTER_B, LETTER_F = 0x42, 0x46
HOW = {0x53: "S", 0x52: "R", 0x58: "X"}  # LINEの,のあとのS・R・X


class DrawStopped(Exception):
    """打った行の描く命令を、描いている途中にBRKで止めた"""


def _floor(v) -> int:
    """座標などの数: 小数は切り捨て(下の整数。文字列はERROR 9)"""
    return int(as_number(v).to_integral_value(rounding=ROUND_FLOOR))


class Evaluator(evaluate.Evaluator):
    VARS = variables.PC1350
    PI_CHAR, ROOT_CHAR = 0xFB, 0xFC  # πの字はPI、√の字はSQRと同じ(観察)

    @staticmethod
    def from_ascii(n: int) -> int | None:
        """CHR$は1〜255のどれでもよい(0は空の文字列。観察)"""
        return n if 1 <= n <= 0xFF else None

    @staticmethod
    def char_bytes(c: int) -> bytes:
        """80h以上は「FEh、字」の2バイト(観察: CHR$ 128は「FE 80」)"""
        return bytes([editor.KANA_MARK, c]) if c >= 0x80 else bytes([c])

    def _operand(self):
        if self.peek() == _CODE["OPEN$"]:  # シリアルの設定の字
            self.pos += 1
            return sio.settings(self.m)
        if self.peek() == _CODE["POINT"]:  # POINT (x,y)
            self.pos += 1
            self.spend(XY_TIME + POINT_TIME)
            self.expect(self.LPAREN)
            x = graphics.check(_floor(self.expression()))
            self.expect(self.COMMA)
            y = graphics.check(_floor(self.expression()))
            self.expect(self.RPAREN)
            return Decimal(graphics.point(self.m, x, y))
        return super()._operand()


class Runner(run.Runner):
    EVALUATOR = Evaluator
    PROGRAM, VARS = program.PC1350, variables.PC1350
    # PRINTは短く、数を字にする時間も短い。スクロールするときに長くかかる(観察: WAIT 0のあとの
    # 繰り返しの1回が、CURSOR 3,3:PRINT " >"で42ms長く、スクロールしながらのPRINT "A"で
    # 135ms、PRINT Iで144ms)
    TIMES = replace(PC1261, PRINT=ms(38.0), PRINT_NUMBER=ms(10.0))
    NO_PRINTER_TIME = 0

    def _cls(self) -> None:
        self.meter.add(CLS_TIME_1350)
        self.basic.cls()
        self.basic.cleared = True

    def _cursor(self) -> None:
        """CURSOR n(左上から数えた桁)か、CURSOR 桁,行(観察)"""
        n = self._integer()
        if self._take(self.COMMA):
            row = self._integer()
            self.meter.add(CURSOR_ROW_TIME)
            if not (0 <= n < 24 and 0 <= row < 4):
                raise BasicError(3)
            n += 24 * row
        if not 0 <= n < 96:
            raise BasicError(3)
        self.meter.add(CURSOR_TIME)
        self.basic.cursor(n)

    # ---- グラフィック(graphics.py) ----
    def _xy(self) -> tuple[int, int]:
        """(x,y)"""
        if not self._take(self.LPAREN):
            raise BasicError(1, self.pos)
        x = graphics.check(_floor(self._expression()))
        if not self._take(self.COMMA):
            raise BasicError(1, self.pos)
        y = graphics.check(_floor(self._expression()))
        if not self._take(self.RPAREN):
            raise BasicError(1, self.pos)
        self.meter.add(XY_TIME)
        return x, y

    def _letter(self, letters) -> int | None:
        """,のあとの1字の指定(S・R・X)。そのあとが文の終わりか,ならその字"""
        c = self.code[self.pos] if self.pos < len(self.code) else None
        if c not in letters:
            return None
        after = self.pos + 1
        if after < len(self.code) and self.code[after] not in (self.COLON, self.COMMA):
            return None
        self.pos = after
        return c

    def _drawn(self) -> Steps:
        """描いたあとは、PRINTと同じにWAITの時間かENTERを待つ(打った行では待たない。観察)"""
        yield self.meter.take()
        basic = self.basic
        if basic.where != "run":
            return
        basic.display(True)
        basic.state = "print"
        if self.wait is not None:
            yield max(self.wait, 1)
            basic.display(False)
        else:
            yield from basic.wait_enter()

    def _gcursor(self) -> None:
        g = self.basic.graphics
        g.gx, g.gy = self._xy()
        self.meter.add(GCURSOR_TIME)

    def _pset(self) -> Steps:
        """PSET (x,y)[,X]"""
        x, y = self._xy()
        how = "S"
        if self._take(self.COMMA):
            if self._letter((0x58,)) is None:
                raise BasicError(1, self.pos)
            how = "X"
        if not self._at_end():
            raise BasicError(1, self.pos)
        graphics.plot(self.m, x, y, how)
        self.meter.add(PSET_TIME)
        yield from self._drawn()

    def _preset(self) -> Steps:
        x, y = self._xy()
        if not self._at_end():
            raise BasicError(1, self.pos)
        graphics.plot(self.m, x, y, "R")
        self.meter.add(PSET_TIME)
        yield from self._drawn()

    def _gprint(self) -> Steps:
        """GPRINT 列[;列…]。列は0〜255の数か、16進表記の文字列"""
        g = self.basic.graphics
        kept = False
        self.meter.add(GPRINT_TIME)
        while not self._at_end():
            v = self._expression()
            if isinstance(v, bytes):
                columns: Iterable[int] = graphics.hex_columns(v)
                self.meter.add(GPRINT_STRING)
            else:
                n = _floor(v)
                if not 0 <= n <= 0xFF:
                    raise BasicError(3, self.pos)
                columns = [n]
                self.meter.add(GPRINT_NUMBER)
            for c in columns:  # 16進表記の誤りの手前までは書く(観察)
                graphics.column(self.m, g.gx, g.gy, c)
                g.gx += 1
                self.meter.add(GPRINT_COLUMN)
            kept = True
            if self._take(self.COMMA):
                graphics.column(self.m, g.gx, g.gy, 0)  # ,は空の列を1つ書く(観察)
                g.gx += 1
            elif not self._take(self.SEMICOLON):
                kept = False
                break
        if not self._at_end():
            raise BasicError(1, self.pos)
        if not kept:
            g.gx = 0
        yield from self._drawn()

    def _draw_line(self) -> Steps:
        """LINE [(x1,y1)]-(x2,y2)[,S|R|X][,線の形][,B|BF]"""
        g = self.basic.graphics
        given = self.pos < len(self.code) and self.code[self.pos] == self.LPAREN
        start = self._xy() if given else g.last
        if not self._take(0x2D):  # -
            raise BasicError(1, self.pos)
        end = self._xy()
        how: str = "S"
        pattern, kind = 0xFFFF, ""
        if self._take(self.COMMA):
            letter = self._letter(HOW)
            if letter is not None:
                how = HOW[letter]
            if letter is None or self._take(self.COMMA):
                kind = self._box_kind()
                if not kind:
                    pattern = _floor(self._expression())
                    if not 0 <= pattern <= 0xFFFF:
                        raise BasicError(3, self.pos)
                    if self._take(self.COMMA):
                        kind = self._box_kind()
                        if not kind:
                            raise BasicError(1, self.pos)
        if not self._at_end():
            raise BasicError(1, self.pos)
        g.last = end
        (x0, y0), (x1, y1) = start, end
        self.meter.add(LINE_TIME)
        yield self.meter.take()
        spent = 0  # まだ進めていない描く時間
        if kind == "BF":
            for shown, hidden in graphics.fill(self.m, x0, y0, x1, y1, how, pattern):
                spent += FILL_DOT * shown + LINE_OUTSIDE * hidden
                spent = yield from self._drawing(spent)
        else:
            pts = graphics.box(x0, y0, x1, y1) if kind == "B" else graphics.segment(x0, y0, x1, y1)
            dot = BOX_DOT if kind == "B" else LINE_DOT
            extra = PATTERN_DOT if pattern != 0xFFFF else 0
            if not kind:
                spent += LINE_SIDEWAYS * min(abs(x1 - x0), abs(y1 - y0))
            for shown in graphics.draw(self.m, pts, how, pattern):
                spent += (dot if shown else LINE_OUTSIDE) + extra
                spent = yield from self._drawing(spent)
        self.meter.add(spent)
        yield from self._drawn()

    def _drawing(self, spent: int) -> Generator[int, None, int]:
        """描くのにかかった時間をDRAW_STEPずつ進め、そのたびにBRKを見る(描いている途中でも
        止まる。CONTでは次の文から。観察)。進めずに残った時間を返す"""
        while spent >= DRAW_STEP:
            yield DRAW_STEP
            spent -= DRAW_STEP
            if self.m.brk:
                if self.basic.where == "run":
                    self._broken()
                raise DrawStopped  # 打った行なら>に戻る(観察)
        return spent

    def _box_kind(self) -> str:
        """B(囲む)かBF(塗る)"""
        code, i = self.code, self.pos
        if i < len(code) and code[i] == LETTER_B:
            if i + 1 < len(code) and code[i + 1] == LETTER_F:
                self.pos += 2
                return "BF"
            self.pos += 1
            return "B"
        return ""

    def start(self, line: int | bytes | None) -> Steps:
        """RUNはシリアルを閉じ(設定はそのまま)、GPRINTのカーソルとLINEの始めを初めに戻す
        (GOTO・CONT・DEFのキーではしない。観察)"""
        sio.set_open(self.m, False)
        self.basic.graphics.reset()
        yield from super().start(line)

    # ---- シリアル入出力(sio.py) ----
    def _open(self) -> None:
        """OPEN ["設定"](数ならERROR 9)"""
        text = None
        if not self._at_end():
            v = self._expression()
            if not isinstance(v, bytes):
                raise BasicError(9)
            text = v
        sio.open_port(self.m, text)

    def _close(self) -> None:
        sio.set_open(self.m, False)

    def _console(self) -> None:
        """CONSOLE [字数](文字列ならERROR 9)"""
        n = None
        if not self._at_end():
            v = self._expression()
            if isinstance(v, bytes):
                raise BasicError(9)
            n = int(v)
        sio.console(self.m, n)

    def _save(self) -> Steps:
        """SAVE: 開いていて、送るプログラムがあれば、相手を待つ。何か書いてあればERROR 1
        (観察)"""
        if not self._at_end():
            raise BasicError(1, self.pos)
        if sio.is_open(self.m) and self.PROGRAM.lines(self.m):
            yield from self.wait_link()

    def _lprint(self) -> Steps:
        """開いていれば、出すものを読んでから(式のエラーはそこで出る)、プリンタでなく
        シリアルの相手に送る(相手を待つ。観察)"""
        if sio.is_open(self.m):
            self._print_items()
            yield from self.wait_link()
            return
        yield from super()._lprint()

    def wait_link(self) -> Steps:
        """シリアルの相手を待つ(エミュレータには相手がない)。BRKで止め、プログラムの中なら
        その文で止まる。打った命令で待っているあいだはbasic.whereを"link"にし、そこで保存した
        状態を戻したときにまた待つ(_resumed)"""
        basic = self.basic
        if basic.where == "run":
            while not self.m.brk:
                yield TICK_2MS
            self._broken()
        before, basic.where = basic.where, "link"
        try:
            while not self.m.brk:
                yield TICK_2MS
        finally:
            basic.where = before


Runner.STATEMENTS = by_code(
    tokens.KEYWORDS_1350,
    STATEMENTS_BY_NAME
    | {
        "CLS": Runner._cls, "CURSOR": Runner._cursor, "LPRINT": Runner._lprint,
        "OPEN": Runner._open, "CLOSE": Runner._close, "CONSOLE": Runner._console,
        "SAVE": Runner._save, "GCURSOR": Runner._gcursor, "GPRINT": Runner._gprint,
        "PSET": Runner._pset, "PRESET": Runner._preset, "LINE": Runner._draw_line,
    },
)  # fmt: skip


class Basic(system.Basic):
    T_EQU = -1  # EQU#はない
    CALL_REGS = {}  # 確かめていない
    TYPED_AT = 0x6EB0  # CALLのとき打った行を置く番地(観察)
    OUTER_RETURN = 0x1FFC  # ROMの番地(ここへ戻ればBASICの命令の続きへ)
    SCREEN = Console
    STATEMENTS = Runner.STATEMENTS
    KEYBOARD, CODES = Keyboard1350, CODES_1350
    EVALUATOR, RUNNER = Evaluator, Runner
    PROGRAM, VARS = program.PC1350, variables.PC1350
    PASSWORD = password.PC1350
    PRINTOUT = printer.PrintOut1350
    TAPEIO = tapeio.TapeIO1350
    DIRECT = (
        system.Basic.DIRECT
        + tuple(_CODE[n] for n in ("OPEN", "CLOSE", "CONSOLE", "SAVE"))
        + DRAWING
    )
    TEXT_PROMPT = 0x3C  # TEXTモードの<(観察)

    def __init__(self, m) -> None:
        self.basic_mode = "RUN"  # MODEのキーで変える(RUNかPRO)
        super().__init__(m)
        self.console = cast(Console, self.screen)
        self._hook_keys()
        self.input_row = 0  # 打った行の頭の行(エラーのあと←・→で呼び出す所)
        self.input_scrolls = 0  # input_rowを決めたときの、スクロールした回数
        self.print_pos: int | None = None  # 次のPRINTを書く桁(CURSORと;のあと)
        self.full_line = False  # ENTERで残した行が、最後の行の終わりまで埋まっている
        self.spare_row = False  # 次の>の前に1行空ける
        self.graphics = graphics.Graphics()
        self.cleared = False  # プログラムのCLSのあと、まだ何も出していない
        self.typed: tuple | None = None  # 最後に出した打っている行(エディタ、字、カーソル)

    def _hook_keys(self) -> None:
        keys = cast(Keyboard1350, self.keys)
        keys.clear_screen = self._cls_key
        keys.toggle_mode = self._toggle_mode

    def restart(self) -> None:
        """電源を入れ直すと、RUNモードから始める(観察。状態を戻すときはloadが戻す)"""
        self.basic_mode = "RUN"
        super().restart()
        self._hook_keys()

    def _power_on(self) -> None:
        """電源を入れると、シリアルは閉じて初めの設定に、TEXTモードはBASICモードに戻る(観察)"""
        super()._power_on()
        self.graphics.reset()
        sio.power_on(self.m)
        textmode.set_on(self.m, self.VARS, False)

    def _toggle_mode(self) -> None:
        self.basic_mode = "PRO" if self.basic_mode == "RUN" else "RUN"

    def _cls_key(self) -> None:
        """CLSのキー。INPUTの打ち込みとその答えのエラーでは液晶を消さない(観察)"""
        if self.where != "input":
            self.cls()

    @property
    def mode(self) -> str:
        return "OFF" if self.m.mode == "OFF" else self.basic_mode

    def _show_mode(self, mode: str) -> None:
        for name in ("RUN", "PRO"):
            self.screen.symbol(name, mode == name)

    def _mode_loop(self, mode: str, keep: bool = False):
        if not keep:
            self.console.clear()
            self.graphics.reset()
            self.console.show(list(self._codes(BANNERS.get(mode, ""))))
            self.console.commit()
        yield from super()._mode_loop(mode, keep)

    def _wait_key(self):
        while True:
            k = yield from super()._wait_key()
            if k == "MODE":  # モードはKeyboard1350.pollが切り替えてある
                return None
            if k == "KANA":
                continue
            if k in ("UP", "DOWN") and self.mode == "RUN":
                self.console.below = True  # 次に出すとき、下の行も書き直す(観察)
            if k in ("UP", "DOWN") and self.mode == "RUN" and self.state == "input":
                # 打っている行に、最後に出した数を足す(観察)
                for u in self.last_number:
                    self.editor.type(u)
                self._show_editor()
                continue
            return k

    # ---- 液晶の表示 ----
    def _enter_empty(self) -> None:
        """何も打たずにENTERを押すと、下の行に>を出す(観察)"""
        self.console.commit()
        self._prompt()

    def _enter(self, mode: str):
        if self.state in ("input", "edit") and self.editor.units:
            # 打った行を、中間コードにしてLISTと同じ形で出し直して残す(観察)
            rows = self._wrapped([], self.EDITOR.units_of(self._entered_code(mode)), trim=False)
            w = self.console.width
            text = [c for r in rows[:-1] for c in r + [self.SPACE] * (w - len(r))] + rows[-1]
            self.console.show(text)
            self.full_line = len(rows[-1]) == w
            self._input_at()
            self.console.commit()
        yield from super()._enter(mode)

    def _type(self, code: int, continues: bool) -> None:
        if self.state == "shown" or (
            self.mode == "PRO" and self.state not in ("input", "edit", "rsv-edit")
        ):
            # PROモードで打ち始めると、液晶を消して1行目から打つ(観察)
            self.console.clear()
        super()._type(code, continues)

    def _show_editor(self) -> None:
        """打っている行は、行をまたいで続ける。登録した行の編集では、続きの行を「行番号:」の
        幅だけ空ける(観察)"""
        text, cursor, shape = self.editor.view(
            self.console.cells, self.keywords, self.CODES, self.blink_off
        )
        if self.state in ("edit", "error-line") and self.editor.head:
            sep = 0 if textmode.is_on(self.m) else 1
            ed = self.editor
            whole, _cols, ends = spans(
                ed.units, self.keywords, self.CODES, ed.head, ed.sep, ed.glued, **ed.style()
            )
            text, cursor = self._indented(
                text, cursor, ed.head + sep, ends if whole[: len(text)] == text else None
            )
        # 字を打ち足したほかは(カーソルを動かした、消したなど)、下の行も書き直す。描いた点は
        # 消える(観察)
        now = (id(self.editor), list(self.editor.units), self.editor.cur)
        before = self.typed
        if before is not None and before[0] == now[0] and before[1:] != now[1:]:
            added = now[1][:-1] == before[1] and now[2] == len(now[1])
            self.console.below = self.console.below or not added
        self.typed = now
        self.console.show(text, cursor, shape)
        digits = self.editor.units[: self.editor.head]
        if self.state == "edit" and digits and all(0x30 <= u <= 0x39 for u in digits):
            # 編集している行の下には、続く行を並べ直す(観察。行番号を数字でないものに
            # 書き換えているあいだは、並べ直さない)
            n = int(bytes(digits))
            rows: list[list[int]] = []
            for number, at in self.PROGRAM.lines(self.m):
                if number > n:
                    rows += self._line_rows(number, at, self._sep(" "))
                if len(rows) >= ROWS:
                    break
            self.console.fill_below(rows)

    def _line_rows(self, n: int, a: int, sep: str = ":") -> list[list[int]]:
        """命令の後ろの空白は、行の終わりでも捨てない(入らなければ命令ごと次の行へ。観察)"""
        head = list(self._codes(f"{n}{sep}"))
        return self._wrapped(head, self.EDITOR.units_of(self.PROGRAM.body(self.m, a)), trim=False)

    def _indented(
        self, text: list[int], cursor: int | None, indent: int, ends: list[int] | None = None
    ) -> tuple[list[int], int | None]:
        """1行目のあとの行の頭をindent字ずつ空けた並びと、カーソルの桁。endsは単位ごとの字の
        終わりで、渡せば命令(後ろの空白まで)を行をまたがずに次の行へ送り、送った命令の前の
        空白は捨てる(LISTと同じ。観察)"""
        w = self.console.width
        if ends is None:
            ends = list(range(1, len(text) + 1))
        places: list[int] = []
        row, col, start = 0, 0, 0
        for end in ends:
            piece = list(range(start, min(end, len(text))))
            start = end
            chunks = [piece] if len(piece) > 1 and end > indent else [[k] for k in piece]
            for chunk in chunks:
                if col + len(chunk) > w:
                    row, col = row + 1, indent
                    if len(chunk) > 1 and text[chunk[0]] == self.SPACE:
                        places.append(row * w + col)  # 捨てた空白は次の字と同じ桁
                        chunk = chunk[1:]
                for _k in chunk:
                    places.append(row * w + col)
                    col += 1
        out = [self.SPACE] * ((row + 1) * w)
        for k, cell in enumerate(places):
            if out[cell] == self.SPACE:
                out[cell] = text[k]
        if cursor is not None:
            if cursor < len(places):
                cursor = places[cursor]
            else:
                cursor = row * w + col if col < w else (row + 1) * w + indent
        while len(out) > w and out[-w:] == [self.SPACE] * w and (cursor or 0) < len(out) - w:
            out = out[:-w]
        return out, cursor

    def _show_result(self, value: Decimal | bytes) -> None:
        """数は打った行の下の行の右に、文字列は液晶を消して1行目に出す(観察)"""
        width = self.console.width
        if isinstance(value, Decimal):
            self.console.show([self.SPACE] * (width - len(self.answer)) + list(self.answer))
            self.last_number = self.answer
        else:
            self.console.clear()
            self.console.show(list(self.spell(value)))
            self._input_at()  # ←・→で呼び出す行は、答えの所に書く(観察)
        self.console.commit()

    def _error(self, number: int) -> None:
        self.error_number = number
        self.state = "error"
        self.console.show(list(self._codes(f"ERROR {number}")))
        self.console.commit()

    def _edit_key(self, k: str) -> None:
        if self.state == "result" and k in ("LEFT", "RIGHT") and self.last_line:
            self.console.back(self._recall_row())  # 答えを消し、打った行を書き直す(観察)
        if self.state == "shown" and k in ("LEFT", "RIGHT") and self.line_no is not None:
            # 出している行の所で編集する。下に並べた行はそのまま(観察)
            self._list_from(self.line_no, " ")
        super()._edit_key(k)

    def _input_at(self) -> None:
        """いまの表示の行を、←・→で呼び出す行として覚える"""
        self.input_row, self.input_scrolls = self.console.row, self.console.scrolls

    def _recall_row(self) -> int:
        """覚えた行の、いまの場所(覚えたあとにスクロールした行数だけ上。観察)"""
        return max(0, self.input_row - (self.console.scrolls - self.input_scrolls))

    def _show_stopped(self) -> bool:
        """止まった行は、液晶を消して1行目から出し、続く行も4行目まで並べる(観察)"""
        if self.stopped_at is not None:
            n = self.stopped_at[0]
            found = self.PROGRAM.at_or_after(self.m, n)
            if found is not None and found[0] == n:
                self._list_from(n, ":")
        shown = super()._show_stopped()
        if shown and textmode.is_on(self.m):
            self.editor.sep = NO_SEP
            self._show_editor()
        return shown

    def _edit_line(self, n: int) -> None:
        super()._edit_line(n)
        if self.state == "edit" and textmode.is_on(self.m):
            self.editor.sep = NO_SEP  # TEXTモードでは、行番号のすぐあとから(観察)
            self._show_editor()

    # ---- TEXTモード(textmode.py) ----
    def _sep(self, sep: str) -> str:
        """行番号のあとの字。TEXTモードでは置かない"""
        return "" if textmode.is_on(self.m) else sep

    def _below_cls(self) -> None:
        """プログラムのCLSのあと、まだ何も出していなければ、メッセージと>は2行目から(PRINTと
        INPUTの?は1行目から。観察)"""
        c = self.console
        if self.cleared and c.row == 0 and not c.used:
            c.row = 1
        self.cleared = False

    def _prompt(self) -> None:
        self._below_cls()
        self.console.below = True  # >を出すと、下の行も書き直す(描いた点は消える。観察)
        if self.spare_row:
            self.spare_row = False
            self.console.show([])
            self.console.commit()
        super()._prompt()
        if textmode.is_on(self.m):
            self.screen.show([self.TEXT_PROMPT])

    def _entered_code(self, mode: str) -> bytes:
        """TEXTモードのPROモードで打った行番号のある行は、打ったとおりの字で登録する"""
        text = self.editor.text()
        if mode == "PRO" and textmode.is_on(self.m) and text[:1].isdigit():
            return text
        return super()._entered_code(mode)

    def _direct(self, code: bytes, mode: str):
        head = code[0] if code else None
        # 24字ちょうどの行の命令のあとは、カーソルのあった行を空けて>を出す(観察)
        self.spare_row = self.full_line and head in self.STATEMENTS
        if head in DRAWING:
            yield from self._draw(code)
            return None
        if head in (_CODE["TEXT"], _CODE["BASIC"]):
            self._convert(head == _CODE["TEXT"], len(code) == 1 and mode == "PRO")
            return None
        if head == _CODE["LOAD"] or head == self.T_LLIST and sio.is_open(self.m):
            # LOADと、開いているあいだのLLISTはシリアルの相手を待つ(閉じていればLOADは、
            # プログラムがなければLLISTは何もしない。LOADのあとに何か書いてあればERROR 1。
            # 観察)
            if head == _CODE["LOAD"] and len(code) > 1:
                raise BasicError(1, 1)
            if sio.is_open(self.m) and (head == _CODE["LOAD"] or self.PROGRAM.lines(self.m)):
                yield from cast(Runner, self.runner).wait_link()
            self._prompt()
            return None
        return (yield from super()._direct(code, mode))

    def _draw(self, code: bytes):
        """打った行の描く命令。描いたあとは>を出さず、次に打つ行は下の行から書く(観察)"""
        r = self.runner
        r.code, r.pos = code, 1
        if code[0] == _CODE["GPRINT"]:
            # 打ったGPRINTは、打った行の下の行の左端から書く(観察)
            row = self.console.next_start() // self.console.width
            self.graphics.gx, self.graphics.gy = 0, row * 8 + 7
        try:
            yield from self.STATEMENTS[code[0]](r)
        except BasicError as err:
            err.at(0)
            raise
        except DrawStopped:
            self._prompt()  # 描いたところまでは残し、打った行の下に>(観察)
            return
        yield self.TIMES.STATEMENT + r.meter.take()
        self.answer = b""
        self.state = "result"

    def _convert(self, to_text: bool, allowed: bool) -> None:
        """TEXT・BASIC: プログラムのどの行も字の並びにするか、中間コードに戻す。PROモードで
        TEXTかBASICだけを打ったときだけ効く。ほかのときと、すでにそのモードのときと、パスワードで
        保護しているときはERROR 1(観察)"""
        if not allowed or textmode.is_on(self.m) == to_text or self.PASSWORD.locked(self.m):
            raise BasicError(1, 0)
        p = self.PROGRAM
        data = b""
        for n, a in p.lines(self.m):
            body = p.body(self.m, a)
            if to_text:
                body = textmode.spelled(body, self.keywords)[: textmode.MAX_BODY]
            else:
                body = self.lexer.tokenize(body)
            if body:
                data += p._line(n, body)
        p.put(self.m, p.first(self.m), data)
        textmode.set_on(self.m, self.VARS, to_text)
        self._prompt()

    def _resumed(self, where: str, at: tuple[int, int]):
        """打った命令でシリアルの相手を待っているところで保存したなら、また待つ"""
        if where == "link":
            yield from cast(Runner, self.runner).wait_link()
            self._prompt()
            yield from self._main(keep=True)
        else:
            yield from super()._resumed(where, at)

    def _def_run(self, key: str, text, value):
        """DEFのキーで実行すると、出している表示(>など)は残し、その下の行から出す。4行目に
        出しているときは、スクロールせずにその行に書く。エラーのあと←・→で呼び出す行は、
        打っていた行の所に書く(観察)"""
        c = self.console
        self._input_at()
        if c.row + c.used < ROWS:
            c.commit()
        yield from super()._def_run(key, text, value)

    def peek(self, line: int, pos: int):
        """↑を離すと、液晶を消して1行目に>(観察)"""
        yield from super().peek(line, pos)
        self.console.clear()
        self._prompt()

    def _message_key(self, k: str) -> bool:
        if self.state == "error" and k in ("LEFT", "RIGHT"):
            self.console.back(self._recall_row())  # エラーの行を消し、打った行を書き直す(観察)
        return super()._message_key(k)

    def _message(self, text: bytes) -> None:
        """プログラムのメッセージは、下の行の左から(左の空白は付けない。観察)"""
        self._below_cls()
        self.console.show(list(bytes(text).lstrip(bytes([self.SPACE]))))
        self.console.commit()

    def _show_line(self, n: int, a: int) -> None:
        """登録した行を、液晶を消して1行目から出し、続く行も4行目まで並べる(観察)"""
        self._listing(n, ":")
        self.state, self.line_no = "shown", n

    def _list_from(self, n: int, sep: str) -> None:
        """行nから4行目まで並べ、行nの所をいまの表示にする(そこで書き直す)"""
        found = self.PROGRAM.at_or_after(self.m, n)
        used = len(self._line_rows(*found, self._sep(sep))) if found else 1
        self._listing(n, sep)
        c = self.console
        c.row, c.used, c.kept = 0, used, False

    def _listing(self, n: int, sep: str) -> None:
        """行n以上の行を、液晶を消して1行目から4行目まで並べる。sepは行番号のあとの字
        (編集しているあいだは空白。TEXTモードでは置かない。観察)"""
        sep = self._sep(sep)
        rows: list[list[int]] = []
        for number, at in self.PROGRAM.lines(self.m):
            if number < n:
                continue
            rows += self._line_rows(number, at, sep)
            if len(rows) >= 4:
                break
        self.console.lines(*rows[:4])

    # ---- プログラム ----
    def show_print(self, items, comma: bool, fmt: Format = Format()) -> None:  # noqa: B008
        """PRINTは、ふつうは下の行の頭から、CURSORのあとはその桁から、;で終わったPRINTの
        あとはその続きから、字を上書きする(行の残りは消さない)。4行目を越えるとスクロールする。
        数は、続けて書くとき以外は右に寄せる。PRINTだけは何も書かない(観察)"""
        if not items:
            self.print_pos = None
            self.display(True)
            self.state = "print"
            return
        trailing = self.runner.trailing
        cont = self.print_pos is not None
        text = self.print_text(items, comma, fmt, joined=(cont or trailing) and not comma)
        scrolls = self.console.scrolls
        at = self.print_pos if cont else self.console.next_start()
        end = self.console.write(at or 0, list(text))
        self.runner.meter.add(SCROLL_TIME * (self.console.scrolls - scrolls))
        self.print_pos = end if trailing else None
        numbers = [v for v in items if isinstance(v, Decimal)]
        if numbers:
            self.last_number = self.display_number(numbers[-1])
        self.display(True)
        self.state = "print"
        self.last_value = items[-1] if items else None

    def input_error(self, number: int, text: bytes, pos: int):
        """INPUTの答えのエラー。←・→、CLS、↑で、エラーを消して答えの行に戻る。↑は押して
        いるあいだ、液晶を消してINPUTの行を出す(観察)"""
        self._input_at()  # 打った答えの行
        recalled = yield from super().input_error(number, text, pos)
        if recalled is None and "UP" in self.m.held:
            r, before = self.runner, self.stopped_at
            self.stopped_at = (self._line_now(), r.stopped_pos())
            yield from self.hold_up(self._show_stopped())
            self.keys.poll()
            self.stopped_at = before
        self.console.back(self._recall_row())
        return recalled

    def read_input(self, prompt, keep, answer=None):
        """打った答えは残す。BRKで止めたときも、?や打ちかけの字を残す(観察)"""
        try:
            text = yield from super().read_input(prompt, keep, answer)
        finally:
            self.console.commit()
        return text

    def cls(self) -> None:
        self.console.clear()
        self.print_pos = None
        self.cleared = False
        self.graphics.reset()  # GPRINTのカーソルとLINEの始めも初めに戻す(観察)

    def cursor(self, n: int) -> None:
        """CURSOR: 次のPRINTを、液晶の左上から数えてn桁目から書く"""
        self.print_pos = n

    def _run_program(self, steps, resumed: bool = False):
        if not resumed:
            self.print_pos = None
        yield from super()._run_program(self._closing(steps), resumed)

    def _closing(self, steps):
        """プログラムが終わると(ENDか最後の行のあと)シリアルを閉じる。STOP・BRK・エラーで
        止まったときは閉じない(観察)"""
        try:
            yield from steps
        except End:
            sio.set_open(self.m, False)
            raise

    def save(self) -> dict:
        d = super().save()
        c = self.console
        d["console"] = [
            bytes(c.text).hex(), c.row, c.used, c.kept, self.basic_mode, self._recall_row(),
            self.print_pos,
        ]  # fmt: skip
        d["graphics"] = self.graphics.save()
        return d

    def prepare(self, d: object) -> Callable[[], None]:
        apply = super().prepare(d)
        if not isinstance(d, dict):
            return apply
        place = self.graphics.parse(d.get("graphics"))
        console = None
        try:
            text, row, used, kept, mode, input_row, print_pos = d["console"]
            console = (
                list(bytes.fromhex(text)), int(row), int(used), bool(kept),
                "PRO" if mode == "PRO" else "RUN", int(input_row),
                None if print_pos is None else int(print_pos),
            )  # fmt: skip
            # 行と桁が液晶の外なら読まない(表示を送るのに、いつまでもかからないように)
            rows, cells = console[1:3], self.console.cells
            if not (all(0 <= r <= ROWS for r in (*rows, console[5])) and sum(rows) <= ROWS
                    and (console[6] is None or 0 <= console[6] < cells)):  # fmt: skip
                console = None
        except (KeyError, TypeError, ValueError, OverflowError):
            pass

        def both() -> None:
            apply()
            self.graphics.place(place)
            if console is None:
                return
            text, row, used, kept, mode, input_row, print_pos = console
            c = self.console
            shown = text[: c.cells]
            c.text = shown + [0x20] * (c.cells - len(shown))
            c.drawn = list(c.text)  # 液晶RAMは本体の状態で戻る
            c.row, c.used, c.kept = row, used, kept
            self.basic_mode = mode
            self.input_row, self.input_scrolls = input_row, c.scrolls
            self.print_pos = print_pos

        return both

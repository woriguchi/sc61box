"""PC-1261系のROMなしのBASICの本体(PC-1350はpc1350.pyで差し替える)。行の入力と実行は
PC-1251系と同じで、2行の液晶への出し方と、字のコード・中間コードの番号を差し替える

- RUNモードで式や代入を打ってENTERを押すと、1行目に打った行(命令は綴りにして)、2行目に
  答えを出す。エラーは1行目に「 ERROR n」(観察)
- PROモードで登録した行や、LIST・↑・↓で出す行は、1行目にその行、2行目に次の行。長い行は
  2行目へ続ける(観察)
- PRINTは2行ぶんの液晶に書く。CURSORで書く桁を決められ、;で終わったPRINTのあとは続けて
  書く(観察)
- プログラムのメッセージ(ERROR n IN 行番号、BREAK IN 行番号)は1行目に出す(観察)
"""

from collections.abc import Callable, Generator
from decimal import Decimal
from typing import cast

from .. import system, workarea
from ..editor import pieces
from ..errors import BasicError
from ..evaluate import expect_end
from ..system import Steps
from ..using import Format
from ..variables import word as word_at
from . import (
    editor,
    evaluate,
    keyboard,
    lexer,
    password,
    printer,
    program,
    reserve,
    run,
    tapeio,
    tokens,
    variables,
)
from .screen import Screen

_CODE = {name: code for code, name in tokens.KEYWORDS.items()}
# RUNモードで行番号なしに打って実行できる文(観察。ほかの文はERROR 1)
DIRECT_NAMES = (
    "DIM", "CLEAR", "POKE", "CALL", "DEGREE", "RADIAN", "GRAD", "WAIT", "RANDOM", "TRON",
    "TROFF", "BEEP", "USING",
)  # fmt: skip
ANGLE_MARKS = {"DEGREE": ("DEG",), "RADIAN": ("RAD",), "GRAD": ("GRAD",)}
# 直接打った行のエラーで、←・→で行を呼び出したときに2行目に出すメッセージ(観察。5と8は
# まだ観察していない)
ERROR_TEXTS = {
    1: b"SYNTAX ERROR",
    2: b"CALCULATION ERROR",
    3: b"ILLEGAL FUNCTION " + b"\xa5" * 7,
    4: b"TOO LARGE A LINE NUMBER",
    6: b"MEMORY OVERFLOW",
    7: b"PRINT USING ERROR",
    9: b"OTHER ERRORS",
}


class Basic(system.Basic):
    PRINT_BUFFER = 0x67B0  # PRINTの字を置く所(観察)
    PRINT_END, PAUSE_UNMARKS = 0x0D, False
    PROMPT, COLON, SPACE, EQ, COMMA, QUOTE, AT = 0x3E, 0x3A, 0x20, 0x3D, 0x2C, 0x22, 0x40
    T_LIST, T_NEW, T_RUN, T_CONT, T_GOTO = (
        _CODE["LIST"], _CODE["NEW"], _CODE["RUN"], _CODE["CONT"], _CODE["GOTO"]
    )  # fmt: skip
    T_PASS, T_LLIST, T_CSAVE, T_CLOAD, T_MERGE = (
        _CODE["PASS"], _CODE["LLIST"], _CODE["CSAVE"], _CODE["CLOAD"], _CODE["MERGE"]
    )  # fmt: skip
    T_ROM = T_INSTAT = T_INPUT = -1  # INPUTを直接打つとERROR 1(観察)
    T_EQU = 0xB9  # EQU#(PC-1260/1261/1262)
    DIRECT = tuple(_CODE[name] for name in DIRECT_NAMES)
    CODES = keyboard.CODES
    USING_CODES = keyboard.CODES | {"[E]": evaluate.E}
    STATEMENTS = run.Runner.STATEMENTS
    EVALUATOR, RUNNER, SCREEN = evaluate.Evaluator, run.Runner, Screen
    KEYBOARD, EDITOR, LEXER = keyboard.Keyboard, editor.Editor, lexer.Lexer
    PROGRAM, VARS = program.PC1261, variables.PC1261
    TIMES = evaluate.Evaluator.TIMES
    PASSWORD, RESERVE = password.PC1261, reserve.PC1261
    TAPEIO = tapeio.TapeIO
    PRINTOUT = printer.PrintOut
    ERROR_MARK = "ERROR"
    INPUT_CL_ASKS = True  # 観察
    # CALLの番地の最後のバイトの番地をXに入れる。打った行は中間コードにして67B0hに置く(観察)
    POINTER_IN_X = True
    LINE_HEAD = 3  # 行番号と長さ
    TYPED_AT, TYPED_SIZE, TYPED_FILL = 0x67B0, 0x50, b"\x0d"
    CALL_R = 0x56
    # 呼んだ先の頭ではA=00h、B=66h、Y=66DDh(打った行でもプログラムの中でも。観察)。LC-3は
    # このA・Bを頼りにするので、前のマシン語が残した値のままにしない
    CALL_REGS = {2: 0x00, 3: 0x66, 6: 0xDD, 7: 0x66}

    def _direct(self, code: bytes, mode: str) -> Generator[int, None, Decimal | bytes | None]:
        if code and code[0] == self.T_EQU:
            self._equ(code, mode)
            return None
        return (yield from super()._direct(code, mode))

    def _equ(self, code: bytes, mode: str) -> None:
        """EQU#n: プログラムの場所の頭を、機種の既定からn×80hだけ後ろへ動かす(その手前の
        RAMをマシン語に使う)。PROモードで、プログラムがないときだけ。nは式で、小数は切り捨てる。
        負か文字列ならERROR 1、頭が配列の下端に届けばERROR 6。式のあとに続きがあれば、頭を
        動かしてからERROR 1。NEWでは戻らず、EQU#0で戻る(観察)"""
        if mode != "PRO" or self.PROGRAM.lines(self.m):
            raise BasicError(1, 0)
        e = self.EVALUATOR(self.m, code, 1, self.runner.meter)
        v = e.expression()
        # 切り捨てる前に負かを見る(EQU#-.5もERROR 1)。文字列はERROR 9ではなくERROR 1(観察)
        if not isinstance(v, Decimal) or v < 0:
            raise BasicError(1, 0)
        m = self.m
        base = m.model.prog_start + int(v) * m.EQU_STEP
        if base + 1 >= word_at(m, self.VARS.ARRAY_PTR):
            raise BasicError(6, 0)
        program.PC1261.set_base(m, base)
        expect_end(e)  # 続きがあってもERROR 1にするのは、頭を動かしたあと(観察)
        self._prompt()

    def __init__(self, m) -> None:
        super().__init__(m)
        self.lcd = cast(Screen, self.screen)  # 2行の液晶(Screen.linesなどを使うための型)
        # PRINTで出した字(2行ぶん)、次に書く桁、次のPRINTがそこから続けて書くか(;で終わった
        # PRINTのあとと、CURSORのあと)
        self.page = [self.SPACE] * self.screen.cells
        self.page_pos = 0
        self.page_cont = False
        # 最後に出したか、プログラムで変数に入れた数(RUNモードの↑・↓で呼び出す。観察)
        self.last_number = b"0."
        self.error_number = 0  # 直接打った行のエラーの番号
        self.notice_row: list[int] | None = None  # 2行目に出しているエラーメッセージ

    def display(self, on: bool) -> None:
        """液晶を消して実行しているあいだは、BUSYの記号を点ける(観察)"""
        super().display(on)
        self.screen.symbol("BUSY", not on)

    def assigned(self, value: Decimal | bytes) -> None:
        """プログラムで数の変数に入れた値も、↑・↓で呼び出す数にする(FOR・NEXTは除く。
        観察)"""
        if isinstance(value, Decimal):
            self.last_number = self.display_number(value)

    def _power_on(self) -> None:
        self.screen.symbol("PRINT", False)
        p = cast(program.Program, self.PROGRAM)
        p.set_start(self.m, p.start(self.m))  # いまのプログラムの頭の番地を置く(観察)
        self.set_angle("DEGREE")

    def set_angle(self, which: str) -> None:
        for name in ("DEG", "RAD", "GRAD"):
            self.screen.symbol(name, name in ANGLE_MARKS[which])

    def _answer(self, value: Decimal, code: bytes) -> bytes:
        """USINGで数の書式を決めてあれば、答えの数もその書式で出す(入らなければERROR 7で、
        エラーの位置は行の終わり。観察)"""
        number = self.runner.using.number
        if number is None:
            return self.display_number(value)
        d = self.dialect
        try:
            text = number.field(value, self.USING_CODES, d.using_zero_quirk, d.using_limit)
        except BasicError as e:
            raise e.at(len(code)) from None
        return text.lstrip(bytes([self.SPACE]))

    def _show_result(self, value: Decimal | bytes) -> None:
        """1行目に打った行、2行目に答え(数は右に寄せる)"""
        echo, _ = self._layout(self.last_line)
        width = self.screen.width
        if isinstance(value, Decimal):
            answer = [self.SPACE] * (width - len(self.answer)) + list(self.answer)
            self.last_number = self.answer
        else:
            answer = list(self.spell(value))
        self.lcd.lines(echo, answer)

    def save(self) -> dict:
        d = super().save()
        d["page"] = bytes(self.page).hex()
        d["page_at"] = [self.page_pos, self.page_cont]
        d["last_number"] = self.last_number.hex()
        return d

    def prepare(self, d: object) -> Callable[[], None]:
        apply = super().prepare(d)
        extra: dict = {}
        if isinstance(d, dict):
            try:
                page = bytes.fromhex(d.get("page", ""))
                if len(page) == self.screen.cells:
                    extra["page"] = list(page)
                pos = int(d["page_at"][0])
                if 0 <= pos <= self.screen.cells:  # 範囲の外なら、いまの位置のまま
                    extra["page_pos"], extra["page_cont"] = pos, bool(d["page_at"][1])
                extra["last_number"] = bytes.fromhex(d.get("last_number", "302e"))
            except (KeyError, IndexError, TypeError, ValueError, OverflowError):
                pass

        def both() -> None:
            apply()
            for name, v in extra.items():
                setattr(self, name, v)

        return both

    def _show_editor(self) -> None:
        """登録した行を編集しているあいだ、行が1行目に収まれば2行目はそのまま。エラーの
        行を呼び出したときは、2行目にエラーメッセージを出す(観察)"""
        text, cursor, shape = self.editor.view(
            self.screen.cells, self.keywords, self.CODES, self.blink_off
        )
        width = self.screen.width
        notice = self.state in ("input", "input-wait")
        keep = self.notice_row if notice else self.lcd.text[width:]
        if (notice or self.state in ("edit", "error-line")) and len(text) <= width and keep:
            if cursor is None or cursor < width:
                text = text + [self.SPACE] * (width - len(text)) + keep
        if self.state == "input-wait":
            self.notice_row = None  # INPUTの答えを呼び出したときのメッセージは、次のキーで消える
        self.screen.show(text, cursor, shape)

    def _notice(self, number: int) -> list[int]:
        """2行目に出すエラーメッセージ"""
        width = self.screen.width
        text = ERROR_TEXTS.get(number, b"")[:width]
        return list(text) + [self.SPACE] * (width - len(text))

    def input_error(self, number: int, text: bytes, pos: int):
        """INPUTの答えのエラーで←・→を押すと、答えを呼び出し、2行目にエラーメッセージを出す
        (次のキーで消える。観察)"""
        recalled = yield from super().input_error(number, text, pos)
        if recalled is not None:
            self.notice_row = self._notice(number)
        return recalled

    def _message_key(self, k: str) -> bool:
        """直接打った行のエラーで←・→を押すと、行を呼び出し、2行目にエラーメッセージを出す
        (次のキーで消える。観察)"""
        number = self.error_number
        go_on = super()._message_key(k)
        if self.state == "input" and k in ("LEFT", "RIGHT"):
            self.notice_row = self._notice(number)
            self._show_editor()
        return go_on

    def _enter(self, mode: str):
        empty = (
            self.state in ("prompt", "result") or self.state == "input" and not self.editor.units
        )
        yield from super()._enter(mode)
        if empty:
            self._enter_empty()

    def _enter_empty(self) -> None:
        """何も打たずにENTERを押すと、答えを消して>を出す(観察)"""
        self._prompt()

    def _wait_key(self):
        while True:
            k = yield from super()._wait_key()
            if k is not None and self.shift_enter(k):
                continue
            if k is not None:
                self.notice_row = None  # エラーメッセージは次のキーで消える(観察)
            return k

    # ---- 印字モード ----
    def shift_enter(self, k: str) -> bool:
        """SHIFTのあとENTER: プリンタがつながっていれば、印字モード(P)とNPを切り替える。
        PRINT・INPUTの待ちでも、待ったまま切り替える。エラーなどのメッセージ(INPUTの答えの
        エラーも)を出しているあいだは効かない。印字モードかどうかはPRINTの記号(PC-1350では
        液晶に出ないビット)で覚え、電源を入れるとNP(観察)"""
        if k != "ENTER" or not self.keys.was_shifted or self.state in system.MESSAGES:
            return False
        if self.m.printer is not None:
            self.screen.symbol("PRINT", not self.screen.lit("PRINT"))
        return True

    def _printing(self) -> bool:
        return self.mode == "RUN" and self.m.printer is not None and self.screen.lit("PRINT")

    def echo_line(self, code: bytes) -> Steps:
        """印字モードでは、RUNモードで計算する行(式と代入。命令は除く)を、計算する前に
        送る。エラーになっても行は送ってある(観察)"""
        if self._printing():
            units, _ = self._layout(code)
            yield from cast(printer.PrintOut, self.printout).echo(units)

    def echo_value(self, value: Decimal | bytes) -> Steps:
        """印字モードでは、答えも送る。数は液晶と同じ字を右に寄せる(観察)"""
        if self._printing():
            out = cast(printer.PrintOut, self.printout)
            if isinstance(value, Decimal):
                yield from out.echo(list(self.answer), right=True)
            else:
                yield from out.echo(out.units(self.spell(value)))

    def _error(self, number: int) -> None:
        self.error_number = number
        super()._error(number)

    def _debug_key(self, k: str):
        """RUNモードの↑・↓。止まった行も続けられるプログラムもなければ、最後に出した数を
        打った行として呼び出す(はじめは0.。観察)。プログラムのエラーメッセージは、↓では
        消えない(観察)"""
        if k == "UP" and self.stopped_at is not None or k == "DOWN" and self.runner.resume:
            yield from super()._debug_key(k)
            return
        if self.state == "program-error" and k == "DOWN":
            return
        if self.state in system.MESSAGES:
            yield from super()._debug_key(k)
            return
        self.editor = self.EDITOR(self.last_number)
        self.state = "input"
        self._show_editor()

    def _show_line(self, n: int, a: int) -> None:
        """登録した行を「行番号:中身」の形で出す。1行に収まれば、2行目に次の行の頭を出す"""
        rows = self._line_rows(n, a)
        after = self.PROGRAM.next_line(self.m, a)
        n2 = self.PROGRAM.number_at(self.m, after)
        if len(rows) == 1 and n2 is not None:
            rows += self._line_rows(n2, after)[:1]
        self.lcd.lines(*rows[:2])
        self.state, self.line_no = "shown", n

    def _line_rows(self, n: int, a: int, sep: str = ":") -> list[list[int]]:
        """登録した行を液晶の行に分ける。続きの行は「行番号:」の幅だけ空けて始める。命令は
        行をまたがず、入らなければ次の行へ送る(前の空白は捨てる。観察)。sepは行番号のあとの字"""
        head = list(self._codes(f"{n}{sep}"))
        return self._wrapped(head, self.EDITOR.units_of(self.PROGRAM.body(self.m, a)))

    def _wrapped(self, head: list[int], units: list[int], trim: bool = True) -> list[list[int]]:
        """行番号の字headと中身unitsを液晶の行に分ける(_line_rowsの分け方)。trimでなければ、
        行の終わりでも命令の後ろの空白を捨てない(PC-1350で打った行を出し直すとき。観察)"""
        width = self.screen.width
        rows = [list(head)]
        words = pieces(units, self.keywords, self.CODES, **self.EDITOR.style())
        for word, _ in words:
            for piece in [word] if len(word) > 1 else [[c] for c in word]:
                if trim and len(word) > 1 and len(rows[-1]) + len(piece) - 1 == width:
                    piece = piece[:-1]  # 命令の後ろの空白は、行の終わりなら捨てる(観察)
                if len(rows[-1]) + len(piece) > width:
                    rows.append([self.SPACE] * len(head))
                    if piece[0] == self.SPACE and len(piece) > 1:
                        piece = piece[1:]
                rows[-1] += piece
        return rows

    def _run_program(self, steps, resumed: bool = False):
        """始めるときは、PRINTの字と続けて書く所を忘れる(保存した状態から続けるときは残す)"""
        if not resumed:
            self.page = [self.SPACE] * self.screen.cells
            self.page_pos = 0
            self.page_cont = False
        yield from super()._run_program(steps, resumed)

    def cls(self) -> None:
        """CLS: 液晶を消し、PRINTを左上から書くようにする"""
        self.page = [self.SPACE] * self.screen.cells
        self.page_pos = 0
        self.page_cont = False
        self.screen.show(self.page)

    def cursor(self, n: int) -> None:
        """CURSOR n: 次のPRINTを、消さずにn桁目(2行目は24から)から書く"""
        self.page_pos = n
        self.page_cont = True

    def show_print(self, items, comma: bool, fmt: Format = Format()) -> None:  # noqa: B008
        """PRINTの出し方(観察)。ふつうは液晶を消して左上から書き、1行目からはみ出した字は
        2行目へ続ける(2行目の終わりで捨てる)。;で終わったPRINTとCURSORのあとのPRINTは、
        消さずにその桁から続けて書き、数も右に寄せない。,で分けたPRINTは、いつも消して
        1行目を半分ずつ使う。PRINTだけは、いまの字を変えずに出す(;のあとでも、次のPRINTは
        消してから書く)"""
        if not items:
            self.page_cont = False
            self.screen.show(self.page)
            self.display(True)
            self.state = "print"
            return
        trailing = self.runner.trailing
        cont = self.page_cont and not comma
        text = self.print_text(items, comma, fmt, joined=cont or trailing)
        if not cont:
            self.page = [self.SPACE] * self.screen.cells
            self.page_pos = 0
        for c in text:
            if self.page_pos < len(self.page):
                self.page[self.page_pos] = c
            self.page_pos += 1
        self.page_cont = trailing
        numbers = [v for v in items if isinstance(v, Decimal)]
        if numbers:
            self.last_number = self.display_number(numbers[-1])
        self.screen.show(self.page)
        w = self.EVALUATOR.WORK
        if w is not None and w.print_page is not None:  # 出した字(観察)
            workarea.put(self.m, w.print_page, bytes(self.page))
        if self.PRINT_BUFFER is not None:
            self.put_text(text)
        self.display(True)
        self.state = "print"
        self.last_value = items[-1] if items else None

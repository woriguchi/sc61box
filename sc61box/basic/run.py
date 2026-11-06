"""プログラムの実行(系統によらない部分)

Runnerは、登録した行を順に実行する。待つ文(PRINT、INPUT、PAUSE、CALLなど)は、
Basicのメソッド(液晶に出す、キーを待つ、CPUに渡す)を使う。字のコードと中間コードの番号は、系統ごとの
子クラス(pc1251/run.py、pc1261/run.py)が決める。
"""

from collections.abc import Generator
from dataclasses import dataclass
from decimal import Decimal

from ..machine import CLOCK
from . import program, timing, variables
from .errors import BasicError
from .evaluate import Evaluator, expect_end, number
from .timing import Meter
from .using import Format, NumberFormat

Steps = Generator[int, None, None]

MAX_GOSUB, MAX_FOR = 10, 5  # 重ねられるGOSUBとFORの数(別々に数える。観察)


class End(Exception):
    """プログラムが終わった(END、最後の行)"""


class Break(Exception):
    """プログラムが止まった。CONTか↓で続けられる。posは止まった所(最後に実行した文の最後の
    単位)の行の中の位置。kindは止まり方で、液晶の出し方が違う(観察)

    stop: STOPかBRK。「BREAK IN 行番号」を出す
    step: TRONのとき、または↓で1行ずつ進めたとき。行を終えて「行番号:」を出す
    quiet: PRINTの待ちで↑を押して離したか、CLか字のキーを押した。>を出す(字のキーなら
    keyに入れ、その字を打ち始める)
    mode: 実行中か、PRINT・INPUTの待ちで、モードを変えた。新しいモードの>を出す
    """

    def __init__(self, line: int, pos: int = 0, kind: str = "stop", key: str = "") -> None:
        super().__init__(f"BREAK IN {line}")
        self.line = line
        self.pos = pos
        self.kind = kind
        self.key = key


class LineError(Exception):
    """プログラムの行で起きたエラー。posは行の中のエラーの位置"""

    def __init__(self, number: int, line: int, pos: int = 0) -> None:
        super().__init__(f"ERROR {number} IN {line}")
        self.number = number
        self.line = line
        self.pos = pos


@dataclass(frozen=True)
class Typed:
    """DEFで実行を始めたときに打っていた行(字の並び)。AREADが読むときに、文字列の変数には
    字の並びのまま入れ、数の変数には式として計算して入れる(観察)"""

    text: bytes


class TypedError(Exception):
    """AREADで打っていた行を計算したときのエラー。プログラムの行のエラーではなく、打った行の
    エラーとして出す(←・→で打った行をエラーの位置にカーソルを置いて呼び出せる。観察)"""

    def __init__(self, number: int, code: bytes, pos: int) -> None:
        super().__init__(f"ERROR {number}")
        self.number = number
        self.code = code  # 打った行の中間コード
        self.pos = pos


@dataclass
class Loop:
    """FORの繰り返し"""

    ref: variables.Ref
    limit: Decimal
    step: Decimal
    addr: int  # FORの文のあとから続ける
    pos: int


class Runner:
    """登録した行を実行する。字のコードと中間コードの番号、文の表、式の読み方とプログラム・
    変数の置き方は、系統ごとの子クラスがクラスの属性に入れる"""

    WAIT_AT: int | None = None  # WAITの値(下位が先、WAITだけならFFFFh)を置く番地(観察)

    # 字のコード
    COLON: int
    SEMICOLON: int
    DOLLAR: int
    COMMA: int
    EQ: int
    LPAREN: int
    RPAREN: int
    MUL: int
    QUOTE: int
    # 中間コード
    T_TO: int
    T_STEP: int
    T_THEN: int
    T_GOTO: int
    T_GOSUB: int
    T_DATA: int
    T_USING: int
    TOKEN: int  # 中間コードの最初の番号
    NOT_STATEMENTS: frozenset[int]  # 文の頭に来るとERROR 9になる中間コード
    STATEMENTS: dict = {}  # 文(中間コードで引く)
    # ふるまいの違い
    TRAILING_SEMICOLON = False  # PRINTの終わりに;を置ける(PC-1261系とPC-1350)
    COMMA_ITEMS = 2  # PRINTを,で分けられる数(PC-1261系とPC-1350は4)
    FOR_INTEGERS = True  # FORの終わりと増分を整数にする(PC-1261系とPC-1350はしない)
    # 出すもののないPRINT・PAUSE・LPRINTで出すもの(NoneならERROR 1。PC-1261系とPC-1350)
    EMPTY_PRINT: list[Decimal | bytes] | None = None
    NEXT_ADDS_FIRST = False  # NEXTで、足してから終わりを調べる(PC-1261系とPC-1350)
    EVALUATOR: type[Evaluator]
    PROGRAM: program.Program  # プログラムと変数の置き方
    VARS: variables.Variables
    TIMES: timing.Timing  # かかる時間

    def __init__(self, basic) -> None:
        self.basic = basic
        self.m = basic.m
        self.addr = 0  # いまの行の番地
        self.code = b""  # いまの行の中身
        self.pos = 0
        self.meter = Meter()  # 文の実行にかかった時間をためる
        self.stmt = 0  # いまの文の頭の位置
        self.at = (0, 0)  # 状態を保存したときに、実行を続ける(行の番地, 位置)
        self.mode = basic.mode  # 実行を始めたときのモード
        self.loops: list[Loop] = []
        self.returns: list[tuple[int, int]] = []
        # 次に読むDATAの(行の番地, 中身の中の位置)。位置がNoneなら、その行から先のDATAの
        # 行を探す。全体がNoneなら最初の行から探す
        self.data: tuple[int, int | None] | None = None
        self.resume: tuple[int, int] | None = None  # CONTで続ける(行の番地, 位置)
        self.wait: int | None = None  # WAITで決めたPRINTの待ち(サイクル)。NoneならENTERを待つ
        self.tron = False  # TRON: 1行ごとに止まる
        # AREADで読む値(DEFで実行を始めたときの答えか、打っていた行)。freshは、実行を始めてから
        # まだ文を実行していない(ラベルを除く)。AREADが値を読めるのはそのときだけ(観察)
        self.aread: Decimal | bytes | Typed | None = None
        self.fresh = False
        self.using = Format()  # USINGの書式
        self.stepping = False  # ↓で、いまの行を終えたら止まる
        # PRINT・INPUTの待ちで↓を押して止まったあとは、CONTが何もしない(↓では続けられる。観察)
        self.waited_step = False
        self.dead_cont = False
        self._jumped = False
        self._chained = False
        self.trailing = False  # いまのPRINTが;で終わった(PC-1261系とPC-1350)

    # ---- 始め方 ----
    def start(self, line: int | bytes | None) -> Steps:
        """RUN: 配列とDATAの位置を消し、WAITをやめて(PRINTはENTERを待つ)、行番号かラベルの
        行(なければ最初の行)から実行する(観察)"""
        self.VARS.clear_arrays(self.m)
        self.data = None
        self.using = Format()
        self.wait = None
        yield from self.go(line)

    def go(self, target: int | bytes | None) -> Steps:
        """GOTO: 変数とDATAの位置はそのままで、FOR・GOSUBを忘れて、行番号かラベルの行(なければ
        最初の行)から実行する(観察)"""
        self.addr = 0  # 行番号は、いまのプログラムから探す
        if target is None:
            found = self.PROGRAM.lines(self.m)[:1]
            if not found:
                raise End
            addr = found[0][1]
        else:
            addr = self._find(target)
        yield from self.run_from(addr)

    def run_from(self, addr: int) -> Steps:
        """番地addrの行から実行する(GOTOとDEF)"""
        self.basic.printout.program_started()
        self.loops.clear()
        self.returns.clear()
        self.fresh = True
        self.stepping = False  # ↓で終わりまで進めたあとのRUN・GOTOは、1行ずつ止まらない
        self.waited_step = self.dead_cont = False
        yield from self._execute(addr, 0)

    def cont(self) -> Steps:
        if self.resume is None:
            raise BasicError(9)
        if self.dead_cont:
            raise End
        addr, pos = self.resume
        yield from self._execute(addr, pos)

    def resume_at(self, at: tuple[int, int]) -> Steps:
        """保存した状態から: FOR・GOSUBなどはそのままで、atから実行を続ける"""
        yield from self._execute(*at)

    def after_call(self, at: tuple[int, int]) -> Steps:
        """保存した状態から: CALLから戻ったときの扱いをしてから、atから続ける"""
        yield from self._execute(*at, returned=True)

    def after_print(self, at: tuple[int, int]) -> Steps:
        """保存した状態から: PRINTの待ちに戻り、ENTERでatから続ける"""
        self.addr, self.pos = at
        self.code = self.PROGRAM.body(self.m, self.addr)
        self.mode = self.basic.mode
        try:
            yield from self.basic.wait_enter()
        except BasicError as e:
            raise LineError(e.number, self.PROGRAM.number_at(self.m, self.addr) or 0) from None
        yield from self._execute(self.addr, self.pos)

    # ---- 状態の保存 ----
    def save(self) -> dict:
        """FOR・GOSUB、DATAの位置、USING、WAIT、TRONなど、RAMの外のBASICの状態"""
        u = self.using
        return {
            "loops": [
                [lp.ref.addr, lp.ref.string, lp.ref.fixed, lp.ref.size, str(lp.limit),
                 str(lp.step), lp.addr, lp.pos]
                for lp in self.loops
            ],
            "returns": [list(r) for r in self.returns],
            "data": list(self.data) if self.data is not None else None,
            "resume": list(self.resume) if self.resume is not None else None,
            "wait": self.wait,
            "tron": self.tron,
            "using": [
                [u.number.width, u.number.decimals, u.number.dot, u.number.exponent]
                if u.number else None,
                u.text,
            ],
            "addr": self.addr, "pos": self.pos, "stmt": self.stmt, "at": list(self.at),
            "aread": (self.aread.hex() if isinstance(self.aread, bytes)
                      else ["t", self.aread.text.hex()] if isinstance(self.aread, Typed)
                      else None if self.aread is None else ["n", str(self.aread)]),
            "fresh": self.fresh, "waited_step": self.waited_step, "dead_cont": self.dead_cont,
        }  # fmt: skip

    def parse(self, d: object) -> dict:
        """saveで書いたものを読み、戻す属性の値を返す(何も変えない)。形が違えばKeyError・
        TypeError・ValueErrorなど"""
        if not isinstance(d, dict):
            raise TypeError(d)
        raw = d.get("aread")
        if isinstance(raw, str):
            aread: Decimal | bytes | Typed | None = bytes.fromhex(raw)
        elif raw is None:
            aread = None
        else:
            aread = Typed(bytes.fromhex(raw[1])) if raw[0] == "t" else Decimal(raw[1])
        data, resume = d["data"], d["resume"]
        if data is not None:
            data = (self._addr_in(data[0]), None if data[1] is None else self._pos_in(data[1]))
        num, text = d["using"]
        wait = d["wait"]
        return {
            "loops": [
                Loop(
                    variables.Ref(self._addr_in(a), bool(st), bool(fx), _count_in(sz, 0x100)),
                    Decimal(lim),
                    Decimal(stp),
                    self._addr_in(ad),
                    self._pos_in(ps),
                )
                for a, st, fx, sz, lim, stp, ad, ps in d["loops"]
            ],
            "returns": [(self._addr_in(a), self._pos_in(p)) for a, p in d["returns"]],
            "data": data,
            "resume": None if resume is None else self._place_in(resume),
            "wait": None if wait is None else _count_in(wait, 1 << 32),
            "tron": bool(d["tron"]),
            "using": Format(
                NumberFormat(
                    _count_in(num[0], 0x100), _count_in(num[1], 0x100), bool(num[2]), bool(num[3])
                )
                if num
                else None,
                None if text is None else _count_in(text, 0x100),
            ),  # fmt: skip
            "addr": self._addr_in(d["addr"]),
            "pos": self._pos_in(d["pos"]),
            "stmt": self._pos_in(d["stmt"]),
            "at": self._place_in(d["at"]),
            "aread": aread,
            "fresh": bool(d.get("fresh")),
            "waited_step": bool(d.get("waited_step")),
            "dead_cont": bool(d.get("dead_cont")),
        }

    def _addr_in(self, v: object) -> int:
        """状態に書いた番地。行の頭といちばん長い行がメモリに入らない番地ならValueError
        (続けたときに、メモリの外を読まないように。プログラムと変数はメモリの終わりから離れている)"""
        return _count_in(v, len(self.m.mem) - LINE_ROOM)

    @staticmethod
    def _pos_in(v: object) -> int:
        """状態に書いた、行の中の位置"""
        return _count_in(v, 0x100)

    def _place_in(self, v: object) -> tuple[int, int]:
        """状態に書いた(行の番地, 行の中の位置)"""
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            raise TypeError(v)
        return self._addr_in(v[0]), self._pos_in(v[1])

    def step(self) -> Steps:
        """↓: 止まっている所から、その行の終わりまで実行して止まる"""
        self.stepping = True
        self.dead_cont = False
        if self.resume is not None:
            addr, pos = self.resume
            last = self.PROGRAM.number_at(self.m, addr) is None  # 最後の行のあとで止まった
            if not last and pos >= len(self.PROGRAM.body(self.m, addr)):
                # 行の終わりで止まっていれば、次の行を終えるまで実行する(観察)
                self.resume = (self.PROGRAM.next_line(self.m, addr), 0)
        yield from self.cont()

    def _lines(self) -> list[tuple[int, int]]:
        """実行している行のプログラム(直接打った行なら、いまのプログラム)の行"""
        return self.PROGRAM.lines(self.m, self.PROGRAM.block_first(self.m, self.addr))

    def _line(self, n: int) -> list[tuple[int, int]]:
        return [(number, a) for number, a in self._lines() if number == n]

    def _label(self, label: bytes) -> tuple[int, int] | None:
        mark = bytes([self.QUOTE]) + label + bytes([self.QUOTE])
        return self.PROGRAM.find_label(self.m, mark) if label else None

    def _lookup(self, target: int | bytes) -> tuple[int, int] | None:
        """行番号かラベル(文字列)の行の(行番号, 番地)"""
        if isinstance(target, bytes):
            return self._label(target)
        return next(iter(self._line(target)), None)

    def _find(self, target: int | bytes) -> int:
        """行番号かラベルの行の番地。なければERROR 4"""
        found = self._lookup(target)
        if found is None:
            raise BasicError(4)
        return found[1]

    # ---- 実行 ----
    def _execute(self, addr: int, pos: int, returned: bool = False) -> Steps:
        """addrの行のposから実行する。returnedなら、CALLの文のマシン語から戻ったところから"""
        self.addr, self.pos = addr, pos
        self.resume = None
        self.mode = self.basic.mode
        while True:
            n = self.PROGRAM.number_at(self.m, self.addr)
            if n is None:
                raise End
            self.code = self.PROGRAM.body(self.m, self.addr)
            # 行の途中(FORのあと、GOSUBのあと、STOPのあと)から続けるときは、区切りの:を飛ばす
            if not returned and 0 < self.pos < len(self.code) and self.code[self.pos] == self.COLON:
                self.pos += 1
            try:
                while returned or self.pos < len(self.code):
                    if returned:
                        returned = False
                        self._call_returned()
                    else:
                        if self.m.brk or self.basic.mode != self.mode:
                            # BRKか、モードを変えた(観察: どちらもCONTで続けられる)
                            self.resume = (self.addr, self.pos)
                            kind = "stop" if self.m.brk else "mode"
                            raise Break(n, self.stopped_pos(), kind)
                        self.at = (self.addr, self.pos)
                        yield self.TIMES.STATEMENT
                        yield from self._statement()
                    self.at = (self.addr, self.pos)
                    spent = self.meter.take()
                    if spent:
                        yield spent
                    if self._jumped:
                        break
                    if self._chained:
                        self._chained = False
                        continue
                    if self.pos < len(self.code):
                        if self.code[self.pos] != self.COLON:
                            raise BasicError(1, self.pos)
                        self.pos += 1
                        if self.pos == len(self.code):
                            raise BasicError(1, self.pos)  # :のあとに文がない(観察)
            except BasicError as e:
                raise LineError(e.number, n, self.pos if e.pos is None else e.pos) from None
            if self._jumped:
                self._jumped = False
            else:
                self.addr, self.pos = self.PROGRAM.next_line(self.m, self.addr), 0
                self.at = (self.addr, 0)
                yield self.TIMES.NEXT_LINE
            if self.tron or self.stepping:
                # 行を終えたところで止まる(観察: TRONのときと、↓を押したとき)
                self.stepping = False
                self.dead_cont = self.waited_step and self.basic.dialect.print_step_ends
                self.waited_step = False
                self.resume = (self.addr, self.pos)
                raise Break(n, len(self.code) - 1, "step")

    def stopped_pos(self) -> int:
        """止まった所として見せる位置: 最後に実行した文の最後の単位(観察)"""
        pos = self.pos - 1
        if 0 < pos < len(self.code) and self.code[pos] == self.COLON:
            pos -= 1
        return max(pos, 0)

    def _jump(self, addr: int, pos: int = 0) -> None:
        self.addr, self.pos = addr, pos
        self._jumped = True

    def _goto_line(self, n: int | bytes, line_end: bool = False) -> None:
        """行番号かラベル(文字列)nの行へ跳ぶ。行がなければERROR 4で、位置は行番号の最後の字。
        line_endなら、行があることを確かめてから、行の終わりかを確かめる(観察)"""
        if isinstance(n, bytes):
            self._goto_label(n, line_end)
            return
        numbers = [number for number, _ in self._lines()]
        if n not in numbers:
            raise BasicError(4, self.pos - 1)
        if line_end:
            self._line_end()
        # 跳ぶ先を探す時間は、いまの行と跳ぶ先の行のあいだの行の数で決まる(観察: 先の行へは
        # 間の行の数だけかかり、前の行へ跳ぶときは、跳ぶ先より前の行の数にはよらない)
        here = self.PROGRAM.number_at(self.m, self.addr)
        target = numbers.index(n)
        start = numbers.index(here) if here in numbers else 0
        self.meter.add(self.TIMES.JUMP + self.TIMES.JUMP_PER_LINE * abs(target - start))
        found = self._line(n)
        self._jump(found[0][1])

    def _goto_label(self, label: bytes, line_end: bool) -> None:
        """ラベルの行へ跳ぶ。ラベルは、すべてのプログラムの行の頭から、最初の行から順に探す
        (観察: 探す時間は、ラベルの字の数、前にある行の数、前にあるラベルの行の数で決まる)"""
        found = self._label(label)
        if found is None:
            raise BasicError(4, self.pos - 1)
        if line_end:
            self._line_end()
        before = [a for _, a in self.PROGRAM.all_lines(self.m) if a < found[1]]
        marks = sum(self.PROGRAM.body(self.m, a)[:1] == bytes([self.QUOTE]) for a in before)
        t = self.TIMES
        self.meter.add(
            t.LABEL
            + t.LABEL_PER_CHAR * len(label)
            + t.LABEL_PER_LINE * len(before)
            + t.LABEL_PER_MARK * marks
        )
        self._jump(found[1])

    def _target(self) -> int | bytes:
        """跳ぶ先: 行番号の数か、ラベルの文字列(観察)"""
        v = self._expression()
        return v if isinstance(v, bytes) else int(v)

    def _ev(self) -> Evaluator:
        return self.EVALUATOR(self.m, self.code, self.pos, self.meter)

    def _expression(self):
        e = self._ev()
        v = e.expression()
        self.pos = e.pos
        return v

    def _integer(self) -> int:
        return int(number(self._expression()))

    def _take(self, c: int) -> bool:
        if self.pos < len(self.code) and self.code[self.pos] == c:
            self.pos += 1
            return True
        return False

    def _at_end(self) -> bool:
        return self.pos >= len(self.code) or self.code[self.pos] == self.COLON

    def _statement(self) -> Steps:
        """文を1つ実行する。位置の決まらないエラーは、文の頭の位置にする(観察: RETURNの
        ERROR 5はRETURNの位置)"""
        start = self.stmt = self.pos
        try:
            c = self.code[self.pos]
            if c == self.QUOTE:
                # 文字列だけの文は何もしない(行の頭なら、DEFで実行するラベル。観察)
                self.pos = self._ev().skip_string()
                # ラベルのあとは「:」なしで文を書ける(観察)
                self._chained = self.pos < len(self.code) and self.code[self.pos] != self.COLON
                return
            if self.EVALUATOR.is_letter(c):
                self._assign()
                self.fresh = False
                return
            self.pos += 1
            handler = self.STATEMENTS.get(c)
            if handler is None:
                # 文の頭に来られない字や関数はERROR 9、ほかの命令はERROR 1(観察)
                raise BasicError(9 if c < self.TOKEN or c in self.NOT_STATEMENTS else 1)
            result = handler(self)
            if result is not None:
                yield from result
            self.fresh = False
        except BasicError as e:
            e.at(start)
            raise

    # ---- 文 ----
    def _assign(self, let: bool = False) -> None:
        """代入。「,」で区切って続けられる(A=1,B=2。観察)。=がなければ、LETのあとなら
        ERROR 1、LETを省いた文ならERROR 9(観察)"""
        while True:
            start = self.pos
            e = self._ev()
            target = e.target()
            e.claim(target)
            if not e.take(self.EQ):
                # 位置は、LETなら変数のあと、LETを省いた文ならその代入の頭(観察)
                raise BasicError(1, e.pos) if let else BasicError(9, start)
            value = e.expression()
            self.pos = e.pos
            try:
                self._store(e.resolve(target, create=True), value)
            except BasicError as err:
                err.at(e.pos - 1)  # 型が合わないときは、式の最後の字(観察)
                raise
            self.meter.add(self.TIMES.ASSIGN)
            if not self._take(self.COMMA):
                return

    def _store(self, ref: variables.Ref, value: Decimal | bytes) -> None:
        """代入・READ・INPUT・AREADで変数に入れる(入れた値をBasicに知らせる)"""
        self.basic.assigned(self.VARS.write(self.m, ref, value))

    def _let(self) -> None:
        self._assign(let=True)

    def _print(self, pause: bool = False) -> Steps:
        items, comma = self._print_items()
        numbers = sum(isinstance(v, Decimal) for v in items)
        # 字にして書き終えてから液晶を点ける(観察)
        yield self.meter.take() + self.TIMES.PRINT + self.TIMES.PRINT_NUMBER * numbers
        self.basic.show_print(items, comma, self.using)
        if pause:
            self.basic.unmark_text()
            yield self.TIMES.PAUSE
        elif self.wait is not None:
            yield max(self.wait, 1)
        else:
            yield from self.basic.wait_enter()
            return
        self.basic.display(False)

    def _lprint(self) -> Steps:
        """LPRINT: PRINTと同じ形の字を、24字ずつの行にしてプリンタに送る。プリンタが
        なければ、何もせずに次の文へ進む(観察)"""
        if self.m.printer is None:
            while self.pos < len(self.code) and self.code[self.pos] != self.COLON:
                if self.code[self.pos] == self.QUOTE:
                    end = self.code.find(self.QUOTE, self.pos + 1)
                    self.pos = len(self.code) if end < 0 else end + 1
                else:
                    self.pos += 1
            return
        items, comma = self._print_items()
        numbers = sum(isinstance(v, Decimal) for v in items)
        yield self.meter.take() + self.TIMES.PRINT_NUMBER * numbers + self.TIMES.LPRINT
        yield from self.basic.printout.lprint(items, comma, self.using)

    def _statement_end(self) -> int:
        """いまの文の終わり(文字列の外の:か、行の終わり)の位置"""
        return self.statement_end(self.code, self.pos)

    def statement_end(self, code: bytes, i: int) -> int:
        """codeの位置iから先で、文の終わり(文字列の外の:か、行の終わり)の位置"""
        while i < len(code) and code[i] != self.COLON:
            if code[i] == self.QUOTE:
                end = code.find(self.QUOTE, i + 1)
                i = len(code) if end < 0 else end + 1
            else:
                i += 1
        return i

    def _csave(self) -> Steps:
        """プログラムの中のCSAVE・CSAVE M(RUNモードで打ったときと同じ)"""
        end = self._statement_end()
        sent = yield from self.basic.tapeio.csave(self.code[:end], self.pos)
        self.pos = end
        if not sent:
            self._broken()

    def _chain(self) -> Steps:
        """CHAIN ["名前"][,行番号]: テープからプログラムを読み込み、最初の行か行番号の行から
        実行する。変数は残す"""
        end = self._statement_end()
        code = self.code[:end]
        e = self._ev()
        if e.peek() == self.QUOTE:
            e.string_literal()
        line = e.integer() if e.take(self.COMMA) else None
        if e.pos != end:
            raise BasicError(1, e.pos)
        loaded = yield from self.basic.tapeio.cload(code, self.pos)
        if not loaded:
            self.pos = end
            self._broken()
        self.loops.clear()
        self.returns.clear()
        self.resume = None
        found = self._line(line) if line is not None else self.PROGRAM.lines(self.m)[:1]
        if not found:
            if line is None:
                raise End
            raise BasicError(4)
        self._jump(found[0][1])

    def _instat(self) -> None:
        raise BasicError(9)  # プログラムの中のINSTATはERROR 9(観察)

    def _broken(self) -> None:
        """カセットの最中にBRKで止めた: その文で止まる(CONTで次の文から続けられる)"""
        self.resume = (self.addr, self.pos)
        raise Break(self.PROGRAM.number_at(self.m, self.addr) or 0, self.stopped_pos())

    def _print_items(self) -> tuple[list[Decimal | bytes], bool]:
        """PRINT・PAUSE・LPRINTの[USING 書式;]と出すもの。(値の列, ,で分けたか)"""
        if self._take(self.T_USING) and self._set_using(after_print=True) and self._at_end():
            raise BasicError(1, self.pos)  # USINGの;のあとに出すものがない(観察)
        if self._at_end():
            if self.EMPTY_PRINT is not None:
                self.trailing = False
                return list(self.EMPTY_PRINT), False
            raise BasicError(1, self.pos)  # 出すものがない(観察)
        items: list[Decimal | bytes] = []
        separators: list[int] = []
        self.trailing = False
        while not self._at_end():
            items.append(self._expression())
            if self.pos < len(self.code) and self.code[self.pos] in (self.COMMA, self.SEMICOLON):
                separators.append(self.code[self.pos])
                if (
                    self.COMMA in separators
                    and len(separators) > 1
                    and (len(separators) >= self.COMMA_ITEMS or self.SEMICOLON in separators)
                ):
                    # ,で分けられるのは2つ(PC-1261系とPC-1350は4つ)までで、;とも混ぜられない(位置は
                    # 越えた区切り)
                    raise BasicError(1, self.pos)
                self.pos += 1
                if self._at_end():
                    if self.TRAILING_SEMICOLON and separators == [self.SEMICOLON] * len(separators):
                        self.trailing = True
                        break
                    raise BasicError(1, self.pos)
            else:
                break
        if not self._at_end():
            raise BasicError(1, self.pos)
        return items, self.COMMA in separators

    def _set_using(self, after_print: bool = False) -> bool:
        """USING [書式]。書式を省くと、書式をやめる。PRINT USINGでは、書式のあとに;が
        要る(観察)。;を読んだらTrue"""
        if not (self._at_end() or self.code[self.pos] == self.SEMICOLON):
            text = self._expression()
            if not isinstance(text, bytes):
                raise BasicError(9, self.pos - 1)
            fmt = Format.parse(text, self.basic.USING_CODES, self.basic.dialect.using_dot_first)
            self.using = self.using.merged(fmt)
            if after_print and not self._at_end() and self.code[self.pos] != self.SEMICOLON:
                raise BasicError(1, self.pos)
        else:
            self.using = Format()
        if after_print:
            if not self._take(self.SEMICOLON):
                raise BasicError(1, self.pos)
            return True
        return False

    def _using(self) -> None:
        self._set_using()

    def _pause(self) -> Steps:
        return self._print(pause=True)

    def _input(self) -> Steps:
        while True:
            prompt = None
            keep = False
            if self.pos < len(self.code) and self.code[self.pos] == self.QUOTE:
                e = self._ev()
                prompt = e.string_literal()
                self.pos = e.pos
                if self._take(self.SEMICOLON):
                    keep = True
                elif not self._take(self.COMMA):
                    raise BasicError(1)
            e = self._ev()
            ref = e.reference(create=True)
            self.pos = e.pos
            answer: tuple[bytes, int] | None = None
            while True:
                text = yield from self.basic.read_input(prompt, keep, answer)
                if text is None:
                    raise End
                self.basic.display(False)
                if not text:
                    # 何も打たずにENTERを押すと、変数はそのままで次の行へ進む(観察)
                    self.pos = len(self.code)
                    return
                try:
                    self._input_value(ref, text)
                    break
                except BasicError as err:
                    # 答えが式として正しくなければ、エラーを出して答えを打ち直させる(観察)
                    pos = len(text) if err.pos is None else err.pos
                    answer = yield from self.basic.input_error(err.number, text, pos)
            if not self._take(self.COMMA):
                return

    def _input_value(self, ref: variables.Ref, text: bytes) -> None:
        if ref.string:
            value: Decimal | bytes = text
        else:
            ev = self.EVALUATOR(self.m, self.basic.lexer.tokenize(text), 0, self.meter)
            value = ev.expression()
            if ev.pos != len(ev.code):
                raise BasicError(1, ev.pos)
        self._store(ref, value)

    def _if(self) -> None:
        """IF 条件 [THEN] 文。数の条件は正のときだけ成り立つ(負の数では成り立たない)。
        文字列の条件は、空でなければ成り立つ。THENのあとが命令でなければ、式を行番号として
        跳ぶ(観察)"""
        cond = self._expression()
        self.meter.add(self.TIMES.IF)
        if not (cond > 0 if isinstance(cond, Decimal) else cond):
            self.pos = len(self.code)
            return
        if (
            self._take(self.T_THEN)
            and not self._at_end()
            and self.code[self.pos] not in self.STATEMENTS
        ):
            self._goto()
            return
        self._chained = True

    def _goto(self) -> None:
        self._goto_line(self._target(), line_end=True)

    def _line_end(self) -> None:
        """行の流れを変える文(GOTO、RETURN、END、THENの行番号)のあとは、行の終わりで
        なければERROR 1(観察: :が続いてもエラー)"""
        if self.pos < len(self.code):
            raise BasicError(1, self.pos)

    def _gosub(self) -> None:
        n = self._target()
        if len(self.returns) >= MAX_GOSUB:
            raise BasicError(5)
        self.returns.append((self.addr, self.pos))
        self._goto_line(n)

    def _return(self) -> None:
        self._line_end()
        if not self.returns:
            raise BasicError(5)
        self.meter.add(self.TIMES.RETURN)
        self._jump(*self.returns.pop())

    def _for(self) -> None:
        """FOR 変数=初め TO 終わり [STEP 増分]。PC-1251系は増分が0ならERROR 9(PC-1261系と
        PC-1350は繰り返し続ける)。文字列の変数はERROR 9(観察)"""
        e = self._ev()
        ref = e.reference(create=True)
        if ref.string:
            raise BasicError(9)
        if not e.take(self.EQ):
            raise BasicError(1)
        self.VARS.write(self.m, ref, number(e.expression()))  # 初めの値は先に入れる(観察)
        if not e.take(self.T_TO):
            raise BasicError(1)
        limit = self._loop_value(e)
        step = self._loop_value(e) if e.take(self.T_STEP) else Decimal(1)
        self.pos = e.pos
        if not self._at_end():
            raise BasicError(1, self.pos)
        if not step and self.FOR_INTEGERS:
            raise BasicError(9)
        if len(self.loops) >= MAX_FOR:
            raise BasicError(5)
        self.meter.add(self.TIMES.FOR)
        # 同じ変数のFORがあっても、新しく積む(観察: GOTOで同じFORに戻るたびに積まれる)
        self.loops.append(Loop(ref, limit, step, self.addr, self.pos))

    def _loop_value(self, e: Evaluator) -> Decimal:
        """FORの終わりか増分。PC-1251系は整数に切り捨て、−32768〜32767の外はERROR 3。
        PC-1261系とPC-1350はそのまま(観察)"""
        v = number(e.expression())
        if not self.FOR_INTEGERS:
            return v
        n = int(v)
        if not -0x8000 <= n <= 0x7FFF:
            raise BasicError(3)
        return Decimal(n)

    def _next(self) -> None:
        """NEXT 変数(変数は省けない。観察)"""
        e = self._ev()
        ref = e.reference()
        self.pos = e.pos
        while self.loops and self.loops[-1].ref != ref:
            self.loops.pop()
        if not self.loops:
            raise BasicError(5)
        loop = self.loops[-1]
        value = number(self.VARS.read(self.m, loop.ref))
        if self.NEXT_ADDS_FIRST:
            value = number(self.VARS.write(self.m, loop.ref, value + loop.step))
            going = value <= loop.limit if loop.step >= 0 else value >= loop.limit
        else:
            # 足す前の値で終わりを調べる(観察: FOR I=1 TO 4 STEP 2はIが5でも1回回る)
            going = value < loop.limit if loop.step >= 0 else value > loop.limit
        self.meter.add(self.TIMES.NEXT_LOOP)
        if going:
            if not self.NEXT_ADDS_FIRST:
                self.VARS.write(self.m, loop.ref, value + loop.step)
            self._jump(loop.addr, loop.pos)
        else:
            self.loops.pop()

    def _on(self) -> None:
        n = self._integer()
        kind = self.code[self.pos] if self.pos < len(self.code) else None
        if kind not in (self.T_GOTO, self.T_GOSUB):
            raise BasicError(1)
        self.pos += 1
        targets = [self._target()]
        while self._take(self.COMMA):
            targets.append(self._target())
        if 1 <= n <= len(targets):
            if kind == self.T_GOSUB:
                if len(self.returns) >= MAX_GOSUB:
                    raise BasicError(5)
                self.returns.append((self.addr, self.pos))
            self._goto_line(targets[n - 1], line_end=kind == self.T_GOTO)

    def _end(self) -> None:
        self._line_end()
        raise End

    def _stop(self) -> None:
        self.resume = (self.addr, self.pos)
        raise Break(self.PROGRAM.number_at(self.m, self.addr) or 0, self.stopped_pos())

    def _rem(self) -> None:
        self.pos = len(self.code)

    def _read(self) -> None:
        """READ: DATAの値を変数に入れる"""
        while True:
            e = self._ev()
            ref = e.reference(create=True)
            self.pos = e.pos
            try:
                value, after = self._next_data()
            except BasicError as err:
                raise BasicError(err.number, self.pos) from None
            self._store(ref, value)
            # 型が合わずに入れられなかったときは、次もその値を読む(観察)
            self.data = after
            if not self._take(self.COMMA):
                return

    def _data_start(self, code: bytes) -> int | None:
        """行の頭(ラベルがあればそのあと。:があってもよい)のDATAの値の位置(観察)"""
        i = 0
        if code[:1] == bytes([self.QUOTE]):
            end = code.find(self.QUOTE, 1)
            i = len(code) if end < 0 else end + 1
            if code[i : i + 1] == bytes([self.COLON]):
                i += 1
        return i + 1 if code[i : i + 1] == bytes([self.T_DATA]) else None

    def _next_data(self) -> tuple[Decimal | bytes, tuple[int, int | None]]:
        """次のDATAの値と、そのあとの読む位置。DATAは行の頭(ラベルのあとでもよい)にあるもの
        だけを読む。値は式として計算する。値がなければERROR 1、DATAがもうなければERROR 5
        (観察)"""
        addr, pos = self.data if self.data is not None else (self.PROGRAM.first(self.m), None)
        while pos is None:
            if self.PROGRAM.number_at(self.m, addr) is None:
                raise BasicError(5)
            pos = self._data_start(self.PROGRAM.body(self.m, addr))
            if pos is None:
                addr = self.PROGRAM.next_line(self.m, addr)
        code = self.PROGRAM.body(self.m, addr)
        if pos >= len(code) or code[pos] in (self.COMMA, self.COLON):
            raise BasicError(1)
        e = self.EVALUATOR(self.m, code, pos, self.meter)
        value = e.expression()
        if e.pos < len(code) and code[e.pos] == self.COMMA:
            return value, (addr, e.pos + 1)
        return value, (self.PROGRAM.next_line(self.m, addr), None)

    def _restore(self) -> None:
        """RESTORE [n]: 次に読むDATAを、最初か行n(行番号かラベル)から探す。行nがなければERROR 4。nを
        省けるのは行の終わりだけで、:が続くとERROR 1(観察)"""
        if self.pos >= len(self.code) or (
            self.basic.dialect.restore_colon and self.code[self.pos] == self.COLON
        ):
            self.data = None  # PC-1245は:が続いてもよい(観察)
            return
        n = self._target()
        found = self._lookup(n)
        if found is None:
            raise BasicError(4, self.pos - 1)
        self.data = (found[1], None)

    def _data(self) -> None:
        in_string = False
        while self.pos < len(self.code):
            c = self.code[self.pos]
            if c == self.QUOTE:
                in_string = not in_string
            elif c == self.COLON and not in_string:
                return
            self.pos += 1

    def _dim(self) -> None:
        while True:
            e = self._ev()
            try:
                c = e.name()
            except BasicError:
                raise BasicError(1) from None  # 位置は文の頭(観察)
            self.pos = e.pos
            string = self._take(self.DOLLAR)
            if not self._take(self.LPAREN):
                raise BasicError(1)
            dims = [self._integer()]
            if self._take(self.COMMA):
                dims.append(self._integer())
            if not self._take(self.RPAREN):
                raise BasicError(1)
            size = 8
            if string:
                size = self._integer() if self._take(self.MUL) else 16
            self.VARS.dim(self.m, c, string, dims, size)
            if not self._take(self.COMMA):
                return

    def _clear(self) -> None:
        self.VARS.clear(self.m)

    def _wait(self) -> None:
        n = None if self._at_end() else self._integer()
        self.wait = None if n is None else n * CLOCK // 64
        if self.WAIT_AT is not None:  # ROMのある本体と同じ番地にも置く(マシン語が読む)
            v = 0xFFFF if n is None else n & 0xFFFF
            self.m.write(self.WAIT_AT, v & 0xFF)
            self.m.write(self.WAIT_AT + 1, v >> 8)

    def _poke(self) -> None:
        a = self._integer()
        while self._take(self.COMMA):
            v = self._integer()
            if not 0 <= a <= 0xFFFF or not 0 <= v <= 0xFF:
                raise BasicError(3)
            self.m.write(a, v)
            a += 1
        self.meter.add(self.TIMES.POKE)

    def _call(self) -> Steps:
        a = self._integer()
        if not 0 <= a <= 0xFFFF:
            raise BasicError(3)
        yield from self.basic.call_machine(a)

    def _call_returned(self) -> None:
        """保存した状態から: CALLの文のマシン語から戻った。エラーの位置は_statementと同じに決める"""
        try:
            self.basic.call_returned(True)
        except BasicError as e:
            e.at(self.stmt)
            raise

    def _angle(self, which: str) -> None:
        self.basic.set_angle(which)

    def _random(self) -> None:
        self.m.rnd_seed = (self.m.rnd_seed * 6364136223846793005 + 1) & ((1 << 64) - 1) or 1

    def _beep(self) -> Steps:
        """BEEP n: 4kHzの音をn回鳴らす。nが1より小さければ鳴らさない(観察)"""
        n = self._integer()
        m = self.m
        if n < 1:
            yield self.TIMES.BEEP_ON  # 鳴らさずに、1回の鳴る時間だけ待つ(観察)
        for _ in range(max(n, 0)):
            m.out_c(m.pc_out & 0x8F | 0x30)
            yield self.TIMES.BEEP_ON
            m.out_c(m.pc_out & 0x8F)
            yield self.TIMES.BEEP_OFF
            if m.brk or self.basic.mode != self.mode:
                self.resume = (self.addr, self.pos)
                kind = "stop" if m.brk else "mode"
                raise Break(self.PROGRAM.number_at(m, self.addr) or 0, self.stopped_pos(), kind)

    def _aread(self) -> None:
        """AREAD 変数: DEFで実行を始めたときの答えか、打っていた行を入れる。ラベルのすぐあとで
        なければ、数の変数には0、文字列の変数には空を入れる。答えの型が合わなければERROR 9(観察)"""
        e = self._ev()
        ref = e.reference(create=True)
        self.pos = e.pos
        value = self.aread if self.fresh else None
        if isinstance(value, Typed):
            value = value.text if ref.string else self._typed_value(value.text)
        if value is None:
            value = b"" if ref.string else Decimal(0)
        self._store(ref, value)

    def _typed_value(self, text: bytes) -> Decimal:
        """打っていた行を式として計算する。誤りや文字列の答えはTypedError(位置は誤りの所。
        文字列の答えなら行の終わり。観察)"""
        code = self.basic.lexer.tokenize(text)
        try:
            e = self.EVALUATOR(self.m, code, 0, self.meter)
            v = e.expression()
            expect_end(e)
        except BasicError as err:
            pos = len(code) if err.pos is None else min(err.pos, len(code))
            raise TypedError(err.number, code, pos) from None
        if not isinstance(v, Decimal):
            raise TypedError(9, code, len(code))
        return v

    def _tron(self) -> None:
        self.tron = True

    def _troff(self) -> None:
        self.tron = False


STATEMENTS_BY_NAME = {
    "LET": Runner._let,
    "PRINT": Runner._print,
    "PAUSE": Runner._pause,
    "INPUT": Runner._input,
    "IF": Runner._if,
    "GOTO": Runner._goto,
    "GOSUB": Runner._gosub,
    "RETURN": Runner._return,
    "FOR": Runner._for,
    "NEXT": Runner._next,
    "ON": Runner._on,
    "END": Runner._end,
    "STOP": Runner._stop,
    "REM": Runner._rem,
    "LPRINT": Runner._lprint,
    "CSAVE": Runner._csave,
    "CHAIN": Runner._chain,
    "INSTAT": Runner._instat,
    "DATA": Runner._data,
    "READ": Runner._read,
    "RESTORE": Runner._restore,
    "DIM": Runner._dim,
    "CLEAR": Runner._clear,
    "WAIT": Runner._wait,
    "POKE": Runner._poke,
    "CALL": Runner._call,
    "DEGREE": lambda r: r._angle("DEGREE"),
    "RADIAN": lambda r: r._angle("RADIAN"),
    "GRAD": lambda r: r._angle("GRAD"),
    "RANDOM": Runner._random,
    "BEEP": Runner._beep,
    "AREAD": Runner._aread,
    "USING": Runner._using,
    "TRON": Runner._tron,
    "TROFF": Runner._troff,
}


LINE_ROOM = 0x104  # 行の頭(行番号と長さ)と、いちばん長い行が入る大きさ


def _count_in(v: object, limit: int) -> int:
    """状態に書いた0以上limit未満の整数。範囲の外ならValueError、整数でなければTypeError"""
    if isinstance(v, bool) or not isinstance(v, int):
        raise TypeError(v)
    if not 0 <= v < limit:
        raise ValueError(v)
    return v

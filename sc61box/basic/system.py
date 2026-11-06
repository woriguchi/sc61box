"""ROMなしのBASICの本体: モード、行の入力、直接の実行、PROモードの行の登録(系統によらない
部分)

本体のmachine.runは、BASICが動いているあいだ(active)、CPUの代わりにBasic.runを呼ぶ。
Basic.runは、Pythonのジェネレータ(_main)を、決めたサイクル数ずつ進める。ジェネレータは
使ったサイクル数をyieldする。字のコードと中間コードの番号、使う部品(式、文、液晶、キー、
パスワード、リザーブ、カセット、プリンタ)は、系統ごとの子クラス(pc1251/system.py、
pc1261/system.py)が決める。
"""

from collections.abc import Callable, Generator
from dataclasses import dataclass
from decimal import Decimal

from .. import routines
from ..i18n import Text
from ..machine import CLOCK, TICK_2MS
from . import dialect, lexer, password, program, reserve, timing, variables
from .editor import Editor, layout, pieces
from .errors import BasicError
from .evaluate import Evaluator, expect_end
from .keyboard import Keyboard
from .run import LINE_ROOM, Break, End, LineError, Runner, Typed, TypedError
from .screen import Screen
from .using import Format

Steps = Generator[int, None, None]

CALL_STACK = 0x58  # CALLで呼んだ先の頭でのR
RETURN = 0x1FFE  # CALLで積む戻り番地(ROMの番地。ここへRTNで戻ればBASICに戻る)
MESSAGES = ("error", "program-error", "break")
EDITING = ("input", "edit", "error-line", "rsv-edit")  # 液晶にカーソルつきの行を出している
CONTINUE_KEYS = "+-*/^"  # 答えを出したあとに打つと、答えに続けて計算するキー
KEY_DELAY = CLOCK * 23 // 1000  # キーを押してから液晶に出るまで(観察)
ENTER_COST = timing.ms(26.0)  # ENTERを押してから行を実行し始めるまで(観察)
ENTER_IDLE = timing.ms(52.0)  # 実行するもののないENTERで、液晶を消している時間(観察)
NUMBER_RESULT = timing.ms(34.5)  # 答えの数を字にして出す(観察)
AUTO_OFF = 1280 * CLOCK * 512 // 1000  # 自動で電源が切れるまで(512msのタイマの1280回。観察)
DIRECT_ASSIGN = timing.ms(13.6)  # RUNモードで打った代入で、変数に入れる(観察)


def _value_out(v: Decimal | bytes | None) -> list | str | None:
    """数か文字列の値を、状態のファイルに書ける形にする"""
    if isinstance(v, bytes):
        return v.hex()
    return None if v is None else ["n", str(v)]


def _value_in(d: object) -> Decimal | bytes | None:
    if isinstance(d, str):
        return bytes.fromhex(d)
    if isinstance(d, list) and len(d) == 2:
        return Decimal(d[1])
    return None


@dataclass
class Call:
    """CALLでマシン語に渡しているあいだのこと"""

    base: int = 0  # CALLの行を置いた番地(OUTER_RETURNで続きを読む位置を決める)
    end: str | None = None  # 戻り方("break"・"error"・"outer")。ふつうに戻ればNone
    missing: int | None = None  # 代替ROMルーチンのないROMの番地へ入ったら、その番地
    stalled: routines.Routine | None = None  # missingで、時間を進めずに待ち続けた代替ROMルーチン


class Basic:
    """ROMなしのBASIC。字のコードと中間コードの番号、使う部品は、系統ごとの子クラスが
    クラスの属性に入れる"""

    # 字のコード
    PROMPT: int
    COLON: int
    SPACE: int
    EQ: int
    COMMA: int
    QUOTE: int
    AT: int  # リザーブの中でENTERの代わりになる字
    CODES: dict[str, int]  # 字から本体の文字コードへ
    USING_CODES: dict[str, int]  # USINGの欄の字から文字コードへ(指数のEは"[E]")
    # 中間コード(その系統にない命令は−1)
    T_LIST: int
    T_NEW: int
    T_RUN: int
    T_CONT: int
    T_GOTO: int
    T_PASS: int
    T_LLIST: int
    T_CSAVE: int
    T_CLOAD: int
    T_MERGE: int
    T_ROM: int
    T_INSTAT: int
    T_INPUT: int  # RUNモードで直接打つとERROR 9にする(PC-1251系)
    DIRECT: tuple[int, ...]  # RUNモードで行番号なしに打って実行できる文
    STATEMENTS: dict  # 文(Runner.STATEMENTS)
    # 部品
    EVALUATOR: type[Evaluator]
    RUNNER: type[Runner]
    SCREEN: type[Screen]
    KEYBOARD: type[Keyboard]
    EDITOR: type[Editor]
    LEXER: type[lexer.Lexer]
    PROGRAM: program.Program  # プログラムと変数の置き方
    VARS: variables.Variables
    TIMES: timing.Timing  # 文と式にかかる時間
    PASSWORD: password.Password  # パスワードの置き方
    RESERVE: reserve.Reserve  # リザーブの置き方
    TAPEIO: type  # カセット(CSAVE、CLOAD、MERGE、CHAIN)
    PRINTOUT: type  # プリンタ(LPRINT、LLIST)
    # ふるまいの違い
    ERROR_MARK: str  # エラーで点ける記号
    # CALLのとき、行の中のいまの位置(読んだ最後のバイトの番地)を置く番地。マシン語がそこを
    # 書き換えてから戻ると、エラーとBREAKの行はそこから決まる(PC-1251系だけ。観察)
    TEXT_POINTER: int | None = None
    # CALLのとき、行の中のいまの位置をXに入れる(PC-1261系。観察)
    POINTER_IN_X = False
    LINE_HEAD = 2  # 行の頭の、行番号のバイト数
    TYPED_AT = 0xC7B0  # RUNモードで打った行を置く番地
    TYPED_SIZE = 80  # 打った行を置く場所の大きさ
    TYPED_FILL = b"\0"  # 打った行のあとを埋めるバイト(観察)
    # PRINT・PAUSEの字の並びを置く番地と大きさ(Noneなら置かない。観察)
    PRINT_BUFFER: int | None = None
    PRINT_BUFFER_SIZE = 0x50
    CALL_R = CALL_STACK  # CALLで呼んだ先の頭でのR(観察)
    # CALLで呼んだ先の頭で、いつも同じ値になる内部RAMの番地と値(観察)
    CALL_REGS: dict[int, int] = {}
    # CALLの戻り番地の上に積む、BASICの命令の続きへの戻り番地(Noneなら積まない)。マシン語が
    # 戻り番地を捨ててここへ戻ると、キャリーが1なら内部RAMのOUTER_ERRNO番地の番号のエラー、
    # 0ならXの次のバイトから行の続きを読む(PC-1350。観察)
    OUTER_RETURN: int | None = None
    OUTER_ERRNO = 0x34
    INPUT_CL_ASKS = False  # INPUT "字",変数でCLを押すと、字の代わりに?を出す(PC-1261系とPC-1350)

    def __init__(self, m) -> None:
        self.m = m
        self._text_end: int | None = None  # put_textで字のあとに00hを置いた番地
        self.screen = self.SCREEN(m)
        self.keys = self.KEYBOARD(m)
        self.dialect = dialect.of(m)  # 機種ごとの違い
        self.keywords = self.dialect.keywords
        self.lexer = self.LEXER(self.keywords, self.dialect.abbreviations)
        self.active = True  # CPUの代わりに動いている(CALLの最中はFalse)
        self.idle = False  # RUNかPROモードで、次の行を打つキーを待っている
        # どこで止まっているか(状態の保存に使う): idle(行の打ち込み)、run(プログラムの
        # 実行)、print・input(PRINT・INPUTの待ち)、call-run・call-direct(CALLの最中)
        self.where = "idle"
        self.waiting = False  # キーを待っている(行の打ち込み、PRINTやINPUTの待ち)
        self.pending_call: int | None = None  # 作業欄の実行のボタンで頼まれたCALLの番地
        self.pending_key: str | None = None  # 実行が止まったあとで受け付けるキー
        self.call = Call()
        # CALLの先で入った、代替ROMルーチンのないROMの番地と、時間を進めずに待ち続けた
        # 代替ROMルーチン(本体の外のアプリに知らせる)
        self.notice: int | None = None
        self.stalled: routines.Routine | None = None
        self.untouched = 0  # キーを待ちながら、キーを押さずにたったサイクル
        self.sleeping = False  # 自動で電源を切っている
        self.waking = False  # 自動で切れた電源をONキーで入れて、キーが離れるのを待っている
        # PRINT・INPUTの待ちでDEFを使ったときに、AREADに渡すもの(_def_sourceと同じ形)
        self.def_source: tuple[bytes | None, Decimal | bytes | None] = (None, None)
        # 液晶に出しているもの: prompt(>)、input(打っている行)、edit(登録した行の編集)、
        # shown(登録した行)、result(答え)、error
        self.state = "prompt"
        self.editor = self.EDITOR()
        self.line_no: int | None = None  # 出している・編集している登録した行の番号
        self.answer = b""  # 出した答えの字(続けて計算するときに使う)
        self.last_value: Decimal | bytes | None = None  # 出している答え(AREADに渡す)
        self.def_latch = False  # DEFを押して、次のキーを待っている
        self.rsv_key = ""  # RSVモードで出しているリザーブのキー
        self.last_line = b""  # 最後にENTERで実行した行(中間コードの並び)
        self.error_pos: int | None = None  # その行のエラーの位置
        # プログラムが止まった行の(番号, 位置)。PROモードの↑・↓で、その行をカーソル付きで出す
        self.stopped_at: tuple[int, int] | None = None
        self.blink_off = False  # 字の上のカーソルを、いまは字のほうにしている
        self.runner = self.RUNNER(self)
        self.tapeio = self.TAPEIO(self)
        self.printout = self.PRINTOUT(self)
        # CALLの最中に本体がCPUを動かすとき、CPUを止める番地(RAMの外のすべて)
        self.guard = m.outside_ram()
        self._steps = self._main()
        self._tick = 0
        self._left = 0  # いまのyieldの残りのサイクル

    def _key_wait(self) -> Steps:
        """キーを待つあいだの2msの1回。そのあいだwaitingを立てる。キーを押さないまま
        AUTO_OFFたつと、電源を切る。ONキーで入れると、液晶もキーを待っていたところも
        そのままで続ける(観察)"""
        m = self.m
        if m.held or m.brk:
            self.untouched = 0
        elif self.untouched >= AUTO_OFF:
            self.untouched = 0
            self.sleeping = True
            m.out_c(m.pc_out & ~0x01 | 0x08)
        if self.sleeping:  # 切れたところ(保存した状態から戻したときも)
            while self.sleeping:
                yield TICK_2MS
        self.display(True)
        self.waiting = True
        used = max(TICK_2MS - m.t2, 1)
        yield used
        self.untouched += used
        self.waiting = False

    def display(self, on: bool) -> None:
        """液晶を点ける・消す(Cポートのビット0)。ROMのある本体は、ENTERを押すと液晶を消し、
        PRINTの字を出したときと、キーを待つときに点ける。文ごとには消さない(観察)"""
        m = self.m
        if bool(m.pc_out & 0x01) != on:
            m.out_c(m.pc_out | 0x01 if on else m.pc_out & ~0x01)

    def wake(self) -> None:
        """ONキーで電源を入れた。自動で切れていたなら続きから、そうでなければ始め直す"""
        if self.sleeping:
            self.sleeping = False
            self.waking = True
        else:
            self.restart()

    def restart(self) -> None:
        """電源を入れ直したときなど: RAMはそのままで、入力待ちから始め直す。実行中の
        プログラム、FOR・GOSUB、CONTで続ける所は忘れる"""
        self.active = True
        self.idle = self.waiting = False
        self.where = "idle"
        self.pending_call = None
        self.pending_key = None
        self.call = Call()
        self.untouched = 0
        self.sleeping = self.waking = False
        if self.def_latch:
            self._def_toggle()
        self.state = "prompt"
        self.editor = self.EDITOR()
        self.line_no = None
        self.stopped_at = None
        self.runner = self.RUNNER(self)
        self.keys = self.KEYBOARD(self.m)
        self._steps = self._main()
        self._left = 0

    # ---- 状態の保存(どこでもセーブ) ----
    def save(self) -> dict:
        """RAMの外にあるBASICの状態。プログラムの実行中なら、続ける所も入れる(文の途中で
        保存したときは、その文の頭から。PRINTとINPUTの待ちは、その待ちから)"""
        r = self.runner
        at = {"run": r.at, "print": (r.addr, r.pos), "input": (r.addr, r.stmt),
              "call-run": (r.addr, r.pos),
              "call-direct": (r.addr, r.pos)}.get(self.where, (0, 0))  # fmt: skip
        ed = self.editor
        return {
            "where": self.where, "at": list(at), "active": self.active,
            "state": self.state, "units": list(ed.units), "cur": ed.cur, "head": ed.head,
            "sep": ed.sep, "glued": ed.glued, "rsv_key": self.rsv_key,
            "line_no": self.line_no, "answer": self.answer.hex(),
            "last_line": self.last_line.hex(), "error_pos": self.error_pos,
            "stopped_at": list(self.stopped_at) if self.stopped_at else None,
            "runner": r.save(),
            "def_latch": self.def_latch, "last_value": _value_out(self.last_value),
            "def_source": [None if self.def_source[0] is None else self.def_source[0].hex(),
                           _value_out(self.def_source[1])],
            "pending_key": self.pending_key, "untouched": self.untouched,
            "sleeping": self.sleeping, "printout": self.printout.save(),
            "call_end": self.call.end, "missing": self.call.missing,
            # 打った行のCALLの最中なら、その行(戻ったあとに行の続きを調べる)
            "call_code": r.code.hex() if self.where == "call-direct" else None,
        }  # fmt: skip

    def prepare(self, d: object) -> Callable[[], None]:
        """saveで書いたものを読み、それに戻す関数を返す。形が違えばValueErrorで、何も変えない
        (本体がRAMを戻す前に調べる)。BASICの状態がなければ、入力待ちから始め直す関数を返す"""
        if not isinstance(d, dict):
            return self._fresh
        try:
            runner = self.runner.parse(d["runner"])
            where = str(d["where"])
            at = self._place_in(d["at"])
            editor = self.EDITOR([int(u) for u in d["units"]], int(d["cur"]), int(d["head"]),
                                 int(d["sep"]), bool(d.get("glued")))  # fmt: skip
            stopped = d["stopped_at"]
            text, value = d.get("def_source") or (None, None)
            key = d.get("pending_key")
            end, missing = d.get("call_end"), d.get("missing")
            fields = {
                "rsv_key": str(d.get("rsv_key") or "A"),
                "state": str(d["state"]),
                "line_no": d["line_no"],
                "answer": bytes.fromhex(d["answer"]),
                "last_line": bytes.fromhex(d["last_line"]),
                "error_pos": d["error_pos"],
                "stopped_at": self._place_in(stopped) if stopped else None,
                "def_latch": bool(d.get("def_latch")),
                "last_value": _value_in(d.get("last_value")),
                "def_source": (None if text is None else bytes.fromhex(text), _value_in(value)),
                "pending_key": None if key is None else str(key),
                "untouched": int(d.get("untouched", 0)),
                "sleeping": bool(d.get("sleeping")),
            }
            call = Call(
                end=None if end is None else str(end),
                missing=None if missing is None else int(missing),
            )
            out = d.get("printout") or {}
            if not isinstance(out, dict):
                raise TypeError(out)
            printout = self.printout.parse(out)
            code = d.get("call_code") if where == "call-direct" else None
            call_code = bytes.fromhex(code) if isinstance(code, str) else None
        except (KeyError, IndexError, TypeError, ValueError, ArithmeticError) as e:
            raise ValueError(Text("basic.not_basic_state")) from e
        active = bool(d.get("active", True))

        def apply() -> None:
            self._fresh()
            for name, v in runner.items():
                setattr(self.runner, name, v)
            self.editor = editor
            for name, v in fields.items():
                setattr(self, name, v)
            self.call = Call(end=call.end, missing=call.missing)
            # restartがDEFの記号を消すので、出し直す(同じ本体に戻したとき)
            self.screen.symbol("DEF", self.def_latch)
            for name, v in printout.items():
                setattr(self.printout, name, v)
            if where in ("call-run", "call-direct"):
                # CALLの最中にもう一度保存しても、同じ所から続けられるように
                self.where = where
                r = self.runner
                r.addr, r.pos = at
                self.active = active
                # CALLの行を置いた番地(call_machineと同じに決める)
                self.call.base = r.addr + self.LINE_HEAD if where == "call-run" else self.TYPED_AT
                if call_code is not None:
                    r.code = call_code
                elif where == "call-direct":  # 前の版の状態: 置いた行から読む
                    base, size = self.TYPED_AT, self.TYPED_SIZE
                    r.code = bytes(self.m.mem[base : base + size]).rstrip(self.TYPED_FILL)
            self._steps = self._resumed(where, at)

        return apply

    def _place_in(self, v: object) -> tuple[int, int]:
        """状態に書いた、プログラムの中の位置(行の番地, 行の中の位置)。行がメモリに入らない
        番地ならValueError(壊れた状態のファイルで、続けたときに落ちないように)"""
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            raise TypeError(v)
        addr, pos = int(v[0]), int(v[1])
        if not (0 <= addr < len(self.m.mem) - LINE_ROOM and 0 <= pos < 0x100):
            raise ValueError(v)
        return addr, pos

    def _fresh(self) -> None:
        self.restart()
        self.tapeio.quiet()  # CSAVEやBEEPの途中で保存した音は止める
        # 本体がRAMの終わりを保存したときのものに戻したので、CALLの最中に止める番地も作り直す
        self.guard = self.m.outside_ram()

    def _resumed(self, where: str, at: tuple[int, int]) -> Steps:
        """保存した状態から続ける"""
        r = self.runner
        if where in ("run", "input"):  # INPUTは、その文からやり直す
            yield from self._run_program(r.resume_at(at), resumed=True)
        elif where == "print":
            yield from self._run_program(r.after_print(at), resumed=True)
        elif where == "call-run":  # CALLから戻ったときの扱いから
            yield from self._run_program(r.after_call(at), resumed=True)
        elif where == "call-direct":
            self.where = "idle"
            yield from self._typed_line(r.code, self._direct_returned())
        yield from self._main(keep=True)

    def run(self, cycles: int) -> int:
        """cyclesぶん進める。使ったサイクル数を返し、CPUのサイクルも進める"""
        if self.waking:
            # 自動で切れた電源を入れたONキーは、BREAKにしない(観察)
            if self.m.brk:
                self.m.cpu.cycles += cycles
                return cycles
            self.waking = False
            self.m.out_c(self.m.pc_out & ~0x08 | 0x01)
        used = 0
        while used < cycles:
            if self._left == 0:
                self._left = next(self._steps)
                if not self.active:  # CALLでCPUに渡した
                    self._left = 0
                    break
            take = min(self._left, cycles - used)
            self._left -= take
            used += take
            self.m.cpu.cycles += take  # 音の出し入れなどが、そのときのサイクルを見る
        return used

    # ---- 全体 ----
    def _main(self, keep: bool = False) -> Steps:
        """keepなら、保存した状態から続ける(液晶と行の打ち込みをそのままにする)"""
        m = self.m
        if not keep:
            self.VARS.initialize(m)
            m.out_c(m.pc_out & ~0x08 | 0x01)  # 液晶を点ける(電源を切ったビットは下ろす)
            self._power_on()
        while True:
            mode = self.mode
            self._show_mode(mode)
            if mode in ("RUN", "PRO", "RSV"):
                yield from self._mode_loop(mode, keep)
                keep = False
            elif mode == "OFF":
                # 電源を切る(液晶を消す)。電源を入れ直すと、restartで始め直す
                self.mark_off()
                m.out_c(m.pc_out & ~0x01 | 0x08)
                yield TICK_2MS
            else:
                self.screen.show([self.PROMPT])
                while self.mode == mode:
                    yield TICK_2MS

    def mark_off(self) -> None:
        """電源を切ったときのマークを内部RAMに書く(アプリを閉じてRAMを保存するときも)"""
        # ROMと同じマーク(machine.off_mark)を書いておくと、保存したRAMをROM使用時にも読める
        a, mark = self.m.off_mark()
        self.m.cpu.ram[a : a + len(mark)] = mark

    @property
    def mode(self) -> str:
        """いまのモード(RUN・PRO・RSV・OFFなど)。ふつうは本体のスイッチ。PC-1350はMODEキーで
        変え、BASICが覚えている"""
        return self.m.mode

    def _power_on(self) -> None:
        """電源を入れたときの表示記号"""

    def _show_mode(self, mode: str) -> None:
        """モードの表示記号"""

    def assigned(self, value: Decimal | bytes) -> None:
        """プログラムの代入・READ・INPUT・AREADで変数に入れた値"""

    def display_number(self, v: Decimal) -> bytes:
        """RUNモードで答えとして出す数の字"""
        return self.EVALUATOR.display_number(v)

    @property
    def def_keys(self) -> tuple[str, ...]:
        """DEFに続けて押すと、そのラベルから実行するキー"""
        return (*self.RESERVE.KEYS, " ")

    def _wait_key(self) -> Generator[int, None, str | None]:
        """押されたキーを待つ。モードが変わればNone。字の上のカーソルは、512msのタイマが
        回るたびに字と入れ替える(観察: 入れ替わる時刻はタイマで決まり、キーを押した時刻に
        よらない。キーを押すとカーソルを出す)"""
        mode = self.mode
        tick = self.m.t512cnt
        while True:
            if self.idle and self.pending_call is not None:
                return "@CALL"
            k = self.keys.poll()
            if k == "SHIFT":
                self.screen.symbol("SHIFT", self.keys.shift)
            elif k is not None:
                self.screen.symbol("SHIFT", self.keys.shift)
                self.blink_off = False
                yield KEY_DELAY
                return k
            if self.mode != mode:
                return None
            if self.m.t512cnt < tick:
                self.blink_off = not self.blink_off
                if self.state in EDITING and not self.editor.at_end():
                    self._show_editor()
            tick = self.m.t512cnt
            yield from self._key_wait()

    # ---- 行の入力 ----
    def _mode_loop(self, mode: str, keep: bool = False) -> Steps:
        """モードを変えたときは、Eの記号を消して>を出す(観察)。keepなら、いまの液晶と行の打ち込みのまま続ける"""
        if not keep:
            self.screen.symbol(self.ERROR_MARK, False)
            self._prompt()
        while True:
            if self.mode != mode:  # 実行中にモードを変えた
                return
            self.idle = True
            k, self.pending_key = self.pending_key, None
            if k is None:
                k = yield from self._wait_key()
            self.idle = False
            if k is None:
                return
            if k == "@CALL":
                yield from self._typed_call()
                continue
            if self.def_latch:
                # DEFのあとの1打鍵: ラベルのキーなら、そのラベルの行から実行する(観察)
                self._def_toggle()
                if k == "DEF":  # もう一度DEFでやめる
                    continue
                if k in self.def_keys and self.state not in MESSAGES:
                    yield from self._def_run(k, *self._def_source())
                    continue
            if k.startswith("DEF:"):  # PRINT・INPUTの待ちで、DEFのあとラベルのキー
                yield from self._def_run(k[4:], *self.def_source)
                continue
            if k == "DEF":
                if mode == "RUN" and self.state not in MESSAGES:
                    self._def_toggle()
                continue
            if k.startswith("RSV:"):
                if self.state in MESSAGES:
                    continue
                if mode == "RSV":
                    self._reserve_open(k[4:])
                else:
                    yield from self._reserve_type(k[4:], mode)
                continue
            if mode == "RUN" and k in ("UP", "DOWN") and self.state not in ("error", "input"):
                yield from self._debug_key(k)
                continue
            if self.state in MESSAGES and not self._message_key(k):
                continue
            if k == "CL":
                self._prompt()
            elif k == "ENTER":
                yield from self._enter(mode)
            elif k in ("UP", "DOWN"):
                if mode == "PRO":
                    self._scroll(-1 if k == "UP" else 1)
            elif k in ("LEFT", "RIGHT", "DEL", "INS"):
                self._edit_key(k)
            elif k in self.CODES:
                self._type(self.CODES[k], k in CONTINUE_KEYS)

    # ---- リザーブとDEF ----
    def _reserve_label(self, key: str) -> int:
        return self.SPACE if key == "SPC" else self.CODES[key]

    def _reserve_open(self, key: str) -> None:
        """RSVモードでSHIFTのあとリザーブのキー: 登録した中身を「キー:中身」の形で出す。
        登録がなければ、すぐ打ち込みにする(観察)"""
        self.rsv_key = key
        content = self.RESERVE.get(self.m, key)
        label = self._reserve_label(key)
        if content is None:
            self.editor = self.EDITOR([label], 1, 1, self.COLON, True)
            self.state = "rsv-edit"
            self._show_editor()
            return
        text, _ = self._layout([label, *content], 1, self.COLON, True)
        self.screen.show(text[: self.screen.cells])
        self.state = "rsv-shown"

    def _reserve_edit(self, k: str) -> None:
        """出しているリザーブを編集にする。←・→で、カーソルを中身の頭に置く(観察)"""
        content = self.RESERVE.get(self.m, self.rsv_key) or b""
        label = self._reserve_label(self.rsv_key)
        self.editor = self.EDITOR([label, *content], 1, 1, self.COLON, True)
        self.state = "rsv-edit"
        self._show_editor()

    def _reserve_store(self) -> None:
        """打ち込んだ中身を中間コードにして登録し、「キー:中身」の形で出す。空なら消す"""
        content = self.lexer.tokenize(self.editor.text()[1:])
        try:
            self.RESERVE.store(self.m, self.rsv_key, content)
        except BasicError as e:
            self.error_pos = 0
            self.last_line = b""
            self._error(e.number)
            return
        if content:
            self._reserve_open(self.rsv_key)
        else:
            self._prompt()

    def shift_content(self, key: str) -> bytes:
        """SHIFTのあとリザーブの位置のキーで打つもの。RSVモードのある機種は登録した中身
        (登録がなければキーの字)、ない機種(PC-1245)はキーに決まった命令(観察)"""
        words = self.dialect.shift_keywords
        if words is not None:
            return bytes([words[key]]) if key in words else b""
        content = self.RESERVE.get(self.m, key)
        return bytes([self._reserve_label(key)]) if content is None else content

    def _reserve_type(self, key: str, mode: str) -> Steps:
        """RUN・PROモードでSHIFTのあとリザーブのキー: 登録した中身を打ったのと同じにする。
        @はENTERで、その先は捨てる(観察)"""
        for u in self.shift_content(key):
            if u == self.AT:
                yield from self._enter(mode)
                return
            self._type(u, False)

    def _def_toggle(self) -> None:
        """DEF: 押すたびにDEFの記号を出したり消したりする(観察)"""
        self.def_latch = not self.def_latch
        self.screen.symbol("DEF", self.def_latch)

    def _def_latched(self, k: str) -> str | None:
        """PRINT・INPUTの待ちでの打鍵とDEF。DEFのあとラベルのキーなら「DEF:キー」を、DEFを
        押した(DEFをやめた)ならNoneを返す。ほかのキーは、DEFをやめてそのまま返す(観察)"""
        if self.def_latch:
            self._def_toggle()
            if k == "DEF":
                return None
            return "DEF:" + k if k in self.def_keys else k
        if k == "DEF":
            self._def_toggle()
            return None
        return k

    def _def_source(self) -> tuple[bytes | None, Decimal | bytes | None]:
        """AREADに渡すもの: (打っている行, 出している答え)"""
        if self.state in ("input", "edit") and self.editor.units:
            return self.editor.text(), None
        if self.state in ("result", "print"):
            return None, self.last_value
        return None, None

    def _def_run(self, key: str, text: bytes | None, value: Decimal | bytes | None) -> Steps:
        """DEFのあとラベルのキー: 行の頭に「"キー"」のある最初の行から実行する。ラベルがなければ
        ERROR 4で、←・→で打っている行を呼び出せる。打っている行(text)か出している答え(value)を、
        AREADで読めるようにする(観察: 打っている行は、AREADが読むときに計算する。答えも打っている
        行もなければ0か空。PRINTの待ちなら出した値、INPUTの待ちなら打った字)"""
        label = bytes([self.QUOTE, self.SPACE if key == " " else self.CODES[key], self.QUOTE])
        found = self.PROGRAM.find_label(self.m, label)
        if found is None:
            self.last_line = self.lexer.tokenize(text) if text else b""
            self.error_pos = len(self.last_line)
            self._error(4)
            return
        self.runner.aread = Typed(text) if text else value
        self.stopped_at = None
        self.display(False)
        yield ENTER_COST
        yield from self._run_program(self.runner.run_from(found[1]))

    def request_call(self, addr: int) -> bool:
        """作業欄の実行のボタン: 次の行を打つキーを待っていれば、「CALL 番地」を打って
        ENTERを押したのと同じにする。待っていなければFalse"""
        if not self.idle or self.pending_call is not None:
            return False
        self.pending_call = addr & 0xFFFF
        return True

    def _typed_call(self) -> Steps:
        addr, self.pending_call = self.pending_call, None
        if addr is None:
            return
        self.screen.symbol(self.ERROR_MARK, False)
        self.editor = self.EDITOR(self.lexer.tokenize(self._codes(f"CALL {addr}")))
        self.state = "input"
        self._show_editor()
        yield from self._enter(self.mode)

    def _debug_key(self, k: str) -> Steps:
        """RUNモードの↑・↓(観察)。↑: 止まった行があれば、押しているあいだその行を止まった
        所にカーソルを置いて出し、離すと>。↓: 続けられるプログラムがあれば、その行の
        終わりまで実行して止まる。どちらもなければ、メッセージを消して>"""
        if k == "UP" and self.PASSWORD.locked(self.m):
            # パスワードで保護しているときは、↑は行を出さない。Eの記号だけ消す(観察)
            self.screen.symbol(self.ERROR_MARK, False)
            return
        if k == "UP" and self.stopped_at is not None:
            yield from self.peek(*self.stopped_at)
            return
        if k == "DOWN" and self.runner.resume is not None:
            self.screen.symbol(self.ERROR_MARK, False)
            self.display(False)
            yield from self._run_program(self.runner.step())
            return
        if self.state in MESSAGES:
            self.screen.symbol(self.ERROR_MARK, False)
            self._prompt()

    def peek(self, line: int, pos: int) -> Steps:
        """↑を押しているあいだ、行lineを位置posにカーソルを置いて出す。離すと>(観察)"""
        self.stopped_at = (line, pos)
        yield from self.hold_up(self._show_stopped())
        self.keys.poll()
        self.screen.symbol(self.ERROR_MARK, False)
        self._prompt()

    def hold_up(self, shown: bool) -> Steps:
        """↑を押しているあいだ待つ。shownなら、出した行のカーソルを点滅させる"""
        self.blink_off = False
        self._tick = self.m.t512cnt
        while "UP" in self.m.held:
            yield max(TICK_2MS - self.m.t2, 1)
            if shown and self.m.t512cnt < self._tick:
                self.blink_off = not self.blink_off
                self._show_editor()
            self._tick = self.m.t512cnt

    def _message_key(self, k: str) -> bool:
        """エラーやBREAKのメッセージを出しているときのキー。続けてふつうに扱うならTrue(観察)

        直接のエラー: CLで>、←・→でその行をエラーの位置にカーソルを置いて呼び出す。
        ほかのキーは効かない。プログラムのエラー: CL・↑・↓で>。ほかは効かない。
        BREAK: CL・↑・↓・ENTERで>。←・→は効かず、字は打てる"""
        state = self.state
        if state == "error":
            if k == "CL":
                self.screen.symbol(self.ERROR_MARK, False)
                self._prompt()
            elif k in ("LEFT", "RIGHT"):
                self.screen.symbol(self.ERROR_MARK, False)
                self.editor = self.EDITOR(self.last_line, self.error_pos)
                self.state = "input"
                self._show_editor()
            return False
        if k in ("CL", "UP", "DOWN") or (state == "break" and k == "ENTER"):
            self.screen.symbol(self.ERROR_MARK, False)
            self._prompt()
            return False
        return state == "break" and k in self.CODES

    def _prompt(self) -> None:
        self.state, self.line_no = "prompt", None
        self.screen.show([self.PROMPT])

    def _type(self, code: int, continues: bool) -> None:
        if self.state == "result" and continues and self.answer:
            self.editor = self.EDITOR(self.answer)
        elif self.state not in ("input", "edit", "rsv-edit"):
            self.editor = self.EDITOR()
            self.line_no = None
        self.editor.type(code)
        if self.state not in ("edit", "rsv-edit"):
            self.state = "input"
        self._show_editor()

    def _edit_key(self, k: str) -> None:
        if self.state == "rsv-shown" and k in ("LEFT", "RIGHT"):
            self._reserve_edit(k)
            return
        if self.state == "rsv-edit":
            # カーソルはキーの字の上へは動かない(観察)
            ed = self.editor
            {"LEFT": lambda: ed.move(-1), "RIGHT": lambda: ed.move(1),
             "DEL": ed.delete, "INS": ed.insert}[k]()  # fmt: skip
            ed.cur = max(ed.cur, ed.head)
            self._show_editor()
            return
        if self.state == "shown" and k in ("LEFT", "RIGHT") and self.line_no is not None:
            self._edit_line(self.line_no)
            return
        if self.state == "error-line" and k in ("LEFT", "RIGHT"):
            # 止まった行を見せているときは、カーソルを1つ動かして編集する(観察)
            ed = self.editor
            if k == "RIGHT" and ed.at_end():
                return  # 終わりにカーソルがあれば、→は効かない(観察)
            cur = max(ed.head, min(len(ed.units), ed.cur + (1 if k == "RIGHT" else -1)))
            self.editor = self.EDITOR(ed.units, cur, ed.head, self.SPACE, ed.glued)
            self.state = "edit"
            self._show_editor()
            return
        if self.state == "result" and k in ("LEFT", "RIGHT") and self.last_line:
            # 実行した行を呼び出して、カーソルを終わりに置く
            self.editor = self.EDITOR(self.last_line)
            self.state = "input"
        elif self.state in ("input", "edit"):
            {"LEFT": lambda: self.editor.move(-1), "RIGHT": lambda: self.editor.move(1),
             "DEL": self.editor.delete, "INS": self.editor.insert}[k]()  # fmt: skip
        else:
            return
        self._show_editor()

    def _show_editor(self) -> None:
        text, cursor, shape = self.editor.view(
            self.screen.cells, self.keywords, self.CODES, self.blink_off
        )
        self.screen.show(text, cursor, shape)

    # ---- 登録した行 ----
    def _edit_line(self, n: int) -> None:
        """登録した行nを、中身の頭にカーソルを置いて編集する"""
        found = self.PROGRAM.at_or_after(self.m, n)
        if found is None or found[0] != n:
            return
        head = list(self._codes(str(n)))
        body = self.PROGRAM.body(self.m, found[1])
        self.editor = self.EDITOR(head + list(body), len(head), len(head))
        self.state = "edit"
        self._show_editor()

    def _show_line(self, n: int, a: int) -> None:
        """登録した行を「行番号:中身」の形で出す"""
        text, _ = self._layout(self.PROGRAM.body(self.m, a))
        head = list(self._codes(str(n))) + [self.COLON]
        self.screen.show((head + text)[: self.screen.cells])
        self.state, self.line_no = "shown", n

    def _show_stopped(self) -> bool:
        """プログラムが止まった行を「行番号:中身」の形で出し、止まった位置にカーソルを
        置く(観察)。その行がなければFalse"""
        if self.stopped_at is None:
            return False
        n, pos = self.stopped_at
        found = self.PROGRAM.at_or_after(self.m, n)
        if found is None or found[0] != n:
            return False
        head = list(self._codes(str(n)))
        body = self.PROGRAM.body(self.m, found[1])
        self.editor = self.EDITOR(
            head + list(body), len(head) + min(pos, len(body)), len(head), self.COLON
        )
        self.state, self.line_no = "error-line", n
        self._show_editor()
        return True

    def _scroll(self, step: int) -> None:
        """↑・↓で、前か次の登録した行を出す。行を出していなければ、プログラムが止まった
        行があればその行、なければ↓で最初の行、↑で最後の行(観察)"""
        all_lines = self.PROGRAM.lines(self.m)
        if not all_lines or self.PASSWORD.locked(self.m):
            return  # パスワードで保護しているときは、行を出さない(観察)
        numbers = [n for n, _ in all_lines]
        if self.state not in ("shown", "edit", "error-line") and self._show_stopped():
            return
        if self.state in ("shown", "edit", "error-line") and self.line_no in numbers:
            now = numbers.index(self.line_no)
            i = max(0, min(len(numbers) - 1, now + step))
            if i == now and self.state == "error-line":
                return  # 止まった行が端の行なら、カーソルを付けたまま出しておく(観察)
        else:
            i = 0 if step > 0 else len(numbers) - 1
        self._show_line(*all_lines[i])

    # ---- ENTER ----
    def _enter(self, mode: str) -> Steps:
        self.display(False)
        if self.state not in ("input", "edit") or not self.editor.units:
            yield ENTER_IDLE  # 実行するものがなくても、液晶をしばらく消す(観察)
        if self.state in ("shown", "rsv-shown"):
            self._prompt()
            return
        if self.state == "rsv-edit":
            self._reserve_store()
            return
        if self.state == "error-line" and self.line_no is not None:
            found = self.PROGRAM.at_or_after(self.m, self.line_no)
            if found is not None:
                self._show_line(*found)
            return
        if self.state not in ("input", "edit") or not self.editor.units:
            return
        yield ENTER_COST
        code = self._entered_code(mode)
        # 呼び出す行は中間コードにしたもの(観察: 綴りで打った命令も命令として出る)
        self.last_line = code
        yield from self._typed_line(code, self._entered(code, mode))

    def _entered(self, code: bytes, mode: str) -> Generator[int, None, Decimal | bytes | None]:
        """ENTERで打った行を、登録するか実行する。答えとして出す値を返す"""
        if mode == "PRO" and code[:1] and self.EVALUATOR.is_digit(code[0]):
            if self.PASSWORD.locked(self.m):
                self._prompt()  # パスワードで保護しているときは、行を登録しない(観察)
            else:
                self._store(code)
            return None
        started = self._program_command(code, mode)
        if started is not None:
            yield from self._run_program(started)
            return None
        return (yield from self._direct(code, mode))

    def _typed_line(
        self, code: bytes, steps: Generator[int, None, Decimal | bytes | None]
    ) -> Steps:
        """打った行codeの実行stepsを進め、エラーかBREAKのメッセージ、または答えを出す"""
        try:
            value = yield from steps
            answer = self._answer(value, code) if isinstance(value, Decimal) else b""
        except (Break, LineError) as e:  # 打ったCALLから、エラーかBREAKで戻った
            yield self.runner.meter.take() + self.TIMES.STOPPED
            self._stop_message(e)
            return
        except BasicError as e:
            default = (
                len(code) - 1
                if code[:1] and code[0] in (self.T_RUN, self.T_GOTO, self.T_CONT)
                else 0
            )
            self.error_pos = default if e.pos is None else min(e.pos, len(code))
            yield self.runner.meter.take()  # エラーまでの計算の時間
            self._error(e.number)
            return
        if value is None:
            return
        yield self.runner.meter.take() + (NUMBER_RESULT if isinstance(value, Decimal) else 0)
        self.answer = answer
        self._show_result(value)
        self.state = "result"
        self.last_value = value
        yield from self.echo_value(value)

    def shift_enter(self, k: str) -> bool:
        """SHIFTのあとENTERを、キーの待ちのどこででも受け持ったらTrue(PC-1261系とPC-1350の印字モード)"""
        return False

    def echo_line(self, code: bytes) -> Steps:
        """印字モードで、計算する行をプリンタにも送る(PC-1261系とPC-1350)"""
        yield from ()

    def echo_value(self, value: Decimal | bytes) -> Steps:
        """印字モードで、答えをプリンタにも送る(PC-1261系とPC-1350)"""
        yield from ()

    def _entered_code(self, mode: str) -> bytes:
        """ENTERで打った行を中間コードにしたもの"""
        return self.lexer.tokenize(self.editor.text())

    def _answer(self, value: Decimal, code: bytes) -> bytes:
        """答えの数の字(codeは打った行)"""
        return self.display_number(value)

    def _show_result(self, value: Decimal | bytes) -> None:
        """答えを出す: 数は右に寄せ、文字列は左から"""
        width = self.screen.width
        if isinstance(value, Decimal):
            self.screen.show([self.SPACE] * (width - len(self.answer)) + list(self.answer))
        else:
            self.screen.show(list(self.spell(value)[:width]))

    def _store(self, code: bytes) -> None:
        """行番号で始まる行を登録する(中身がなければ、その行を消す)"""
        i = 0
        while i < len(code) and self.EVALUATOR.is_digit(code[i]):
            i += 1
        n = int("".join(str(c - self.EVALUATOR.DIGIT_BASE) for c in code[:i]))
        self.PROGRAM.store(self.m, n, code[i:])
        self.stopped_at = None
        found = self.PROGRAM.at_or_after(self.m, n)
        if code[i:] and found is not None:
            self._show_line(*found)
        else:
            self._prompt()

    def _program_command(self, code: bytes, mode: str):
        """RUN・GOTO・CONTなら、プログラムを実行するジェネレータを返す(ほかはNone)"""
        head = code[0] if code else None
        if head not in (self.T_RUN, self.T_GOTO, self.T_CONT):
            if head == self.T_LIST and mode != "PRO" or head == self.T_NEW and mode == "RUN":
                raise BasicError(9)  # PROモードの命令(観察)
            if head in (self.T_ROM, self.T_INSTAT):
                raise BasicError(8)  # つないでいない機器の命令(観察)
            return None
        if mode in ("PRO", "RSV"):
            raise BasicError(9)
        e = self.EVALUATOR(self.m, code, 1)
        line = None if e.pos >= len(code) else e.expression()  # 行番号かラベル(観察)
        if isinstance(line, Decimal):
            line = int(line)
        expect_end(e)
        self.stopped_at = None
        if head == self.T_CONT:
            return self.runner.cont()
        if head == self.T_GOTO:
            if line is None:
                raise BasicError(1)
            return self.runner.go(line)
        return self.runner.start(line)

    def _run_program(self, steps, resumed: bool = False) -> Steps:
        """プログラムを実行し、終わり方に合わせて液晶を変える。resumedは、保存した状態から
        続けるとき"""
        self.state = "running"
        self.where = "run"
        try:
            yield from steps
        except End:
            yield self.runner.meter.take() + self.TIMES.STOPPED
            yield from self.printout.program_ended()
            self.stopped_at = None
            self._prompt()
        except Break as b:
            if b.kind in ("stop", "step"):
                yield self.runner.meter.take() + self.TIMES.STOPPED
            if b.kind == "stop":
                self._stop_message(b)
            elif b.kind == "step":
                self._message(self._codes(f"{b.line}:"))
                self.state = "break"
            elif b.kind == "mode":
                self.state = "prompt"  # 新しいモードの入力待ちが>を出す
            elif b.key.startswith("DEF:"):
                self.pending_key = b.key  # 出しているものはそのままで、ラベルから実行する
            else:
                self._prompt()
                if b.key in self.CODES:
                    self._type(self.CODES[b.key], False)
                elif b.key.startswith("RSV:"):
                    self.pending_key = b.key
            self.stopped_at = (b.line, b.pos)
        except LineError as e:
            yield self.runner.meter.take() + self.TIMES.STOPPED
            self._stop_message(e)
        except TypedError as e:  # AREADが打っていた行を計算したときのエラー(観察)
            yield self.runner.meter.take()
            self.last_line, self.error_pos = e.code, e.pos
            self.stopped_at = None
            self._error(e.number)
        finally:
            self.where = "idle"
        left = self.runner.meter.take()  # 止まるまでの計算の時間
        if left:
            yield left

    def _direct(self, code: bytes, mode: str) -> Generator[int, None, Decimal | bytes | None]:
        """行番号のない行を実行する。命令は液晶を自分で変えてNoneを返し、式と代入は液晶に
        出す値を返す。代入は、式のあとに余計なものがあっても先に入れてからエラーにする(観察)"""
        head = code[0] if code else None
        if head == self.T_PASS:
            self._pass(code)
            return None
        if head == self.T_LLIST and mode in ("PRO", "RUN"):
            yield from self.printout.llist(code)
            return None
        if head in (self.T_CSAVE, self.T_CLOAD, self.T_MERGE) and mode in ("PRO", "RUN"):
            yield from self.tapeio.command(code)
            return None
        if mode == "PRO" and head == self.T_LIST:
            if self.PASSWORD.locked(self.m):
                # パスワードで保護しているときは、LISTは何もせず、LIST nはERROR 1(観察)
                if len(code) > 1:
                    raise BasicError(1, 0)
                self._prompt()
                return None
            self._list(code)
            return None
        if head == self.T_NEW and len(code) == 1 and mode == "PRO":
            if self.PASSWORD.locked(self.m) and not self.dialect.new_when_locked:
                self._prompt()  # PC-1245は、保護しているあいだNEWで何もしない(観察)
                return None
            self.PROGRAM.clear(self.m)
            self.PASSWORD.unlock(self.m)
            self.stopped_at = None
            self._prompt()
            return None
        if head in self.STATEMENTS:
            if head == self.T_INPUT:
                raise BasicError(9, 1)
            if head not in self.DIRECT:
                raise BasicError(1, 0)
            r = self.runner
            r.code, r.pos = code, 1
            try:
                result = self.STATEMENTS[head](r)
                if result is not None:
                    yield from result
            except BasicError as err:
                err.at(0)
                raise
            yield from self._statement_done(code)
            return None
        yield from self.echo_line(code)
        e = self.EVALUATOR(self.m, code, 0, self.runner.meter)
        while True:
            value = self._direct_item(e)
            # 「,」で区切って、代入と式をいくつも並べられる。出すのは最後の値(観察)
            if not e.take(self.COMMA):
                break
        expect_end(e)
        return value

    def _statement_done(self, code: bytes) -> Steps:
        """打った行の命令を終えた。行に続きがあればエラー、なければ入力待ちに戻る"""
        r = self.runner
        if r.pos < len(code):
            raise BasicError(1, r.pos)
        yield self.TIMES.STATEMENT + r.meter.take()  # 文にかかった時間は、この行で使う
        self._prompt()

    def _direct_returned(self) -> Generator[int, None, None]:
        """保存した状態から: 打った行のCALLのマシン語から戻った(_directと同じに続ける)"""
        try:
            self.call_returned(False)
        except BasicError as err:
            err.at(0)
            raise
        yield from self._statement_done(self.runner.code)

    def _direct_item(self, e: Evaluator) -> Decimal | bytes:
        """行番号のない行の、「,」で区切った1つ: 代入なら入れて出す値を、式なら値を返す"""
        start = e.pos
        c = e.peek()
        if c is not None and self.EVALUATOR.is_letter(c):
            target = e.target()
            e.claim(target)
            if e.take(self.EQ):
                value = e.expression()
                try:
                    stored = self.VARS.write(self.m, e.resolve(target, create=True), value)
                except BasicError as err:
                    err.at(e.pos - 1)  # 型が合わないときは、式の最後の字(観察)
                    raise
                self.runner.meter.add(DIRECT_ASSIGN)
                # 文字列の代入は、変数に入った字ではなく式の値を出す(観察)
                return value if isinstance(value, bytes) else stored
            e.pos = start
        return e.expression()

    def _pass(self, code: bytes) -> None:
        """PASS "字": 字は文字列でしか書けない(閉じる"はなくてよい)。PASSを行ってから、
        あとに余計なものがあればERROR 1(観察)"""
        if len(code) < 2 or code[1] != self.QUOTE:
            raise BasicError(1, len(code) - 1)
        end = code.find(self.QUOTE, 2)
        word, pos = (code[2:], len(code)) if end < 0 else (code[2:end], end + 1)
        self.PASSWORD.apply(self.m, word, self.dialect.pass_exact)
        if pos < len(code):
            raise BasicError(1, pos)
        self._prompt()

    def _list(self, code: bytes) -> None:
        """LIST [n]: n以上の最初の行を出す。行がなければ>のまま、n以上の行がなければ
        ERROR 4(観察)"""
        n = 0
        arg = code[1:]
        if arg:
            e = self.EVALUATOR(self.m, code, 1)
            n = e.integer()
            expect_end(e)
        if not self.PROGRAM.lines(self.m) and not arg:
            self._prompt()
            return
        found = self.PROGRAM.at_or_after(self.m, n)
        if found is None:
            raise BasicError(4)
        self._show_line(*found)

    def _codes(self, text: str) -> bytes:
        return bytes(self.CODES[ch] for ch in text)

    def _message(self, text: bytes) -> None:
        self.screen.show(list(text[: self.screen.width]))

    # ---- プログラムの実行で使うメソッド ----
    def print_text(
        self, items, comma: bool, fmt: Format, cells: int | None = None, joined: bool = False
    ) -> bytes:
        """PRINT・PAUSE・LPRINTの字の並び。fmtはUSINGの書式。液晶の幅で切らない。
        cellsは数を右に寄せる幅(LPRINTはどの機種もプリンタの1行の24字。観察)。joinedなら
        1つの数も右に寄せず、つなげて出す"""
        cells = cells or self.screen.width
        sp = bytes([self.SPACE])

        def piece(v) -> bytes:
            if isinstance(v, Decimal):
                d = self.dialect
                return fmt.show_number(
                    v, self.display_number, self.USING_CODES, d.using_zero_quirk, d.using_limit
                )
            return fmt.show_string(self.spell(v), self.SPACE)

        if comma:
            half = cells // 2
            return b"".join(self._half(v, piece(v), half, sp) for v in items)
        if len(items) == 1 and isinstance(items[0], Decimal) and not joined:
            t = piece(items[0]).rstrip(sp)[-cells:]
            return sp * (cells - len(t)) + t
        return b"".join(piece(v) for v in items)

    def put_text(self, text: bytes) -> None:
        """PRINTの字の並びをPRINT_BUFFERから置く。その場所は先に空白で埋め、字のすぐあとに00hを
        置く(観察)"""
        at = self.PRINT_BUFFER
        assert at is not None
        m = self.m
        text = text[: self.PRINT_BUFFER_SIZE - 1]
        for i in range(self.PRINT_BUFFER_SIZE):
            m.write(at + i, text[i] if i < len(text) else 0x00 if i == len(text) else self.SPACE)
        self._text_end = at + len(text)

    def unmark_text(self) -> None:
        """put_textで字のあとに置いた00hを空白にする(PAUSEは00hを置かない。観察)"""
        if self._text_end is not None:
            self.m.write(self._text_end, self.SPACE)

    def print_text_of(self, code: bytes) -> tuple[bytes, int]:
        """中間コードcodeをPRINTの出すものとして読み、(print_textの字の並び, 数の数)にする
        (代替ROMルーチンが使う)。誤りがあればBasicError"""
        r = self.runner
        saved = r.code, r.pos, r.trailing
        try:
            r.code, r.pos = code, 0
            items, comma = r._print_items()
        finally:
            r.code, r.pos, r.trailing = saved
        return self.print_text(items, comma, Format()), sum(isinstance(v, Decimal) for v in items)

    def spell(self, text: bytes) -> bytes:
        """文字列に入った命令の中間コード(INPUTに命令のキーで答えたときなど)を、LISTと同じ
        綴りにする(観察)"""
        units = self.EDITOR.units_of(text)
        if all(c < self.EDITOR.TOKEN for c in units):
            return text
        words = pieces(units, self.keywords, self.CODES, **self.EDITOR.style())
        return bytes(c for word, _ in words for c in word)

    def show_print(self, items, comma: bool, fmt: Format = Format()) -> None:  # noqa: B008
        """PRINT・PAUSEの出し方"""
        text = self.print_text(items, comma, fmt)
        if self.PRINT_BUFFER is not None:
            self.put_text(text)
        self._message(text)
        self.display(True)
        self.state = "print"
        self.last_value = items[-1] if items else None

    @staticmethod
    def _half(v, t: bytes, half: int, sp: bytes) -> bytes:
        """,で分けたときの半分: 数は右に、文字列は左に寄せる。spは空白の字"""
        if isinstance(v, Decimal):
            t = t.rstrip(sp)[-half:]
            return sp * (half - len(t)) + t
        return t[:half] + sp * (half - len(t[:half]))

    def wait_enter(self) -> Steps:
        """PRINTのあと、ENTERを待つ(BRKで止める)。↓なら続けて、その行を終えたら止まる。
        ↑なら押しているあいだPRINTの行を出し、離すとそこで止まる(観察)"""
        r = self.runner
        self.where = "print"
        while True:
            if self.m.brk or self.mode != r.mode:
                r.resume = (r.addr, r.pos)
                kind = "stop" if self.m.brk else "mode"
                raise Break(self._line_now(), r.stopped_pos(), kind)
            k = self.keys.poll()
            if k is not None and self.shift_enter(k):
                continue
            if k is not None and k != "SHIFT":
                k = self._def_latched(k)
                if k is None:
                    continue
            if k is not None and k.startswith("DEF:"):
                # DEFのあとラベルのキーで、出している値を渡してラベルから実行し直す(観察)
                r.resume = (r.addr, r.pos)
                self.def_source = (None, self.last_value)
                raise Break(self._line_now(), r.stopped_pos(), "quiet", k)
            if k in ("ENTER", "DOWN"):
                r.stepping = r.waited_step = k == "DOWN"  # ENTERなら、前の↓は取り消す(観察)
                self.where = "run"
                self.display(False)
                yield KEY_DELAY
                return
            if k == "UP" and not self.PASSWORD.locked(self.m):  # 保護していれば↑は効かない(観察)
                r.resume = (r.addr, r.pos)
                line = self._line_now()
                yield from self.peek(line, r.stopped_pos())
                raise Break(line, r.stopped_pos(), "quiet")
            if k is not None and (k == "CL" or k in self.CODES or k.startswith("RSV:")):
                # CLか字のキーで、そこで止まって>に戻る(字と、SHIFTのあとのリザーブのキーは、
                # そのまま打ち始める。観察)
                r.resume = (r.addr, r.pos)
                yield KEY_DELAY
                raise Break(self._line_now(), r.stopped_pos(), "quiet", k)
            yield from self._key_wait()

    def _line_now(self) -> int:
        return self.PROGRAM.number_at(self.m, self.runner.addr) or 0

    def read_input(
        self, prompt: bytes | None, keep: bool, answer: tuple[bytes, int] | None = None
    ) -> Generator[int, None, bytes | None]:
        """INPUTの打ち込み。打った字(promptを残すときは、promptのあと)を返す。answerは、
        エラーのあとで呼び出した答えと、カーソルを置く位置"""
        head = list(prompt or b"") if keep else []
        self.editor = self.EDITOR(head)
        shown = list(prompt) if prompt is not None else list(self._codes("?"))
        if answer is not None:
            self.editor = self.EDITOR(head + list(answer[0]), len(head) + answer[1])
            self._show_editor()
        elif keep:
            self._show_editor()
        else:
            self.screen.show(shown)
        self.state = "input-wait"
        r = self.runner
        self.where = "input"
        while True:
            if self.m.brk or self.mode != r.mode:
                r.resume = (r.addr, r.stmt)  # CONTでINPUTからやり直す
                kind = "stop" if self.m.brk else "mode"
                raise Break(self._line_now(), r.stopped_pos(), kind)
            k = self.keys.poll()
            if k is None:
                yield from self._key_wait()
                continue
            yield KEY_DELAY
            if self.shift_enter(k):
                continue
            if k != "SHIFT":
                k = self._def_latched(k)
                if k is None:
                    continue
            if k.startswith("DEF:"):
                # DEFのあとラベルのキーで、打った字を渡してラベルから実行し直す(観察)
                r.resume = (r.addr, r.stmt)
                self.def_source = (self.editor.text()[len(head) :], None)
                raise Break(self._line_now(), r.stopped_pos(), "quiet", k)
            if k.startswith("RSV:"):
                # SHIFTのあとリザーブのキー: 登録した中身を打つ(@はENTER。観察)
                for u in self.shift_content(k[4:]):
                    if u == self.AT:
                        self.where = "run"
                        return self.editor.text()[len(head) :]
                    self.editor.type(u)
                self._show_editor()
                continue
            if k == "ENTER":
                self.where = "run"
                return self.editor.text()[len(head) :]
            if k == "DOWN":
                # 何も打たずにENTERを押したのと同じに進み、その行を終えたら止まる(観察)
                r.stepping = r.waited_step = True
                self.where = "run"
                return b""
            if k == "CL":
                self.editor = self.EDITOR(head)
                if keep:
                    self._show_editor()
                else:
                    self.screen.show(list(self._codes("?")) if self.INPUT_CL_ASKS else shown)
                continue
            if k in ("LEFT", "RIGHT", "DEL", "INS"):
                {"LEFT": lambda: self.editor.move(-1), "RIGHT": lambda: self.editor.move(1),
                 "DEL": self.editor.delete, "INS": self.editor.insert}[k]()  # fmt: skip
            elif k in self.CODES:
                self.editor.type(self.CODES[k])
            else:
                continue
            self._show_editor()

    def input_error(
        self, number: int, text: bytes, pos: int
    ) -> Generator[int, None, tuple[bytes, int] | None]:
        """INPUTの答えのエラー: 「ERROR n」を出してキーを待つ。CL・↑なら答えを打ち直させ
        (Noneを返す)、←・→なら答えをエラーの位置にカーソルを置いて呼び出す。ほかのキーと
        BRKは効かない(観察)"""
        r = self.runner
        self.where = "input"
        self._message(self._codes(f" ERROR {number}"))
        self.screen.symbol(self.ERROR_MARK, True)
        try:
            while True:
                if self.mode != r.mode:
                    r.resume = (r.addr, r.stmt)
                    raise Break(self._line_now(), r.stopped_pos(), "mode")
                k = self.keys.poll()
                if k in ("CL", "UP"):
                    return None
                if k in ("LEFT", "RIGHT"):
                    return text, min(pos, len(text))
                yield from self._key_wait()
        finally:
            self.screen.symbol(self.ERROR_MARK, False)

    def call_machine(self, addr: int) -> Steps:
        """CALL: 戻り番地RETURNを積んでCPUに渡し、RTNで戻ってくるのを待つ。呼んだ先の頭では、
        ROMのある本体と同じくJが1、RがCALL_R(戻り番地を積んだあと)になる(観察)。ほかの
        レジスタの値は、POINTER_IN_XのXとCALL_REGSのほかは決めない"""
        cpu = self.m.cpu
        cpu.ram[1] = 1  # J
        for a, v in self.CALL_REGS.items():
            cpu.ram[a] = v
        self.call = Call()
        if self.TEXT_POINTER is not None or self.POINTER_IN_X:
            r = self.runner
            if self.where == "run":
                base = r.addr + self.LINE_HEAD
            else:
                # 打った行は中間コードにしてTYPED_ATに置く(マシン語がポインタの先を読める)
                base, size = self.TYPED_AT, self.TYPED_SIZE
                self.m.mem[base : base + size] = r.code[:size].ljust(size, self.TYPED_FILL)
            at = (base + r.pos - 1) & 0xFFFF
            self.call.base = base
            if self.TEXT_POINTER is None:
                cpu.ram[4], cpu.ram[5] = at & 0xFF, at >> 8
            else:
                self.m.mem[self.TEXT_POINTER] = at & 0xFF
                self.m.mem[self.TEXT_POINTER + 1] = at >> 8
                cpu.ram[0x15] = 0x10 if self.where == "run" else 0x00  # 実行中かのフラグ(観察)
        self.guard = self.m.outside_ram()  # # ram: でRAMの終わりが動くので、CALLごとに作る
        cpu.r = self.CALL_R + 2
        if self.OUTER_RETURN is not None:
            cpu.r += 2
            cpu.push(self.OUTER_RETURN >> 8)
            cpu.push(self.OUTER_RETURN & 0xFF)
        cpu.push(RETURN >> 8)
        cpu.push(RETURN & 0xFF)
        cpu.pc = addr
        self.active = False
        back, self.where = self.where, "call-run" if self.where == "run" else "call-direct"
        yield 1
        self.where = back
        self.call_returned(back == "run")

    def call_returned(self, running: bool) -> None:
        """CALLから戻った。エラー・BREAKで戻ったか、代替ROMルーチンのないROMのルーチンでやめたなら、
        LineErrorかBreakを投げる。runningはプログラムの中のCALLか"""
        call, self.call = self.call, Call()
        if call.end == "outer":
            self._call_outer(call.base)
        elif call.end is not None:
            self._call_ended(call.end, running)
        if call.missing is not None:
            # ROMなしにないROMのルーチンを呼んだか、代替ROMルーチンが時間を進めずに待ち続けた:
            # そこでやめて知らせる
            if call.stalled is not None:
                self.stalled = call.stalled
            else:
                self.notice = call.missing
            if running:
                r = self.runner
                r.resume = (r.addr, r.pos)  # CONTで、CALLの次から続けられる
                raise Break(self.PROGRAM.number_at(self.m, r.addr) or 0, r.stopped_pos())

    def _pointed_line(self, at: int) -> tuple[int, int, int] | None:
        """番地atを含む、登録した行の(行番号, 行の番地, 行の中の位置)"""
        m = self.m
        for number, a in self.PROGRAM.lines(m):
            head = a + self.LINE_HEAD
            if head <= at < self.PROGRAM.next_line(m, a) - 1:
                return number, a, at - head
        return None

    def _call_outer(self, base: int) -> None:
        """CALLのマシン語が、BASICの命令の続きへの戻り番地へ戻った(OUTER_RETURN)。baseは
        CALLの行を置いた番地"""
        cpu = self.m.cpu
        if cpu.c:
            raise BasicError(cpu.ram[self.OUTER_ERRNO])
        x = cpu.ram[4] | cpu.ram[5] << 8
        self.runner.pos = max(0, x + 1 - base)

    def _call_ended(self, end: str, running: bool) -> None:
        """CALLから、エラーかBREAKで戻った。エラーの行は、TEXT_POINTERの番地が指す行。BREAKは
        CALLの行で止まり(打った行なら0)、CONTはポインタが指す文の次の文から続ける(観察)"""
        m, r = self.m, self.runner
        assert self.TEXT_POINTER is not None
        at = m.mem[self.TEXT_POINTER] | m.mem[self.TEXT_POINTER + 1] << 8
        pointed = self._pointed_line(at)
        if end == "error":
            line, pos = (pointed[0], pointed[2] + 1) if pointed else (0, 0)
            raise LineError(m.cpu.ram[0x14], line, pos)
        if pointed is not None:
            _, a, pos = pointed
            r.resume = (a, r.statement_end(self.PROGRAM.body(m, a), pos + 1))
        else:
            r.resume = (r.addr, r.pos) if running else None
        raise Break(self.PROGRAM.number_at(m, r.addr) or 0 if running else 0, r.stopped_pos())

    def _stop_message(self, e: Break | LineError) -> None:
        """「BREAK IN 行番号」か「ERROR 番号 IN 行番号」を出す"""
        if isinstance(e, LineError):
            # 左の空白はPC-1251で2字、PC-1245で1字(観察)
            text = self.dialect.error_lead + self._codes(f"ERROR {e.number} IN {e.line}")
            self._message(text)
            self.screen.symbol(self.ERROR_MARK, True)
            self.state = "program-error"
        else:
            self._message(self._codes(f" BREAK IN {e.line}"))
            self.state = "break"
        self.stopped_at = (e.line, e.pos)

    def trapped(self, pc: int, own: bool) -> bool:
        """CALLの最中に、CPUがguardの番地pcで止まった。戻り番地ならBASICに戻す。本体の
        guard(own)で止まったときは、代替ROMルーチンを動かす。代替ROMルーチンがないか、時間を
        進めずに待ち続けたら、CALLをやめてBASICに戻る(プログラムの中ならBREAK)。扱ったらTrue"""
        if pc == RETURN:
            if self.TEXT_POINTER is not None and self.m.cpu.ram[0x15] == 0x30:
                self.call.end = "break"  # 内部RAMの15hが30hならBREAK(観察)
            self.active = True
            return True
        if pc == self.OUTER_RETURN:
            self.call.end = "outer"
            self.active = True
            return True
        if pc == RETURN + 1 and self.TEXT_POINTER is not None:
            # 戻り番地の次へ戻ると、14h番地の番号のエラー(観察)
            self.call.end = "error"
            self.active = True
            return True
        if not own:
            return False
        try:
            if routines.call(self.m, pc):
                return True
        except routines.Stalled as e:
            self.call.stalled = e.routine
        self.call.missing = pc  # BASICに戻ってやめる
        self.active = True
        return True

    def set_angle(self, which: str) -> None:
        """DEGREE・RADIAN・GRAD: 角度の表示記号を変える(角度は記号で決まる。angle_turn)"""
        raise NotImplementedError

    def _error(self, number: int) -> None:
        self.state = "error"
        self.screen.show(list(self._codes(f" ERROR {number}")))
        self.screen.symbol(self.ERROR_MARK, True)

    def _layout(self, units, head: int = 0, sep: int | None = None, glued: bool = False):
        """editor.layoutを、この系統の字のコードで"""
        sep = self.SPACE if sep is None else sep
        units = self.EDITOR.units_of(units)
        return layout(units, self.keywords, self.CODES, head, sep, glued, **self.EDITOR.style())

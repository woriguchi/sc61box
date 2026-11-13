"""カセット: CSAVE・CLOAD・CLOAD?・CLOAD M・MERGE・CHAIN(系統によらない部分)。テープの
形は系統ごとのcassette.py(FORMAT)が受け持ち、ここはBASICの命令としての
ふるまい(待ち方、液晶、BRK、RAMへの置き方)を受け持つ。字のコードと中間コードの番号は
Basicのものを使う
"""

from collections.abc import Generator
from types import ModuleType

from ..machine import TICK_2MS
from . import timing
from .cassette import Received
from .errors import BasicError
from .evaluate import Evaluator, expect_end
from .variables import word

Steps = Generator[int, None, None]

TAPE_END = timing.ms(13.0)  # カセットを読み終えてから>を出すまで(観察)
CSAVE_END = timing.ms(5.0)  # カセットに送り終えてから>を出すまで(観察)
CSAVE_M_START = timing.ms(80.0)  # CSAVE Mで、音を出し始めるまでに余分にかかる(観察)


class TapeIO:
    """FORMATはテープの形(系統ごとのcassette.py)、T_CHAINはCHAINの中間コード"""

    FORMAT: ModuleType
    T_CHAIN: int
    TAIL_ONES = 0  # CSAVEで、最後のバイトのあと(BRKで止めたときも)に足す1のビットの数
    M_START = CSAVE_M_START
    START_HOLD: tuple[int, int] | None = None  # 初めの1の前にCポートに出す音の値と時間
    END_HOLD: tuple[int, int] | None = None  # 送り終えたあとCポートに出す音の値と時間
    LEADER_CHECKS = 15  # 初めの1のあいだにBRKを見る回数(終わりの約500msでは見ない。観察)

    def __init__(self, basic) -> None:
        self.basic = basic
        self.m = basic.m
        self.dialect = basic.dialect
        codes = basic.CODES
        self.QUOTE, self.COMMA, self.SPACE = basic.QUOTE, basic.COMMA, basic.SPACE
        self.QUESTION, self.SEMICOLON, self.LETTER_M = codes["?"], codes[";"], codes["M"]
        self.T_CSAVE, self.T_CLOAD, self.T_MERGE = basic.T_CSAVE, basic.T_CLOAD, basic.T_MERGE
        self.program = basic.PROGRAM

    def command(self, code: bytes) -> Steps:
        """RUN・PROモードのCSAVE・CLOAD・CLOAD?・CLOAD M・MERGE。BRKで止めると、何も
        出さずに>に戻る(観察)。読む命令は、始めたときのm.on_cloadを受け取り、終えたら読み終えたかを
        それに知らせる(状態を戻して捨てたCLOADが、あとで置いた知らせ先を使わないように)"""
        done = None
        if code[0] != self.T_CSAVE:
            done, self.m.on_cload = self.m.on_cload, None
        loaded = False
        try:
            if code[0] == self.T_CSAVE:
                yield from self.csave(code, 1)
            else:
                loaded = yield from self.cload(code)
        finally:
            self.quiet()
            if done is not None:
                done(loaded)
        self.basic._prompt()

    def csave(self, code: bytes, pos: int) -> Generator[int, None, bool]:
        """CSAVE ["名前"]、CSAVE M ["名前";]始め,終わり。送り終えたらTrue、BRKで止めたら
        False"""
        e = self.basic.EVALUATOR(self.m, code, pos)
        machine = e.take(self.LETTER_M)
        name = e.string_literal() if e.peek() == self.QUOTE else b""
        place = b""
        if machine:
            if name and not e.take(self.SEMICOLON):
                raise BasicError(1, e.pos)
            start = self._address(e)
            if not e.take(self.COMMA):
                raise BasicError(1, e.pos)
            last = self._address(e)
            expect_end(e)
            if start > last:
                raise BasicError(9, e.pos - 1)
            data = bytes(self.m.read(a) for a in range(start, last + 1))
            place = self.FORMAT.place_field(start, last - start + 1)
            yield self.M_START
        else:
            expect_end(e)
            data = bytes(self.m.mem[self.program.top(self.m) : self.program.end(self.m)])
        kind = self.FORMAT.MACHINE if machine else self.FORMAT.BASIC
        bits = self.FORMAT.bits(self.FORMAT.file_bytes(kind, name, data, place))
        head = self.FORMAT.HEAD + (len(place) + 1 if place else 0)
        return (yield from self._send_bits(bits, head, len(data)))

    def _address(self, e: Evaluator) -> int:
        v = e.integer()
        if not 0 <= v <= 0xFFFF:
            raise BasicError(3, e.pos)
        return v

    def _send_bits(self, bits: list[int], head: int, size: int) -> Generator[int, None, bool]:
        """ビットを、Cポートの4kHzと2kHzの音の切り替えで送る(1ビット2ms。観察)。headは
        BRKを見ない頭のバイトの数、sizeは中身(プログラムかデータ)のバイト数。送り終えるか
        BRKで止めると、1をTAIL_ONES送ってEND_HOLDを出す(観察)"""
        m = self.m
        mode = -1
        send = bits + [1] * self.TAIL_ONES
        stopped = False
        yield self.dialect.tape_before
        try:
            if self.START_HOLD is not None:
                level, hold = self.START_HOLD
                m.out_c(m.pc_out & 0x0F | level << 4)
                yield hold
            i = 0
            while i < len(send):
                if not stopped and i < len(bits) and m.brk and self._brk_checked(i, head, size):
                    stopped = True  # 音は止める(プログラムの中なら、このあとBREAK)
                    send = send[:i] + [1] * self.TAIL_ONES
                    continue
                want = self.FORMAT.ONE if send[i] else self.FORMAT.ZERO
                if want != mode:
                    m.out_c(m.pc_out & 0x0F | want << 4)
                    mode = want
                i += 1
                yield self.FORMAT.BIT
            if self.END_HOLD is not None:
                level, hold = self.END_HOLD
                m.out_c(m.pc_out & 0x0F | level << 4)
                yield hold
        finally:
            self.quiet()
        # BRKで止めても、送り終えたときと同じだけ待ってから>に戻る(観察)
        yield CSAVE_END + self.dialect.csave_after
        return not stopped

    def _after_brk(self, seen: int) -> Steps:
        """CLOADをBRKで止めたとき: 読み終えたときと同じだけ、BRKを見たとき(サイクルseen)から
        待つ(観察)"""
        if self.dialect.cload_after:
            left = seen + self.dialect.cload_after + TAPE_END - self.m.cpu.cycles
            if left > 0:
                yield left

    def _brk_checked(self, i: int, head: int, size: int) -> bool:
        """CSAVEでi番目のビットを送る前にBRKを見るか。初めの1のあいだは約500msごと(最後の
        約500msでは見ない)。そのあとは、頭のheadバイト(種類と名前、CSAVE Mの置く場所)では見ず、
        中身のsizeバイトの1バイトごとに、下位の4ビットを送ったところで見る。中身にはさむ
        チェックサムと、中身のあとのバイト(終わりのマークなど)では見ない(観察)"""
        f = self.FORMAT
        if i < f.LEADER:
            return 0 < i <= 250 * self.LEADER_CHECKS and i % 250 == self.dialect.leader_brk
        i -= f.LEADER + head * f.HEAD_BITS
        if i < 0 or i % f.DATA_BITS != f.BRK_AT:
            return False
        k = i // f.DATA_BITS
        return k % (f.BLOCK + 1) != f.BLOCK and k - k // (f.BLOCK + 1) < size

    def quiet(self) -> None:
        if self.m.pc_out & 0xF0:
            self.m.out_c(self.m.pc_out & 0x0F)

    def cload(self, code: bytes, pos: int = 1) -> Generator[int, None, bool]:
        """CLOAD ["名前"]、CLOAD M ["名前"[;番地]]、CLOAD? ["名前"]、MERGE ["名前"]、
        CHAIN ["名前"]。読み終えたらTrue、BRKで止めたらFalse。名前や種類の違うファイル、
        名前のチェックサムの合わないファイルは飛ばし、読めるファイルが来るまで待つ(観察)"""
        head = code[pos - 1]
        e = self.basic.EVALUATOR(self.m, code, pos)
        verify = head == self.T_CLOAD and e.take(self.QUESTION)
        machine = head == self.T_CLOAD and not verify and e.take(self.LETTER_M)
        name = e.string_literal() if e.peek() == self.QUOTE else None
        place: int | None = None
        if machine and (
            name is None and e.pos < len(code) or name is not None and e.take(self.SEMICOLON)
        ):
            place = self._address(e)
        if head != self.T_CHAIN:
            expect_end(e)
        kind = self.FORMAT.MACHINE if machine else self.FORMAT.BASIC
        yield self.dialect.tape_before
        found = yield from self._find_file(kind, name)
        if found is None:
            yield from self._after_brk(self.m.cpu.cycles)
            return False
        try:
            if self.dialect.cload_busy:
                # 読むファイルが見つかると、右端に*を出し、液晶を点けてBUSYの記号を点ける(観察)
                self._show_found()
                self.basic.display(True)
                self.basic.screen.symbol("BUSY", True)
            loaded = yield from self._cload_body(head, verify, machine, place, *found)
            if not loaded:
                yield from self._after_brk(self.m.cpu.cycles)
        finally:
            if self.dialect.cload_busy:
                self.basic.screen.symbol("BUSY", False)
        return loaded

    def _show_found(self) -> None:
        """読むファイルが見つかったことを、液晶の右端の*で知らせる(1行の液晶は消してから)"""
        cells = self.basic.screen.cells
        self.basic.screen.show([self.SPACE] * (cells - 1) + [self.basic.CODES["*"]])

    def _cload_body(
        self, head: int, verify: bool, machine: bool, place: int | None, tape, rec
    ) -> Generator[int, None, bool]:
        """cloadの続き: 見つけたファイルの中身を読んで置く"""
        m = self.m
        error: int | None = None
        cut = False
        start = 0
        try:
            if machine:
                start, data, last = self.FORMAT.machine_body(rec.data, self.FORMAT.HEAD)
            else:
                data, last = self.FORMAT.basic_body(rec.data, self.FORMAT.HEAD)
        except self.FORMAT.ChecksumError as err:
            data, last, error, cut = err.data, err.at, err.at, err.cut
            start = self.FORMAT.machine_start(rec.data, self.FORMAT.HEAD) if machine else 0
        # 中身は届いたバイトから順に置く(観察: CLOADはプログラムの終わりを読み始める所に
        # してから置き、MERGEは終わりのFFの所から置く。PC-1261系とPC-1350は区切りを置くことがある)
        if machine:
            at, first = start if place is None else place, self.FORMAT.HEAD + 9
        else:
            at = self.program.merge_at(m) if head == self.T_MERGE else self.program.top(m)
            first = self.FORMAT.HEAD
            if not verify and head != self.T_MERGE:
                self.basic.VARS.set_end(m, at)
        reset_at = self.program.end(m) if head == self.T_MERGE else at
        program_load = not machine and not verify
        differs = False  # CLOAD?で違いを見つけた(そこで読むのをやめる)
        vars_ = self.basic.VARS
        for k, b in enumerate(data):
            yield from self._tape_wait(tape, rec.at(first + k + k // self.FORMAT.BLOCK))
            if m.brk:
                break
            if verify:
                if m.read(at + k) != b:
                    differs = True
                    break
                continue
            if program_load and at + k >= word(m, vars_.ARRAY_PTR):
                # 行が配列の場所に届くと、配列(PC-1261系とPC-1350は2字の名前の変数も)を消して
                # 続け、固定の変数の場所に届くとERROR 6。プログラムは読み始めた所で終わる(観察)
                if at + k >= vars_.ARRAY_TOP:
                    self.program.put(m, reset_at, b"")
                    raise BasicError(6)
                vars_.clear_arrays(m)
            m.write((at + k) & 0xFFFF, b)  # ROMの番地には置かない(本体の書き込みと同じ)
        if not differs:
            yield from self._tape_wait(tape, rec.at(last))
        while cut and not differs and not m.brk:
            yield TICK_2MS  # テープが途中で切れていれば、続きを待ち続ける(観察)
        if error is not None or m.brk:
            # チェックサムが合わないときとBRKで止めたときは、プログラムの終わりの番地にFFを置く。
            # プログラムを読んでいたなら、読み始めた所で終わる(観察)
            if program_load:
                self.program.put(m, reset_at, b"")
            else:
                m.mem[self.program.end(m)] = 0xFF
        elif program_load:
            self.program.put(m, at, data)
            self.program.loaded(m, at, data)
        if m.brk:
            return False
        if program_load:
            self.basic.stopped_at = None
        failed = error is not None or verify and (differs or m.read(at + len(data)) != 0xFF)
        if failed and not self.dialect.cload_after:
            raise BasicError(8)
        # 読み終えて>を出すまで待つ機種は、チェックサムが合わないときとCLOAD?で違うときも、
        # 同じだけ待ってからERROR 8を出す(観察)
        if self.dialect.cload_after:
            yield self.dialect.cload_after
        if self.dialect.cload_busy:
            self.basic.display(False)
        if program_load and not failed:
            self.program.separated(m, at, data)
            if head == self.T_MERGE:
                self.program.merged(m, at)
        yield TAPE_END
        if failed:
            raise BasicError(8)
        return True

    def _find_file(
        self, kind: int, name: bytes | None
    ) -> Generator[int, None, tuple[object, Received] | None]:
        """テープから、種類と名前の合うファイルを探して、名前のチェックサムまで読む。(テープ,
        読んだもの)。BRKで止めたらNone。テープがなければ、入れられるまで待つ"""
        m, f = self.m, self.FORMAT
        tape = None
        files: list[Received] = []
        k = 0
        while True:
            if m.brk:
                return None
            if m.tape is not tape:
                tape = m.tape
                files, k = [], 0
                if tape is not None:
                    m.xin(m.cpu.cycles)  # 読み始めると再生が始まる
                    files = f.files(tape)
            if tape is not None and k < len(files):
                rec = files[k]
                k += 1
                if rec.times[0] < m.cpu.cycles - (tape.start or 0) or len(rec.data) < f.HEAD:
                    continue  # 頭を聞き逃したか、短すぎる
                yield from self._tape_wait(tape, rec.at(f.HEAD - 1))
                if m.brk:
                    return None
                field = rec.data[1 : f.HEAD - 1]
                if f.checksum(field) != rec.data[f.HEAD - 1] or rec.data[0] != kind:
                    continue
                if name is not None and f.read_name(field) != name[: f.NAME_SIZE]:
                    continue
                return tape, rec
            yield TICK_2MS

    def _tape_wait(self, tape, at: float) -> Steps:
        """テープの時刻at(再生を始めてからのサイクル)まで待つ。BRKで抜ける"""
        m = self.m
        while m.cpu.cycles - (tape.start or 0) < at and not m.brk:
            yield max(1, min(TICK_2MS, int(at - (m.cpu.cycles - (tape.start or 0)))))

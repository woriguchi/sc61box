"""BASICが計算に使うRAM(作業領域)

ROMのある本体は、計算の途中の演算子・関数と待たせている値を液晶RAMに積み、文字列をRAMの
作業場所に置く。PC-1251系は液晶に映る所に積む(液晶を消しているあいだに書くので、ふつうは
見えないが、マシン語が液晶を点けたままにすると画面が乱れて見える)。PC-1261系とPC-1350は液晶に
映らない所に積む。ここでは、マシン語から見える形(番地、積む値の形、ポインタ)をROMのある本体の
観察に合わせる。ROMの中の受け渡しの順序だけで決まる値(前の値の残り、計算の途中の桁)は
まねない。
"""

from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from weakref import WeakKeyDictionary

from ..number import put_num, put_str_work
from .errors import BasicError

STRING = 0xD0  # 文字列の値の印(8バイトの5バイト目。続けて番地と長さ)


@dataclass(frozen=True)
class Layout:
    ops: int  # 演算子・関数の中間コードを積む所
    ops_size: int
    ops_count: int | None  # 積んだ数(opsの下位バイトに足した値)を置く番地
    values: int  # 待たせている値を8バイトずつ積む所
    values_size: int
    values_top: int | None  # 次に積む番地の下位バイトを置く番地
    strings: int  # 文字列の作業場所(頭の番地。上位バイトは作業場所の中で変わらない)
    strings_end: int  # 作業場所の終わり(含まない)
    strings_next: int | None  # 次に置く番地の下位バイトを置く番地(Noneなら持っておく)
    copy: int  # 代入した値の写し(8バイト)
    copy_number: int | None  # 代入した数の、もう1つの写し
    target: int  # 代入する変数の番地−1(2バイト)と、型(数は88h、文字列は00h)
    call: int  # CALLの番地(上位バイトが先)
    number_work: int  # STR$が数を字にする28バイトの頭
    number_first: int  # そのうちSTR$のあとに跡が残る所の頭(頭からのバイト数)
    number_text: int  # STR$が字の並び(24バイト)を置く所
    unary_minus: int  # 符号の−を積むときの中間コード
    string_array: int  # 文字列の配列の名前を積むときに、字のコードに重ねるビット
    array_kinds: bool  # 配列の名前の種類のバイトを、ops+10hからの並びに積む
    dim_pushes: bool  # DIMで2次元の配列を作るとき、1つ目の大きさを積む
    colon: int  # 文の区切りの字(積みきれないエラーの位置を決める)
    for_at: int  # FORの記録を積む所
    for_top: int  # 次に積む番地の下位バイトを置く番地
    gosub_at: int  # GOSUBの記録を積む所
    gosub_top: int  # 次に積む番地の下位バイトを置く番地
    # FORの記録が「変数の番地−1、終わりの2バイトの整数、増分の8バイトの数、戻る位置」
    # (PC-1251系)か、「変数の番地−1、終わりと増分の7バイトの数、戻る位置」か。戻る位置は、
    # PC-1251系は番地と行番号の4バイト、ほかは番地の2バイト
    int_limit: bool
    # 直前に実行した文の最後のバイトの番地(下位が先)を置く番地。line_numbersなら、続けてその
    # 行の行番号の2バイトを置く(PC-1251系)
    last: int
    line_numbers: bool
    # READで最後に読んだ値の最後のバイトの番地を置く番地(RUNの直後は最初の行、RESTORE nの
    # あとはn行の、本文の1つ前の番地)
    data: int
    reading: int | None  # CALLのとき、いま読んでいる位置(CALLの番地の最後のバイト)を置く番地
    program_head: int | None  # プログラムの頭(FFh)の番地を置く番地
    # 状態のビット: RUNで06hにし、PRINT・PAUSEでビット2を、READでビット1を下ろし、RESTOREで
    # ビット1を立てる
    flags: int
    print_end: int  # PRINT・PAUSEで出した字の終わりの桁(1つだけの数は右に寄せるので液晶の幅)
    print_item: int | None  # PRINT・PAUSEの最後の項目の欄の頭の桁
    print_token: int | None  # PRINT・PAUSEの中間コードの番地(下位が先)
    # USINGの数の書式の、小数点より前の#の数、小数点と後ろの#の数と、文字列の書式の&の数(3バイト)
    using: int
    print_copies: bool  # PRINT・PAUSEの最初の項目と,のあとの項目を、代入した値の写しの場所に置く
    print_page: int | None  # PRINT・PAUSEで出した液晶の字を置く所


class Text(bytes):
    """文字列の作業場所に置いた文字列(atは置いた番地)"""

    at: int


_free: WeakKeyDictionary = WeakKeyDictionary()  # strings_nextのない本体の、次に置く番地


def free(m, w: Layout) -> int:
    """文字列の作業場所の、次に置く番地"""
    if w.strings_next is None:
        return _free.get(m, w.strings)
    return w.strings & 0xFF00 | m.mem[w.strings_next]


def set_free(m, w: Layout, at: int) -> None:
    if w.strings_next is None:
        _free[m] = at
    else:
        put(m, w.strings_next, bytes([at & 0xFF]))


def place(m, w: Layout, s: bytes, at: int | None = None) -> Text:
    """sを文字列の作業場所のat(なければ空いている所)に置き、次に置く番地をそのあとにする。
    作業場所からはみ出す字は書かない"""
    if at is None:
        at = free(m, w)
    end = min(at + len(s), w.strings_end)
    if at < end:
        put(m, at, s[: end - at])
    set_free(m, w, max(end, at))
    t = Text(s)
    t.at = at
    return t


def release(m, w: Layout, s: bytes) -> None:
    """作業場所の文字列sを使い終えた(数を返す演算)。次に置く番地をsの番地に戻す"""
    at = getattr(s, "at", None)
    if at is not None:
        set_free(m, w, at)


def entry(v: Decimal | bytes) -> bytes:
    """積む値の8バイト。数はBASICの変数と同じ形、文字列は印と番地と長さ"""
    if isinstance(v, bytes):
        at = getattr(v, "at", 0)
        return bytes([0, 0, 0, 0, STRING, at & 0xFF, at >> 8, len(v) & 0xFF])
    buf = bytearray(8)
    put_num(buf, 0, v)
    return bytes(buf)


class Stacks:
    """演算子・関数と、待たせている値の積み場所。積みきれなければERROR 5。ただし、演算子が
    積んであるだけ積んであり、値には空きがあるところへ2項の演算子が来たらERROR 1(観察)"""

    def __init__(self, m, w: Layout) -> None:
        self.m, self.w = m, w
        self.ops = self.values = 0

    def push(
        self, token: int, value: Decimal | bytes | None = None, kind: int | None = None
    ) -> None:
        """tokenと待たせる値valueを積む。kindは配列の名前の種類(array_kindsの機種)"""
        m, w = self.m, self.w
        if self.ops == w.ops_size:
            full = value is None or self.values == w.values_size
            raise BasicError(5 if full else 1)
        put(m, w.ops + self.ops, bytes([token]))
        if kind is not None and w.array_kinds:
            put(m, w.ops + 0x10 + self.ops, bytes([kind]))
        self._count(self.ops + 1, self.values)
        if value is not None:
            if self.values == w.values_size:
                raise BasicError(5)
            put(m, w.values + 8 * self.values, entry(value))
            self._count(self.ops, self.values + 1)

    def pop(self, value: bool) -> None:
        self._count(self.ops - 1, self.values - value)

    def reset(self) -> None:
        """何も積んでいない数を書く"""
        self._count(0, 0)

    def _count(self, ops: int, values: int) -> None:
        m, w = self.m, self.w
        self.ops, self.values = ops, values
        if w.ops_count is not None:
            put(m, w.ops_count, bytes([w.ops + ops & 0xFF]))
        if w.values_top is not None:
            put(m, w.values_top, bytes([w.values + 8 * values & 0xFF]))


def assigning(m, w: Layout, addr: int, string: bool) -> None:
    """代入する変数(番地addr)を書く"""
    put(m, w.target, bytes([addr - 1 & 0xFF, addr - 1 >> 8 & 0xFF, 0x00 if string else 0x88]))


def assigned(m, w: Layout, v: Decimal | bytes) -> None:
    """代入した値の写しを書く"""
    data = entry(v)
    put(m, w.copy, data)
    if w.copy_number is not None and isinstance(v, Decimal):
        put(m, w.copy_number, data)


def called(m, w: Layout, addr: int) -> None:
    put(m, w.call, bytes([addr >> 8, addr & 0xFF]))


def put_number_text(
    m, w: Layout, text: bytes, codes: dict[str, int], with_text: bool = True
) -> None:
    """STR$(with_textでないときはPRINT)が数を字にした跡(観察)。PRINTは字の並びを置かない"""
    text_at = w.number_text if with_text else None
    areas = [(w.number_work + w.number_first, w.number_work + 28)]
    if text_at is not None:
        areas.append((text_at, text_at + 24))
    before = [bytes(m.mem[lo:hi]) for lo, hi in areas]
    put_str_work(m, w.number_work, w.number_first, text_at, text, codes)
    for (lo, hi), old in zip(areas, before, strict=True):  # putを通して書き直す
        new = bytes(m.mem[lo:hi])
        m.mem[lo:hi] = old
        put(m, lo, new)


def record_size(w: Layout) -> tuple[int, int]:
    """(FORの記録の大きさ, GOSUBの記録の大きさ)"""
    return (16, 4) if w.int_limit else (18, 2)


def for_record(w: Layout, var: int, limit: Decimal, step: Decimal, back: bytes) -> bytes:
    """FORの記録。varは変数の番地、backは戻る位置(position)"""
    head = bytes([var - 1 & 0xFF, var - 1 >> 8 & 0xFF])
    lim, stp = entry(limit), entry(step)
    if w.int_limit:
        n = int(limit) & 0xFFFF
        return head + bytes([n & 0xFF, n >> 8]) + stp + back
    return head + lim[:7] + stp[:7] + back


def set_records(m, w: Layout, loops: int, gosubs: int) -> None:
    """積んだFOR・GOSUBの数を書く"""
    fs, gs = record_size(w)
    put(m, w.for_top, bytes([w.for_at + fs * loops & 0xFF]))
    put(m, w.gosub_top, bytes([w.gosub_at + gs * gosubs & 0xFF]))


def put_word(m, at: int | None, v: int) -> None:
    """atに2バイトの番地vを下位から書く(atがNoneなら書かない)"""
    if at is not None:
        put(m, at, bytes([v & 0xFF, v >> 8 & 0xFF]))


def put(m, at: int, data: bytes) -> None:
    """作業領域にdataを書く。作業領域へはすべてここを通して書き、文の途中なら書いた順を覚える
    (Timeline)"""
    tl = getattr(getattr(getattr(m, "basic", None), "runner", None), "timeline", None)
    if tl is not None:
        tl.wrote(at, bytes(m.mem[at : at + len(data)]), data)
    m.mem[at : at + len(data)] = data
    m.lcd_dirty = True


class Timeline:
    """1つの文のあいだに作業領域へ書いた順と時刻。文の時間を待つあいだに、書いた順に書き戻す

    ROMのある本体は、式を読み進めるのに合わせて演算子と値を1つずつ積み、計算のたびに時間が
    かかるので、液晶を点けたままにすると積むようすが少しずつ変わって見える(観察)。ROMなしの
    BASICは文を一度に実行して残りの時間を待つので、書いたもの(積んだ数やポインタも)を、その
    ときまでにかかった計算の時間とともに覚えておき、待つあいだに書き戻す。文が終わったときの
    RAMは変わらない。Runnerが持ち、文ごとに作り直す"""

    def __init__(self, meter) -> None:
        self.meter = meter  # 文の頭からかかった計算の時間(cycles)
        self.writes: list[tuple[int, int, bytes, bytes]] = []  # (時刻, 番地, 前の中身, 書いたもの)
        self.pending: deque[tuple[int, int, bytes, bytes]] | None = None  # 書き戻しの残り
        self.after: list[tuple[int, bytes]] = []  # 文が終わったときの中身

    def wrote(self, at: int, old: bytes, new: bytes) -> None:
        if self.pending is None:
            self.writes.append((self.meter.cycles, at, old, new))

    def rewind(self, m) -> bool:
        """文の頭の中身に戻して、書き戻しを始める。書いたものがなければFalse"""
        if not self.writes:
            return False
        self.after = [(at, bytes(m.mem[at : at + len(new)])) for _, at, _, new in self.writes]
        for _, at, old, _ in reversed(self.writes):
            m.mem[at : at + len(old)] = old
        self.pending = deque(self.writes)
        m.lcd_dirty = True
        return True

    def next_time(self) -> int | None:
        return self.pending[0][0] if self.pending else None

    def step(self, m) -> None:
        """次の1つを書く"""
        if self.pending:
            _, at, _, new = self.pending.popleft()
            m.mem[at : at + len(new)] = new
            m.lcd_dirty = True

    def finish(self, m) -> None:
        """書き戻しの途中なら、残りを書き終える(文が終わったときの中身にする)"""
        if self.pending is not None:
            self.pending.clear()
            for at, data in self.after:
                m.mem[at : at + len(data)] = data
            m.lcd_dirty = True

"""ROMなしで動かすときに、ROMの代わりに置くもの

ROMのファイルがないときは、ROMの番地を0で埋めて動かす(machine.new_machineのrom=False)。
本の見本やエミュレータに同梱のプログラムには、ROMの文字の形の表を読むものや、ROMの
ルーチンを呼ぶものがある。そのいくつかがROMなしでも動くように、次のものを用意する。

- 文字の形の表。PC-1251と同じ番地と並び(本体の文字コードcの形が、11h〜1Fhは4414h+5c、
  30h〜6Ahは43C4h+5cから5バイト)に置く。字の形は、エミュレータで1から描いたもの
  (シャープのROMの字の形は使っていない)
- 代替ROMルーチン。その番地に飛んできたら、エミュレータが働きをまねて、呼んだ所へ戻す

代替ROMルーチンは、ROMのプログラムをコピーしないように、次の決まりを守って作った。

- 入口は、romsymsの表にある番地だけ(市販の資料の入口の表に、ROMのある本体で呼んで働きを
  確かめた入口を加えたもの)
- まねるのは、入口で受け取るもの(内部RAM、メモリ)と、戻るときに返すもの(内部RAM、
  キャリー、エラーの番号)だけ。どちらも、ROMのある本体で値を与えて呼び、結果を見て決めた。
  かかる時間は、そのときに測ったサイクル数の真ん中の値にした
- ROMの命令の並び、ルーチンの中の分け方、ROMの中の表はまねていない。作業に使うRAMも途中の
  使い方はまねず、戻ったときに変わっている所だけを、ROMのある本体と同じにした。
  計算はPythonのdecimalとmathで行うので、答えの下の桁がROMと違うことがある。
  返すもの以外のレジスタやRAMの値もROMと違う
- ROMの番地を読むと、上の文字の形の表のほかは0が返る。ただしBASIC ROMの番地は、ROMの中身を
  乱数の表として読むゲームのために、エミュレータの作る乱数の並びで埋める(fill_data)

どれも、ROMなしの作業欄(workbench)と、ROMなしのBASICのCALLで使う。ここにあるのはPC-1251系と
PC-1245のもの(MODELS)。PC-1260/1261/1262のものはnorom1261.py、PC-1350のものはnorom1350.pyに
ある。代替ROMルーチンは、どれも登録簿(routines.py)から呼ぶ。installは機種の文字の形の表を書く。
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from weakref import WeakKeyDictionary

from .basictext import CHARS
from .charset import ASCII, CODES, FROM_ASCII, glyph
from .machine import TICK_2MS
from .number import (
    angle_turn,
    arc_value,
    compute,
    cut,
    get_num,
    leading_number,
    number_text,
    power,
    put_num,
    random_value,
    to_degrees,
    to_dms,
    trig_value,
)
from .routines import CheckSpec


def font_addr(code: int) -> int:
    """本体の文字コードcodeの形の番地(PC-1251のROMと同じ)"""
    return (0x4414 if code < 0x20 else 0x43C4) + 5 * code


# この文字の形の表を使う機種(routines.FAMILIESの1251の系統)。PC-1260/1261/1262とPC-1350は
# 表の番地が違い、ここの番地はRAMの中やROMの番地に当たる
MODELS = ("1245", "1250", "1251", "1255")


def used(m) -> bool:
    """この文字の形の表を使う本体か(ROMなしで、MODELSの機種)"""
    return m.norom and m.model.name in MODELS


def in_table(code: int) -> bool:
    """文字の形の表にある文字コードか"""
    return 0x11 <= code < 0x20 or 0x30 <= code < 0x6B


def install(m) -> None:
    """ROMなしの本体mに、機種の文字の形の表をROMの番地に書く"""
    from . import norom1261, norom1350

    if not m.norom:
        return
    if norom1261.used(m):
        norom1261.install(m)
    elif norom1350.used(m):
        norom1350.install(m)
    elif used(m):
        _install(m)


def _install(m) -> None:
    for code, ch in CHARS.items():
        if in_table(code):
            at = font_addr(code)
            m.mem[at : at + 5] = glyph(ch)


# BASIC ROMの番地。ROMのある本体のこの番地の中身を、乱数の表として読むゲームがある
DATA_TOP, DATA_END = 0x4000, 0x8000
VERSION_AT = 0x7FFF  # この番地の値で、PRINTBUFの入口の番地を選ぶプログラムがある


def filler(n: int, seed: int = 0x2545F491) -> bytes:
    """エミュレータが作る乱数の並び(xorshift32)をnバイト。マシン語の命令の並びに似せて、半分は
    00h〜7Fh、半分は00h〜FFhから選ぶ(値を閾値と比べて事が起きるかを決めるゲームで、起きる
    割合がROMのある本体から離れすぎないように)"""
    out = bytearray(n)
    x = seed
    for i in range(n):
        x ^= x << 13 & 0xFFFFFFFF
        x ^= x >> 17
        x ^= x << 5 & 0xFFFFFFFF
        out[i] = x >> 24 if x & 0x100 else x >> 24 & 0x7F
    return bytes(out)


def fill_data(m) -> None:
    """ROMなしの本体m(MODELSの機種)のBASIC ROMの番地を乱数の並びで埋め、文字の形の表を書く。
    VERSION_ATは0のまま(PRINTBUFの代替ROMルーチンは、0の版の番地に置いてある)。前の版(この番地が0)で
    保存した状態も読み込めるように、埋める前のROMの印を残す"""
    if not used(m):
        return
    install(m)
    m.old_digests.add(m._rom_digest())
    m.mem[DATA_TOP:DATA_END] = filler(DATA_END - DATA_TOP)
    m.mem[VERSION_AT] = 0
    install(m)


# キーの名前(machine.KEYS)から、ROMのキーを読むルーチンが返す本体の文字コードへ。
# 英字・数字・記号は文字コードの表から引く。ほかはROMのある本体で確かめたもの
KEY_CODES = {ch: code for code, ch in CHARS.items() if len(ch) == 1}
KEY_CODES.update(
    {"ENTER": 0x00, "CL": 0x02, "SHIFT": 0x09, "DEF": 0x0A, "UP": 0x0C, "DOWN": 0x0D,
     "RIGHT": 0x0E, "LEFT": 0x0F, "SPC": 0x11}
)  # fmt: skip
BRK_CODE = 0x07  # BRKを押しているときに、キーを読むルーチンがAに返す値(観察)
SHIFTS = ("SHIFT", "DEF")  # キーを待つルーチンは、これだけを押しても戻らない

FX, FY = 0x20, 0x28  # 演算X・演算Y(内部RAM)
ERRNO = 0x14  # エラーの番号(内部RAM)
INT_RANGE = 0x12  # 2なら、数→整数を−32768〜32767にする。ほかは0〜65535(内部RAM)


def _error(m, n: int = 2) -> None:
    """キャリーを1にし、ERRNOにエラーの番号を入れる"""
    m.cpu.c = 1
    m.cpu.ram[ERRNO] = n


def _answer(m, f, *args) -> None:
    """f(*args)を演算Xに入れる。答えがなければエラー2"""
    v = compute(f, *args)
    if v is None:
        _error(m)
        return
    put_num(m.cpu.ram, FX, v)
    m.cpu.c = 0


def _binary(f):
    """演算Yと演算Xからfで求めた数を、演算Xに入れるルーチン"""
    return lambda m: _answer(m, f, get_num(m.cpu.ram, FY), get_num(m.cpu.ram, FX))


def _unary(f):
    """演算Xからfで求めた数を、演算Xに入れるルーチン"""
    return lambda m: _answer(m, f, get_num(m.cpu.ram, FX))


def _trig(fn, exact: tuple[int | None, ...]):
    """SIN・COS・TAN。角度を度にして1E10以上ならエラー。直角の倍数なら、exactの値
    (Noneはエラー)を返す"""

    def run(m) -> None:
        turn = angle_turn(m)
        _answer(m, lambda x: trig_value(fn, exact, x, turn), get_num(m.cpu.ram, FX))

    return run


def _arc(fn):
    """ASN・ACS・ATN。答えを液晶の記号の角度の単位にする"""

    def run(m) -> None:
        turn = angle_turn(m)
        _answer(m, lambda x: arc_value(fn, x, turn), get_num(m.cpu.ram, FX))

    return run


def _rnd(m) -> None:
    """RND。演算Xの数のrandom_valueを演算Xに入れる"""
    v = random_value(m, get_num(m.cpu.ram, FX))
    _answer(m, lambda: v)


def _i2f(signed: bool):
    """28・29番地(下位が先)の16ビットの整数を演算Xにするルーチン"""

    def run(m) -> None:
        ram = m.cpu.ram
        n = ram[FY] | ram[FY + 1] << 8
        if signed and n & 0x8000:
            n -= 0x10000
        put_num(ram, FX, Decimal(n))
        m.cpu.c = 0

    return run


def _f2i(m) -> None:
    """演算Xを0の方へ切り捨てた整数を28・29番地へ。範囲の外ならエラー3"""
    ram = m.cpu.ram
    n = int(get_num(ram, FX))
    lo, hi = (-0x8000, 0x7FFF) if ram[INT_RANGE] & 0x7F == 2 else (0, 0xFFFF)
    if not lo <= n <= hi:
        _error(m, 3)
        return
    n &= 0xFFFF
    ram[FY], ram[FY + 1] = n & 0xFF, n >> 8
    m.cpu.c = 0


def _range16(m) -> None:
    m.cpu.ram[INT_RANGE] = 2


def _string(m, at: int) -> bytes:
    """演算X(at=FX)か演算Y(FY)の文字列。後ろの4バイトがD0・番地(下位が先)・長さ
    (D0かどうかは見ない)"""
    ram = m.cpu.ram
    a = ram[at + 5] | ram[at + 6] << 8
    return bytes(m.read((a + i) & 0xFFFF) for i in range(ram[at + 7]))


def _strings(f, two: bool = False):
    """演算Xの文字列(twoなら演算Yと演算Xの文字列)からfで求めた数を、演算Xに入れるルーチン"""

    def run(m) -> None:
        args = [_string(m, FY), _string(m, FX)] if two else [_string(m, FX)]
        _answer(m, f, *args)

    return run


STR_PTR = 0xC6F7  # 文字列を置く場所(C701〜C7AF)の、次に使う番地の下位バイト
STR_END = 0xB0


def _asc(s: bytes) -> Decimal:
    return Decimal(ASCII.get(s[0], 0) if s else 0)


def _put_string(m, data: bytes) -> None:
    """dataを文字列を置く場所の空いている所に書き、演算Xをその文字列にする。入りきらなければ
    エラー6。STR_PTRが0なら1とみなす"""
    at = m.mem[STR_PTR] or 1
    if at + len(data) > STR_END:
        _error(m, 6)
        return
    a = 0xC700 + at
    m.mem[a : a + len(data)] = data
    m.mem[STR_PTR] = at + len(data)
    m.cpu.ram[FX : FX + 8] = bytes([0, 0, 0, 0, 0xD0, a & 0xFF, a >> 8, len(data)])
    m.cpu.c = 0


def _chr(m) -> None:
    """CHR$。演算XのASCIIの字1つの文字列(0なら空の文字列)。本体にない字ならエラー9"""
    n = int(get_num(m.cpu.ram, FX))
    if n == 0:
        _put_string(m, b"")
    elif n in FROM_ASCII:
        _put_string(m, bytes([FROM_ASCII[n]]))
    else:
        _error(m, 9)


def _str(m) -> None:
    """STR$。演算Xの数を字にした文字列"""
    text = number_text(get_num(m.cpu.ram, FX))
    _put_string(m, bytes(CODES[ch] for ch in text))


def _keyscan(m) -> None:
    """1F44: キーを1回読む。押されていればCとZを1、Aに本体の文字コード、Bに44h。なければ
    CとZを0、AをFFh、Bを00h。BRKを押していれば、CとZを1、Aを07hにし、Bは変えない(観察)"""
    cpu = m.cpu
    if m.brk:
        cpu.ram[2] = BRK_CODE
        cpu.c = cpu.z = 1
        return
    codes = sorted(KEY_CODES[k] for k in m.held if k in KEY_CODES)
    if codes:
        cpu.ram[2], cpu.ram[3] = codes[0], 0x44
        cpu.c = cpu.z = 1
        m.pass_time(129)  # 押していれば、押していないときより長い(観察)
    else:
        cpu.ram[2], cpu.ram[3] = 0xFF, 0x00
        cpu.c = cpu.z = 0


@dataclass
class _Wait:
    """キーを待つルーチンが待っているあいだの様子"""

    pc: int
    r: int
    seen: int  # 最後に見たサイクル
    old: set[str]  # 待ち始めに押していて、まだ離していないキー


_waits: WeakKeyDictionary[object, _Wait] = WeakKeyDictionary()


def save_wait(m) -> dict | None:
    """キーを待つルーチンが待っているあいだの様子(状態の保存用)。待っていなければNone"""
    w = _waits.get(m)
    return None if w is None else {"pc": w.pc, "r": w.r, "seen": w.seen, "old": sorted(w.old)}


def prepare_wait(m, d: object) -> Callable[[], None]:
    """save_waitの値を調べ、待ちの様子を戻す関数を返す(Noneなら待ちを捨てる)。おかしければ
    ValueError"""
    if d is None:
        return lambda: _forget(m)
    if not isinstance(d, dict) or set(d) != {"pc", "r", "seen", "old"}:
        raise ValueError("KEYWAIT")
    limits = {"pc": 0xFFFF, "r": 0x7F, "seen": None}
    for k, top in limits.items():
        v = d[k]
        if type(v) is not int or v < 0 or top is not None and v > top:
            raise ValueError("KEYWAIT")
    old = d["old"]
    if not isinstance(old, list) or not all(type(k) is str and k in KEY_CODES for k in old):
        raise ValueError("KEYWAIT")
    w = _Wait(d["pc"], d["r"], d["seen"], set(old))

    def apply() -> None:
        _waits[m] = w

    return apply


def _forget(m) -> None:
    _waits.pop(m, None)


def _keywait(m) -> bool:
    """呼んだあとに押したキーを待ち、Aに本体の文字コード、ENTERとCLならCを1にする。
    SHIFT・DEFは数えない(続けて押したキーの文字コードも変えない)。BRKは、待ち始めから
    押していても、AとBを07h、Cを0にして戻る(観察)。待っているあいだは、2msずつ時間を進めて
    Falseを返す"""
    cpu = m.cpu
    if m.brk:
        _waits.pop(m, None)
        cpu.ram[2] = cpu.ram[3] = BRK_CODE
        cpu.c, cpu.z = 0, 1
        return True
    held = {k for k in m.held if k in KEY_CODES and k not in SHIFTS}
    w = _waits.get(m)
    if w is None or (w.pc, w.r) != (cpu.pc, cpu.r) or cpu.cycles - w.seen > 2 * TICK_2MS:
        w = _waits[m] = _Wait(cpu.pc, cpu.r, 0, set(held))
    w.old &= held  # 離したキーは、もう一度押せば数える
    new = held - w.old
    if not new:
        m.pass_time(TICK_2MS - m.t2)
        w.seen = cpu.cycles
        return False
    del _waits[m]
    code = min(KEY_CODES[k] for k in new)
    cpu.ram[2] = cpu.ram[3] = code
    cpu.c = int(code in (0x00, 0x02))
    cpu.z = 1
    return True


def _keywait_shown(m) -> bool:
    """1D0D: Cポートを01h(液晶をつけ、音を止める)にしてから、KEYWAITと同じにキーを待つ"""
    if m.pc_out != 0x01:
        m.out_c(0x01)
    return _keywait(m)


def _glyph_addr(m) -> None:
    """1FBC: Aの文字コードの形の番地−1をXに入れる"""
    cpu = m.cpu
    x = (font_addr(cpu.ram[2]) - 1) & 0xFFFF
    cpu.ram[4], cpu.ram[5] = x & 0xFF, x >> 8


def _word(m, a: int) -> int:
    return m.mem[a] | m.mem[a + 1] << 8


def _set(cpu, at: int, v: int) -> None:
    """内部RAMのat・at+1番地に16ビットのvを置く"""
    cpu.ram[at], cpu.ram[at + 1] = v & 0xFF, v >> 8 & 0xFF


def _program_head(m) -> None:
    """118F: C6E1h番地からのJ+1バイトを04h番地(X)からに読む(Jが1ならプログラムの頭の番地)。
    DPは最後に読んだ番地、Pは5+J(観察)"""
    cpu = m.cpu
    j = cpu.ram[1]
    for k in range(j + 1):
        cpu.ram[4 + k & 0x7F] = m.read(0xC6E1 + k & 0xFFFF)
    cpu.dp, cpu.p = 0xC6E1 + j & 0xFFFF, 5 + j & 0x7F
    m.pass_time(4 * j)


def _ba_to_y(minus: bool, ba: int | None = None):
    """11EE(minusがFalse)・11F5(True)・11F9(True、baがC7B0h): 02h番地(A)からのJ+1バイトを
    06h番地(Y)からに1バイトずつ写す。baがあれば先にBAをその値にする。minusならYから1を引き、
    DPをできたYに、Qを7にする(Jが1ならYがBA−1)。そうでなければQは3+J。Pは7+J(観察)"""

    def run(m) -> None:
        cpu = m.cpu
        j = cpu.ram[1]
        if ba is not None:
            _set(cpu, 2, ba)
        for k in range(j + 1):
            cpu.ram[6 + k & 0x7F] = cpu.ram[2 + k & 0x7F]
        cpu.p = 7 + j & 0x7F
        if minus:
            y = _word_ram(cpu, 6) - 1 & 0xFFFF
            _set(cpu, 6, y)
            cpu.dp, cpu.q = y, 7
        else:
            cpu.q = 3 + j & 0x7F
        m.pass_time(2 * j)

    return run


def _x_from_1c(m) -> None:
    """1899: 内部RAMの1Ch番地からのJ+1バイトを、04h番地(X)からに1バイトずつ写す。Pは5+J、
    Qは1Dh+J(観察)"""
    cpu = m.cpu
    j = cpu.ram[1]
    for k in range(j + 1):
        cpu.ram[4 + k & 0x7F] = cpu.ram[0x1C + k & 0x7F]
    cpu.p, cpu.q = 5 + j & 0x7F, 0x1D + j & 0x7F
    m.pass_time(2 * j)


def _push_x(m) -> None:
    """11C7: 04h番地(X)からのJ+1バイトをスタックに積む(戻り番地はその下へずらす)。Aは
    積んだあとのスタックの位置"""
    cpu = m.cpu
    n, r = cpu.ram[1] + 1, cpu.r
    back = bytes(cpu.ram[r : r + 2])
    cpu.r = r = r - n
    cpu.ram[r : r + 2] = back
    cpu.ram[r + 2 : r + 2 + n] = cpu.ram[4 : 4 + n]
    cpu.ram[2] = r


def _pop_x(m) -> None:
    """11D2: 11C7で積んだJ+1バイトを04h番地(X)からに戻す。Aは戻したバイトのあった位置、Bは
    呼んだときのスタックの位置"""
    cpu = m.cpu
    n, r = cpu.ram[1] + 1, cpu.r
    back = bytes(cpu.ram[r : r + 2])
    cpu.ram[4 : 4 + n] = cpu.ram[r + 2 : r + 2 + n]
    cpu.ram[2], cpu.ram[3] = r + 2, r
    cpu.r = r + n
    cpu.ram[cpu.r : cpu.r + 2] = back


def _ba_to_x_minus(b: int | None = None, a: int | None = None):
    """11F1・1184(bがF8h)・119C(bがC7h)・119A(bがC7h、aがB0h): 02h番地(A)からのJ+1バイトを
    04h番地(X)からに1バイトずつ写し、Xから1を引く。bがあれば先にBを、aがあればAをその値に
    する(Jが1ならXがbの上位とAの番地−1)。DPはできたX、Pは5+J、Qは5になる(観察)"""

    def run(m) -> None:
        cpu = m.cpu
        j = cpu.ram[1]
        if a is not None:
            cpu.ram[2] = a
        if b is not None:
            cpu.ram[3] = b
        for k in range(j + 1):  # 重なっていれば、写したバイトをまた写す(ROMと同じ)
            cpu.ram[4 + k] = cpu.ram[2 + k]
        x = (cpu.ram[4] | cpu.ram[5] << 8) - 1 & 0xFFFF
        _set(cpu, 4, x)
        cpu.dp, cpu.p, cpu.q = x, 5 + j, 5
        m.pass_time(2 * j)

    return run


def _ba_to_x(m) -> None:
    """11E9: 02h番地(A)からのJ+1バイトを04h番地(X)からに1バイトずつ写す。Pは5+J、Qは3+J(観察)"""
    cpu = m.cpu
    j = cpu.ram[1]
    for k in range(j + 1):
        cpu.ram[4 + k & 0x7F] = cpu.ram[2 + k & 0x7F]
    cpu.p, cpu.q = 5 + j & 0x7F, 3 + j & 0x7F
    m.pass_time(2 * j)


def _swap_x_1c(m) -> None:
    """1ACF: 04h番地(X)からと1Ch番地からのJ+1バイトを入れ替える。Pは5+J、Qは1Dh+J(観察)"""
    cpu = m.cpu
    j = cpu.ram[1]
    for k in range(j + 1):
        x, y = 4 + k & 0x7F, 0x1C + k & 0x7F
        cpu.ram[x], cpu.ram[y] = cpu.ram[y], cpu.ram[x]
    cpu.p, cpu.q = 5 + j & 0x7F, 0x1D + j & 0x7F
    m.pass_time(3 * j)


def _copy_b(m) -> None:
    """1FB6: X+1番地からのBバイトをY+1番地からに写す(Bが0なら256バイト)。XとYは最後に
    読み書きした番地、Aは最後に写したバイト、Bは0、DPはY、Qは3、Cは0、Zは1(観察)"""
    cpu = m.cpu
    x, y = _word_ram(cpu, 4), _word_ram(cpu, 6)
    n = cpu.ram[3] or 256
    v = 0
    for _ in range(n):
        x, y = x + 1 & 0xFFFF, y + 1 & 0xFFFF
        v = m.read(x)
        m.write(y, v)
    cpu.ram[2], cpu.ram[3] = v, 0
    _set(cpu, 4, x)
    _set(cpu, 6, y)
    cpu.dp, cpu.q, cpu.c, cpu.z = y, 3, 0, 1
    m.pass_time(24 * n)


def _word_ram(cpu, at: int) -> int:
    return cpu.ram[at] | cpu.ram[at + 1] << 8


def _draw_text(m, text: bytes) -> None:
    """字の並びを、字の形の表の形で液晶の左から書く(表にない文字コードは、その番地にあるもの)"""
    addrs = m.column_addrs()
    for i, code in enumerate(text[: m.model.cells]):
        at = font_addr(code)
        for k in range(5):
            m.write(addrs[5 * i + k], m.read(at + k & 0xFFFF))
    m.lcd_dirty = True


SHOW_RAM_TIME = {16: 4943, 24: 7302}  # 400Cにかかる時間(桁の数ごと。字で約±50変わる。観察)


def _show_ram(m) -> None:
    """400C: 内部RAMの20h番地からの字(液晶の桁の数だけ)を、字の形の表の形で液晶に書く。
    表にない文字コードは、その番地にあるもの(ROMなしでは0)を書く。Cは0、Zは1(観察)"""
    cpu = m.cpu
    _draw_text(m, bytes(cpu.ram[0x20 : 0x20 + m.model.cells]))
    cpu.ram[3] = 0
    cpu.c, cpu.z = 0, 1
    m.lcd_dirty = True
    m.pass_time(SHOW_RAM_TIME.get(m.model.cells, SHOW_RAM_TIME[24]) - SHOW_RAM_TIME[24])


TEXT_TOP = 0xC7B0  # 字の並びを作る場所


def print_text(m, at: int) -> tuple[bytes, int]:
    """番地atからの中間コード(00hまで)をPRINTの出すものとして読み、(液晶に出す字の並び, 数の
    数)にする。出すものがないか、ROMなしのBASICがなければ空。誤りがあればBasicError"""
    code = bytearray()
    while len(code) < 80 and m.read(at + len(code) & 0xFFFF):
        code.append(m.read(at + len(code) & 0xFFFF))
    if not code or m.basic is None:
        return b"", 0
    return m.basic.print_text_of(bytes(code))


def _print_buffer(m) -> None:
    """567C(BASIC ROMの00版): X+1番地からの中間コード(00hまで)をPRINTの出すものとして読み、
    液晶に出す字の並びをC7B0h番地から置く。C7B0h〜C7FFh番地は先に11h(空白)で埋め、字のすぐ
    あとに00hを置く(1つの数だけのときは右に寄せて24字)。液晶には、その24字を字の形の表の形で
    書く(表示はつけない)。出すものがなければ何も置かない(観察)"""
    from .basic.errors import BasicError

    cpu = m.cpu
    for a in range(TEXT_TOP, 0xC800):
        m.write(a, 0x11)
    try:
        text, numbers = print_text(m, _word_ram(cpu, 4) + 1 & 0xFFFF)
    except BasicError as e:  # ROMのある本体はBASICのエラーにする
        _error(m, e.number)
        return
    if not text:
        return
    text = text[:0x4F]
    for i, c in enumerate(text):
        m.write(TEXT_TOP + i, c)
    m.write(TEXT_TOP + len(text), 0x00)
    _draw_text(m, text[:24].ljust(24, b"\x11"))
    spent = PRINT_BUFFER_TIME + PRINT_BUFFER_CHAR * len(text) + PRINT_BUFFER_NUMBER * numbers
    m.pass_time(spent - PRINT_BUFFER_EMPTY)


# 567Cにかかる時間。出すものがないとき、字の並びを作るとき、字1つごと、数1つごと(数の桁や,で
# 分けたかによって約±20%変わる。観察)
PRINT_BUFFER_EMPTY, PRINT_BUFFER_TIME = 696, 10400
PRINT_BUFFER_CHAR, PRINT_BUFFER_NUMBER = 165, 2800


def _noise(m) -> None:
    """6F40(PC-1245): 2msのタイマのフラグを待って消し、Aをキャリーとともに右へ回す(ビット0が
    キャリー、キャリーがビット7へ)。Cポートと5Fh番地を、20h+キャリー×10h+前の5Fh番地の
    ビット0にする。Zは0、PとQは5Fh(観察)"""
    cpu = m.cpu
    if not m.t2ms:
        left = TICK_2MS - m.t2  # 次の刻みまで。11サイクルごとにフラグを見る
        m.pass_time(max(0, -(-(left - 25) // 11)) * 11)
    m.t2ms = 0
    a = cpu.ram[2]
    cpu.ram[2] = a >> 1 | cpu.c << 7
    cpu.c = a & 1
    v = 0x20 | cpu.c << 4 | cpu.ram[0x5F] & 1
    cpu.ram[0x5F] = v
    m.out_c(v)
    cpu.z = 0
    cpu.p = cpu.q = 0x5F


def _swap_ba_y(m) -> None:
    """18BB: 02h番地(A)からと06h番地(Y)からのJ+1バイトを入れ替える。Pは3+J、Qは7+J(観察)"""
    cpu = m.cpu
    j = cpu.ram[1]
    for k in range(j + 1):
        cpu.ram[2 + k], cpu.ram[6 + k] = cpu.ram[6 + k], cpu.ram[2 + k]
    cpu.p, cpu.q = 3 + j, 7 + j
    m.pass_time(3 * j)


def _y_to_dp(m) -> None:
    """18E7: DPの番地からのJ+1バイトに06h番地(Y)からを書き、前の中身を0Ch番地からに移す。
    Jが6以上で2つの場所が重なるときは、0Ch番地からへ写したバイトをまた写したものを書く。
    DPは最後に書いた番地、Pは0Dh+J、Qは7+J(観察)"""
    cpu = m.cpu
    j, dp = cpu.ram[1], cpu.dp
    data = bytearray(cpu.ram[6 : 6 + j + 1])
    for k in range(6, j + 1):
        data[k] = data[k - 6]
    for k in range(j + 1):
        a = dp + k & 0xFFFF
        cpu.ram[0x0C + k] = m.read(a)
        m.write(a, data[k])
    cpu.dp, cpu.p, cpu.q = dp + j & 0xFFFF, 0x0D + j, 7 + j
    m.pass_time(8 * j)


def _save_x(m) -> None:
    """1118: X(04h・05h番地)をC6B5h・C6B6h番地に置き、AにXの上位を入れる。DPはC6B6h、
    Pは5(観察)"""
    cpu = m.cpu
    m.write(0xC6B5, cpu.ram[4])
    m.write(0xC6B6, cpu.ram[5])
    cpu.ram[2] = cpu.ram[5]
    cpu.dp, cpu.p = 0xC6B6, 5


def _load_x(m) -> None:
    """1125: Jを1にし、AにいまのXの上位を入れてから、C6B5h・C6B6h番地の値をXに入れる。
    DPはC6B6h、Pは5(観察)"""
    cpu = m.cpu
    cpu.ram[1] = 1
    cpu.ram[2] = cpu.ram[5]
    _set(cpu, 4, _word(m, 0xC6B5))
    cpu.dp, cpu.p = 0xC6B6, 5


def _swap_port(m) -> None:
    """1FB1: AをCポートに出して5Fh番地にも置き、前に5Fh番地にあった値をAに入れる。PとQは5Fh
    (観察)"""
    cpu = m.cpu
    a, old = cpu.ram[2], cpu.ram[0x5F]
    m.out_c(a)
    cpu.ram[0x5F] = a
    cpu.ram[2] = old
    cpu.p = cpu.q = 0x5F


SHOW_TIME = {16: 6050, 24: 8390}  # 11AFの、字のない行を出す時間(桁の数ごと。観察)


def _show_text(m) -> None:
    """11AF: C7B0h番地からの24バイトを内部RAMの20h〜37h番地にコピーし、液晶の桁の数だけ出す。
    00hから後ろは4Fhにし、液晶には何も出さない。形の表にない字は空白(観察)"""
    cpu = m.cpu
    text = bytes(m.mem[0xC7B0 : 0xC7B0 + 24])
    n = text.index(0) if 0 in text else 24
    cpu.ram[0x20 : 0x20 + 24] = text[:n] + bytes([0x4F]) * (24 - n)
    addrs = m.column_addrs()
    cells = m.model.cells
    for i in range(cells):
        ch = CHARS.get(text[i]) if i < n and in_table(text[i]) else None
        g = glyph(ch) if ch else bytes(5)
        for j in range(5):
            m.mem[addrs[5 * i + j]] = g[j]
    m.lcd_dirty = True
    m.pass_time(SHOW_TIME.get(cells, SHOW_TIME[24]) + 110 * min(n, cells))


def _display(on: bool):
    """11E0(onがTrue)・11E5: Cポートと5Fh番地を01h(00h)にし、前に5Fh番地にあった値をAに入れる。
    PとQは5Fh(観察)"""

    def run(m) -> None:
        cpu = m.cpu
        v = 0x01 if on else 0x00
        cpu.ram[2], cpu.ram[0x5F] = cpu.ram[0x5F], v
        m.out_c(v)
        cpu.p = cpu.q = 0x5F

    return run


def _wait_2ms(n: int):
    """2msのタイマのフラグをn回待つ(立っていれば、すぐに消して数える)"""

    def run(m) -> None:
        for _ in range(n):
            if not m.t2ms:
                m.pass_time(TICK_2MS - m.t2)
            m.t2ms = 0

    return run


def _floor(x: Decimal) -> Decimal:
    return x.to_integral_value(rounding=ROUND_FLOOR)


def _sgn(x: Decimal) -> Decimal:
    return Decimal((x > 0) - (x < 0))


def _flag(b: bool) -> Decimal:
    return Decimal(int(b))


# 名前(romsyms.ROUTINES_1251): (代わりに動かす関数, 使ったことにするサイクル数)。関数がFalseを
# 返したら、まだ待っている(時間は関数が進めた)。サイクル数は、ROMのある本体でいくつかの値を与えて
# 測ったときの真ん中の値
ROUTINES: dict[str, tuple[Callable[..., bool | None], int]] = {
    "FADD": (_binary(lambda y, x: y + x), 830),
    "FSUB": (_binary(lambda y, x: y - x), 850),
    "FMUL": (_binary(lambda y, x: y * x), 2170),
    "FDIV": (_binary(lambda y, x: y / x), 3620),
    "FPOW": (_binary(power), 62000),
    "FSQR": (_unary(lambda x: x.sqrt()), 9060),
    "FSIN": (_trig(math.sin, (0, 1, 0, -1)), 58500),
    "FCOS": (_trig(math.cos, (1, 0, -1, 0)), 58400),
    "FTAN": (_trig(math.tan, (0, None, 0, None)), 38300),
    "FASN": (_arc(math.asin), 52800),
    "FACS": (_arc(math.acos), 58500),
    "FATN": (_arc(math.atan), 39600),
    "FEXP": (_unary(lambda x: x.exp()), 34800),
    "FLN": (_unary(lambda x: x.ln()), 39200),
    "FLOG": (_unary(lambda x: x.log10()), 32400),
    "FABS": (_unary(abs), 12),
    "FSGN": (_unary(_sgn), 170),
    "FINT": (_unary(_floor), 700),
    "FDMS": (_unary(to_dms), 6690),
    "FDEG": (_unary(to_degrees), 11700),
    "FRND": (_rnd, 10900),
    "FROUND": (_unary(lambda x: cut(x, 10, ROUND_HALF_UP)), 176),
    "FEQ": (_binary(lambda y, x: _flag(y == x)), 1000),
    "FNE": (_binary(lambda y, x: _flag(y != x)), 1000),
    "FLT": (_binary(lambda y, x: _flag(y < x)), 1000),
    "FGT": (_binary(lambda y, x: _flag(y > x)), 1000),
    "FLE": (_binary(lambda y, x: _flag(y <= x)), 1000),
    "FGE": (_binary(lambda y, x: _flag(y >= x)), 1000),
    "SEQ": (_strings(lambda y, x: _flag(y == x), two=True), 80),
    "SNE": (_strings(lambda y, x: _flag(y != x), two=True), 100),
    "SLT": (_strings(lambda y, x: _flag(y < x), two=True), 390),
    "SGT": (_strings(lambda y, x: _flag(y > x), two=True), 320),
    "SLE": (_strings(lambda y, x: _flag(y <= x), two=True), 410),
    "SGE": (_strings(lambda y, x: _flag(y >= x), two=True), 330),
    "FASC": (_strings(_asc), 3940),
    "FVAL": (_strings(leading_number), 1080),
    "FCHRS": (_chr, 640),
    "FSTRS": (_str, 3300),
    "I2F": (_i2f(True), 3700),
    "U2F": (_i2f(False), 3690),
    "RANGE16": (_range16, 23),
    "F2I": (_f2i, 450),
    "KEYSCAN": (_keyscan, 731),
    "KEYWAIT": (_keywait, 2600),
    "KEYWAIT2": (_keywait, 2600),
    "DISPON": (_display(True), 28),
    "DISPOFF": (_display(False), 35),
    "WAIT2MS": (_wait_2ms(1), 12),
    "WAIT4MS": (_wait_2ms(2), 12),
    "WAIT6MS": (_wait_2ms(3), 12),
    "GLYPH": (_glyph_addr, 120),
    "PRGTOP": (_program_head, 19),
    "SHOWBUF": (_show_text, 0),
    "PUSHX": (_push_x, 40),
    "POPX": (_pop_x, 46),
    "BA2Y": (_ba_to_y(False), 22),
    "BA2YM": (_ba_to_y(True), 39),
    "TEXTBUF": (_ba_to_y(True, 0xC7B0), 58),
    "X1C": (_x_from_1c, 15),
    "KEYWAIT0": (_keywait_shown, 2600),
    "SWAPC": (_swap_port, 13),
    "BA2XM": (_ba_to_x_minus(), 32),
    "LCDXM": (_ba_to_x_minus(0xF8), 47),
    "EXBAY": (_swap_ba_y, 16),
    "Y2DP": (_y_to_dp, 24),
    "SAVEX": (_save_x, 32),
    "LOADX": (_load_x, 40),
    "BA2X": (_ba_to_x, 15),
    "EXX1C": (_swap_x_1c, 16),
    "TEXTXM": (_ba_to_x_minus(0xC7), 47),
    "TEXTX": (_ba_to_x_minus(0xC7, 0xB0), 51),
    "COPYB": (_copy_b, 1),
    "SHOWRAM": (_show_ram, SHOW_RAM_TIME[24]),
    "PRINTBUF": (_print_buffer, PRINT_BUFFER_EMPTY),
    "NOISE": (_noise, 39),
}


def routine_fns() -> dict[str, Callable[..., int | None]]:
    """ROUTINESを、登録簿(routines.py)の形の関数(使ったサイクル数か、待っているならNone)にする"""

    def wrap(fn, cycles: int):
        return lambda m: None if fn(m) is False else cycles

    return {name: wrap(fn, cycles) for name, (fn, cycles) in ROUTINES.items()}


def _as_is(case, rnd) -> None:
    """乱数で決めた値をそのまま与える"""


# ROMのある本体と比べられる代替ROMルーチン(routinecheck)。名前: (与える値, 比べないもの,
# サイクル数の違ってよい割合)。ほかの代替ROMルーチンは返すものだけをまね、レジスタや時間はROMと違う
CHECK: dict[str, CheckSpec] = {
    name: (_as_is, (), 0.0)
    for name in ("DISPON", "DISPOFF", "BA2XM", "LCDXM", "EXBAY", "Y2DP", "SAVEX", "LOADX", "SWAPC",
                 "BA2X", "EXX1C", "TEXTXM", "TEXTX", "NOISE", "BA2Y", "BA2YM", "TEXTBUF",
                 "PRGTOP", "X1C")
}  # fmt: skip


def _copy_inputs(case, rnd) -> None:
    """COPYB: XとYをRAMの中に向ける"""
    case.ram[4:8] = bytes([rnd.randrange(256), 0xC0, rnd.randrange(256), 0xC2])
    case.ram[3] = rnd.choice((0, 1, 5, 40))


def _text_inputs(case, rnd) -> None:
    """SHOWRAM: 内部RAMの20h番地からを、字の形の表にある字にする"""
    codes = [c for c in CHARS if in_table(c)]
    case.ram[0x20:0x38] = bytes(rnd.choice(codes) for _ in range(24))


def _print_inputs(case, rnd) -> None:
    """PRINTBUF: C101番地からにPRINTの出すものを置き、XをC100番地に向ける。変数AとBに数を入れる。
    内部RAMの17h番地のビット6は0にする(1のときのROMのある本体の働きはまねていない)"""
    import re

    def code(text: str) -> bytes:
        return bytes(CODES[ch] for ch in re.findall(r"\[E\]|.", text))

    texts = ('"   SCORE : ";A', '"AB"', "A", "A;B", '"X",A', "A,B", '"HI";A;"!"', "B",
             '"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"', '"ABCDEFGHIJKLMNOPQRSTUVW";A')  # fmt: skip
    text = rnd.choice(texts)
    case.mem[0xC100] = b"\0" + code(text) + b"\0"
    case.ram[4:6] = bytes([0x00, 0xC1])
    case.ram[0x17] &= ~0x40
    for at in (0xC698, 0xC690):  # 変数AとB
        ram = bytearray(0x30)
        put_num(ram, 0x20, Decimal(rnd.choice(("0", "7", "9750", "-12.5", "123456789", "0.25"))))
        case.mem[at] = bytes(ram[0x20:0x28])


CHECK["COPYB"] = (_copy_inputs, (), 0.0)
# SHOWRAMは、A・X・Y・08h・0Bh番地、P・Q・DPとC6E9h番地をまねていない
CHECK["SHOWRAM"] = (_text_inputs, (2, 4, 5, 6, 7, 8, 9, 0x0B, "p", "q", "dp", 0xC6E9), 0.01)
# PRINTBUFは、C7B0h番地からの字と液晶だけをまねる(作業に使うRAMとレジスタはまねていない)
CHECK["PRINTBUF"] = (
    _print_inputs,
    (*range(0x50), "c", "z", "p", "q", "dp", *range(0xC600, 0xC7B0)),
    0.25,
)

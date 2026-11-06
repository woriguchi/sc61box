"""PC-1260/1261/1262をROMなしで動かすときの、代替ROMルーチンと文字の形の表

受け持つのは、romsyms.ROUTINES_1261の入口だけ。決め方はnorom.pyと同じで、ROMのある本体で
値を与えて呼び、戻ったときの内部RAM、メモリ、フラグ、ポートと、かかったサイクル数を見て
決めた。ROMの命令の並びや表は写していない。サイクル数はCPUのサイクル(時刻には本体の比で直す)。
返すもの以外の作業用のRAM(スタックより下など)はROMと違う。

文字の形の表は、BASIC ROMと同じ番地と並び(8045hから1字5バイト、右の列が先)に置く。字の形は
エミュレータで描いたもの(PC-1251系と同じ形の字と、basic/pc1261/font.pyの字)で、シャープの
ROMの形は使っていない。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from weakref import WeakKeyDictionary

from . import charset
from .basic.pc1261 import font
from .basic.pc1261 import screen as pc1261_screen
from .basic.screen import BLOCK, INSERT_MARK
from .machine import TICK_2MS
from .routines import CheckSpec, spend

MODELS = ("1260", "1261", "1262")
FONT_TOP = 0x8045  # 空白(20h)の形の番地

# 表の後ろの、英数字とカナのほかの字(F0h〜FDh。観察)
EXTRA = {0xF0: "0", 0xF1: "年", 0xF2: "月", 0xF3: "日", 0xF4: "円", 0xF5: "♠", 0xF6: "♥",
         0xF7: "♦", 0xF8: "♣", 0xFB: "π", 0xFC: "√", 0xFD: "~"}  # fmt: skip
SHAPES = {0xF9: BLOCK, 0xFA: INSERT_MARK}


def used(m) -> bool:
    return m.norom and m.model.name in MODELS


def glyph_index(code: int) -> tuple[int, int]:
    """(表の何番目か, GLYPHのサイクル数の元)。表にない文字コードは空白(0番目)"""
    if 0x20 <= code < 0x7B:
        return code - 0x20, 116
    if 0xA0 <= code < 0xE0:
        return code - 0x45, 136
    if 0xF0 <= code < 0xFE:
        return code - 0x55, 156
    return 0, 112 if code < 0x20 else 128 if code < 0xA0 else 148 if code < 0xF0 else 157


def glyph(code: int) -> bytes:
    """文字コードの形(5列、左から)"""
    if code in SHAPES:
        return SHAPES[code]
    ch = EXTRA.get(code) or pc1261_screen.char(code)
    if not ch:
        return bytes(5)
    ch = font.SAME.get(ch, ch)
    return font.glyph(ch) or charset.glyph(ch)


def install(m) -> None:
    """文字の形の表を、BASIC ROMの番地に書く"""
    for code in range(0x100):
        index, _ = glyph_index(code)
        if index or code == 0x20:
            at = FONT_TOP + 5 * index
            m.mem[at : at + 5] = bytes(reversed(glyph(code)))


# ---- レジスタの受け渡し ----


def _copy(cpu, src: int, dst: int) -> None:
    """内部RAMのsrcからのJ+1バイトをdstからへ。Pは写し終えた次、Qは読み終えた次"""
    j = cpu.ram[1]
    for k in range(j + 1):
        cpu.ram[dst + k & 0x7F] = cpu.ram[src + k & 0x7F]
    cpu.p, cpu.q = dst + j + 1 & 0x7F, src + j + 1 & 0x7F


def copy_to(src: int, dst: int, base: int):
    def run(m) -> int:
        _copy(m.cpu, src, dst)
        return base + 2 * m.cpu.ram[1]

    return run


def _swap(a: int, b: int, base: int):
    def run(m) -> int:
        cpu = m.cpu
        j = cpu.ram[1]
        for k in range(j + 1):
            x, y = a + k & 0x7F, b + k & 0x7F
            cpu.ram[x], cpu.ram[y] = cpu.ram[y], cpu.ram[x]
        cpu.p, cpu.q = a + j + 1 & 0x7F, b + j + 1 & 0x7F
        return base + 3 * j

    return run


def _to_p(src: int, base: int):
    """内部RAMのsrcからのJ+1バイトを、Pの指す所へ。PとQは写し終えた次"""

    def run(m) -> int:
        cpu = m.cpu
        j, p = cpu.ram[1], cpu.p
        for k in range(j + 1):
            cpu.ram[p + k & 0x7F] = cpu.ram[src + k & 0x7F]
        cpu.p, cpu.q = p + j + 1 & 0x7F, src + j + 1 & 0x7F
        return base + 2 * j

    return run


def _swap_p(b: int, base: int):
    """Pの指す所からと、内部RAMのbからのJ+1バイトを入れ替える"""

    def run(m) -> int:
        cpu = m.cpu
        j, p = cpu.ram[1], cpu.p
        for k in range(j + 1):
            x, y = p + k & 0x7F, b + k & 0x7F
            cpu.ram[x], cpu.ram[y] = cpu.ram[y], cpu.ram[x]
        cpu.p, cpu.q = p + j + 1 & 0x7F, b + j + 1 & 0x7F
        return base + 3 * j

    return run


def _y_plus_to_15(m) -> int:
    """DPをYにし、YからJ+1バイトを内部RAMの15番地へ写して、その数(J+1バイト)に1を足す"""
    cpu = m.cpu
    j = cpu.ram[1]
    cpu.dp = _word(cpu, 6)
    carry = 1
    for k in range(j + 1):
        v = cpu.ram[6 + k] + carry
        cpu.ram[0x15 + k], carry = v & 0xFF, v >> 8
    cpu.p, cpu.q = 0x15 + j + 1, 7
    return 27 + 2 * j


def _pop_x(m) -> int:
    """呼び出し元の戻り番地(この呼び出しの戻り番地の上の2バイト)をXへ取り出し、戻り番地を
    その所へ上げる(呼び出し元へ戻るが、呼び出し元のRTNはもう1つ前へ戻る)。写すのはJ+1バイトずつ。Aに取り出した
    所のR、Bにもとの戻り番地のR"""
    cpu = m.cpu
    j, r0 = cpu.ram[1], cpu.r
    for k in range(j + 1):
        cpu.ram[4 + k & 0x7F] = cpu.ram[r0 + 2 + k & 0x7F]
    for k in range(j + 1):  # 前から順に写す(Jが2以上なら、写した値をまた写す)
        cpu.ram[r0 + 2 + k & 0x7F] = cpu.ram[r0 + k & 0x7F]
    cpu.ram[2], cpu.ram[3] = r0 + 2 & 0xFF, r0
    cpu.r = r0 + 2
    cpu.p, cpu.q, cpu.c, cpu.z = r0 + 2 + j + 1 & 0x7F, r0 + j + 1 & 0x7F, 0, 0
    return 42 + 4 * j


def _push_x(m) -> int:
    """Xを、この呼び出しの戻り番地の下に積む(戻ったあと、RTNでXへ進める)。Jが1のとき。Aに新しいR"""
    cpu = m.cpu
    r0 = cpu.r
    cpu.ram[r0 - 2 & 0x7F], cpu.ram[r0 - 1 & 0x7F] = cpu.ram[r0], cpu.ram[r0 + 1]
    cpu.ram[r0], cpu.ram[r0 + 1] = cpu.ram[4], cpu.ram[5]
    cpu.r = r0 - 2
    cpu.ram[2] = r0 - 2 & 0xFF
    cpu.p, cpu.q, cpu.c, cpu.z = r0 + 2 & 0x7F, r0, 0, 0
    return 40


def _sub_y(m, cycles: int) -> int:
    """BAからYを引く。Jが0なら、Aから引いた借りを、Yの上位からBを引くのに使う(答えの下位は
    A、上位はYの上位)。Jは0〜3のとき(観察)"""
    cpu = m.cpu
    ram, j = cpu.ram, cpu.ram[1]
    if j == 0:
        d = ram[2] - ram[6]
        ram[2] = d & 0xFF
        d2 = ram[7] - ram[3] - (d < 0)
        ram[7], cpu.c = d2 & 0xFF, int(d2 < 0)
    else:
        d = _word(cpu, 2) - _word(cpu, 6)
        _set(cpu, 2, d & 0xFFFF)
        cpu.c = int(d < 0)
    cpu.z, cpu.p, cpu.q = 0, 3 + j, 7 + j
    return cycles + 6 * j


def _load_sub_y(m) -> int:
    """DPからJ+1バイトをAからへ読み(DPは読んだ最後)、BAからYを引く(_sub_y)"""
    cpu = m.cpu
    _load(m, 2, cpu.dp)
    return 4 * cpu.ram[1] + _sub_y(m, 42)


def _store_y(m) -> int:
    """YからJ+1バイトをDPからのメモリへ書き、メモリにあった値を内部RAMの0C番地からへ置く"""
    cpu = m.cpu
    j, dp = cpu.ram[1], cpu.dp
    for k in range(j + 1):
        a = dp + k & 0xFFFF
        old = m.read(a)
        m.write(a, cpu.ram[6 + k & 0x7F])
        cpu.ram[0x0C + k & 0x7F] = old
    cpu.dp = dp + j & 0xFFFF
    cpu.p, cpu.q = 0x0C + j + 1 & 0x7F, 6 + j + 1 & 0x7F
    return 24 + 8 * j


def _skip_line(m) -> int:
    """X+1から0D(行の終わり)を探し、Xをその手前にする。Aに0D(観察)"""
    cpu = m.cpu
    x0 = _word(cpu, 4)
    x = x0
    for _ in range(0x10000):
        if m.read(x + 1 & 0xFFFF) == 0x0D:
            break
        x = x + 1 & 0xFFFF
    _set(cpu, 4, x)
    cpu.ram[2], cpu.dp = 0x0D, x
    cpu.q, cpu.c, cpu.z = 5, 0, 1
    return 25 + 18 * (x - x0 & 0xFFFF)


def _peek_ba(m) -> int:
    """BAの番地のバイトをAへ"""
    cpu = m.cpu
    cpu.ram[2] = m.read(_word(cpu, 2))
    cpu.ram[0], cpu.p = 0, 3
    return 21


def _word(cpu, at: int) -> int:
    return cpu.ram[at] | cpu.ram[at + 1] << 8


def _set(cpu, at: int, v: int) -> None:
    cpu.ram[at], cpu.ram[at + 1] = v & 0xFF, v >> 8 & 0xFF


def copy_minus(dst: int, base: int, b: int | None = None):
    """AからJ+1バイトをdst(XかY)へ写し、dstから1を引く。DPはできた値、Qはdst+1"""

    def run(m) -> int:
        cpu = m.cpu
        if b is not None:
            cpu.ram[3] = b
        _copy(cpu, 2, dst)
        v = _word(cpu, dst) - 1 & 0xFFFF
        _set(cpu, dst, v)
        cpu.q, cpu.dp = dst + 1, v
        return base + 2 * cpu.ram[1]

    return run


# ---- メモリ ----


def _set_dp(a: int):
    def run(m) -> int:
        m.cpu.dp = a
        return 12

    return run


def _load(m, reg: int, addr: int) -> None:
    """メモリのaddrからJ+1バイトを内部RAMのregからへ"""
    cpu = m.cpu
    j = cpu.ram[1]
    for k in range(j + 1):
        cpu.ram[reg + k] = m.read(addr + k & 0xFFFF)
    cpu.dp, cpu.p = addr + j & 0xFFFF, reg + j + 1


def _exchange(m, reg: int, addr: int) -> None:
    """内部RAMのregからとメモリのaddrからのJ+1バイトを入れ替える"""
    cpu = m.cpu
    j = cpu.ram[1]
    for k in range(j + 1):
        a = addr + k & 0xFFFF
        v = m.read(a)
        m.write(a, cpu.ram[reg + k])
        cpu.ram[reg + k] = v
    cpu.dp, cpu.p = addr + j & 0xFFFF, reg + j + 1


def copy_b(m) -> int:
    cpu = m.cpu
    x, y, n = _word(cpu, 4), _word(cpu, 6), cpu.ram[3] or 256
    v = 0
    for _ in range(n):
        x, y = x + 1 & 0xFFFF, y + 1 & 0xFFFF
        v = m.read(x)
        m.write(y, v)
    cpu.ram[2], cpu.ram[3] = v, 0
    _set(cpu, 4, x)
    _set(cpu, 6, y)
    cpu.dp, cpu.q, cpu.c, cpu.z = y, 3, 0, 1
    return 24 * n + 1


def _set_662e(m) -> int:
    cpu = m.cpu
    cpu.ram[2], cpu.ram[3] = 0xCE, 0xFF
    _exchange(m, 2, 0x662E)
    return 29 + 6 * cpu.ram[1]


def _move_6619(m) -> int:
    _load(m, 0x0A, 0x6619)
    _exchange(m, 0x0A, 0x661B)
    return 36 + 10 * m.cpu.ram[1]


def _load_66e1(m) -> int:
    _load(m, 4, 0x66E1)
    return 26 + 4 * m.cpu.ram[1]


def _fill_6650(m) -> int:
    """6650〜667F(液晶の2行の字)をAで埋める"""
    cpu = m.cpu
    for a in range(0x6650, 0x6680):
        m.write(a, cpu.ram[2])
    cpu.ram[0], cpu.dp = 0x2F, 0x667F
    return 161


def _set_662b(m) -> int:
    """662Bのビット1が0なら1にして、SET662Eと同じことをする(INKEYの前。観察)"""
    cpu = m.cpu
    cpu.z = 0
    v = m.read(0x662B)
    if v & 0x02:
        cpu.dp = 0x662B
        return 36
    m.write(0x662B, v | 0x02)
    return _set_662e(m) + 46


def _wait_tick(m) -> int:
    """2msのタイマの刻みの印を待って消し、次の刻みの印を待って消す(印は11サイクルごとに見る。
    入ったときに印がなければ、刻みを2つ待つ。観察)"""
    num, den = m.cpu.ratio
    wait = TICK_2MS - m.t2 + (0 if m.t2ms else TICK_2MS)
    # 待つ刻みまでのCPUのサイクル数。時刻はサイクル×num/denの端数(_frac)を持ち越して進むので、
    # その端数のぶん早く刻みに届く
    left = -(-(wait * den - m.cpu._frac) // num)
    cycles = 31 + 11 * -(-(left - 19) // 11)
    m.cpu.z = 0
    spend(m, cycles)
    m.t2ms = 0
    return 0


def _fill_67b0(m) -> int:
    cpu = m.cpu
    for a in range(0x67B0, 0x6800):
        m.write(a, 0x0D)
    cpu.ram[0], cpu.ram[2] = 0x4F, 0x0D
    cpu.dp = 0x67FF
    return 261


def _inc_66e1(m) -> int:
    cpu = m.cpu
    _load(m, 6, 0x66E1)
    _set(cpu, 6, _word(cpu, 6) + 1 & 0xFFFF)
    _exchange(m, 6, 0x66E3)
    _load(m, 6, 0x66E3)
    v = m.read(0x66D9) & 0xDF
    m.write(0x66D9, v)
    cpu.z = int(v == 0)
    cpu.dp, cpu.q = 0x66D9, 7
    return 68 + 14 * cpu.ram[1]


# ---- 液晶と字の形 ----


def _port_c(v: int, cycles: int):
    """AをvにしてCポートに出し、5F番地と入れ替える"""

    def run(m) -> int:
        cpu = m.cpu
        cpu.ram[2], cpu.ram[0x5F] = cpu.ram[0x5F], v
        m.out_c(v)
        cpu.p = cpu.q = 0x5F
        return cycles

    return run


def _glyph_addr(m) -> int:
    """形の終わりの次の番地をXに、FONT_TOPからの差をBAに入れる。Jが1のとき(観察)"""
    cpu = m.cpu
    _set(cpu, 4, FONT_TOP)
    cpu.q = 4
    return _glyph_from_x(m) + 37


def _glyph_from_x(m) -> int:
    """Aの字が表の何番目か(n-1)から、Xに5nを足し、BAに5nを入れる(表の頭をXに置いて呼ぶ。観察)"""
    cpu = m.cpu
    index, cycles = glyph_index(cpu.ram[2])
    n = index + 1
    carry = index > 0 and (4 * n & 0xFF) + n > 0xFF
    _set(cpu, 2, 5 * n)
    cpu.ram[0x0B] = 5 * n & 0xFF
    x = _word(cpu, 4) + 5 * n
    _set(cpu, 4, x & 0xFFFF)
    if carry:
        cpu.q = 3
    # キャリーとZは、Xに足した16ビットの結果から(観察)
    cpu.p, cpu.c, cpu.z = 5, int(x > 0xFFFF), int(x & 0xFFFF == 0)
    return cycles - 37 + carry


def lcd_cell(at: int) -> int:
    """66E9番地の形の値(ビット7で右の12桁)から、液晶の番地"""
    return (0x2800 if at & 0x80 else 0x2000) + (at & 0x7F)


def _draw(m, code: int, at: int) -> tuple[int, int]:
    """codeの形を表から液晶のatからの5バイトに書く。(最後に読んだ番地, 最後の値)"""
    x = FONT_TOP + 5 * (glyph_index(code)[0] + 1)
    v = 0
    for k in range(5):
        x -= 1
        v = m.read(x)
        m.write(at + k, v)
    return x, v


def _cursor(m) -> int:
    cpu = m.cpu
    pos = m.read(0x66E9)
    at = lcd_cell(pos)
    x, v = _draw(m, 0xF9, at)
    cpu.ram[2], cpu.ram[3], cpu.ram[0x0B] = v, 0, 0x39
    _set(cpu, 4, x)
    _set(cpu, 6, at + 4)
    cpu.p, cpu.q, cpu.dp, cpu.c, cpu.z = 8, 3, at + 4, 0, 1
    return 381 if pos & 0x80 else 376


# ---- キーと電源 ----

# KEYNUM: キーの番号と、見つかる走査の線(0〜7。観察)
KEY_NUMBERS = {
    "V": (0x00, 0), "F": (0x01, 1), "R": (0x02, 2), "UP": (0x03, 3), "4": (0x04, 4),
    "1": (0x05, 5), "7": (0x06, 6), "B": (0x07, 0), "G": (0x08, 1), "T": (0x09, 2),
    "LEFT": (0x0A, 3), "P": (0x0B, 4), "=": (0x0C, 5), "N": (0x0D, 0), "H": (0x0E, 1),
    "Y": (0x0F, 2), "RIGHT": (0x10, 3), "O": (0x11, 4), "M": (0x12, 0), "J": (0x13, 1),
    "U": (0x14, 2), "SPC": (0x16, 0), "K": (0x17, 1), "I": (0x18, 2), "ENTER": (0x19, 0),
    "L": (0x1A, 1), "0": (0x1B, 0), "C": (0x1C, 0), "D": (0x1D, 1), "E": (0x1E, 2),
    "DOWN": (0x1F, 3), "/": (0x20, 4), "*": (0x21, 5), "CL": (0x22, 6), "-": (0x23, 7),
    "X": (0x24, 0), "S": (0x25, 1), "W": (0x26, 2), "SHIFT": (0x27, 3), "6": (0x28, 4),
    "3": (0x29, 5), "9": (0x2A, 6), "+": (0x2B, 7), "Z": (0x2C, 0), "A": (0x2D, 1),
    "Q": (0x2E, 2), "DEF": (0x2F, 3), "5": (0x30, 4), "2": (0x31, 5), "8": (0x32, 6),
    ".": (0x33, 7),
}  # fmt: skip
BRK_NUMBER = 0x34  # BRK(ON)を押しているときにAに返す値


def _key_number(m) -> int:
    """押しているキーの番号をAに返す(キャリー1)。なければAをFFh、キャリー0。2つ以上押して
    いるときはAを35hにする(実機は押した組み合わせでAとBとサイクル数が変わる)"""
    cpu = m.cpu
    ram = cpu.ram
    if m.brk:
        ram[2] = BRK_NUMBER
        cpu.c = cpu.z = 1
        return 21
    keys = [KEY_NUMBERS[k] for k in m.held if k in KEY_NUMBERS]
    m.out_a(0)  # 読み終えたら、ポートAとBは0(観察)
    m.out_b(0)
    ram[9], ram[0x0A] = 0, 0x80
    cpu.p = cpu.q = 0x5D
    if not keys:
        ram[2], ram[3], ram[8] = 0xFF, 0, 0x34
        cpu.c = cpu.z = 0
        return 953
    number, line = keys[0] if len(keys) == 1 else (0x35, min(k[1] for k in keys))
    ram[2], ram[3], ram[8] = number, 0, 0x34 + line
    cpu.c = cpu.z = 1
    return 994 + 19 * line


# MODESW: モードスイッチ → (B, M, キャリー, IBに出す値, サイクル数)
MODE_SWITCH = {
    "RUN": (0x08, 0x00, 0, 0x08, 296),
    "PRO": (0x02, 0x01, 1, 0x02, 216),
    "RSV": (0x01, 0x02, 1, 0x01, 129),
    "OFF": (0x04, 0x00, 1, 0x08, 304),
}


def _mode_switch(m) -> int:
    cpu = m.cpu
    b, mm, c, pb, cycles = MODE_SWITCH.get(m.mode, MODE_SWITCH["RUN"])
    cpu.ram[2], cpu.ram[3], cpu.ram[0x0A] = 0x08, b, mm
    cpu.ram[0x5C], cpu.ram[0x5D] = 0, pb
    m.out_a(0)
    m.out_b(pb)
    cpu.c, cpu.z = c, 1 - c
    cpu.p, cpu.q, cpu.dp = 3, 0x5D, 0x203C
    return cycles


def _power_off(m) -> int:
    """内部RAMの20h〜27hをA5hで埋め、ONキーを押していなければ電源を切る"""
    cpu = m.cpu
    cpu.ram[0x20:0x28] = bytes([0xA5]) * 8
    cpu.ram[0], cpu.ram[2] = 7, 0xA5
    if m.brk:
        cpu.p, cpu.z = 0x28, 0
        return 48
    cpu.ram[2] = cpu.ram[0x5F] = 0x08
    cpu.p = cpu.q = 0x5F
    cpu.z = 1
    m.out_c(0x08)
    return 48


# INKEY: キーから文字コードへ(観察)。SHIFTのあと8はカナの入力の切り替え
PLAIN = {
    "*": 0x2A, "+": 0x2B, "-": 0x2D, ".": 0x2E, "/": 0x2F, "=": 0x3D, "CL": 0x02, "UP": 0x04,
    "DOWN": 0x05, "ENTER": 0x0D, "RIGHT": 0x0E, "LEFT": 0x0F, "SPC": 0x20,
} | {ch: ord(ch) for ch in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"}  # fmt: skip
SHIFTED = PLAIN | {
    "*": 0x3C, "-": 0x3E, ".": 0xFC, "/": 0x5E, "0": 0xFB, "1": 0x28, "2": 0x29, "3": 0x40,
    "6": 0x5C, "7": 0x14, "=": 0xF4, "CL": 0x03, "ENTER": 0x06, "RIGHT": 0x0B, "LEFT": 0x0C,
    "SPC": 0xF1, "E": 0x23, "I": 0x3A, "O": 0x2C, "P": 0x3B, "Q": 0x21, "R": 0x24, "S": 0xF3,
    "T": 0x25, "U": 0x3F, "V": 0xF6, "W": 0x22, "X": 0xF8, "Y": 0x26, "Z": 0xFA,
} | {ch: ord(ch) + 0x40 for ch in "ABCDFGHJKLMN"}  # fmt: skip
KANA = PLAIN | {
    "*": 0xA3, "+": 0xA1, "-": 0xB0, ".": 0xDD, "/": 0xA4, "=": 0xD1, "A": 0xC0, "B": 0xD7,
    "C": 0xD5, "D": 0xC3, "E": 0xB3, "F": 0xC5, "G": 0xC7, "H": 0xC9, "I": 0xBA, "J": 0xCB,
    "K": 0xCD, "L": 0xCF, "M": 0xDB, "N": 0xD9, "O": 0xBC, "P": 0xBE, "Q": 0xB1, "R": 0xB4,
    "S": 0xC2, "T": 0xB5, "U": 0xB8, "V": 0xD6, "W": 0xB2, "X": 0xD4, "Y": 0xB6, "Z": 0xD3,
}  # fmt: skip
KANA_SHIFTED = SHIFTED | {
    "*": 0xA2, "+": 0xDF, "-": 0xDE, ".": 0xA6, "/": 0xA5, "=": 0xD2, "A": 0xC1, "B": 0xD8,
    "C": 0xAD, "D": 0xC4, "E": 0xA9, "F": 0xC6, "G": 0xC8, "H": 0xCA, "I": 0xBB, "J": 0xCC,
    "K": 0xCE, "L": 0xD0, "M": 0xDC, "N": 0xDA, "O": 0xBD, "P": 0xBF, "Q": 0xA7, "R": 0xAA,
    "S": 0xAF, "T": 0xAB, "U": 0xB9, "V": 0xAE, "W": 0xA8, "X": 0xAC, "Y": 0xB7, "Z": 0xD3,
    "SPC": 0x20,
}  # fmt: skip
SHIFT_MARK, DEF_MARK = 0x20, 0x40  # 203D番地の、SHIFTとDEFの記号のビット
# キーを1つだけ押してから受け付けるまでと、戻るまで(CPUのサイクル。観察)。受け付けるまでに
# 離したキーや、ほかのキーと一緒に押したキーは数えない
INKEY_ACCEPT, INKEY_TIME = 1408, 2586
INKEY_BLINK = 1920  # 入ってから512msのタイマを始めから数えるまで(CPUのサイクル。観察)


@dataclass
class _Input:
    """INKEYが待っているあいだの様子"""

    pc: int
    r: int
    seen: int  # 最後に見たサイクル
    armed: bool = False  # すべてのキーを離したあとか(押したキーを数えてよいか)
    key: str | None = None  # 1つだけ押しているキー
    since: int = 0  # keyを押し始めたサイクル
    reset: int | None = None  # 512msのタイマを始めから数えるサイクル(数えたらNone)


_inputs: WeakKeyDictionary[object, _Input] = WeakKeyDictionary()


def _blink(m) -> None:
    """66E9の桁のカーソルを、■と66E8の字とで入れ替える。662Bのビット4が■を出しているか"""
    flags = m.read(0x662B)
    block = not flags & 0x10
    _draw(m, 0xF9 if block else m.read(0x66E8), lcd_cell(m.read(0x66E9)))
    m.write(0x662B, flags & ~0x10 | (0x10 if block else 0))


def _accept(m, k: str) -> tuple[int, int] | None:
    """1つだけ押したキーkを受け付ける。SHIFT・DEFは記号を点けて次のキーの字を変え、SHIFTの
    あと8はカナの入力を切り替える。DEFのあと=と空白は、ROMのある本体はBASICへ移るが、ここ
    では数えない。返すキーなら(文字コード, キーの番号)"""
    kana_at, kana_bit = m.model.symbols["KANA"]
    marks = m.read(0x203D)
    prefix = "SHIFT" if marks & SHIFT_MARK else "DEF" if marks & DEF_MARK else None
    if k in ("SHIFT", "DEF"):
        mark = SHIFT_MARK if k == "SHIFT" else DEF_MARK
        m.write(0x203D, marks & ~(SHIFT_MARK | DEF_MARK) | (0 if marks & mark else mark))
        return None
    if prefix == "SHIFT" and k == "8":
        m.write(0x203D, marks & ~SHIFT_MARK)
        m.write(kana_at, m.read(kana_at) ^ kana_bit)
        return None
    if prefix == "DEF" and k in ("=", "SPC") or k not in KEY_NUMBERS:
        m.write(0x203D, marks & ~DEF_MARK)
        return None
    kana = bool(m.read(kana_at) & kana_bit)
    if prefix == "SHIFT":
        table = KANA_SHIFTED if kana else SHIFTED
    else:
        table = KANA if kana else PLAIN
    return table[k], KEY_NUMBERS[k][0]


def _inkey(m) -> int | None:
    """すべてのキーを離したあとに1つだけ押したキーを待ち、Aに文字コードを返す。待つあいだ
    512msごとにカーソルを点滅させる(観察)"""
    cpu = m.cpu
    w = _inputs.get(m)
    if w is None or (w.pc, w.r) != (cpu.pc, cpu.r) or cpu.cycles - w.seen > 2 * TICK_2MS:
        w = _inputs[m] = _Input(cpu.pc, cpu.r, cpu.cycles)
        w.reset = cpu.cycles + cpu._ticks(INKEY_BLINK)
        m.write(0x662B, m.read(0x662B) & ~0x03)
    if w.reset is not None and cpu.cycles >= w.reset:
        w.reset = None
        m.out_c(0x03)  # 液晶をつけ、512msのタイマを始めから数える
    found: tuple[int, int] | None = None  # (文字コード, キーの番号)
    if m.brk:
        found = (0x07, BRK_NUMBER)
    else:
        held = {k for k in m.held if k in KEY_NUMBERS}
        if not held:
            w.armed, w.key = True, None
        elif len(held) > 1 or not w.armed:
            w.armed, w.key = False, None
        else:
            if w.key not in held:  # 前に見たときより後に押した
                w.key, w.since = next(iter(held)), w.seen
            left = w.since + cpu._ticks(INKEY_ACCEPT) - cpu.cycles
            if left <= TICK_2MS - m.t2:
                m.pass_time(max(left, 0))
                w.armed, w.key = False, None
                found = _accept(m, next(iter(held)))
                w.seen = cpu.cycles
    if found is None:
        if m.t512:
            m.t512 = 0
            if w.reset is None:
                _blink(m)
        m.pass_time(TICK_2MS - m.t2)
        w.seen = cpu.cycles
        return None
    del _inputs[m]
    code, number = found
    marks = m.read(0x203D)
    kana_at, kana_bit = m.model.symbols["KANA"]
    shifted = bool(marks & SHIFT_MARK) or (
        m.read(kana_at) & kana_bit and not marks & DEF_MARK and number >= 0x2A
    )
    ram = cpu.ram
    ram[0], ram[2], ram[3] = 1, code, 0x84 if shifted else 0x83
    _set(cpu, 6, 0x6681)
    prefix = marks & (SHIFT_MARK | DEF_MARK)
    cpu.c = int(code < 0x41 and code not in (0x20, 0x3D))
    cpu.z = int(code == 0x20 or (not prefix and (code == 0x3D or 0x41 <= code <= 0x5A)))
    m.write(0x662C, code)
    m.write(0x6628, 0x01)
    m.write(0x6680, 0x00)
    m.write(0x6681, 0xFB)
    m.write(0x662B, m.read(0x662B) | 0x01)
    return 563 if m.brk else INKEY_TIME - INKEY_ACCEPT


# 名前(romsyms.ROUTINES_1261): 代わりに動かす関数(使ったCPUのサイクル数を返す。Noneなら、まだ
# 待っていて入口にとどまる)
ROUTINES: dict[str, Callable[..., int | None]] = {
    "BA2X": copy_to(2, 4, 15),
    "BA2Y": copy_to(2, 6, 22),
    "BA2XM": copy_minus(4, 32),
    "BA2YM": copy_minus(6, 39),
    "LCDYM": copy_minus(6, 50, b=0x20),
    "B67XM": copy_minus(4, 36, b=0x67),
    "B67YM": copy_minus(6, 43, b=0x67),
    "Y2RP": _to_p(6, 13),
    "R3A2RP": _to_p(0x3A, 13),
    "EXXR0C": _swap(4, 0x0C, 16),
    "EXAY": _swap(2, 6, 16),
    "EXYRP": _swap_p(6, 14),
    "YINC2R15": _y_plus_to_15,
    "POPX": _pop_x,
    "PUSHX": _push_x,
    "SUBY": lambda m: _sub_y(m, 35),
    "LDSUBY": _load_sub_y,
    "R382X": copy_to(0x38, 4, 15),
    "X2R38": copy_to(4, 0x38, 15),
    "R3A2X": copy_to(0x3A, 4, 15),
    "X2R3A": copy_to(4, 0x3A, 15),
    "EXXR38": _swap(4, 0x38, 16),
    "EXXR28": _swap(4, 0x28, 16),
    "DP203D": _set_dp(0x203D),
    "DP662B": _set_dp(0x662B),
    "COPYB": copy_b,
    "SET662E": _set_662e,
    "MV6619": _move_6619,
    "FILL67B0": _fill_67b0,
    "FILL6650": _fill_6650,
    "LDX66E1": _load_66e1,
    "STYDP": _store_y,
    "PEEKBA": _peek_ba,
    "SKIPLINE": _skip_line,
    "SET662B": _set_662b,
    "WAIT2MS": _wait_tick,
    "INC66E1": _inc_66e1,
    "DISPOFF": _port_c(0x00, 24),
    "DISPON": _port_c(0x01, 17),
    "GLYPH": _glyph_addr,
    "GLYPHX": _glyph_from_x,
    "CURSOR": _cursor,
    "KEYNUM": _key_number,
    "INKEY": _inkey,
    "MODESW": _mode_switch,
    "POWEROFF": _power_off,
}


NOT_CR = [b for b in range(0x100) if b != 0x0D]


def _check_inputs(name: str):
    """ROMのある本体と比べるとき(routinecheck)に与える値。6500h〜67FFhの作業場所を乱数で
    埋め、番地を指すレジスタはRAMに向ける"""

    def run(case, rnd) -> None:
        work = bytearray(rnd.randrange(256) for _ in range(0x300))
        work[0x1E9] = rnd.choice((0x00, 0x0B, 0x55, 0x80, 0xCB))  # 66E9h(CURSORの桁)
        case.mem[0x6500] = bytes(work)
        if name in ("CURSOR", "KEYNUM", "MODESW"):
            case.ram[1] = 1
        if name == "COPYB":
            case.ram[4:8] = bytes([rnd.randrange(256), 0x65, rnd.randrange(256), 0x66])
            case.ram[3] = rnd.choice((0, 1, 5, 40))
        elif name in ("SUBY", "LDSUBY"):
            case.ram[1] = rnd.choice((0, 1, 2, 3))  # Jが4以上は、まねていない
        elif name == "SKIPLINE":
            x = rnd.randrange(0x4000, 0x6600)
            case.ram[4], case.ram[5] = x & 0xFF, x >> 8
            n = rnd.randrange(40)
            case.mem[x + 1] = bytes(rnd.choice(NOT_CR) for _ in range(n)) + b"\x0d"
        elif name == "GLYPHX" and rnd.random() < 0.5:
            x = rnd.randrange(0xFF00, 0x10000)  # 足すとFFFFhを越えて、キャリーが出る
            case.ram[4], case.ram[5] = x & 0xFF, x >> 8
        elif name == "PEEKBA":
            case.ram[3] = rnd.randrange(0x40, 0x68)  # RAMを読む(ROMなしの本体にROMの中身はない)
        elif name == "POPX":
            case.outer = True  # 呼び出し元の戻り番地も、比べるときの戻り番地にする
            case.ram[1] = rnd.randrange(2)  # Jが2以上は、スタックの上のポート(5Ch〜)まで書き換える
        elif name == "STYDP":
            case.ram[1] = rnd.randrange(6)  # Jが6以上は、写す元と先が重なる(まねていない)
        elif name in ("Y2RP", "R3A2RP", "EXYRP"):
            case.p = rnd.randrange(0x10, 0x30)  # 写す元とスタックに重ならない所
        elif name == "KEYNUM":
            case.held = set(rnd.sample(sorted(KEY_NUMBERS), rnd.choice((0, 1))))
        elif name == "MODESW":
            case.mode = rnd.choice(tuple(MODE_SWITCH))
        elif name == "POWEROFF":
            case.brk = rnd.random() < 0.5
        elif name == "INKEY":
            case.mem[0x66E8] = bytes([0x46, 0x85])
            case.mem[0x662B] = bytes([0x17])
            case.mem[0x203D] = bytes([0])
            key = rnd.choice("ABQZ059")
            case.presses = [(0.2, {key}), (0.3, set())]

    return run


# 名前: (与える値, 比べないもの, サイクル数の違ってよい割合)。ROMのある本体と比べるとき
# (routinecheck)に使う
CHECK: dict[str, CheckSpec] = {name: (_check_inputs(name), (), 0.0) for name in ROUTINES}
# INKEYは、作業に使うレジスタとRAM、Cポートを比べない(まねていない)。戻るまでの時間は1%まで
CHECK["INKEY"] = (
    _check_inputs("INKEY"),
    (4, 5, 8, 9, 0x0A, 0x5F, "p", "q", "dp", "pa", "pc", 0x6627, 0x6628),
    0.01,
)

"""PC-1350をROMなしで動かすときの、代替ROMルーチンと文字の形の表

受け持つのは、romsyms.ROUTINES_1350の入口だけ。決め方はnorom1261.pyと同じで、ROMのある本体で
値を与えて呼び、戻ったときの内部RAM、メモリ、フラグ、ポートと、かかったサイクル数を見て決めた。
サイクル数はCPUのサイクル。

文字の形の表は、BASIC ROMと同じ番地と並び(808Ahから1字5バイト、右の列が先)に置く。字の形は
ROMなしのBASICが液晶に出す字と同じ(エミュレータで描いたもの)。
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from . import norom, norom1261
from .basic.errors import BasicError
from .basic.pc1261 import console
from .machine import TICK_2MS
from .number import get_num, put_num
from .routines import CheckSpec

FONT_TOP = 0x808A  # 空白(20h)の形の番地
TEXT = 0x6D00  # 液晶の4行の字(1行24字)
LCD_BLOCKS = (0x7000, 0x7200, 0x7400, 0x7600, 0x7800)  # 液晶RAMの、30列ずつの区画
LCD_BANDS = (0x00, 0x40, 0x1E, 0x5E)  # 各区画の中の、液晶の各行の頭


def used(m) -> bool:
    return m.norom and m.model.name == "1350"


def glyph_index(code: int) -> int | None:
    """文字コードの字の形が表の何番目か。表にない文字コードはNone"""
    if 0x20 <= code < 0x80:
        return code - 0x20
    if 0xA0 <= code < 0xE0:
        return code - 0x40
    if 0xF0 <= code:
        return code - 0x50
    return None


def install(m) -> None:
    """フォントとキーの表を、BASIC ROMの番地に書く"""
    for code in range(0x100):
        index = glyph_index(code)
        if index is not None:
            at = FONT_TOP + 5 * index
            m.mem[at : at + 5] = bytes(reversed(console.glyph(code)))
    for name, code in key_codes().items():
        m.mem[KEY_TABLE + KEY_NUMBERS[name][0]] = code
    m.mem[KEY_TABLE + BRK_NUMBER] = KEY_CODES["BRK"]


def key_codes() -> dict[str, int]:
    """キーの番号(KEYNUMが返すもの)の表に置く、キーの文字コード。字のキーは字のASCIIのコード、
    ほかのキーはKEY_CODES。DEL・INS・KANAは決めていない(0のまま)"""
    out = {}
    for name in KEY_NUMBERS:
        if name in KEY_CODES:
            out[name] = KEY_CODES[name]
        elif len(name) == 1:
            out[name] = ord(name)
    return out


def lcd_addr(row: int, col: int) -> int:
    """液晶の行row(0〜3)の列col(0〜149)の液晶RAMの番地"""
    return LCD_BLOCKS[col // 30] + LCD_BANDS[row] + col % 30


def _show_text(m) -> int:
    """6D00hからの96字を、表の字の形で液晶の4行に書く。各行の頭の6列と字のあいだの列は0。
    Jが1のときの働き(観察)"""
    cpu = m.cpu
    for row in range(4):
        for col in range(6):
            m.write(lcd_addr(row, col), 0)
        for i in range(24):
            index = glyph_index(m.read(TEXT + 24 * row + i))
            g = FONT_TOP + 5 * (index or 0)
            for k in range(5):
                m.write(lcd_addr(row, 6 * (i + 1) + k), m.read(g + 4 - k))
            m.write(lcd_addr(row, 6 * (i + 1) + 5), 0)
    m.write(0x7881, 0)
    m.write(0x7886, m.read(0x7886) & ~0x04 | 0x08)
    m.write(0x788F, m.read(0x788F) & ~0x03 | 0x02)
    ram = cpu.ram
    ram[0], ram[2] = 0x17, 0xFF
    ram[6], ram[7], ram[8], ram[9], ram[0x0A] = 0x1D, 0x78, 0x28, 0, 0
    ram[0x10:0x28] = bytes(m.read(TEXT + i) for i in range(24))
    cpu.c, cpu.z, cpu.p, cpu.q, cpu.dp = 1, 0, 5, 2, 0x788F
    m.lcd_dirty = True
    return 26300


def _fill_6eb0(m) -> int:
    cpu = m.cpu
    for a in range(0x6EB0, 0x6F00):
        m.write(a, 0x0D)
    cpu.ram[0], cpu.ram[2] = 0x4F, 0x0D
    cpu.dp = 0x6EFF
    return 261


# KEYNUM: キーの番号と、見つかる走査の線(0〜6。観察)
KEY_NUMBERS = {
    "Y": (0x00, 0), "H": (0x01, 1), "N": (0x02, 2), "DEL": (0x03, 3), "INS": (0x04, 4),
    "U": (0x06, 0), "J": (0x07, 1), "M": (0x08, 2), "MODE": (0x09, 3), "I": (0x0B, 0),
    "K": (0x0C, 1), "SPC": (0x0D, 2), "CLS": (0x0E, 3), "O": (0x0F, 0), "L": (0x10, 1),
    "ENTER": (0x11, 2), "P": (0x12, 0), "=": (0x13, 1), "SHIFT": (0x15, 0), "SHIFT2": (0x15, 0),
    "DEF": (0x16, 1), "KANA": (0x17, 2), ",": (0x18, 3), ";": (0x19, 4), ":": (0x1A, 5),
    ")": (0x1B, 6), "Q": (0x1C, 0), "A": (0x1D, 1), "Z": (0x1E, 2), "-": (0x1F, 3),
    "*": (0x20, 4), "/": (0x21, 5), "(": (0x22, 6), "W": (0x23, 0), "S": (0x24, 1),
    "X": (0x25, 2), "+": (0x26, 3), "3": (0x27, 4), "6": (0x28, 5), "9": (0x29, 6),
    "E": (0x2A, 0), "D": (0x2B, 1), "C": (0x2C, 2), ".": (0x2D, 3), "2": (0x2E, 4),
    "5": (0x2F, 5), "8": (0x30, 6), "R": (0x31, 0), "F": (0x32, 1), "V": (0x33, 2),
    "0": (0x34, 3), "1": (0x35, 4), "4": (0x36, 5), "7": (0x37, 6), "T": (0x38, 0),
    "G": (0x39, 1), "B": (0x3A, 2), "RIGHT": (0x3B, 3), "LEFT": (0x3C, 4), "DOWN": (0x3D, 5),
    "UP": (0x3E, 6),
}  # fmt: skip
BRK_NUMBER = 0x3F  # BRK(ON)を押しているときにAに返す値
# キーの番号から文字コードを引く表。マシン語が、KEYNUMで得たキーの番号を足した番地を読む
# (漢字表示システムのマシン語モニタなど)。字のキーでないキーの文字コードは、漢字表示システムの
# SYMBOL1350.hに書かれた値
KEY_TABLE = 0x8403
KEY_CODES = {
    "SPC": 0x20, "CLS": 0x02, "MODE": 0x08, "ENTER": 0x0D, "RIGHT": 0x0E, "LEFT": 0x0F,
    "DOWN": 0x05, "UP": 0x04, "BRK": 0x07, "SHIFT": 0x10, "SHIFT2": 0x10, "DEF": 0x12,
}  # fmt: skip
MANY = 0x40  # キーを2つ以上押しているときにAに返す値


def _key_number(m) -> int:
    """押しているキーの番号をAに返す(キャリー1)。なければAをFFh、キャリー0。2つ以上押して
    いるときはAを40hにする(実機は押した組み合わせでサイクル数と8番地の値が変わる)"""
    cpu = m.cpu
    ram = cpu.ram
    if m.brk:
        ram[2] = BRK_NUMBER
        cpu.c = cpu.z = 1
        return 21
    keys = {KEY_NUMBERS[k] for k in m.held if k in KEY_NUMBERS}
    m.out_a(0)  # 読み終えたら、ポートAは0(観察)
    ram[9], ram[0x0A], ram[0x0B] = 0, 0xC0, 0x20
    cpu.p, cpu.q, cpu.dp = 8, 9, 0x7E00
    if not keys:
        ram[2], ram[3], ram[8] = 0xFF, 0, 0x3F
        cpu.c = cpu.z = 0
        return 1117
    if len(keys) == 1:
        (number, line), extra = next(iter(keys)), 0
    else:
        number, line, extra = MANY, max(k[1] for k in keys), 37
    ram[2], ram[3], ram[8] = number, 0, 0x3F + line
    cpu.c = cpu.z = 1
    return 1162 + 19 * line + extra


def _swap_port(m) -> int:
    norom._swap_port(m)
    return 13


def _wait_6ms(m) -> int:
    """2msのタイマのフラグを3回待つ(立っていれば、すぐに消して数える)。Zは0。待つ時間のほかに
    20サイクル(呼んだときにフラグが立っていれば19。観察)"""
    early = m.t2ms
    for _ in range(3):
        if not m.t2ms:
            m.pass_time(TICK_2MS - m.t2)
        m.t2ms = 0
    m.cpu.z = 0
    return 19 if early else 20


def _push_x(m) -> int:
    """Xを、戻り番地の下に積む。Aは積んだあとのスタックの位置。Pは戻り番地のあった所+2、
    Qは戻り番地のあった所、CとZは0(観察。Jが1のとき)"""
    cpu = m.cpu
    r = cpu.r
    norom._push_x(m)
    cpu.p, cpu.q, cpu.c, cpu.z = r + 2, r, 0, 0
    return 40


def _pop_x(m) -> int:
    """PUSHXで積んだXを戻す。Aは戻したバイトのあった位置、Bは呼んだときのスタックの位置。
    PはA+2、QはA、CとZは0(観察。Jが1のとき)"""
    cpu = m.cpu
    norom._pop_x(m)
    cpu.p, cpu.q, cpu.c, cpu.z = cpu.ram[2] + 2, cpu.ram[2], 0, 0
    return 46


def _copy_5r(m) -> int:
    """X−1から下へ5バイトをY+1から上へ写し、その次の1バイトを0にする(字の形を液晶へ写す)。
    XとYは進めたまま、AとBは0、DPは最後に書いた番地、Zは1、Cは0、Qは7(観察)"""
    cpu = m.cpu
    x, y = norom1261._word(cpu, 4), norom1261._word(cpu, 6)
    for _ in range(5):
        x, y = x - 1 & 0xFFFF, y + 1 & 0xFFFF
        m.write(y, m.read(x))
    y = y + 1 & 0xFFFF
    m.write(y, 0)
    norom1261._set(cpu, 4, x)
    norom1261._set(cpu, 6, y)
    cpu.ram[2] = cpu.ram[3] = 0
    cpu.dp, cpu.z, cpu.c, cpu.q = y, 1, 0, 7
    m.lcd_dirty = True
    return 135


NUM = 0x10  # 数を置く内部RAM(10h〜17h。BASICの変数と同じ形)
STRING_MARK = 0xD0  # 文字列のとき14h番地に置く値。15h・16hは字の番地、17hは字の数(観察)
STR_BUF = 0x6E60  # 文字列の字を置く番地
ERRNO = 0x34  # エラーの番号(内部RAM)


def _error(m, n: int) -> None:
    cpu = m.cpu
    cpu.c = cpu.z = 1
    cpu.ram[ERRNO] = n


def _evaluate(m) -> int:
    """Xの次からの式を計算する。数は10h〜17hに、文字列は6E60hからに置き、14h〜17hに印と番地、
    字の数を入れる。Xは式の最後の字、DPはX、キャリーは0。式が誤りならキャリーとZを1にし、
    34h番地にエラーの番号、Xは誤りを見つけた字(観察。ROMなしのBASICの式の計算を使う)"""
    cpu = m.cpu
    basic = getattr(m, "basic", None)
    if basic is None:
        _error(m, 1)
        return 500
    x = norom1261._word(cpu, 4)
    code = bytearray()
    while len(code) < 0x100:
        c = m.read(x + 1 + len(code) & 0xFFFF)
        code.append(c)
        if c == 0x0D:
            break
    e = basic.EVALUATOR(m, bytes(code), 0)
    try:
        v = e.expression()
    except BasicError as err:
        _error(m, err.number)
        x = x + max(e.pos, err.pos or 0) & 0xFFFF
        norom1261._set(cpu, 4, x)
        cpu.dp = x
        return 500 + e.meter.cycles
    if isinstance(v, bytes):
        v = v[:0x50]
        for i, b in enumerate(v):
            m.write(STR_BUF + i, b)
        cpu.ram[0x14:0x18] = bytes([STRING_MARK, STR_BUF & 0xFF, STR_BUF >> 8, len(v)])
    else:
        put_num(cpu.ram, NUM, v)
    x = x + e.pos & 0xFFFF
    norom1261._set(cpu, 4, x)
    cpu.dp, cpu.c, cpu.z = x, 0, 0
    return 600 + e.meter.cycles


def _is_number(m) -> int:
    """14h番地をD0hと比べる。数ならキャリーが1、文字列ならZが1。Pは14h(観察)"""
    cpu = m.cpu
    v = cpu.ram[0x14]
    cpu.c, cpu.z, cpu.p = int(v < STRING_MARK), int(v == STRING_MARK), 0x14
    return 10


def _to_int(m) -> int:
    """10h〜17hの数の整数の部分(0〜65535)を18h・19hに、上位をBに入れ(1より小さい正の数ならBはそのまま)、
    キャリーを0にする。範囲の外はエラー3、文字列はエラー9で、キャリーとZを1にする(観察)"""
    cpu = m.cpu
    if cpu.ram[0x14] == STRING_MARK:
        _error(m, 9)
        return 50
    x = get_num(cpu.ram, NUM)
    v = int(x)
    if not 0 <= v <= 0xFFFF or x < 0:
        _error(m, 3)
        return 80
    cpu.ram[0x18], cpu.ram[0x19] = v & 0xFF, v >> 8
    if v or x == 0:
        cpu.ram[3] = v >> 8
    cpu.c = cpu.z = 0
    return 300


# 名前(romsyms.ROUTINES_1350): 代わりに動かす関数(使ったCPUのサイクル数を返す)
ROUTINES: dict[str, Callable[..., int | None]] = {
    "BA2XM": norom1261.copy_minus(4, 21),
    "BA2YM": norom1261.copy_minus(6, 21),
    "COPYB": norom1261.copy_b,
    "FILL6EB0": _fill_6eb0,
    "SHOWTEXT": _show_text,
    "KEYNUM": _key_number,
    "BA2Y": norom1261.copy_to(2, 6, 15),
    "BA2X": norom1261.copy_to(2, 4, 15),
    "SWAPC": _swap_port,
    "WAIT6MS": _wait_6ms,
    "PUSHX": _push_x,
    "POPX": _pop_x,
    "R382X": norom1261.copy_to(0x38, 4, 15),
    "X2R38": norom1261.copy_to(4, 0x38, 15),
    "COPY5R": _copy_5r,
    "EVAL": _evaluate,
    "NUMCHK": _is_number,
    "F2I": _to_int,
}


def _check_inputs(name: str):
    """ROMのある本体と比べるとき(routinecheck)に与える値。6100h〜63FFhの作業場所と6D00hからの
    字を乱数で決め、番地を指すレジスタはRAMに向ける"""

    def run(case, rnd) -> None:
        case.mem[0x6100] = bytes(rnd.randrange(256) for _ in range(0x300))
        case.mem[TEXT] = bytes(rnd.choice(b'ABCXYZ 0189<>.-"\xb1\xdf') for _ in range(0x60))
        case.dp = 0x6400 + rnd.randrange(0x100)
        if name == "KEYNUM":
            case.ram[1] = 1
            case.held = set(rnd.sample(sorted(KEY_NUMBERS), rnd.choice((0, 1))))
        elif name in ("NUMCHK", "F2I"):
            _number_inputs(case, rnd)
        elif name == "COPY5R":
            case.ram[4:8] = bytes([rnd.randrange(256), 0x61, rnd.randrange(256), 0x62])
        elif name == "COPYB":
            case.ram[4:8] = bytes([rnd.randrange(256), 0x61, rnd.randrange(256), 0x62])
            case.ram[3] = rnd.choice((0, 1, 5, 40))

    return run


def _number_inputs(case, rnd) -> None:
    """NUMCHK・F2I: 10h〜17hに数か、文字列の印。F2Iの範囲の外の数のうち、65536〜1E20ぐらいの
    ときにROMのある本体が18h・19hとBに残す途中の値はまねていないので、与えない"""
    if rnd.random() < 0.25:
        case.ram[0x14:0x18] = bytes([STRING_MARK, 0x60, 0x6E, rnd.randrange(8)])
    else:
        v = rnd.choice(("0", "1", "1.5", "123", "65535", "-1", "-0.5", "1E20", "&3021", "0.25"))
        put_num(case.ram, NUM, Decimal(int(v[1:], 16)) if v[0] == "&" else Decimal(v))


# 名前: (与える値, 比べないもの, サイクル数の違ってよい割合)。SHOWTEXTは、決めていないB・X・
# 0Bh番地とポートAを比べない。EVALはBASICのCALLから呼んだときしか働かないので、ここでは比べない
# (tests/test_norom1350.pyでCALLから呼んで比べる)。F2Iは18h・19h・B・キャリー・Z・34hを比べる
CHECK: dict[str, CheckSpec] = {name: (_check_inputs(name), (), 0.0) for name in ROUTINES}
CHECK["SHOWTEXT"] = (_check_inputs("SHOWTEXT"), (3, 4, 5, 0x0B, "pa"), 0.012)
del CHECK["EVAL"]
CHECK["F2I"] = (_check_inputs("F2I"), (*range(0x10, 0x18), 0, 2, 8, 0x32, "p", "q", "cycles"), 0.0)

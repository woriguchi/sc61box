"""SC61860の逆アセンブラ(マシン語の作業欄で使う)

命令の名前と形は tools/asm61860.py のアセンブラと同じ。相対ジャンプは向きを名前から外し、
飛び先の番地を書く(アセンブラはJRNZなどの名前から向きを選ぶので、そのまま組み直せる)。
番地と値は&なしの16進表記。DTCのあとの表は、手前のPTCで行の数がわかれば「DB」の行にする。
"""

from collections.abc import Iterator
from typing import NamedTuple

from .i18n import tr

# オペコード: (名前, 形)。形は "" なし、"n" 1バイト、"nm" 2バイト(上位が先)、
# "r+" 前への相対、"r-" 後ろへの相対。LP・CAL・PTCは別に扱う
OPS: dict[int, tuple[str, str]] = {
    0x00: ("LII", "n"),
    0x01: ("LIJ", "n"),
    0x02: ("LIA", "n"),
    0x03: ("LIB", "n"),
    0x04: ("IX", ""),
    0x05: ("DX", ""),
    0x06: ("IY", ""),
    0x07: ("DY", ""),
    0x08: ("MVW", ""),
    0x09: ("EXW", ""),
    0x0A: ("MVB", ""),
    0x0B: ("EXB", ""),
    0x0C: ("ADN", ""),
    0x0D: ("SBN", ""),
    0x0E: ("ADW", ""),
    0x0F: ("SBW", ""),
    0x10: ("LIDP", "nm"),
    0x11: ("LIDL", "n"),
    0x12: ("LIP", "n"),
    0x13: ("LIQ", "n"),
    0x14: ("ADB", ""),
    0x15: ("SBB", ""),
    0x18: ("MVWD", ""),
    0x19: ("EXWD", ""),
    0x1A: ("MVBD", ""),
    0x1B: ("EXBD", ""),
    0x1C: ("SRW", ""),
    0x1D: ("SLW", ""),
    0x1E: ("FILM", ""),
    0x1F: ("FILD", ""),
    0x20: ("LDP", ""),
    0x21: ("LDQ", ""),
    0x22: ("LDR", ""),
    0x23: ("CLRA", ""),
    0x24: ("IXL", ""),
    0x25: ("DXL", ""),
    0x26: ("IYS", ""),
    0x27: ("DYS", ""),
    0x28: ("JRNZ", "r+"),
    0x29: ("JRNZ", "r-"),
    0x2A: ("JRNC", "r+"),
    0x2B: ("JRNC", "r-"),
    0x2C: ("JR", "r+"),
    0x2D: ("JR", "r-"),
    0x2F: ("LOOP", "r-"),
    0x30: ("STP", ""),
    0x31: ("STQ", ""),
    0x32: ("STR", ""),
    0x34: ("PUSH", ""),
    0x37: ("RTN", ""),
    0x38: ("JRZ", "r+"),
    0x39: ("JRZ", "r-"),
    0x3A: ("JRC", "r+"),
    0x3B: ("JRC", "r-"),
    0x40: ("INCI", ""),
    0x41: ("DECI", ""),
    0x42: ("INCA", ""),
    0x43: ("DECA", ""),
    0x44: ("ADM", ""),
    0x45: ("SBM", ""),
    0x46: ("ANMA", ""),
    0x47: ("ORMA", ""),
    0x48: ("INCK", ""),
    0x49: ("DECK", ""),
    0x4A: ("INCM", ""),
    0x4B: ("DECM", ""),
    0x4C: ("INA", ""),
    0x4D: ("NOPW", ""),
    0x4E: ("WAIT", "n"),
    0x50: ("INCP", ""),
    0x51: ("DECP", ""),
    0x52: ("STD", ""),
    0x53: ("MVDM", ""),
    0x54: ("READM", ""),
    0x55: ("MVMD", ""),
    0x57: ("LDD", ""),
    0x58: ("SWP", ""),
    0x59: ("LDM", ""),
    0x5A: ("SL", ""),
    0x5B: ("POP", ""),
    0x5D: ("OUTA", ""),
    0x5F: ("OUTF", ""),
    0x60: ("ANIM", "n"),
    0x61: ("ORIM", "n"),
    0x62: ("TSIM", "n"),
    0x63: ("CPIM", "n"),
    0x64: ("ANIA", "n"),
    0x65: ("ORIA", "n"),
    0x66: ("TSIA", "n"),
    0x67: ("CPIA", "n"),
    0x6B: ("TEST", "n"),
    0x70: ("ADIM", "n"),
    0x71: ("SBIM", "n"),
    0x74: ("ADIA", "n"),
    0x75: ("SBIA", "n"),
    0x78: ("CALL", "nm"),
    0x79: ("JP", "nm"),
    0x7C: ("JPNZ", "nm"),
    0x7D: ("JPNC", "nm"),
    0x7E: ("JPZ", "nm"),
    0x7F: ("JPC", "nm"),
    0xC0: ("INCJ", ""),
    0xC1: ("DECJ", ""),
    0xC2: ("INCB", ""),
    0xC3: ("DECB", ""),
    0xC4: ("ADCM", ""),
    0xC5: ("SBCM", ""),
    0xC6: ("TSMA", ""),
    0xC7: ("CPMA", ""),
    0xC8: ("INCL", ""),
    0xC9: ("DECL", ""),
    0xCA: ("INCN", ""),
    0xCB: ("DECN", ""),
    0xCC: ("INB", ""),
    0xCE: ("NOPT", ""),
    0xD0: ("SC", ""),
    0xD1: ("RC", ""),
    0xD2: ("SR", ""),
    0xD4: ("ANID", "n"),
    0xD5: ("ORID", "n"),
    0xD6: ("TSID", "n"),
    0xD8: ("LEAVE", ""),
    0xDA: ("EXAB", ""),
    0xDB: ("EXAM", ""),
    0xDD: ("OUTB", ""),
    0xDF: ("OUTC", ""),
    0x35: ("DATA", ""),
    0x4F: ("CUP", ""),
    0x56: ("READ", ""),
    0x69: ("DTC", ""),
    0x6F: ("CDN", ""),
    0x72: ("LIIH", "n"),
    0x73: ("LIIH", "n"),
    0x76: ("LIIH", "n"),
    0x77: ("LIIH", "n"),
}

# 呼び出しの命令(1命令ずつの実行で、呼んだ先を戻るまで実行するときに使う)
CALLS = (0x78,)  # CALL。CALは0xE0〜0xFF


class Ins(NamedTuple):
    addr: int
    size: int
    name: str
    operand: str
    target: int | None  # 飛び先(ジャンプと呼び出し、DTCの表の行)
    note: str = ""  # 添え書き(DTCの表の行の行き先など)

    def text(self) -> str:
        return f"{self.name} {self.operand}".rstrip()

    def line(self) -> str:
        """添え書きまでつけた1行(.hexの「;」のあとに書く形)"""
        return f"{self.text()} ; {self.note}" if self.note else self.text()


def length(op: int) -> int:
    """オペコードopの命令のバイト数"""
    if 0x80 <= op <= 0xBF:
        return 1
    if op >= 0xE0:
        return 2
    if op == 0x7A:
        return 4
    kind = OPS.get(op, ("", ""))[1]
    return {"": 1, "n": 2, "nm": 3, "r+": 2, "r-": 2}[kind]


def decode(read, addr: int) -> Ins:
    """addr番地の命令を読む。readは番地からバイトを返す関数"""
    op = read(addr)
    b = [read((addr + i) & 0xFFFF) for i in range(1, 4)]
    if 0x80 <= op <= 0xBF:
        return Ins(addr, 1, "LP", f"{op & 0x3F:02X}", None)
    if op >= 0xE0:
        t = (op & 0x1F) << 8 | b[0]
        return Ins(addr, 2, "CAL", f"{t:04X}", t)
    if op == 0x7A:
        t = b[1] << 8 | b[2]
        return Ins(addr, 4, "PTC", f"{b[0]:02X},{t:04X}", t)
    if op not in OPS:
        return Ins(addr, 1, "???", "", None)
    name, kind = OPS[op]
    if kind == "n":
        return Ins(addr, 2, name, f"{b[0]:02X}", None)
    if kind == "nm":
        t = b[0] << 8 | b[1]
        jump = name.startswith(("JP", "CALL"))
        return Ins(addr, 3, name, f"{t:04X}", t if jump else None)
    if kind in ("r+", "r-"):
        base = (addr + 1) & 0xFFFF
        t = (base + b[0] if kind == "r+" else base - b[0]) & 0xFFFF
        return Ins(addr, 2, name, f"{t:04X}", t)
    return Ins(addr, 1, name, "", None)


PTC, DTC = 0x7A, 0x69
PTC_NEAR = 16  # DTCの何バイト手前までPTCを探すか


def find_ptc(read, addr: int) -> int | None:
    """addr番地のDTCの表の行の数(手前のPTCのh)。PTCからaddrまでのあいだの命令を順に読んで
    ちょうどaddrに着き、あいだに飛ぶ命令がなければ、そのPTCを使う。見つからなければNone"""
    for back in range(4, PTC_NEAR + 1):
        p = (addr - back) & 0xFFFF
        if read(p) != PTC:
            continue
        a = (p + 4) & 0xFFFF
        while a != addr and (a - p) & 0xFFFF < back:
            ins = decode(read, a)
            if ins.target is not None or ins.name in ("RTN", "DTC", "???"):
                break
            a = (a + ins.size) & 0xFFFF
        if a == addr:
            return read((p + 1) & 0xFFFF)
    return None


def table(read, addr: int, rows: int) -> list[Ins]:
    """addr番地(DTCの次)からのDTCの表。「値,行き先」の3バイトの行がrows行と、どれでも
    ないときの行き先の2バイトの行"""
    out = []
    for i in range(rows):
        a = (addr + 3 * i) & 0xFFFF
        v, hi, lo = (read((a + k) & 0xFFFF) for k in range(3))
        t = hi << 8 | lo
        out.append(Ins(a, 3, "DB", f"{v:02X},{hi:02X},{lo:02X}", t, f"→{t:04X}"))
    a = (addr + 3 * rows) & 0xFFFF
    hi, lo = read(a), read((a + 1) & 0xFFFF)
    t = hi << 8 | lo
    out.append(Ins(a, 2, "DB", f"{hi:02X},{lo:02X}", t, tr("ほかは→{addr:04X}", addr=t)))
    return out


def lines(read, addr: int) -> Iterator[Ins]:
    """addr番地から命令を順に読む。DTCのあとは、表の行の数がわかれば(読んできたPTCか、
    すぐ手前のPTC)表の行を出す"""
    rows: int | None = None
    while True:
        ins = decode(read, addr)
        yield ins
        addr = (addr + ins.size) & 0xFFFF
        if ins.name == "PTC":
            rows = read((ins.addr + 1) & 0xFFFF)
        elif ins.name == "DTC":
            n = rows if rows is not None else find_ptc(read, ins.addr)
            rows = None
            if n is not None:
                for row in table(read, addr, n):
                    yield row
                    addr = (addr + row.size) & 0xFFFF
        elif ins.target is not None or ins.name == "RTN":
            rows = None  # 飛んだ先のDTCには、ここまでのPTCを使わない


def is_call(read, addr: int) -> bool:
    op = read(addr)
    return op in CALLS or op >= 0xE0

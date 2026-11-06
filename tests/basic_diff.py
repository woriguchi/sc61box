"""差分試験の道具: 同じキー操作をROMのある本体とROMなしの本体に与え、液晶とRAMを比べる

手順は(動作, 引数)の列。動作は "mode"(モードを変える)、"type"(字を打つ。\\nでENTER)、
"keys"(キーの名前の列を押す)、"wait"(秒)、"look"(この時点の様子を記録する)、"brk"(BRKを
0.3秒押す)。
"""

from collections.abc import Sequence
from dataclasses import dataclass

import helpers
from helpers import finish

from sc61box import norom
from sc61box.autotype import Typer
from sc61box.basic import attach
from sc61box.basictext import CHARS
from sc61box.machine import CLOCK, new_machine

CURSORS = {bytes([0x40] * 5): "_", bytes([0x7F] * 5): "#"}


def basic_machine(model: str | None = None):
    """ROMなしで、BASICを付けた本体(機種を書かなければhelpers.MODEL)"""
    m = new_machine(model or helpers.MODEL, rom=False)
    norom.install(m)
    attach(m)
    m.run(CLOCK // 2)
    return m


def lcd(m) -> str:
    """液晶の字。その本体の字の形の表(ROMのものか、エミュレータが描いたもの)で読む。
    読めない形は?、カーソルは_と#"""
    table = {bytes(5): " "} | CURSORS
    for code, ch in CHARS.items():
        if 0x11 <= code < 0x20 or 0x30 <= code < 0x6B:
            a = norom.font_addr(code)
            table.setdefault(bytes(m.mem[a : a + 5]), ch)
    cols = m.columns()
    return "".join(table.get(bytes(cols[i : i + 5]), "?") for i in range(0, len(cols), 5))


@dataclass
class Look:
    """ある時点の様子"""

    lcd: str
    symbols: str
    program: bytes  # プログラムの領域(先頭のFFから終わりのFFまで)
    variables: bytes  # 配列の下端から固定の変数Aまで
    # C6E3h・C6FChの番地(PC-1261系とPC-1350は、プログラムの終わり、配列の下端、いまのプログラムの頭)
    pointers: bytes


def _word(m, a: int) -> int:
    return m.mem[a] | m.mem[a + 1] << 8


def lcd_pc1261(m) -> str:
    """PC-1261系(2行の液晶)の字。ROMのある本体はROMの字の形の表で、ROMなしの本体はエミュレータが
    描いた字の形で読む。行の終わりに改行を入れる"""
    from sc61box import lcdtext
    from sc61box.basic.pc1261 import screen

    if getattr(m, "basic", None) is None:
        table = lcdtext._table(m.mem)
    else:
        codes = [*range(0x21, 0x7F), *range(0xA1, 0xE0)]
        table = {screen.glyph(c): screen.char(c) for c in reversed(codes)} | {bytes(5): " "}
    table = table | CURSORS
    cols = m.columns()
    text = "".join(table.get(bytes(cols[i : i + 5]), "?") for i in range(0, len(cols), 5))
    w = m.model.cells
    return "\n".join(text[i : i + w] for i in range(0, len(text), w))


def look_pc1261(m) -> Look:
    """PC-1261系の本体の様子"""
    from sc61box.basic.pc1261 import program, variables

    v = variables.PC1261
    start = m.model.prog_start  # MERGEで分けたプログラムも含めて見る
    end = _word(m, m.model.prog_end_ptr)
    bottom = _word(m, v.ARRAY_PTR)
    return Look(
        lcd_pc1261(m),
        " ".join(sorted(m.symbols())),
        bytes(m.mem[start : end + 1]) if start <= end < v.ARRAY_TOP else b"",
        bytes(m.mem[bottom : v.FIXED_TOP]) if start <= bottom <= v.FIXED_TOP else b"",
        bytes(m.mem[m.model.prog_end_ptr : m.model.prog_end_ptr + 2])
        + bytes(m.mem[v.ARRAY_PTR : v.ARRAY_PTR + 2])
        + bytes(m.mem[program.PC1261.START_PTR : program.PC1261.START_PTR + 2])
        + b"".join(bytes(m.mem[a : a + 2]) for a in v.BASE_PTRS),
    )


def lcd_1350(m) -> str:
    """PC-1350の液晶の字(4行×25字。1字は6列で、5列ぶんを形として読む)。ROMのある本体は
    ROMの字の形の表で、ROMなしの本体はエミュレータが描いた字の形で読む"""
    from sc61box import lcdtext
    from sc61box.basic.pc1261 import console, screen

    if getattr(m, "basic", None) is None:
        table = lcdtext._table(m.mem)
    else:
        codes = [*range(0x21, 0x7F), *range(0xA1, 0xE0), *console.CHARS]
        chars = {c: console.CHARS.get(c) or screen.char(c) for c in codes}
        table = {console.glyph(c): chars[c] for c in reversed(codes)} | {bytes(5): " "}
    table = table | CURSORS
    cols = m.columns()
    rows = []
    for band in range(4):
        row = cols[band * 150 : (band + 1) * 150]
        rows.append("".join(table.get(bytes(row[i : i + 5]), "?") for i in range(0, 150, 6)))
    return "\n".join(rows)


def look_1350(m) -> Look:
    """PC-1350の本体の様子。ポインタは6F00hからの9バイトと、RAMの頭+6のコピー"""
    from sc61box.basic.pc1261 import variables

    v = variables.PC1350
    start = m.model.prog_start
    end = _word(m, m.model.prog_end_ptr)
    bottom = _word(m, v.ARRAY_PTR)
    head = m.model.ram[0] + 6
    return Look(
        lcd_1350(m),
        " ".join(sorted(m.symbols())),
        bytes(m.mem[start : end + 1]) if start <= end < v.ARRAY_TOP else b"",
        bytes(m.mem[bottom : v.FIXED_TOP]) if start <= bottom <= v.FIXED_TOP else b"",
        bytes(m.mem[v.POINTERS : v.POINTERS + 9]) + bytes(m.mem[head : head + 9]),
    )


def look(m) -> Look:
    """PC-1251・PC-1245の本体の様子"""
    if m.model.family == "1350":
        return look_1350(m)
    if m.model.lines == 2:
        return look_pc1261(m)
    start = m.program_start()
    end = _word(m, 0xC6E3)
    bottom = _word(m, 0xC6FC)
    return Look(
        lcd(m),
        " ".join(sorted(m.symbols())),
        bytes(m.mem[start : end + 1]) if start <= end < 0xC800 else b"",
        bytes(m.mem[bottom:0xC6A0]) if 0xB800 <= bottom <= 0xC6A0 else b"",
        bytes(m.mem[0xC6E3:0xC6E5]) + bytes(m.mem[0xC6FC:0xC6FE]),
    )


def play(m, steps: Sequence[tuple[str, object]]) -> list[Look]:
    """本体mにstepsを与え、"look"ごとの様子を返す"""
    t = Typer(m)
    out: list[Look] = []
    for action, arg in steps:
        if action == "mode":
            t.add_mode(str(arg))
        elif action == "type":
            t.add_text(str(arg))
        elif action == "keys":
            assert isinstance(arg, list)
            t.add_keys([[k] for k in arg])
        elif action == "wait":
            assert isinstance(arg, (int, float))
            finish(m, t)
            m.run(int(CLOCK * arg))
        elif action == "look":
            finish(m, t)
            m.run(CLOCK // 5)
            out.append(look(m))
        elif action == "brk":  # BRKを0.3秒押す
            finish(m, t)
            m.brk = True
            m.run(CLOCK * 3 // 10)
            m.brk = False
        finish(m, t)
    return out


def _same_but_blink(u: str, v: str) -> bool:
    """字の上のカーソル(#)は点滅するので、片方が#の桁はどの字とも同じとみる。点滅の向きは
    512msのタイマで決まり、タイマの位相は起動のしかたで本体ごとに違う"""
    return len(u) == len(v) and all(a == b or "#" in (a, b) for a, b in zip(u, v, strict=True))


def differences(a: list[Look], b: list[Look]) -> list[str]:
    """2つの様子の列の違いを、読める形の文の列にする(なければ空)"""
    out = []
    for i, (x, y) in enumerate(zip(a, b, strict=True)):
        for name in ("lcd", "symbols", "program", "variables", "pointers"):
            u, v = getattr(x, name), getattr(y, name)
            if name == "lcd" and _same_but_blink(u, v):
                continue
            if u != v:
                if isinstance(u, bytes) and isinstance(v, bytes):
                    u, v = u.hex(" "), v.hex(" ")
                out.append(f"{i}番目の{name}: {u!r} と {v!r}")
    return out

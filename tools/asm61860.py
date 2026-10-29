"""SC61860の小さなアセンブラ。このエミュレータで読める.hexを書き出す

1行に1命令。「ラベル:」「命令 オペランド」「; コメント」が書ける。
オペランドには数(16進は&か0x、または末尾h)、ラベル、EQUで決めた名前、
それらの足し算・引き算、lo()・hi()が使える。

    ORG  &C200          以降の番地
    NAME EQU &C501      名前に値をつける
    IF 式 / ELSE / ENDIF 式が0でないときだけ間の行を使う(「#」の行も対象)
    DB   1,2,3          バイトを並べる
    JRNZ ラベル          JRNZP/JRNZMのどちらかを自動で選ぶ(JR/JRZ/JRC/JRNCも)
    LP   n              P=n(n<64)
    CAL  nnnn           2バイトで0000〜1FFF(内部ROM)を呼ぶ
    PTC  h,nnnn         DTCの件数hと、処理のあとに戻る番地nnnnを決める(4バイト)
    DTC                 Aの値で分ける。後ろに「DB 値,hi(行き先),lo(行き先)」をh行、
                        どれでもないときの行き先「DB hi(行き先),lo(行き先)」を1行置く

出力は「番地 データ ; 命令  コメント」の行を並べた.hex(このエミュレータの
16進ダンプの形式)。-Dで名前に値をつけて渡せる。--rom 1251(または1245)を付けると、
ROMのルーチンの名前(FADD、KEYSCANなど。sc61box/romsyms.py)が使える。

    uv run python tools/asm61860.py vline.asm vline.hex
    uv run python tools/asm61860.py sprite.asm sprite.hex -D MASK=1
    uv run python tools/asm61860.py add.asm add.hex --rom 1251
"""

import os
import re
import sys

import typer

# オペランドの形: "" なし、"n" 1バイト、"nm" 2バイト(上位が先)、"r" 相対
OPS: dict[str, tuple[int, str]] = {}


def _op(code: int, names: str, arg: str = "") -> None:
    for n in names.split():
        OPS[n] = (code, arg)


for _c, _n in [
    (0x00, "LII"), (0x01, "LIJ"), (0x02, "LIA"), (0x03, "LIB"), (0x11, "LIDL"),
    (0x12, "LIP"), (0x13, "LIQ"), (0x4E, "WAIT"), (0x54, "READM"),
    (0x60, "ANIM"), (0x61, "ORIM"), (0x62, "TSIM"), (0x63, "CPIM"),
    (0x64, "ANIA"), (0x65, "ORIA"), (0x66, "TSIA"), (0x67, "CPIA"),
    (0x6B, "TEST"), (0x70, "ADIM"), (0x71, "SBIM"), (0x74, "ADIA"), (0x75, "SBIA"),
    (0xD4, "ANID"), (0xD5, "ORID"), (0xD6, "TSID"),
]:  # fmt: skip
    _op(_c, _n, "n")
for _c, _n in [(0x10, "LIDP"), (0x78, "CALL"), (0x79, "JP"), (0x7C, "JPNZ"),
               (0x7D, "JPNC"), (0x7E, "JPZ"), (0x7F, "JPC")]:  # fmt: skip
    _op(_c, _n, "nm")
for _c, _n in [
    (0x28, "JRNZP"), (0x29, "JRNZM"), (0x2A, "JRNCP"), (0x2B, "JRNCM"),
    (0x2C, "JRP"), (0x2D, "JRM"), (0x38, "JRZP"), (0x39, "JRZM"),
    (0x3A, "JRCP"), (0x3B, "JRCM"), (0x2F, "LOOP"),
]:  # fmt: skip
    _op(_c, _n, "r")
for _c, _n in [
    (0x04, "IX"), (0x05, "DX"), (0x06, "IY"), (0x07, "DY"), (0x08, "MVW"), (0x09, "EXW"),
    (0x0A, "MVB"), (0x0B, "EXB"), (0x0C, "ADN"), (0x0D, "SBN"), (0x0E, "ADW"), (0x0F, "SBW"),
    (0x14, "ADB"), (0x15, "SBB"), (0x18, "MVWD"), (0x19, "EXWD"), (0x1A, "MVBD"),
    (0x1B, "EXBD"), (0x1C, "SRW"), (0x1D, "SLW"), (0x1E, "FILM"), (0x1F, "FILD"),
    (0x20, "LDP"), (0x21, "LDQ"), (0x22, "LDR"), (0x23, "CLRA"), (0x24, "IXL"),
    (0x25, "DXL"), (0x26, "IYS"), (0x27, "DYS"), (0x30, "STP"), (0x31, "STQ"),
    (0x32, "STR"), (0x34, "PUSH"), (0x37, "RTN"), (0x40, "INCI"), (0x41, "DECI"),
    (0x42, "INCA"), (0x43, "DECA"), (0x44, "ADM"), (0x45, "SBM"), (0x46, "ANMA"),
    (0x47, "ORMA"), (0x48, "INCK"), (0x49, "DECK"), (0x4A, "INCM"), (0x4B, "DECM"),
    (0x4C, "INA"), (0x4D, "NOPW"), (0x50, "INCP"), (0x51, "DECP"), (0x52, "STD"),
    (0x53, "MVDM"), (0x55, "MVMD"), (0x57, "LDD"), (0x58, "SWP"), (0x59, "LDM"),
    (0x5A, "SL"), (0x5B, "POP"), (0x5D, "OUTA"), (0x5F, "OUTF"), (0xC0, "INCJ"),
    (0xC1, "DECJ"), (0xC2, "INCB"), (0xC3, "DECB"), (0xC4, "ADCM"), (0xC5, "SBCM"),
    (0xC6, "TSMA"), (0xC7, "CPMA"), (0xC8, "INCL"), (0xC9, "DECL"), (0xCA, "INCN"),
    (0xCB, "DECN"), (0xCC, "INB"), (0xCE, "NOPT"), (0xD0, "SC"), (0xD1, "RC"),
    (0xD2, "SR"), (0xD8, "LEAVE"), (0xDA, "EXAB"), (0xDB, "EXAM"), (0xDD, "OUTB"),
    (0xDF, "OUTC"),
]:  # fmt: skip
    _op(_c, _n)

# 向きを自動で選ぶ相対ジャンプ: (前へ, 後ろへ)
AUTO = {"JR": ("JRP", "JRM"), "JRZ": ("JRZP", "JRZM"), "JRNZ": ("JRNZP", "JRNZM"),
        "JRC": ("JRCP", "JRCM"), "JRNC": ("JRNCP", "JRNCM")}  # fmt: skip


class AsmError(Exception):
    pass


def _num(tok: str) -> str:
    tok = tok.strip()
    if tok.startswith("&"):
        return "0x" + tok[1:]
    if re.fullmatch(r"[0-9][0-9A-Fa-f]*[hH]", tok):
        return "0x" + tok[:-1]
    return tok


def evaluate(expr: str, syms: dict[str, int]) -> int:
    expr = re.sub(r"&[0-9A-Fa-f]+|\b[0-9][0-9A-Fa-f]*[hH]\b", lambda m: _num(m.group()), expr)
    env = {"lo": lambda v: v & 0xFF, "hi": lambda v: (v >> 8) & 0xFF, **syms}
    try:
        return int(eval(expr, {"__builtins__": {}}, env))  # noqa: S307 (読むのは利用者が書いたソースだけ)
    except Exception as e:  # noqa: BLE001
        raise AsmError(f"式を計算できない: {expr} ({e})") from e


def parse(src: str) -> list[tuple[int, str, str, str, str]]:
    """(行番号, ラベル, 命令, オペランド, コメント)の列"""
    out = []
    for n, raw in enumerate(src.splitlines(), 1):
        code, _, com = raw.partition(";")
        label = ""
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*):", code)
        if m:
            label = m.group(1)
            code = code[m.end() :]
        parts = code.split(None, 1)
        mnem = parts[0].upper() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""
        if len(parts) > 1 and parts[1].split(None, 1)[0].upper() == "EQU":
            label, mnem, arg = parts[0], "EQU", parts[1].split(None, 1)[1]
        out.append((n, label, mnem, arg, com.strip()))
    return out


def select(src: str, defines: dict[str, int]) -> str:
    """IF〜ELSE〜ENDIFで使わない行を空にする(行番号は変えない)。IFの式には-Dの名前と、
    それより前のEQUの値が使える"""
    syms = dict(defines)
    out: list[str] = []
    stack: list[tuple[bool, bool]] = []  # (外側が有効か, 条件)
    active = True
    for n, raw in enumerate(src.splitlines(), 1):
        code = raw.split(";", 1)[0].strip()
        m = re.fullmatch(r"(IF|ELSE|ENDIF)\b\s*(.*)", code, re.IGNORECASE)
        if m:
            kw = m.group(1).upper()
            try:
                if kw == "IF":
                    cond = active and bool(evaluate(m.group(2), syms))
                    stack.append((active, cond))
                    active = cond
                elif kw == "ELSE":
                    outer, cond = stack[-1]
                    active = outer and not cond
                else:
                    active = stack.pop()[0]
            except IndexError as e:
                raise AsmError(f"{n}行目: IFがない{kw}") from e
            except AsmError as e:
                raise AsmError(f"{n}行目: {e}") from e
            out.append("")
            continue
        if not active:
            out.append("")
            continue
        eq = re.fullmatch(r"([A-Za-z_]\w*)\s+EQU\s+(.*)", code, re.IGNORECASE)
        if eq:
            try:
                syms[eq.group(1)] = evaluate(eq.group(2), syms)
            except AsmError:
                pass  # ラベルを使う式は、あとのassembleで計算する
        out.append(raw)
    if stack:
        raise AsmError("ENDIFが足りない")
    return "\n".join(out)


def size_of(mnem: str, arg: str) -> int:
    if mnem in ("", "EQU", "ORG"):
        return 0
    if mnem == "DB":
        return len([a for a in arg.split(",") if a.strip()])
    if mnem == "LP" or mnem in AUTO:
        return 1 if mnem == "LP" else 2
    if mnem == "CAL":
        return 2
    if mnem == "PTC":
        return 4
    if mnem == "DTC":
        return 1
    if mnem not in OPS:
        raise AsmError(f"知らない命令: {mnem}")
    return {"": 1, "n": 2, "nm": 3, "r": 2}[OPS[mnem][1]]


def check_page(arg: str, syms: dict[str, int], tables: dict[str, int]) -> None:
    """lo(表-1)に添字(1から)を足して引く書き方では、表-1から表の最後までが
    同じ256バイトの中にないと、繰り上がりが上位バイトに伝わらずに違う番地を読む"""
    m = re.fullmatch(r"lo\((\w+)-1\)", arg.replace(" ", ""))
    if not m or m.group(1) not in tables:
        return
    start = syms[m.group(1)] - 1
    end = start + tables[m.group(1)]
    if start >> 8 != end >> 8:
        raise AsmError(f"表{m.group(1)}({start + 1:04X}〜{end:04X})の前後が256バイトの境目をまたぐ")


def assemble(src: str, defines: dict[str, int] | None = None) -> list[tuple[int, bytes, str, str]]:
    """(番地, バイト, 命令の文字列, コメント)の列"""
    lines = parse(src)
    syms: dict[str, int] = dict(defines or {})
    # 1回目: 番地を決める。DBの表は、ラベルから次の命令までの長さも覚えておく
    pc = 0
    tables: dict[str, int] = {}
    table = None
    for n, label, mnem, arg, _ in lines:
        try:
            if mnem == "EQU":
                syms[label] = evaluate(arg, syms)
                continue
            if label:
                syms[label] = pc
            if mnem == "ORG":
                pc = evaluate(arg, syms)
                table = None
                continue
            if mnem == "DB":
                if label:
                    table = label
                    tables[table] = 0
                if table:
                    tables[table] += size_of(mnem, arg)
            elif mnem or label:
                table = None
            pc += size_of(mnem, arg)
        except AsmError as e:
            raise AsmError(f"{n}行目: {e}") from e
    # 2回目: バイトにする
    out = []
    pc = 0
    for n, label, mnem, arg, com in lines:
        try:
            if mnem == "EQU":
                continue
            if mnem == "ORG":
                pc = evaluate(arg, syms)
                continue
            if not mnem:
                if com and not label:
                    out.append((-1, b"", "", com))
                continue
            text = f"{mnem} {arg}".strip()
            if mnem == "DB":
                data = bytes(evaluate(a, syms) & 0xFF for a in arg.split(",") if a.strip())
                text = ""
            elif mnem == "LP":
                v = evaluate(arg, syms)
                if not 0 <= v < 64:
                    raise AsmError(f"LPは0〜3Fまで: {v:X}")
                data = bytes([0x80 | v])
                text = f"LP {v:02X}"
            elif mnem == "CAL":  # 2バイトで0000〜1FFFを呼ぶ(E0+上位5ビット、下位)
                v = evaluate(arg, syms)
                if not 0 <= v < 0x2000:
                    raise AsmError(f"CALで呼べるのは0000〜1FFFまで: {v:X}")
                data = bytes([0xE0 | v >> 8, v & 0xFF])
                text = f"CAL {v:04X}" + (f"  ({arg})" if not arg.startswith("&") else "")
            elif mnem == "PTC":  # 7A h n m
                h, _, a = arg.partition(",")
                hv, av = evaluate(h, syms), evaluate(a, syms)
                if not 0 <= hv <= 255:
                    raise AsmError(f"PTCの件数は0〜255: {hv}")
                data = bytes([0x7A, hv, av >> 8 & 0xFF, av & 0xFF])
                text = f"PTC {hv:02X},{av:04X}"
                if not a.strip().startswith("&"):
                    text += f"  ({a.strip()})"
            elif mnem == "DTC":
                data = bytes([0x69])
                text = "DTC"
            else:
                if mnem in AUTO:
                    t = evaluate(arg, syms)
                    mnem = AUTO[mnem][0] if t > pc + 1 else AUTO[mnem][1]
                    text = f"{mnem} {arg}"
                code, kind = OPS[mnem]
                if kind == "":
                    data = bytes([code])
                elif kind == "n":
                    v = evaluate(arg, syms)
                    check_page(arg, syms, tables)
                    if not -128 <= v <= 255:
                        raise AsmError(f"1バイトに入らない: {v}")
                    data = bytes([code, v & 0xFF])
                    if not re.fullmatch(r"&?[0-9A-Fa-f]+h?", arg):
                        text = f"{mnem} {v & 0xFF:02X}  ({arg})"
                    else:
                        text = f"{mnem} {v & 0xFF:02X}"
                elif kind == "nm":
                    v = evaluate(arg, syms)
                    data = bytes([code, v >> 8 & 0xFF, v & 0xFF])
                    text = f"{mnem} {v:04X}" + (f"  ({arg})" if not arg.startswith("&") else "")
                else:  # 相対。基点はオフセットのバイトの番地
                    t = evaluate(arg, syms)
                    d = t - (pc + 1)
                    if mnem.endswith("M") or mnem == "LOOP":
                        d = -d
                    if not 0 <= d <= 255:
                        raise AsmError(f"{mnem}で{arg}に届かない(差{d})")
                    data = bytes([code, d])
            if label:
                com = f"{label}: {com}".strip()
            out.append((pc, data, text, com))
            pc += len(data)
        except AsmError as e:
            raise AsmError(f"{n}行目: {e}") from e
    return out


def to_hex(rows: list[tuple[int, bytes, str, str]], header: str = "") -> str:
    lines = [header.rstrip()] if header else []
    for addr, data, text, com in rows:
        if addr < 0:
            lines.append(f"; {com}")
            continue
        if not text:  # DB は12バイトずつ
            for i in range(0, len(data), 12):
                chunk = data[i : i + 12]
                c = f"  ; {com}" if com and i == 0 else ""
                lines.append(f"{addr + i:04X} " + " ".join(f"{b:02X}" for b in chunk) + c)
            continue
        hexs = " ".join(f"{b:02X}" for b in data)
        tail = f"{text:<18} {com}".rstrip()
        lines.append(f"{addr:04X} {hexs:<9} ; {tail}")
    return "\n".join(lines) + "\n"


def build(src: str, defines: dict[str, int]) -> tuple[list[tuple[int, bytes, str, str]], str]:
    """ソースの文字列を組んで、行の列と.hexの中身を返す。「#」の行は.hexの頭に写す"""
    text = select(src, defines)
    header = "\n".join(ln for ln in text.splitlines() if ln.startswith("#")) + "\n"
    body = "\n".join("" if ln.startswith("#") else ln for ln in text.splitlines())
    rows = assemble(body, defines)
    return rows, to_hex(rows, header)


def main(
    src: str,
    out: str,
    define: list[str] = typer.Option([], "-D", help="NAME=値。IFやEQUの式で使える"),
    rom: str | None = typer.Option(
        None, help="ROMのルーチンの名前を使う機種(1251か1245)。FADD、KEYSCANなど"
    ),
) -> None:
    defines = {}
    if rom:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        from sc61box.romsyms import symbols

        try:
            defines.update(symbols(rom))
        except ValueError as e:
            sys.exit(str(e))
    for d in define:
        name, _, value = d.partition("=")
        defines[name.strip()] = evaluate(value or "1", {})
    try:
        rows, hextext = build(open(src, encoding="utf-8").read(), defines)
    except AsmError as e:
        sys.exit(str(e))
    open(out, "w", encoding="utf-8").write(hextext)
    last = max(a + len(d) for a, d, _, _ in rows if a >= 0)
    first = min(a for a, _, _, _ in rows if a >= 0)
    print(f"{out}: {first:04X}-{last - 1:04X} ({last - first}バイト)")


if __name__ == "__main__":
    typer.run(main)

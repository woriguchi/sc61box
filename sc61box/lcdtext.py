"""液晶RAMを文字に読み戻す(テストと確認用)

液晶の5列ずつを、BASIC ROMの文字の形と照らし合わせる。

* PC-1251・PC-1245: 4504h(数字)からの数字と英字の形。
* PC-1261など: 20hからの文字コードの順に1字5バイト(空白が8045h)。左右が逆に並ぶ。
* PC-1350: 同じ形の表が808Ah(空白)から。7Fhの次がA0hで、80h〜9Fhはない。液晶は
  桁に分かれていないので、6列ずつを1字として読む(4行×25字)。

2行以上の液晶では、行の終わりに改行を入れる。
"""

_A = bytes.fromhex("7c1211127c")  # 「A」の形


def _table_s1(
    mem, base: int, ascii_end: int, ascii_off: int, kana_off: int, pi_sqrt: tuple[int, int]
) -> dict[bytes, str]:
    """S1系(PC-1261など、PC-1350)の文字の形の表。文字コードcの形は、英数字と記号なら
    base+5*(c-ascii_off)、半角カナ(A1h〜DFh)ならbase+5*(c-kana_off)にある。pi_sqrtは
    π・√の形の番目"""
    t = {bytes(5): " "}

    def glyph(index: int) -> bytes:
        return bytes(reversed(mem[base + 5 * index : base + 5 * index + 5]))

    for code in range(0x21, ascii_end):
        t.setdefault(glyph(code - ascii_off), "¥" if code == 0x5C else chr(code))
    for code in range(0xA1, 0xE0):
        t.setdefault(glyph(code - kana_off), bytes([code]).decode("cp932"))
    t.setdefault(glyph(pi_sqrt[0]), "π")
    t.setdefault(glyph(pi_sqrt[1]), "√")
    return t


def _table(mem) -> dict[bytes, str]:
    if mem[0x812F : 0x812F + 5] == _A:  # PC-1350のROM
        return _table_s1(mem, 0x808A, 0x80, 0x20, 0x40, (0xAB, 0xAC))
    if mem[0x80EA : 0x80EA + 5] == _A:  # PC-1261などのROM
        return _table_s1(mem, 0x7FA5, 0x7C, 0, 0x25, (0xC6, 0xC7))
    t = {bytes(5): " "}
    base = 0x43C4
    for code in range(0x40, 0x4A):
        t[bytes(mem[base + 5 * code : base + 5 * code + 5])] = chr(ord("0") + code - 0x40)
    for code in range(0x51, 0x6B):
        t[bytes(mem[base + 5 * code : base + 5 * code + 5])] = chr(ord("A") + code - 0x51)
    return t


def lcd_text(machine, unknown: str = "?") -> str:
    t = getattr(machine, "_glyphs", None)
    if t is None:
        t = machine._glyphs = _table(machine.mem)
    cols = machine.columns()
    if machine.model.family == "1350":
        rows = []
        for band in range(4):
            row = cols[band * 150 : (band + 1) * 150]
            rows.append("".join(t.get(bytes(row[i : i + 5]), unknown) for i in range(0, 150, 6)))
        return "\n".join(rows)
    text = "".join(t.get(bytes(cols[i : i + 5]), unknown) for i in range(0, len(cols), 5))
    lines = machine.model.lines
    if lines > 1:
        n = len(text) // lines
        text = "\n".join(text[i * n : (i + 1) * n] for i in range(lines))
    return text

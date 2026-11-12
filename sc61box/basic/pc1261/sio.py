"""PC-1350のシリアル入出力: OPEN・CLOSE・CONSOLE・OPEN$と、SAVE・LOAD(観察)

エミュレータにはシリアルの相手がないので、ROMのある本体に何もつないでいないときと同じに
ふるまう。

- 設定は78B1h〜78B3hに置く。78B1hは終わりの字、78B2hは通信速度(300が01h、600が02h、
  1200が04h)、78B3hはビット7がデータ8ビット、ビット6・5がパリティ(Nが00b、Oが10b、Eが11b)、
  ビット4がストップ2ビット、ビット2〜0がフロー制御(Cが100b、Lが010b、Fが001b)。初期値は
  「1200,N,8,1,A,C,&1A」(1Ah、04h、84h)。OPENで書いた字は、文字列の作業場所(6E60h〜)に
  置いたあとにFFhを書く
- OPENしているかのフラグは78B0hのビット7。CONSOLEの字数は78B4h・78B5h(どちらも同じ値。
  初期値は40)
- 電源を入れると、シリアルを閉じて、設定とCONSOLEの字数を初期値に戻す
- RUNと、プログラムの終わり(ENDか最後の行のあと)でも閉じる(設定はそのまま)
- OPENしているあいだのSAVE・LOAD・LPRINT・LLISTは、相手を待ったまま止まる。BRKで止めると、
  打った行なら>に戻り、プログラムの中なら「BREAK IN 行番号」で止まる
- 閉じているあいだのSAVE・LOADは何もしない
"""

from ..errors import BasicError

SETTINGS = 0x78B1  # 終わりの字、通信速度、そのほかのビット
DEFAULT = bytes([0x1A, 0x04, 0x84])
BAUD = {b"300": 0x01, b"600": 0x02, b"1200": 0x04}
PARITY = {b"N": 0x00, b"O": 0x40, b"E": 0x60}
FLOW = {b"C": 0x04, b"L": 0x02, b"F": 0x01}
OPEN_FLAG = (0x78B0, 0x80)
CONSOLE_WIDTH = (0x78B4, 0x78B5)
CONSOLE_DEFAULT = 40
CONSOLE_MAX = 160  # CONSOLEで160より大きい字数は160にする(観察)
# OPENの字の7つの項目に書けるもの(観察: 通信速度は300・600・1200だけで、7つ目の16進表記は
# 大文字の2桁)
CHOICES = (
    (b"300", b"600", b"1200"),
    (b"N", b"E", b"O"),
    (b"7", b"8"),
    (b"1", b"2"),
    (b"A",),
    (b"C", b"F", b"L"),
)
HEX = b"0123456789ABCDEF"


def _name(table: dict[bytes, int], v: int) -> bytes:
    return next((k for k, bits in table.items() if bits == v), next(iter(table)))


def settings(m) -> bytes:
    """OPEN$の字"""
    end, baud, bits = m.mem[SETTINGS : SETTINGS + 3]
    return b",".join([
        _name(BAUD, baud), _name(PARITY, bits & 0x60), b"8" if bits & 0x80 else b"7",
        b"2" if bits & 0x10 else b"1", b"A", _name(FLOW, bits & 0x07), b"&%02X" % end,
    ])  # fmt: skip


def _store(m, text: bytes) -> None:
    """OPEN$の字の形の設定を、78B1h〜78B3hに置く"""
    baud, parity, data, stop, _, flow, end = text.split(b",")
    bits = (
        PARITY[parity] | FLOW[flow] | (0x80 if data == b"8" else 0) | (0x10 if stop == b"2" else 0)
    )
    m.mem[SETTINGS : SETTINGS + 3] = bytes([int(end[1:], 16), BAUD[baud], bits])


def is_open(m) -> bool:
    a, bit = OPEN_FLAG
    return bool(m.mem[a] & bit)


def set_open(m, on: bool) -> None:
    a, bit = OPEN_FLAG
    m.mem[a] = m.mem[a] | bit if on else m.mem[a] & ~bit


def power_on(m) -> None:
    set_open(m, False)
    m.mem[SETTINGS : SETTINGS + 3] = DEFAULT
    for a in CONSOLE_WIDTH:
        m.mem[a] = CONSOLE_DEFAULT


def changed(current: bytes, text: bytes) -> bytes:
    """OPEN "text"で変えたあとの設定。空の項目はいまのまま。書けないものはERROR 1"""
    fields = current.split(b",")
    given = text.split(b",")
    if not text or len(given) > len(fields):
        raise BasicError(1)
    for i, value in enumerate(given):
        if not value:
            continue
        if i < len(CHOICES):
            ok = value in CHOICES[i]
        else:
            ok = len(value) == 3 and value[:1] == b"&" and all(c in HEX for c in value[1:])
        if not ok:
            raise BasicError(1)
        fields[i] = value
    return b",".join(fields)


def open_port(m, text: bytes | None) -> None:
    """OPEN ["設定"]。開いていればERROR 8"""
    if is_open(m):
        raise BasicError(8)
    if text is not None:
        _store(m, changed(settings(m), text))
        at = getattr(text, "at", None)  # 文字列の作業場所に置いた字のあと
        if at is not None:
            m.mem[at + len(text)] = 0xFF
    set_open(m, True)


def console(m, n: int | None) -> None:
    """CONSOLE [字数]。1より小さければERROR 3"""
    if n is None:
        return
    if n < 1:
        raise BasicError(3)
    for a in CONSOLE_WIDTH:
        m.mem[a] = min(n, CONSOLE_MAX)

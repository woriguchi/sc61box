"""PC-1350のシリアル入出力: OPEN・CLOSE・CONSOLE・OPEN$と、SAVE・LOAD(観察)

エミュレータにはシリアルの相手がないので、ROMのある本体に何もつないでいないときと同じに
ふるまう。

- 設定はOPEN$の字のまま6E60hから置き、FFhで終える。6E60hが00hなら初期値
  「1200,N,8,1,A,C,&1A」(ROMのある本体は、OPENで書いた字をここに置き、設定はほかの所に
  持つ。どちらも電源を入れると初期値に戻るので、ここは同じにしていない)
- OPENしているかのフラグは78B0hのビット7。CONSOLEの字数は78B4h・78B5h(どちらも同じ値。
  初期値は40)
- 電源を入れると、シリアルを閉じて、設定とCONSOLEの字数を初期値に戻す
- RUNと、プログラムの終わり(ENDか最後の行のあと)でも閉じる(設定はそのまま)
- OPENしているあいだのSAVE・LOAD・LPRINT・LLISTは、相手を待ったまま止まる。BRKで止めると、
  打った行なら>に戻り、プログラムの中なら「BREAK IN 行番号」で止まる
- 閉じているあいだのSAVE・LOADは何もしない
"""

from ..errors import BasicError

SETTINGS = 0x6E60
DEFAULT = b"1200,N,8,1,A,C,&1A"
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


def settings(m) -> bytes:
    """OPEN$の字"""
    if m.mem[SETTINGS] == 0:
        return DEFAULT
    end = bytes(m.mem[SETTINGS : SETTINGS + 32]).find(b"\xff")
    return bytes(m.mem[SETTINGS : SETTINGS + (end if end >= 0 else 0)]) or DEFAULT


def is_open(m) -> bool:
    a, bit = OPEN_FLAG
    return bool(m.mem[a] & bit)


def set_open(m, on: bool) -> None:
    a, bit = OPEN_FLAG
    m.mem[a] = m.mem[a] | bit if on else m.mem[a] & ~bit


def power_on(m) -> None:
    set_open(m, False)
    m.mem[SETTINGS] = 0
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
        new = changed(settings(m), text)
        m.mem[SETTINGS : SETTINGS + len(new) + 1] = new + b"\xff"
    set_open(m, True)


def console(m, n: int | None) -> None:
    """CONSOLE [字数]。1より小さければERROR 3"""
    if n is None:
        return
    if n < 1:
        raise BasicError(3)
    for a in CONSOLE_WIDTH:
        m.mem[a] = min(n, CONSOLE_MAX)

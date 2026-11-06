"""PC-1350のTEXTモード: TEXTでプログラムの行を字の並びにし、BASICで中間コードに戻す(観察)

- TEXTは、行の中の命令の中間コードを、綴りのあとに空白を1つ置いた字にする(前には置かない)。
  ほかのバイトはそのまま。77バイトを越える行は77バイトで切る
- BASICは、行の字の並びを、打った行と同じに中間コードにする
- TEXTモードかどうかのフラグは6F16hのビット6(RAMの頭のコピーにも置く)。電源を入れると
  BASICモードに戻る(プログラムは字の並びのまま)
- TEXTモードでは、PROモードで打った行番号のある行を、中間コードにせずに打ったとおりに
  登録し(行番号のあとの空白も残す)、行番号のあとに「:」を置かずに出す。>の代わりに<を出す
"""

from ..editor import WIDE
from . import editor

FLAG = (0x6F16, 0x40)
MAX_BODY = 77  # TEXTで字にした行の中身の長さの上限(観察)


def spelled(body: bytes, keywords: dict[int, str]) -> bytes:
    """行の中身の命令を綴りにする(TEXT)"""
    out = bytearray()
    for u in editor.units_of(body):
        if u >= WIDE:
            out += bytes([editor.KANA_MARK, u - WIDE])
        elif u in keywords:
            out += keywords[u].encode("ascii") + b" "
        else:
            out.append(u)
    return bytes(out)


def is_on(m) -> bool:
    a, bit = FLAG
    return bool(m.mem[a] & bit)


def set_on(m, vars_, on: bool) -> None:
    """TEXTモードのフラグを、RAMの頭のコピーにも書く"""
    a, bit = FLAG
    for at in (a, vars_.copy_of(m, a)):
        if at is not None:
            m.mem[at] = m.mem[at] | bit if on else m.mem[at] & ~bit

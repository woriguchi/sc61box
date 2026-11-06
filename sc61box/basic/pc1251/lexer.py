"""PC-1251系の打った行(本体の文字コードの並び)を中間コードの並びにする"""

from ...basictext import CHARS
from .. import lexer

_CODES = {ch: code for code, ch in CHARS.items() if len(ch) == 1}


def spelling(word: str) -> bytes:
    """綴りを本体の文字コードの並びにする"""
    return bytes(_CODES[ch] for ch in word)


class Lexer(lexer.Lexer):
    QUOTE, SPACE, DOT, REM = 0x12, 0x11, 0x4A, 0xD3
    LETTERS = (0x51, 0x6A)
    REM_DROPS_SPACE = True  # 観察

    @staticmethod
    def spell(word: str) -> bytes:
        return spelling(word)

"""PC-1261系とPC-1350の打った行(ASCII)を中間コードの並びにする。字のコードのほかはPC-1251系と同じ"""

from .. import lexer


class Lexer(lexer.Lexer):
    QUOTE, SPACE, DOT, REM = 0x22, 0x20, 0x2E, 0xD7
    LETTERS = (0x41, 0x5A)
    REM_DROPS_SPACE = False  # REMのあとの空白も残す(観察)

    @staticmethod
    def spell(word: str) -> bytes:
        return word.encode("ascii")

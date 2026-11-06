"""PC-1251系のキー。字は本体の文字コード"""

from ... import keytype
from ...basictext import CHARS
from .. import keyboard
from . import reserve

# 字(指数のEは"€")から本体の文字コードへ
CODES = {ch: code for code, ch in CHARS.items() if len(ch) == 1} | {keytype.EXP: 0x4B, "'": 0x10}


class Keyboard(keyboard.Keyboard):
    CODES = CODES
    RESERVE_KEYS = frozenset(reserve.MARKS)

    def __init__(self, m) -> None:
        super().__init__(m)
        table = keytype.SHIFTED_1245 if m.model.name == "1245" else keytype.SHIFTED
        self.shifted = {key: ch for ch, key in table.items()}

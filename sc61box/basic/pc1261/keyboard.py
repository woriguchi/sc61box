"""PC-1261系とPC-1350のキー。PC-1261系のキーの並びはPC-1245と同じで、字はASCIIとカナ。
PC-1261系はSHIFTのあと8でカナの入力を切り替え、KANAの記号を点ける(観察)"""

from collections.abc import Callable

from ... import keytype
from ...machine import KEYS_1350, SYMBOLS_1350
from .. import keyboard
from ..editor import WIDE
from . import reserve

KANA = {bytes([c]).decode("cp932"): c for c in range(0xA1, 0xE0)}
# 字から文字コードへ(カナは単位の番号: editor.WIDE+字のコード)
CODES = {chr(c): c for c in range(0x20, 0x7F)} | {"¥": 0x5C}
CODES |= {ch: WIDE + c for ch, c in KANA.items()}
# PC-1350にはπ(FBh)と√(FCh)の字もある。RAMでは1バイト(SHIFTのあとI・O。観察)
CODES_1350 = CODES | {"π": 0xFB, "√": 0xFC}
# カナの入力のときに、キーだけで打つ字と、SHIFTのあとに打つ字
_PLAIN = {keys[0][0]: ch for ch, keys in keytype.KANA_1261.items() if len(keys) == 1}
_SHIFTED = {keys[1][0]: ch for ch, keys in keytype.KANA_1261.items() if len(keys) == 2}


class Keyboard(keyboard.Keyboard):
    CODES = CODES
    RESERVE_KEYS = frozenset(reserve.MARKS)

    def __init__(self, m) -> None:
        super().__init__(m)
        self.ascii_shifted = {key: ch for ch, key in keytype.SHIFTED_1261.items()}
        # カナの入力かは、KANAの記号で覚えている(電源を入れ直しても、状態を戻しても続く。観察)
        a, bit = m.model.symbols["KANA"]
        self.set_kana(bool(m.mem[a] & bit))

    def set_kana(self, on: bool) -> None:
        self.kana = on  # カナの入力
        self.shifted = _SHIFTED if on else self.ascii_shifted
        a, bit = self.m.model.symbols["KANA"]
        self.m.mem[a] = self.m.mem[a] | bit if on else self.m.mem[a] & ~bit
        self.m.lcd_dirty = True

    def poll(self) -> str | None:
        k = super().poll()
        if k == "8" and self.was_shifted:
            self.set_kana(not self.kana)
            return "KANA"
        if self.kana and not self.was_shifted and k in _PLAIN:
            return _PLAIN[k]
        return k


_PLAIN_1350 = {keys[0][0]: ch for ch, keys in keytype.KANA_1350.items() if len(keys) == 1}
_SHIFTED_1350 = {keys[1][0]: ch for ch, keys in keytype.KANA_1350.items() if len(keys) == 2}


class Keyboard1350(keyboard.Keyboard):
    """PC-1350のキー。SHIFTで打つ記号はQ〜Pの上と数字の側。KANAのキーでカナの入力に、
    SHIFTのあとKANAのキーで英小文字の入力(SML)に切り替える。海外向けの本体では、KANAの
    キーはどちらでも英小文字の入力を切り替える。どちらの入力かは記号で覚える。右上の
    SHIFTも左下のSHIFTと同じ(観察)"""

    CODES = CODES_1350
    EXTRA_KEYS = frozenset(["MODE", "CLS", "KANA", "INS", "DEL"])

    def __init__(self, m) -> None:
        super().__init__(m)
        self.ascii_shifted: dict[str, str] = {key: ch for ch, key in keytype.SHIFTED_1350.items()}
        self.shifted = self.ascii_shifted
        self.clear_screen: Callable[[], None] | None = None  # CLSのキーで液晶を消す関数
        self.toggle_mode: Callable[[], None] | None = None  # MODEのキーでRUN・PROを切り替える関数
        self.kana = self._lit("KANA")
        self.small = self._lit("SML")
        self.shifted = _SHIFTED_1350 if self.kana else self.ascii_shifted

    def _lit(self, name: str) -> bool:
        a, bit = SYMBOLS_1350[name]
        return bool(self.m.mem[a] & bit)

    def _light(self, name: str, on: bool) -> None:
        a, bit = SYMBOLS_1350[name]
        self.m.mem[a] = self.m.mem[a] | bit if on else self.m.mem[a] & ~bit
        self.m.lcd_dirty = True

    def _held(self) -> set[str]:
        """本体にあるキーだけ。右上のSHIFTはSHIFTにする"""
        return {"SHIFT" if k == "SHIFT2" else k for k in self.m.held if k in KEYS_1350}

    def poll(self) -> str | None:
        k = super().poll()
        if k == "CLS":  # 液晶を消し、ほかの機種のCLと同じに扱う(観察)
            if self.clear_screen is not None:
                self.clear_screen()
            return "CL"
        if k == "MODE" and self.toggle_mode is not None:
            self.toggle_mode()  # キーを待っているどこでも(PRINT・INPUTの待ちでも)効く(観察)
        if k == "KANA":
            if self.was_shifted or self.m.overseas:
                self.small, self.kana = not self.small, False
            else:
                self.kana, self.small = not self.kana, False
            self.shifted = _SHIFTED_1350 if self.kana else self.ascii_shifted
            self._light("KANA", self.kana)
            self._light("SML", self.small)
            return "KANA"
        if self.kana and not self.was_shifted and k in _PLAIN_1350:
            return _PLAIN_1350[k]
        if self.small and not self.was_shifted and k is not None and len(k) == 1 and k.isalpha():
            return k.lower()
        return k

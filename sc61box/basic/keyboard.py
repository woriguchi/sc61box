"""本体のキーを読み、押されたキーを1つずつ字か操作にする(系統によらない部分)"""

from . import dialect

CONTROLS = ("ENTER", "CL", "LEFT", "RIGHT", "UP", "DOWN", "DEF")
SHIFT_EDIT = {"LEFT": "DEL", "RIGHT": "INS"}  # SHIFTのあとの←・→(観察)
# 押し続けると繰り返すキー(SHIFTのあとでなく押したとき。字のキーとDEL・INSは繰り返さない。
# 繰り返しの間は機種で違う: dialect.py。観察)
REPEAT_KEYS = ("LEFT", "RIGHT", "UP", "DOWN")


class Keyboard:
    """m.heldを見て、新しく押されたキーを返す。SHIFTは次の1打鍵だけ効く。字の表(CODES)と、
    SHIFTのあとに打つ字(shifted)とリザーブのキー(RESERVE_KEYS)は、系統ごとの子クラスが
    決める"""

    CODES: dict[str, int]  # キーの字から本体の文字コードへ
    RESERVE_KEYS: frozenset[str] = frozenset()  # SHIFTのあとで「RSV:キー」にするキー
    EXTRA_KEYS: frozenset[str] = frozenset()  # 名前のまま返す機種のキー(PC-1350のMODEなど)

    def __init__(self, m) -> None:
        self.m = m
        self.prev: set[str] = set()
        self.pending: list[str] = []  # 押されて、まだ返していないキー
        self.shift = False
        self.repeat: tuple[str, int] | None = None  # 繰り返すキーと、次に繰り返す時刻
        d = dialect.of(m)
        self.repeat_delay, self.repeat_every = d.repeat_delay, d.repeat_every
        self.shifted: dict[str, str] = {}  # SHIFTのあとのキー → 字
        self.was_shifted = False  # 最後に返したキーは、SHIFTのあとに押した

    def poll(self) -> str | None:
        """新しく押されたキーがあれば、その字(CODESにある1字)か操作の名前(CONTROLS、
        SHIFT、DEL、INS、SHIFTのあとのリザーブのキーなら「RSV:キー」)を返す。なければNone"""
        held = self._held()
        now = self.m.cpu.cycles
        new = held - self.prev
        if self.repeat is not None and (new or self.repeat[0] not in held):
            self.repeat = None
        # 同じときに押されたキーは、取りこぼさないように順に返す
        self.pending += sorted(new)
        if self.repeat is not None and now >= self.repeat[1] and not self.pending:
            key, at = self.repeat
            self.repeat = (key, at + self.repeat_every)
            self.prev = held
            return key
        self.prev = held
        while self.pending:
            k = self.pending.pop(0)
            if k == "SHIFT":
                self.shift = not self.shift
                return "SHIFT"
            self.was_shifted = self.shift
            if self.shift:
                self.shift = False
                if k in SHIFT_EDIT:
                    return SHIFT_EDIT[k]
                ch = self.shifted.get(k)
                if ch is not None:
                    return ch
                if k in self.RESERVE_KEYS:
                    return "RSV:" + k
            if k == "SPC":
                return " "
            if k in REPEAT_KEYS:
                self.repeat = (k, now + self.repeat_delay)
            if k in CONTROLS or k in self.CODES or k in self.EXTRA_KEYS:
                return k
        return None

    def _held(self) -> set[str]:
        """押されているキーの名前"""
        return set(self.m.held)

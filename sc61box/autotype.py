"""キー操作を順に打つ(ファイルや貼り付けの打ち込み、パソコンのキーボード)"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeGuard

from .keytype import keys_for, keys_for_program
from .machine import CLOCK, PC1251


@dataclass(frozen=True, eq=False)
class Call:
    """キューの要素: 前の打鍵が終わったところで呼ぶ関数"""

    fn: Callable[[], object]


@dataclass(frozen=True, eq=False)
class Write:
    """キューの要素: 前の打鍵が終わったところでRAMに書くダンプ(番地とバイトの組)"""

    blocks: list[tuple[int, bytes]]


Entry = list[str] | Call | Write  # キューの要素


def _lf(text: str) -> str:
    """改行をLFにそろえる"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


class Typer:
    """キー操作のキューを、決まった時間ずつ押して順に届ける。時間はエミュレータのサイクルで数える。

    キューの要素は同時に押すキーの名前のリストで、@で始まる次の指示も入る。
    "@MODE:PRO"(スイッチを動かす)、"@IDLE"(ROMが入力待ちに戻るまで待つ)。前の打鍵が
    終わったところで関数を呼ぶ、ダンプを書くものは、関数とダンプをそのまま持つ要素(Call、Write)
    にする(キューから消せば、関数とダンプも残らない)。
    パソコンのキーボードで押されたキーは、ROMが入力を待っているあいだはLIVEのマーカーと
    押した時刻をつけて同じキューに入り、押し続けているあいだは離されるまで押しておく(速く
    打っても取りこぼさないように1つずつ届ける)。プログラムが動いているあいだはキューに入れず、
    押されたときにすぐ押し、離されたときに離す(ゲームの同時押しがそのまま伝わる)。
    """

    DOWN = CLOCK * 70 // 1000
    UP = CLOCK * 60 // 1000
    AFTER_ENTER = CLOCK * 450 // 1000
    MODE_WAIT = CLOCK * 300 // 1000  # スイッチを動かしたあとROMが気づくまで
    # 液晶にモードの記号がある機種で、記号が変わるのを待つ長さの上限(PC-1251は約0.8秒まで
    # かかる。気づく前に押したキーは、ROMがモードを切り替えるときに捨てる)
    MODE_LIMIT = CLOCK * 1500 // 1000

    LIVE = "@LIVE"
    # パソコンのキーを押しておく時間と次までの間。ROMは離したあと40msほどキーのない時間が
    # ないと次を取りこぼすので、1打鍵に0.1秒かける
    LIVE_DOWN = CLOCK * 50 // 1000
    LIVE_UP = CLOCK * 50 // 1000
    LIVE_MAX_WAIT = CLOCK * 600 // 1000  # この時間より長く順番を待ったキーは捨てる
    # ROMが入力待ちで止まってからこの時間がたつまでは、パソコンのキーをキューに入れて1つずつ届ける
    # (1打鍵を受けたROMが次の入力待ちに戻るまでのあいだに押したキーも、キューに入れる)
    WAIT_SPAN = CLOCK * 300 // 1000
    # キューを通さずにすぐ押したキー(動いているプログラムが読むキー)を、押し始めから最低この時間は
    # 押しておく。指で押した時間をそのまま本体に伝え、短すぎてプログラムのキー読みの間隔から
    # 漏れるものだけを補う(長くすると、ゲームで短く押しても自機が止まらなくなる)
    DIRECT_MIN = CLOCK * 25 // 1000

    def __init__(self, machine: PC1251, on_mode=None):
        self.m = machine
        if machine.model.lines == 2 or machine.model.family == "1350":
            # PC-1261などとPC-1350のROMは、押して離すまでが短いと1つおきに取りこぼし、
            # 表示が流れるところでは離している時間も長く要る
            self.DOWN = CLOCK * 100 // 1000
            self.UP = CLOCK * 120 // 1000
            self.LIVE_DOWN = CLOCK * 80 // 1000
            self.LIVE_UP = CLOCK * 120 // 1000
            self.MODE_WAIT = CLOCK * 700 // 1000
        self.mode_key = machine.model.family == "1350"  # RUNとPROをMODEキーで切り替える機種
        if self.mode_key:
            self.UP = CLOCK * 150 // 1000
            self.LIVE_UP = CLOCK * 150 // 1000
        self.on_mode = on_mode  # スイッチを動かす関数
        # Writeのダンプを書く関数(なければ本体のRAMにそのまま書く)。アプリは作業欄の書いた範囲の
        # 記録も合わせて更新する関数にする
        self.on_write: Callable[[list[tuple[int, bytes]]], None] | None = None
        self.queue: list[Entry] = []
        self.cur: list[str] | None = None
        self.until = 0
        self.phase = 0  # 0: 押している、1: 離して待っている、2: 離されるまで押している
        self.physical: set[str] = set()  # パソコンのキーボードで押されている本体のキー
        # 本体のキーごとに、そのキーを押しているパソコンのキー(↑と8のように、2つのキーが同じ
        # 本体のキーになることがある。最後の1つが離されたときに本体のキーを離す)
        self.sources: dict[str, set[object]] = {}
        self.mouse_keys: set[str] = set()  # マウスで押している本体のキー
        self.mouse_at: dict[str, int] = {}  # マウスで押したキーと、押し始めたサイクル
        self.mouse_off: dict[str, int] = {}  # マウスを離したが、まだ押しておくキーと離すサイクル
        self.live = False
        self.quick = False
        self.mode_shown: str | None = None  # 液晶に出るのを待っているモードの記号
        self.mode_limit = 0
        self.rush = False  # いまのパソコンのキーは、ROMの入力待ちに届けたもの(速く回してよい)
        self.ready_at = 0  # ENTERのあと、ROMが入力待ちに戻っていれば次を打ってよいサイクル
        self.stamp = ""
        self.direct: dict[str, int] = {}  # キューを通さずに押しているキーと、押し始めたサイクル
        self.direct_off: dict[str, int] = {}  # 離されたが、まだ押しておくキーと離すサイクル
        self.wait_seen = 0  # ROMが入力待ちで止まっているのを最後に見たサイクル

    def press_live(self, name: str, source: object = None) -> None:
        """パソコンのキー(source。キーコードなど)が押され、本体のキーnameになった"""
        self.sources.setdefault(name, set()).add(source)
        if name in self.physical:
            return
        self.physical.add(name)
        c = self.m.cpu.cycles
        if self._direct(c):
            self.direct[name] = c
            self.direct_off.pop(name, None)
            self.m.held.add(name)
        else:
            self.queue.append([self.LIVE, str(c), name])

    def _direct(self, c: int) -> bool:
        """パソコンのキーをキューに入れずにすぐ押してよいか。ファイルなどの打ち込みの途中と、
        ROMが入力待ちで止まっている(止まってからWAIT_SPANたっていない)ときはキューに入れる"""
        if self.queue or (self.cur is not None and not self.live):
            return False
        if self.m.waiting_for_key():
            self.wait_seen = c
        return c - self.wait_seen > self.WAIT_SPAN

    def add_live_keys(self, keys: list[list[str]]) -> None:
        """パソコンで打った記号やBackspaceを直した打鍵を足す。1文字ぶんの打鍵には
        同じ時刻をつけ、まとめて扱う"""
        stamp = str(self.m.cpu.cycles)
        self.queue.extend([self.LIVE, stamp, *k] for k in keys)

    def release_live(self, name: str, source: object = None) -> None:
        """パソコンのキー(source)が離された。同じ本体のキーをほかのパソコンのキーがまだ押して
        いれば、本体のキーは押したままにする。すぐ押したキーは、押し始めからDIRECT_MINたつまでは
        押しておく"""
        held_by = self.sources.get(name, set())
        held_by.discard(source)
        if held_by:
            return
        self.sources.pop(name, None)
        if name not in self.physical:
            return
        self.physical.discard(name)
        start = self.direct.get(name)
        if start is not None:
            if self.m.cpu.cycles - start >= self.DIRECT_MIN:
                self._lift(name)
            else:
                self.direct_off[name] = start + self.DIRECT_MIN

    def release_physical(self) -> None:
        """パソコンのキーがすべて離された(ほかのウィンドウに移ったときなど)"""
        self.physical.clear()
        self.sources.clear()
        for name in list(self.direct):
            self._lift(name)

    def press_mouse(self, name: str) -> None:
        """本体のキーをマウスで押した(キューを通さず、すぐ押す)"""
        self.mouse_keys.add(name)
        self.mouse_at[name] = self.m.cpu.cycles
        self.mouse_off.pop(name, None)
        self.m.held.add(name)

    def release_mouse(self, name: str) -> None:
        """マウスを離した。パソコンのキーボードで同じキーを押していれば、押したままにする。
        押し始めからLIVE_DOWNたつまでは押しておく(画面を指で軽く叩くと、押してから離すまでが
        1フレームに収まり、ROMがキーを読む間隔より短くなる)"""
        self.mouse_keys.discard(name)
        start = self.mouse_at.pop(name, None)
        if start is not None and self.m.cpu.cycles - start < self.LIVE_DOWN:
            self.mouse_off[name] = start + self.LIVE_DOWN
        elif not self._kept(name):
            self.m.held.discard(name)

    def _kept(self, name: str) -> bool:
        """本体のキーnameを、マウス、すぐ押したパソコンのキー、キューから押しているもののどれかが
        まだ押しているか"""
        if name in self.mouse_keys or name in self.mouse_off or name in self.direct:
            return True
        return self.cur is not None and name in self.cur and self.phase != 1

    def _lift(self, name: str) -> None:
        """すぐ押したキーを離す(マウスかキューからも押していれば、本体のキーは押したままにする)"""
        self.direct.pop(name, None)
        self.direct_off.pop(name, None)
        if not self._kept(name):
            self.m.held.discard(name)

    @property
    def rushing(self) -> bool:
        """パソコンのキーの打鍵を、ROMが入力を待っているところへ届けている最中か。そのあいだは
        エミュレータを速く回して、1打鍵にかかる時間(ROMがキーを読み取る待ち)を縮めてよい。
        ENTERのあとの待ち(RUNならプログラムが動き出す)と、押し続けているあいだ(ROMが
        キーの繰り返しを数える)は含めない。プログラムの実行中に押したキーも含めない"""
        if self.cur is not None:
            if not (self.live and self.rush):
                return False
            return self.phase == 0 or (self.phase == 1 and self.cur not in (["ENTER"], ["MODE"]))
        return bool(self.queue) and self._is_live(self.queue[0]) and self.m.waiting_for_key()

    def _is_live(self, e: Entry) -> TypeGuard[list[str]]:
        """パソコンのキーボードで押したキーの要素か"""
        return isinstance(e, list) and e[:1] == [self.LIVE]

    @property
    def scripted(self) -> bool:
        """ファイルや貼り付けの打ち込みの途中か(パソコンのキーは含めない)"""
        if self.cur is not None and not self.live:
            return True
        return any(not self._is_live(e) for e in self.queue)

    def add_text(self, text: str) -> None:
        self.queue.extend(keys_for(_lf(text), self.m.model.name))

    def add_program(self, text: str) -> None:
        """BASICの行を打つ。79字を超える行は分けて打つ(keytype.keys_for_program)"""
        self.queue.extend(keys_for_program(_lf(text), self.m.model.name))

    def add_keys(self, keys: list[list[str]]) -> None:
        self.queue.extend(keys)

    def add_mode(self, mode: str) -> None:
        self.queue.append([f"@MODE:{mode}"])

    def add_idle(self) -> None:
        """ROMが入力待ちに戻るまで(最長1分)、次の打鍵を待つ"""
        self.queue.append(["@IDLE"])

    def add_call(self, fn: Callable[[], object]) -> None:
        """前の打鍵が終わったところで、fn()を呼ぶ"""
        self.queue.append(self.call(fn))

    def call(self, fn: Callable[[], object]) -> Call:
        """fn()を呼ぶ1つの打鍵の代わり(キューの途中に入れるとき用)"""
        return Call(fn)

    def add_write(self, blocks: list[tuple[int, bytes]]) -> None:
        """前の打鍵が終わったところで、ダンプをRAMに書き込む"""
        self.queue.append(Write(blocks))

    def clear(self) -> None:
        """打ちかけのものを捨て、押しているキーを離す"""
        if self.cur:
            self.m.held.difference_update(set(self.cur) - self.mouse_keys - set(self.mouse_off))
        for name in list(self.direct):
            self._lift(name)
        self.queue.clear()
        self.cur = None
        self.phase = 0
        self.live = False
        self.mode_shown = None

    def restored(self) -> None:
        """本体の状態を戻したあと(CPUのサイクルが過去や先へ飛ぶ)に、打ちかけのものを捨て、
        サイクルで覚えている時刻を戻した本体に合わせる。ROMが入力を待って止まっている状態なら
        キーをキューで届け、プログラムが動いている状態ならすぐ押す"""
        self.clear()
        c = self.m.cpu.cycles
        self.wait_seen = c if self.m.waiting_for_key() else c - self.WAIT_SPAN - 1
        self.until = self.ready_at = c
        # マウスを離したあと押しておくキーは離し、押しているキーは押し始めを今にする
        for name in list(self.mouse_off):
            del self.mouse_off[name]
            if not self._kept(name):
                self.m.held.discard(name)
        self.mouse_at = dict.fromkeys(self.mouse_at, c)

    @property
    def busy(self) -> bool:
        return bool(self.queue) or self.cur is not None

    def step(self) -> None:
        c = self.m.cpu.cycles
        if self.m.waiting_for_key():
            self.wait_seen = c
        for name, at in list(self.direct_off.items()):
            if c >= at:
                self._lift(name)
        for name, at in list(self.mouse_off.items()):
            if c >= at:
                del self.mouse_off[name]
                if not self._kept(name):
                    self.m.held.discard(name)
        if self.cur == ["@IDLE"]:
            if self.m.waiting_for_key() or c >= self.until:
                self.cur = None
        elif self.cur is None:
            if self.queue:
                self._next(c)
        elif self.phase == 2:
            if not set(self.cur) <= self.physical or self.queue:
                self._release(c)
        elif self.phase == 1 and self._mode_pending(c):
            pass
        elif c >= self.until or (self.phase == 1 and self._ready(c)):
            if self.phase == 1:
                self.cur = None
            elif self.live and set(self.cur) <= self.physical and not self.queue:
                self.phase = 2  # まだ押されているので、離されるまで押しておく
            else:
                self._release(c)

    def _next(self, c: int) -> None:
        entry = self.queue.pop(0)
        if isinstance(entry, Call):
            self.cur = None
            entry.fn()
            return
        if isinstance(entry, Write):
            self.cur = ["@WRITE"]  # 書いたあと、ふつうの打鍵と同じく次まで間をおく(phase 1)
            if self.on_write is not None:
                self.on_write(entry.blocks)
            else:
                for addr, data in entry.blocks:
                    for i, b in enumerate(data):
                        self.m.write(addr + i, b)
            self.until = c
            self.phase = 1
            return
        self.cur = entry
        tag = entry[0] if entry else ""
        if tag == "@IDLE":
            self.until = c + CLOCK * 60
        elif tag.startswith("@MODE:"):
            self._switch(tag[6:], c)
        else:
            self._press(c)

    def _switch(self, mode: str, c: int) -> None:
        if self.mode_key and mode in ("RUN", "PRO"):
            # MODEキーで切り替える。いまのモードは液晶の記号で見る
            now = "PRO" if "PRO" in self.m.symbols() else "RUN"
            self.cur = ["MODE"] if now != mode else None
            if self.cur:
                self._press(c)
            return
        if self.mode_key and self.on_mode:
            self.on_mode(mode)
            self.cur = None
            return
        self.live = False
        shown = self.m.symbols()
        if self.on_mode:
            self.on_mode(mode)
        else:
            self.m.mode = mode
        self.until = c + self.MODE_WAIT
        self.phase = 1
        # 液晶にいまのモードの記号が出ている機種は、新しいモードの記号が出るまで待つ
        symbol = {"RUN": "RUN", "PRO": "PRO", "RSV": "RESERVE"}.get(mode)
        self.mode_shown = symbol if shown & {"RUN", "PRO", "RESERVE"} else None
        self.mode_limit = c + self.MODE_LIMIT

    def _mode_pending(self, c: int) -> bool:
        """モードを切り替えたあと、ROMがまだ液晶の記号を変えていない(上限まで待つ)"""
        if self.mode_shown is None:
            return False
        if self.mode_shown in self.m.symbols() or c >= self.mode_limit:
            self.mode_shown = None
            return False
        return True

    def _press(self, c: int) -> None:
        assert self.cur is not None
        if self.cur[:1] == [self.LIVE]:
            stamp = self.cur[1]
            self.cur = self.cur[2:]
            late = c - int(stamp) > self.LIVE_MAX_WAIT
            if stamp != self.stamp and late and not set(self.cur) <= self.physical:
                # 待ちすぎた打鍵は、同じ文字の残りの打鍵ごと捨てる
                while self.queue and self._is_live(head := self.queue[0]) and head[1] == stamp:
                    self.queue.pop(0)
                self.cur = None
                return
            self.stamp = stamp  # 1文字の途中の打鍵は、遅れていても最後まで押す
            self.live = True
        else:
            self.live = False
        # パソコンのキーそのものは短く押す。記号などを直した打鍵は打ち込みと同じ長さにする
        self.quick = self.live and set(self.cur) <= self.physical
        # ROMが入力を待って止まっているところへ届けるキーだけを速く回す(プログラムの
        # INKEY$などで読まれるキーは、実行中なので速くしない)
        self.rush = self.live and self.m.waiting_for_key()
        self.m.held.update(self.cur)
        self.until = c + (self.LIVE_DOWN if self.quick else self.DOWN)
        self.phase = 0

    def _ready(self, c: int) -> bool:
        """パソコンのキーのENTERのあと、ROMが入力待ちに戻ったか(次のキーを待たせない)"""
        return self.live and self.rush and c >= self.ready_at and self.m.waiting_for_key()

    def _release(self, c: int) -> None:
        assert self.cur is not None
        self.m.held.difference_update(self.cur)
        self.m.held.update(self.direct)
        self.m.held.update(self.mouse_keys)
        self.m.held.update(self.mouse_off)
        if self.cur in (["ENTER"], ["MODE"]):
            self.until = c + self.AFTER_ENTER
            self.ready_at = c + self.LIVE_UP
        else:
            self.until = c + (self.LIVE_UP if self.quick else self.UP)
        self.phase = 1

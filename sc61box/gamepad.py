"""ゲームパッドでポケコンのキーを押す

OSにつながっているゲームパッドのうち、SDLのGameControllerの対応表にあるもの(8BitDo、Xbox、
PlayStation、Switchのコントローラなど)を使う。ボタン、十字キー、スティックの向き、トリガーの
それぞれに、ポケコンのキーを1つ割り当てる(PadMap)。割り当ては、読み込んだプログラムの
「# pad:」の行、プログラムのフォルダに保存した自分の割り当て、既定の順に決まる(App.pad_map_for)。

PadMapは画面を持たず、試験から直接使える。パッドのイベントを入力の名前に直すのはPads。
ブラウザ(Pyodide)のpygame-ceにはコントローラの仕組みがないので、ページが読んだGamepad APIの
状態から作る(WebPads)。
"""

import json
import os
import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pygame

try:
    from pygame._sdl2 import controller
except ImportError:  # ブラウザ(Pyodide)のpygame-ceにはない
    controller = None
if TYPE_CHECKING:
    from pygame._sdl2.controller import Controller

from . import machine
from .i18n import Text

# 入力の名前はSDLの対応表の書き方(a、dpup、leftshoulderなど)。表示はLABELS
BUTTONS = {
    pygame.CONTROLLER_BUTTON_A: "a",
    pygame.CONTROLLER_BUTTON_B: "b",
    pygame.CONTROLLER_BUTTON_X: "x",
    pygame.CONTROLLER_BUTTON_Y: "y",
    pygame.CONTROLLER_BUTTON_BACK: "back",
    pygame.CONTROLLER_BUTTON_START: "start",
    pygame.CONTROLLER_BUTTON_GUIDE: "guide",
    pygame.CONTROLLER_BUTTON_LEFTSHOULDER: "leftshoulder",
    pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: "rightshoulder",
    pygame.CONTROLLER_BUTTON_LEFTSTICK: "leftstick",
    pygame.CONTROLLER_BUTTON_RIGHTSTICK: "rightstick",
    pygame.CONTROLLER_BUTTON_DPAD_UP: "dpup",
    pygame.CONTROLLER_BUTTON_DPAD_DOWN: "dpdown",
    pygame.CONTROLLER_BUTTON_DPAD_LEFT: "dpleft",
    pygame.CONTROLLER_BUTTON_DPAD_RIGHT: "dpright",
}
# 軸: (負の向きの入力, 正の向きの入力)。スティックは十字キーと同じ入力にする
AXES = {
    pygame.CONTROLLER_AXIS_LEFTX: ("dpleft", "dpright"),
    pygame.CONTROLLER_AXIS_LEFTY: ("dpup", "dpdown"),
    pygame.CONTROLLER_AXIS_RIGHTX: ("dpleft", "dpright"),
    pygame.CONTROLLER_AXIS_RIGHTY: ("dpup", "dpdown"),
    pygame.CONTROLLER_AXIS_TRIGGERLEFT: (None, "lefttrigger"),
    pygame.CONTROLLER_AXIS_TRIGGERRIGHT: (None, "righttrigger"),
}
PRESS, RELEASE = 0.5, 0.3  # 軸をこの割合より倒すと押したことに、戻すと離したことにする


def lean(now: str | None, value: float, minus: str | None, plus: str | None) -> str | None:
    """軸の値valueから、倒している向きの入力(なければNone)。nowはいままでの向き。PRESSを
    越えて倒し、倒している向きの値がRELEASEを下回ると(反対側へ越えたときも)戻す"""
    want = now
    if now is not None and value * (1 if now == plus else -1) < RELEASE:
        want = None
    if abs(value) > PRESS:
        want = plus if value > 0 else minus
    return want


def net(changes: list[tuple[str, int, bool]]) -> list[tuple[str, int, bool]]:
    """1回に受け取った押す・離すから、離してすぐ同じ入力を押したもの(十字キーを離すのと
    同時にスティックを同じ向きに倒したときなど)を除く。押し続けていたことになる"""
    out: list[tuple[str, int, bool] | None] = []
    released: dict[tuple[str, int], int] = {}  # 離したあとまだ押していない入力: outでの位置
    for name, iid, pressed in changes:
        key = (name, iid)
        if pressed and key in released:
            out[released.pop(key)] = None
            continue
        if not pressed:
            released[key] = len(out)
        out.append((name, iid, pressed))
    return [c for c in out if c is not None]


ORDER = (
    "dpup", "dpdown", "dpleft", "dpright", "a", "b", "x", "y",
    "leftshoulder", "rightshoulder", "lefttrigger", "righttrigger",
    "back", "start", "leftstick", "rightstick", "guide",
)  # fmt: skip
LABELS = {
    "dpup": "↑", "dpdown": "↓", "dpleft": "←", "dpright": "→",
    "a": "A", "b": "B", "x": "X", "y": "Y",
    "leftshoulder": "L", "rightshoulder": "R", "lefttrigger": "ZL", "righttrigger": "ZR",
    "back": "Select", "start": "Start", "leftstick": "L3", "rightstick": "R3", "guide": "Home",
}  # fmt: skip

# 割り当てられるポケコンのキーの名前(全機種のキーとBRK)
KEY_NAMES = frozenset(machine.KEYS) | frozenset(machine.KEYS_1350) | {"BRK"}


def key_names(family: str) -> frozenset[str]:
    """機種の系列familyで割り当てられるキーの名前"""
    return frozenset(machine.KEYS_1350 if family == "1350" else machine.KEYS) | {"BRK"}


DEFAULT = {
    "dpup": "8", "dpdown": "2", "dpleft": "4", "dpright": "6",
    "a": "SPC", "b": "0", "start": "ENTER", "back": "BRK",
}  # fmt: skip


class PadMap:
    """入力の名前からポケコンのキーの名前への割り当て。originは割り当ての出どころ(IDと値で持ち、
    sourceで、そのときの言語の説明にする)"""

    def __init__(self, keys: dict[str, str] | None = None, source: str | Text = "") -> None:
        self.keys = dict(DEFAULT if keys is None else keys)
        self.origin = source

    @property
    def source(self) -> str:
        """割り当ての出どころの説明(いまの言語の文)"""
        return str(self.origin)

    @source.setter
    def source(self, text: str | Text) -> None:
        self.origin = text

    def get(self, name: str) -> str | None:
        return self.keys.get(name)

    def set(self, name: str, key: str | None) -> None:
        if key is None:
            self.keys.pop(name, None)
        else:
            self.keys[name] = key

    def copy(self, source: str | Text) -> "PadMap":
        return PadMap(self.keys, source)

    def text(self) -> str:
        """# pad: の行の値(「dpup=8 dpdown=2 a=SPC」)"""
        return " ".join(f"{name}={self.keys[name]}" for name in ORDER if name in self.keys)

    @classmethod
    def parse(
        cls, value: str, source: str | Text = "", names: frozenset[str] = KEY_NAMES
    ) -> tuple["PadMap", list[str]]:
        """# pad: の値を読む。読めなかった語も返す(入力の名前が違うものと、キーの名前が
        namesにないもの)。区切りは空白だけ(PC-1350には「,」のキーがある)"""
        keys: dict[str, str] = {}
        bad = []
        for word in value.split():
            name, _, key = word.partition("=")
            name, key = name.lower(), key.upper()
            if name not in ORDER or key not in names:
                bad.append(word)
                continue
            keys[name] = key
        return cls(keys, source), bad

    @classmethod
    def load(cls, path: str, source: str | Text) -> "PadMap | None":
        """保存した割り当てを読む。なければ、読めなければNone"""
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        keys = {
            n: k for n, k in data.items() if n in ORDER and isinstance(k, str) and k in KEY_NAMES
        }
        return cls(keys, source)

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({name: self.keys[name] for name in ORDER if name in self.keys}, f, indent=1)


class Pads:
    """つながっているゲームパッドと、押している入力。pygameのイベントから入力の名前の
    押す・離すを作る(handle)。同じ入力を十字キーとスティックの両方から押せるので、入力ごとに
    押している元(ボタンか、どの軸か)を覚え、すべて離れたときに離す"""

    def __init__(self) -> None:
        self.devices: dict[int, Controller] = {}  # instance_id: 開いたコントローラ
        # (instance_id, 入力の名前): 押している元の集合("button"か軸の番号)
        self.held: dict[tuple[int, str], set[int | str]] = {}
        self.axis_on: dict[tuple[int, int], str] = {}  # (instance_id, 軸): 倒している向きの入力
        # 離したことにしたが、まだ倒れている軸(instance_id, 軸)。中立に戻るまで押し直さない
        self.stuck: set[tuple[int, int]] = set()
        if controller is None:
            return
        try:
            controller.init()
            if hasattr(controller, "set_eventstate"):  # pygame-ceはinit()で有効になる
                controller.set_eventstate(True)
            for i in range(controller.get_count()):
                self._open(i)
        except pygame.error:
            pass

    def _open(self, index: int) -> None:
        if controller is None or not controller.is_controller(index):
            return
        try:
            c = controller.Controller(index)
        except pygame.error:
            return
        self.devices[c.as_joystick().get_instance_id()] = c

    def names(self) -> list[str]:
        return [c.name for c in self.devices.values()]

    def poll(self) -> list[tuple[str, int, bool]]:
        """イベントの来ない入力の変化(ブラウザ)。パソコンではイベントで受けるので、いつも空"""
        return []

    def pressed(self) -> set[str]:
        """いま押している入力の名前"""
        return {name for _iid, name in self.held}

    def handle(self, ev) -> list[tuple[str, int, bool]]:
        """イベントを(入力の名前, instance_id, 押したか)の列にする。パッドを外したときは、
        押していた入力を離す"""
        t = ev.type
        if t == pygame.CONTROLLERDEVICEADDED:
            self._open(ev.device_index)
            return []
        if t == pygame.CONTROLLERDEVICEREMOVED:
            self.devices.pop(ev.instance_id, None)
            return self._release(lambda iid: iid == ev.instance_id)
        if t in (pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLERBUTTONUP):
            name = BUTTONS.get(ev.button)
            if name is None:
                return []
            return self._change(ev.instance_id, name, "button", t == pygame.CONTROLLERBUTTONDOWN)
        if t == pygame.CONTROLLERAXISMOTION and ev.axis in AXES:
            return self._axis(ev.instance_id, ev.axis, ev.value / 32767)
        return []

    def _change(
        self, iid: int, name: str, by: int | str, pressed: bool
    ) -> list[tuple[str, int, bool]]:
        """元byが入力nameを押した・離した。入力が押されていない状態から押されたとき、
        押している元がなくなったときだけ、押す・離すを返す"""
        key = (iid, name)
        sources = self.held.get(key, set())
        if pressed:
            was = bool(sources)
            sources.add(by)
            self.held[key] = sources
            return [] if was else [(name, iid, True)]
        sources.discard(by)
        if sources or key not in self.held:
            return []
        del self.held[key]
        return [(name, iid, False)]

    def _axis(self, iid: int, axis: int, value: float) -> list[tuple[str, int, bool]]:
        """軸の値から、倒した向きの入力を押す・離す。PRESSを越えて押し、倒している向きの値が
        RELEASEを下回って(反対側へ越えたときも)離す"""
        if (iid, axis) in self.stuck:
            if abs(value) >= RELEASE:
                return []
            self.stuck.discard((iid, axis))
        minus, plus = AXES[axis]
        now = self.axis_on.get((iid, axis))
        want = lean(now, value, minus, plus)
        if want == now:
            return []
        out = []
        if now is not None:
            out += self._change(iid, now, axis, False)
        if want is not None:
            out += self._change(iid, want, axis, True)
            self.axis_on[(iid, axis)] = want
        else:
            self.axis_on.pop((iid, axis), None)
        return out

    def _release(self, which) -> list[tuple[str, int, bool]]:
        """which(instance_id)が真のパッドの、押している入力をすべて離す"""
        out = [(name, iid, False) for iid, name in self.held if which(iid)]
        for name, iid, _ in out:
            del self.held[(iid, name)]
        for key in [k for k in self.axis_on if which(k[0])]:
            del self.axis_on[key]
        self.stuck = {k for k in self.stuck if not which(k[0])}
        return out

    def release_all(self) -> list[tuple[str, int, bool]]:
        """押している入力をすべて離す(割り当てを変える前など)。倒れたままの軸は、中立に
        戻るまで押し直さない(ボタンは、押し直すまでイベントが来ない)"""
        tilted = set(self.axis_on)
        out = self._release(lambda _iid: True)
        self.stuck = tilted
        return out

    def sync(self) -> list[tuple[str, int, bool]]:
        """外れたのにイベントが来なかったパッドを閉じ、押していた入力を離す。pygame 2.6までは、
        つないだときのイベントを取り出す前に外れたパッド(Joy-Conを2つつないで1つにまとめた
        ときなど)でpygame.event.get()がKeyErrorになり(pygame/pygame#3634)、その回の
        イベントが失われる"""
        gone = []
        for iid, c in self.devices.items():
            try:
                attached = c.attached()
            except pygame.error:
                attached = False
            if not attached:
                gone.append(iid)
        for iid in gone:
            del self.devices[iid]
        return self._release(lambda iid: iid in gone)


# ブラウザのGamepad APIの標準の配置(mappingが"standard")の、ボタンの番号と軸の番号
WEB_BUTTONS = {
    0: "a", 1: "b", 2: "x", 3: "y", 4: "leftshoulder", 5: "rightshoulder",
    8: "back", 9: "start", 10: "leftstick", 11: "rightstick",
    12: "dpup", 13: "dpdown", 14: "dpleft", 15: "dpright", 16: "guide",
}  # fmt: skip
# 任天堂の配置(右がA、下がB、上がX、左がY)のパッドの、標準の番号のボタン。Gamepad APIは位置で
# 番号を付けるので、パソコン版(SDL2は印字で読む)と同じに、印字の名前にする
WEB_BUTTONS_NINTENDO = {**WEB_BUTTONS, 0: "b", 1: "a", 2: "y", 3: "x"}
# 1つだけの右のJoy-Con。Chromiumは横持ちに向きを変えて、Aを下、Xを右、Bを左、Yを上の番号にする。
# Firefoxは向きを変えない(LinuxではProコントローラと同じ番号で届く)
WEB_BUTTONS_JOYCON_R = {**WEB_BUTTONS, 0: "a", 1: "x", 2: "b", 3: "y"}
# 任天堂のパッドのうち、Aを下、Bを右の番号で出すもの(Switch用のNINTENDO 64コントローラ)
NINTENDO_STANDARD = {0x2019}
# 任天堂の配置の8BitDoの製品ID(SF30 Pro・SN30 Pro・Pro 2・Pro 3。SDLのusb_ids.h)。ほかの
# 8BitDo(Ultimate 2C、M30、Xbox用など)は標準の配置として読む
NINTENDO_8BITDO = {0x6000, 0x6100, 0x6001, 0x6101, 0x6003, 0x6006, 0x6009}
WEB_TRIGGERS = {6: pygame.CONTROLLER_AXIS_TRIGGERLEFT, 7: pygame.CONTROLLER_AXIS_TRIGGERRIGHT}
WEB_AXES = (
    pygame.CONTROLLER_AXIS_LEFTX, pygame.CONTROLLER_AXIS_LEFTY,
    pygame.CONTROLLER_AXIS_RIGHTX, pygame.CONTROLLER_AXIS_RIGHTY,
)  # fmt: skip


def pad_name(gid: str) -> str:
    """Gamepad APIのidから、パッドの名前を取り出す。Chromeは「名前 (STANDARD GAMEPAD Vendor:
    2dc8 Product: 6101)」、Firefoxは「2dc8-6101-名前」の形"""
    name = re.sub(r"^[0-9a-f]{1,4}-[0-9a-f]{1,4}-", "", gid.strip(), flags=re.I)
    name = re.sub(r"\s*\([^()]*\b(?:Vendor|STANDARD GAMEPAD)\b[^()]*\)$", "", name, flags=re.I)
    return name.strip() or gid.strip()


def pad_ids(gid: str) -> tuple[int, int] | None:
    """Gamepad APIのidから(製造元のID, 製品のID)を取り出す。Firefoxは頭の0を省く"""
    found = re.search(
        r"Vendor:\s*([0-9a-f]{1,4})\s+Product:\s*([0-9a-f]{1,4})\b|^([0-9a-f]{1,4})-([0-9a-f]{1,4})-",
        gid.strip(),
        flags=re.I,
    )
    if not found:
        return None
    vendor, product = found.group(1, 2) if found.group(1) else found.group(3, 4)
    return int(vendor, 16), int(product, 16)


def nintendo_layout(gid: str) -> bool:
    """Gamepad APIのidから、任天堂の配置のパッド(Proコントローラ、Joy-Con、8BitDoのSN30 Proなど)
    か。8BitDoは製品のIDで決める(idにIDがなければ名前で)"""
    ids = pad_ids(gid)
    if ids and ids[0] == 0x2DC8:
        return ids[1] in NINTENDO_8BITDO
    if ids and ids[0] == 0x057E:
        return ids[1] not in NINTENDO_STANDARD
    if re.search(r"\bN64\b|NINTENDO 64", gid, flags=re.I):
        return False
    if re.search(r"Nintendo|Joy-Con", gid, flags=re.I):
        return True
    if ids:  # ほかの製造元の「Pro Controller」(NACONのPS4用など)は名前で決めない
        return False
    return bool(re.search(r"\bPro Controller\b|8BitDo (?:SF30|SN30|Pro [23])\b", gid, flags=re.I))


def web_buttons(gid: str) -> dict[int, str]:
    """標準の配置のパッドの、ボタンの番号と入力の名前の表"""
    right = pad_ids(gid) == (0x057E, 0x2007) or re.search(r"Joy-Con \(R\)", gid, flags=re.I)
    if right and re.search(r"\bVendor:", gid):  # Chromiumのidの形
        return WEB_BUTTONS_JOYCON_R
    return WEB_BUTTONS_NINTENDO if nintendo_layout(gid) else WEB_BUTTONS


# ページの行の先頭にこの行があれば、ページが入力を止めている(使い方を出しているなど)
HOLD = "hold"


class WebPads(Pads):
    """ブラウザのゲームパッド。ブラウザはパッドのイベントを出さないので、フレームごとにページ
    からいまの状態を読み(read)、ボタンと軸から押されている入力を求めて、前のフレームと比べる
    (poll)。readは、つながっているパッドごとに「番号、配置、id、ボタンの値(,区切り)、軸の値
    (,区切り)」をタブで区切った行を返す(先頭にHOLDの行があれば、本体へは送らない)。配置が
    "standard"でないパッドも標準の番号で読み、名前に配置がわからないことを添える"""

    def __init__(self, read: Callable[[], str]) -> None:
        self.read = read
        self.devices = {}
        self.held = {}
        self.axis_on = {}  # (番号, 軸): 倒している向きの入力
        self.stuck = set()
        self.pads: dict[int, tuple[str, str | Text]] = {}  # 番号: (id, 出す名前)
        self.buttons: dict[int, dict[int, str]] = {}  # 番号: ボタンの番号と入力の名前の表
        self.down: dict[int, set[int]] = {}  # 番号: 押しているボタンの番号
        self.on: dict[int, set[str]] = {}  # 番号: 押したことにしている入力
        # 番号: 離したことにしたが、まだ押されている入力。いちど離されるまで押したことにしない
        self.blocked: dict[int, set[str]] = {}

    def names(self) -> list[str]:
        return [str(self.pads[i][1]) for i in sorted(self.pads)]

    def pressed(self) -> set[str]:
        return {name for names in self.on.values() for name in names}

    def poll(self) -> list[tuple[str, int, bool]]:
        rows = self.read().splitlines()
        hold = bool(rows) and rows[0] == HOLD
        out: list[tuple[str, int, bool]] = []
        seen = set()
        for line in rows[1:] if hold else rows:
            parts = line.split("\t")
            if len(parts) != 5:
                continue
            try:
                iid = int(parts[0])
                buttons = [float(v) for v in parts[3].split(",") if v]
                axes = [float(v) for v in parts[4].split(",") if v]
            except ValueError:
                continue
            mapping, gid = parts[1], parts[2]
            seen.add(iid)
            if iid not in self.pads or self.pads[iid][0] != gid:  # 新しいパッドか、替わった
                out += self._forget(iid)
                name = pad_name(gid)
                shown = name if mapping == "standard" else Text("pad.web_layout_unknown", name=name)
                self.pads[iid] = (gid, shown)
                self.buttons[iid] = web_buttons(gid) if mapping == "standard" else WEB_BUTTONS
            raw = self._raw(iid, buttons, axes)
            blocked = self.blocked.get(iid, set())
            self.blocked[iid] = blocked = (blocked | raw if hold else blocked) & raw
            out += self._diff(iid, raw - blocked)
        for iid in [i for i in self.pads if i not in seen]:
            out += self._forget(iid)
        return out

    def _raw(self, iid: int, buttons: list[float], axes: list[float]) -> set[str]:
        """いま押されている入力。ボタンもPRESSを越えて押し、RELEASEを下回って離す。ZL・ZRは
        値の変わるボタンなので、軸と同じに扱う"""
        down = self.down.setdefault(iid, set())
        tilts = [(WEB_TRIGGERS[i], v) for i, v in enumerate(buttons) if i in WEB_TRIGGERS]
        tilts += list(zip(WEB_AXES, axes, strict=False))
        for i, value in enumerate(buttons):
            if i not in WEB_BUTTONS:
                continue
            if value > PRESS:
                down.add(i)
            elif value < RELEASE:
                down.discard(i)
        for axis, value in tilts:
            want = lean(self.axis_on.get((iid, axis)), value, *AXES[axis])
            if want is None:
                self.axis_on.pop((iid, axis), None)
            else:
                self.axis_on[(iid, axis)] = want
        table = self.buttons.get(iid, WEB_BUTTONS)
        names = {table[i] for i in down}
        return names | {name for (i, _axis), name in self.axis_on.items() if i == iid}

    def _diff(self, iid: int, now: set[str]) -> list[tuple[str, int, bool]]:
        """押したことにする入力をnowにして、前との違いを返す(離すのが先)"""
        before = self.on.get(iid, set())
        self.on[iid] = now
        return [(n, iid, False) for n in ORDER if n in before - now] + [
            (n, iid, True) for n in ORDER if n in now - before
        ]

    def _forget(self, iid: int) -> list[tuple[str, int, bool]]:
        """番号iidのパッドを外したことにして、押していた入力を離す"""
        out = [(n, iid, False) for n in ORDER if n in self.on.get(iid, set())]
        for table in (self.pads, self.buttons, self.down, self.on, self.blocked):
            table.pop(iid, None)
        for key in [k for k in self.axis_on if k[0] == iid]:
            del self.axis_on[key]
        return out

    def release_all(self) -> list[tuple[str, int, bool]]:
        """押している入力をすべて離す。まだ押されている入力は、いちど離されるまで押し直さない"""
        out = []
        for iid in sorted(self.on):
            names = self.on[iid]
            self.blocked.setdefault(iid, set()).update(names)
            out += [(n, iid, False) for n in ORDER if n in names]
            self.on[iid] = set()
        return out

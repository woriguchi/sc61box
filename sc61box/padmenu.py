"""ゲームパッドの割り当てを変える画面(PadPanel)。割り当てそのものはgamepad.PadMap

本体の絵の下に欄を足して、つながっているパッド、入力ごとの割り当て、保存のボタンを出す。
入力の割り当ては、パッドの並びにならべる(左に十字キー、まんなかにSelect・Start、右に
A・B・X・Y、上にL・R)。割り当てを変えるときは、パッドのボタンを押すか割り当てをクリックして
入力を選び、本体の絵のキーをクリックするか、パソコンのキーを打つ。本体の絵のキーには、
割り当ててある入力の札を出す(draw_badges)。

パッドの入力の名前は、欄の中でも本体の絵の上でも同じ札(暗い地に黄色の字)で書き、
割り当てたキーの名前は白の字で書く。どちらがパッドでどちらがキーかを色で見分ける。
"""

import pygame

from .gamepad import LABELS, ORDER, PadMap
from .i18n import tr
from .overlay import GREY, WHITE, wrap_text

BG = (24, 26, 30)
CHIP = (44, 47, 54)
CHIP_ON = (70, 92, 140)
CHIP_PRESSED = (96, 150, 110)
BUTTON = (58, 61, 68)
BUTTON_OFF = (40, 42, 48)
BADGE = (26, 28, 34)  # パッドの入力の札(欄の中でも本体の絵の上でも同じ)
BADGE_INK = (255, 214, 120)
BADGE_ON = (96, 150, 110)
NONE_INK = (120, 124, 132)  # 割り当てていない印
LH = 26
CHIP_H = 26
ROW_H = 30

# 入力を置く場所(列, 行)。パッドを上から見た並び(8BitDo SN30 Proの印字の位置)。列の幅は
# その列に置く入力の札の幅で決める(列ごとに違う)。Homeは3列目と4列目のまんなか
LAYOUT: dict[str, tuple[float, int]] = {
    "lefttrigger": (0, 0), "leftshoulder": (1, 0), "rightshoulder": (6, 0), "righttrigger": (7, 0),
    "dpup": (1, 1), "back": (3, 1), "start": (4, 1), "x": (6, 1),
    "dpleft": (0, 2), "dpright": (2, 2), "leftstick": (3, 2), "rightstick": (4, 2),
    "y": (5, 2), "a": (7, 2),
    "dpdown": (1, 3), "guide": (3.5, 3), "b": (6, 3),
}  # fmt: skip
COLS, ROWS = 8, 4
GAP = 6

ACTIONS = ("save_prog", "save_default", "reset", "from_prog", "copy", "close")


def key_label(key: str | None) -> str:
    """割り当てたキーの表示。ないときは「―」"""
    if key is None:
        return "―"
    return {"SPC": "SPACE", "UP": "↑", "DOWN": "↓", "LEFT": "◀", "RIGHT": "▶"}.get(key, key)


def badge(font, text: str, on: bool = False) -> pygame.Surface:
    """パッドの入力の札(暗い地に黄色の字。onなら緑の地に白)"""
    img = font.render(text, True, WHITE if on else BADGE_INK)
    out = pygame.Surface((img.get_width() + 8, img.get_height() + 2), pygame.SRCALPHA)
    pygame.draw.rect(out, BADGE_ON if on else BADGE, out.get_rect(), border_radius=4)
    out.blit(img, (4, 1))
    return out


def chip_width(font, small, name: str, pad_map: PadMap) -> int:
    """入力nameの割り当て1つの幅(札と、キーの名前と、余白)"""
    return small.size(LABELS[name])[0] + 8 + 8 + font.size(key_label(pad_map.get(name)))[0] + 16


def grid_columns(font, small, w: int, pad_map: PadMap) -> list[tuple[int, int]] | None:
    """パッドの形に置くときの、列ごとの(左端, 幅)。幅wに入らなければNone"""
    widths = [0] * COLS
    for name, (col, _row) in LAYOUT.items():
        if col == int(col):
            widths[int(col)] = max(widths[int(col)], chip_width(font, small, name, pad_map))
    spare = w - sum(widths) - GAP * (COLS - 1)
    if spare < 0:
        return None
    gap = GAP + min(24, spare // (COLS - 1))  # 余裕があれば少し広げる
    out, x = [], 0
    for cw in widths:
        out.append((x, cw))
        x += cw + gap
    return out


class PadPanel:
    def __init__(self) -> None:
        self.selected: str | None = None  # 割り当てを変える入力
        self.hits: list[tuple[pygame.Rect, str, str]] = []  # (場所, 種類, 値)
        self.height = 0  # 欄の高さ(measureで決める)
        self.top = 0  # 窓の中で欄を描いた位置(drawで決める)

    def hit(self, pos) -> tuple[str, str] | None:
        """posにあるもの。("input", 入力の名前)か("action", 動作の名前)"""
        for r, kind, value in self.hits:
            if r.collidepoint(pos):
                return kind, value
        return None

    def _buttons(self, prog: str | None, prog_pad: bool) -> list[tuple[str, str, bool]]:
        return [
            ("save_prog", tr("このプログラム用に保存"), prog is not None),
            ("save_default", tr("既定として保存"), True),
            ("reset", tr("初期設定に戻す"), True),
            ("from_prog", tr("# pad: に戻す"), prog_pad),
            ("copy", tr("# pad: の行をコピー"), True),
            ("close", tr("閉じる(Esc)"), True),
        ]

    def _notes(self, names: list[str], selected: str | None) -> list[str]:
        """入力の並びの上に出す説明。入力を選んでいるあいだは、その入力への割り当て方"""
        if selected is not None:
            return [
                tr(
                    "{name}に割り当てるキーを、本体の絵でクリックするか、パソコンで打ちます。"
                    "Deleteで割り当てを外し、Escでやめます",
                    name=LABELS[selected],
                )
            ]
        if names:
            first = tr(
                "パッドのボタンを押すか、下の割り当てをクリックすると、その割り当てを変えられます"
            )
        else:
            first = tr("下の割り当てをクリックすると、その割り当てを変えられます")
        return [
            first,
            tr("ボタンの名前はA・B・X・Yの位置の約束(SDL)で、パッドの印字と違うことがあります。"
               "印字と違うときは、割り当てたいボタンを実際に押して選んでください"),
        ]  # fmt: skip

    def _layout(
        self, font, small, width: int, names: list[str], pad_map: PadMap, prog, prog_pad
    ) -> dict:
        """欄の中の各部の寸法。入力の並びは、パッドの形に置けるだけの幅があればその形に
        (入らなければ小さい字で、それでも入らなければ順に並べる)"""
        pad = 12
        w = width - 2 * pad
        grid, chip_font = None, font
        for f in (font, small):
            grid = grid_columns(f, small, w, pad_map)
            if grid is not None:
                chip_font = f
                break
        # 説明の場所の高さは、入力を選んでいるときと選んでいないときの長いほうに合わせ、
        # 選ぶたびに欄の高さが変わらないようにする
        notes = [
            line for text in self._notes(names, self.selected) for line in wrap_text(small, text, w)
        ]
        note_rows = len(notes)
        longest = max(ORDER, key=lambda n: small.size(LABELS[n])[0])
        for sel in (None, longest):
            if sel != self.selected:
                other = [
                    line for text in self._notes(names, sel) for line in wrap_text(small, text, w)
                ]
                note_rows = max(note_rows, len(other))
        button_rows: list[list[tuple[str, str, bool]]] = [[]]
        x = 0
        for act, label, enabled in self._buttons(prog, prog_pad):
            bw = font.size(label)[0] + 18
            if x + bw > w and button_rows[-1]:
                button_rows.append([])
                x = 0
            button_rows[-1].append((act, label, enabled))
            x += bw + 6
        chips_h = ROW_H * (ROWS if grid else self._flat_rows(font, small, w, pad_map))
        return {
            "pad": pad,
            "w": w,
            "grid": grid,
            "chip_font": chip_font,
            "notes": notes,
            "note_rows": note_rows,
            "buttons": button_rows,
            "chips_h": chips_h,
        }

    @staticmethod
    def _flat_rows(font, small, w: int, pad_map: PadMap) -> int:
        rows, x = 1, 0
        for name in ORDER:
            cw = chip_width(font, small, name, pad_map)
            if x + cw > w and x:
                rows += 1
                x = 0
            x += cw + GAP
        return rows

    def measure(self, font, small, width: int, names: list[str], pad_map, prog, prog_pad) -> int:
        """幅widthでの欄の高さを決めて返す"""
        lay = self._layout(font, small, width, names, pad_map, prog, prog_pad)
        self.height = (
            lay["pad"] + LH + 18 * lay["note_rows"] + 6 + lay["chips_h"] + 6
            + ROW_H * len(lay["buttons"]) + 18 + lay["pad"]
        )  # fmt: skip
        return self.height

    def draw(
        self,
        dst: pygame.Surface,
        top: int,
        font: pygame.font.Font,
        small: pygame.font.Font,
        names: list[str],
        pad_map: PadMap,
        pressed: set[str],
        prog: str | None,
        prog_pad: bool,
        dirty: bool,
    ) -> None:
        """窓のtopから下に欄を描く。namesはつながっているパッド、pressedはいま押している入力、
        progは読み込んであるプログラムの題名(なければNone)、prog_padはそのプログラムに
        # pad: があるか、dirtyは保存していない変更があるか"""
        width = dst.get_width()
        lay = self._layout(font, small, width, names, pad_map, prog, prog_pad)
        pad, w = lay["pad"], lay["w"]
        self.measure(font, small, width, names, pad_map, prog, prog_pad)
        self.top = top
        pygame.draw.rect(dst, BG, (0, top, width, self.height))
        pygame.draw.line(dst, (60, 62, 68), (0, top), (width, top))
        self.hits = []
        x0 = pad
        y = top + pad
        dst.blit(font.render(tr("ゲームパッドの割り当て"), True, WHITE), (x0, y))
        if names:
            who = tr("、").join(names)
        else:
            who = tr("パッドがつながっていません(つなぐとここに出ます)")
        img = small.render(who, True, GREY)
        if img.get_width() <= w // 2:
            dst.blit(img, (x0 + w - img.get_width(), y + 4))
        y += LH
        for line in lay["notes"]:
            dst.blit(small.render(line, True, GREY), (x0, y))
            y += 18
        y += 18 * (lay["note_rows"] - len(lay["notes"])) + 6
        if lay["grid"]:
            cols = lay["grid"]
            for name in ORDER:
                col, row = LAYOUT[name]
                if col == int(col):
                    x, cw = cols[int(col)]
                else:  # 2つの列のまんなかに
                    cw = chip_width(lay["chip_font"], small, name, pad_map)
                    left, right = cols[int(col)], cols[int(col) + 1]
                    x = (left[0] + right[0] + right[1]) // 2 - cw // 2
                self._chip(dst, lay["chip_font"], small, name, pad_map, pressed, x0 + x,
                           y + row * ROW_H, cw)  # fmt: skip
            y += ROW_H * ROWS
        else:
            x = x0
            for name in ORDER:
                cw = chip_width(font, small, name, pad_map)
                if x + cw > x0 + w and x > x0:
                    x, y = x0, y + ROW_H
                self._chip(dst, font, small, name, pad_map, pressed, x, y, cw)
                x += cw + GAP
            y += ROW_H
        y += 6
        for row in lay["buttons"]:
            x = x0
            for act, label, enabled in row:
                img = font.render(label, True, WHITE if enabled else GREY)
                r = pygame.Rect(x, y, img.get_width() + 18, CHIP_H)
                pygame.draw.rect(dst, BUTTON if enabled else BUTTON_OFF, r, border_radius=5)
                dst.blit(img, (r.x + 9, r.y + 3))
                if enabled:
                    self.hits.append((r, "action", act))
                x = r.right + 6
            y += ROW_H
        if prog is None:
            target = tr("対象: (プログラムを読み込んでいません)")
        else:
            target = tr("対象: {name}", name=prog)
        state = tr("いまの割り当て: {source}", source=pad_map.source)
        if dirty:
            state += tr("(変更あり、保存していません)")
        dst.blit(small.render(f"{target}   {state}", True, GREY), (x0, y))

    def _chip(self, dst, font, small, name, pad_map, pressed, x: int, y: int, cw: int) -> None:
        """入力1つの割り当て(入力の札「↑」と、キーの名前「8」)。選んでいれば枠、押していれば緑"""
        key = pad_map.get(name)
        tag = badge(small, LABELS[name], on=name in pressed)
        img = font.render(key_label(key), True, WHITE if key is not None else NONE_INK)
        r = pygame.Rect(x, y, cw, CHIP_H)
        if name == self.selected:
            color = CHIP_ON
        elif name in pressed:
            color = CHIP_PRESSED
        else:
            color = CHIP
        pygame.draw.rect(dst, color, r, border_radius=5)
        if name == self.selected:
            pygame.draw.rect(dst, WHITE, r, 1, border_radius=5)
        left = r.x + (cw - tag.get_width() - 8 - img.get_width()) // 2
        dst.blit(tag, (left, r.y + (CHIP_H - tag.get_height()) // 2))
        dst.blit(img, (left + tag.get_width() + 8, r.y + 3))
        self.hits.append((r, "input", name))


def draw_badges(
    dst: pygame.Surface,
    font: pygame.font.Font,
    key_rects: dict[str, tuple[int, int, int, int]],
    scale: float,
    margin: int,
    pad_map: PadMap,
    selected: str | None,
    pressed: set[str],
) -> None:
    """本体の絵のキーに、割り当ててある入力の札を右下に出す(キーの字を隠さないように)。
    key_rectsは絵の中のキーの範囲で、scaleとmarginで窓の座標に直す"""
    by_key: dict[str, list[str]] = {}
    for name in ORDER:
        key = pad_map.get(name)
        if key is not None and key in key_rects:
            by_key.setdefault(key, []).append(name)
    for key, names in by_key.items():
        _x0, _y0, x1, y1 = key_rects[key]
        on = selected in names or any(n in pressed for n in names)
        img = badge(font, "·".join(LABELS[n] for n in names), on)
        r = img.get_rect()
        r.bottomright = (int((x1 + margin) * scale) + 3, int((y1 + margin) * scale) + 3)
        dst.blit(img, r)

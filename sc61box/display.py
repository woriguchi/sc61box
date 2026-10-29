"""筐体と液晶の描画

筐体の絵は機種ごとのフォルダ(PC-1251はassets/、ほかはassets/pc1245/など)にあり、
液晶の桁数・行数、ドットの大きさと間隔、スイッチの位置はlayout.json、表示記号の位置は
symbols.txtに書いてある。

液晶は次の点を実機に似せた。

* 点灯ドットは濃い青紫。消灯ドットもマルチプレックス駆動の電圧で薄く見え、電源を切ると消える。
* ドットと表示記号は、反射板に落ちた影が右下にずれて見える。
* 応答が遅いので、動くものは尾を引く。液晶の分子の傾きは時定数(TAU_RISE_MS、TAU_FALL_MS)で
  電圧に追いつき、見た目の濃さは傾きがOPACITY_LO〜OPACITY_HIのあいだで急に変わる。
  消えかけのドットは少しのあいだ濃いまま残り、そのあと短い時間で消える。
* Cポートのビット0で表示を切ると、液晶全体が消える。
"""

import json
import math
import os

import pygame
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .machine import BASE_MODEL

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

MARGIN = 28  # 本体のまわりの机の幅

# PC-1251の絵の寸法(Panelはどの機種もlayout.jsonの値を使う)
with open(os.path.join(ASSETS, "keys.json")) as _f:
    IMG_H = json.load(_f)["height"]
IMG_W = 1425
OUT_W, OUT_H = IMG_W + 2 * MARGIN, IMG_H + 2 * MARGIN
CORNER_R = 8  # 本体の角の丸み
CELLS, CW, H = 24, 5, 7
W = CELLS * CW  # 120列
DOT, PITCH = 5, 7
PHYS_W = CELLS * (CW + 1) - 1
MAT_W = PHYS_W * PITCH - 1
MAT_H = H * PITCH - 1
MAT_X, MAT_Y = 152, 160  # 本体の絵(body.png)での液晶の1桁目の左上
ANN_Y, ANN_H = 125, 18


def asset_dir(model: str = "1251") -> str:
    model = BASE_MODEL.get(model, model)
    return ASSETS if model == "1251" else os.path.join(ASSETS, f"pc{model}")


def asset_path(model: str, name: str) -> str:
    """絵のファイル。RAMの範囲だけが違う機種は元の機種の絵を使い、型番を刷り替えた本体の絵
    (body_top.png)だけをその機種のフォルダに置く"""
    own = os.path.join(ASSETS, f"pc{model}", name)
    if model in BASE_MODEL and os.path.exists(own):
        return own
    return os.path.join(asset_dir(model), name)


def layout(model: str = "1251") -> dict:
    """液晶とスイッチの配置(assets/…/layout.json)"""
    with open(asset_path(model, "layout.json")) as f:
        return json.load(f)


def body_size(model: str = "1251") -> tuple[int, int]:
    """本体の絵の大きさ"""
    return tuple(layout(model).get("size", (IMG_W, IMG_H)))  # type: ignore[return-value]


def out_size(model: str = "1251") -> tuple[int, int]:
    """机を含めた絵の大きさ"""
    w, h = body_size(model)
    return w + 2 * MARGIN, h + 2 * MARGIN


DOT_INK = (28, 36, 64)
SHADOW_INK = (40, 48, 44)
OFF_ALPHA = 30  # 消灯ドットの濃さ
ON_ALPHA = 238
SHADOW_ALPHA = 60  # 反射板に落ちる影の濃さ(点灯時)
SHADOW_DX, SHADOW_DY = 2, 2  # 影のずれ(px)
ANN_SHADOW_PAD = 4  # 表示記号の影が、記号の段の下へはみ出す幅
LEVELS = 8
TAU_RISE_MS = 30.0  # 分子の傾きが電圧に追いつく時定数(点くとき)
TAU_FALL_MS = 100.0  # 消えるとき
OPACITY_LO, OPACITY_HI = 0.22, 0.78  # 傾きがこのあいだで、見た目の濃さが0から1へ変わる


def _opacity_table() -> list[int]:
    """傾き(0〜1を256段)から、ドットの濃さの段(0〜LEVELS-1)を引く表"""
    out = []
    for i in range(256):
        t = min(1.0, max(0.0, (i / 255 - OPACITY_LO) / (OPACITY_HI - OPACITY_LO)))
        out.append(int(t * t * (3 - 2 * t) * (LEVELS - 1) + 0.5))
    return out


OPACITY = _opacity_table()


def _surface(img: Image.Image) -> pygame.Surface:
    mode = img.mode if img.mode in ("RGB", "RGBA") else "RGBA"
    img = img.convert(mode)
    s = pygame.image.frombytes(img.tobytes(), img.size, mode)
    return s.convert_alpha() if mode == "RGBA" else s.convert()


class Panel:
    def __init__(self, model: str = "1251"):
        def path(name: str) -> str:
            return asset_path(model, name)

        lay = layout(model)
        self.img_w, self.img_h = body_size(model)
        self.out_w, self.out_h = out_size(model)
        self.corner = lay.get("corner", CORNER_R)
        self.cells = lay["cells"]
        self.lines = lay.get("lines", 1)
        # 1行のドットの段数と、1桁の列数。PC-1350は1列を1桁とみる(8段×4行、150桁)
        self.line_rows = lay.get("line_rows", H)
        self.cw = lay.get("cell_width", CW)
        self.w = self.cells * self.cw  # 1行の列の数
        self.mat_x, self.mat_y = lay["mat"]
        self.dot_w, self.dot_h = lay["dot"]
        self.pitch_x, self.pitch_y = lay["pitch"]
        # 桁の左端から次の桁の左端まで。書いてなければ、桁の間は1ドットぶん
        self.cell_pitch = lay.get("cell_pitch", (self.cw + 1) * self.pitch_x)
        self.line_pitch = lay.get("line_pitch", 0)  # 行の間隔(2行の液晶)
        self.ann_y, self.ann_h = lay["ann"]
        # 右端と下端のドットの外に1pxの余白を含む
        self.col_x = [self._col_x(x) for x in range(self.w)]
        self.mat_w = self.col_x[-1] + self.dot_w + 1
        self.mat_h = (
            (self.lines - 1) * self.line_pitch
            + self.line_rows * self.pitch_y
            - self.pitch_y
            + self.dot_h
            + 1
        )
        with open(path("keys.json")) as f:
            keys = json.load(f)
        self.key_rects = {k: tuple(v) for k, v in keys["keys"].items()}
        self.body_h = keys["top"]  # 液晶部の高さ。その下がキーボードの絵
        self.body = Image.open(path("body_top.png")).convert("RGB")
        self.sw_xy = tuple(lay["switch_xy"])
        self.switch_area = tuple(lay["switch_area"])  # クリックでスイッチが動く範囲
        self.switch_stops = [(m, y) for m, y in lay["switch_stops"]]  # 段の中心のy
        self.switch = {
            m: _surface(Image.open(path(f"switch_{m}.png"))) for m, _y in self.switch_stops
        }
        self.out = pygame.Surface((self.out_w, self.out_h))
        self.out.blit(_surface(self._desk()), (0, 0))
        self.rim = _surface(self._rim())
        self.canvas = pygame.Surface((self.img_w, self.img_h))
        self.canvas.blit(_surface(self.body), (0, 0))
        kb_up = Image.open(path("keyboard_up.png")).convert("RGB")
        kb_down = Image.open(path("keyboard_down.png")).convert("RGB")
        self.canvas.blit(_surface(kb_up), (0, self.body_h))
        self.key_up = {}
        self.key_down = {}
        for name, (x0, y0, x1, y1) in self.key_rects.items():
            box = (x0, y0 - self.body_h, x1, y1 - self.body_h)
            self.key_up[name] = _surface(kb_up.crop(box))
            self.key_down[name] = _surface(kb_down.crop(box))
        self.shown_down: set[str] = set()
        self.glass = _surface(self._glass())
        self.grid = self._grid()
        self.grid_level = 0.0
        mx = self.mat_x
        self.dots = [self._dot(k) for k in range(LEVELS)]
        self.shadows = [self._shadow(k) for k in range(LEVELS)]
        self.symbols = {}
        # 記号の下地。影が右下へはみ出す分も含めて、毎フレーム貼り直す
        self.sym_bg: list[tuple[pygame.Surface, tuple[int, int]]] = []
        with open(path("symbols.txt")) as f:
            for line in f:
                # 名前、ドットの左端からのx、絵の上端からのy(なければann_y)
                name, x, *rest = line.split()
                y = int(rest[0]) if rest else self.ann_y
                mask = Image.open(path(f"sym_{name}.png")).convert("L")
                imgs = []
                for k in range(LEVELS):
                    a = int(ON_ALPHA * k / (LEVELS - 1))
                    im = Image.new("RGBA", mask.size, DOT_INK + (0,))
                    im.putalpha(mask.point(lambda v, a=a: v * a // 255))
                    imgs.append(_surface(im))
                ghost = Image.new("RGBA", mask.size, DOT_INK + (0,))
                ghost.putalpha(mask.point(lambda v: v * OFF_ALPHA // 2 // 255))
                shadows = [self._sym_shadow(mask, k) for k in range(LEVELS)]
                self.symbols[name] = (mx + int(x), y, imgs, shadows, _surface(ghost))
                sx = mx + int(x)
                box = (sx - 2, y - 2, sx + mask.width + 4, y + self.ann_h + ANN_SHADOW_PAD)
                self.sym_bg.append((_surface(self.body.crop(box)), box[:2]))
        self.level = [[0.0] * self.w for _ in range(self.line_rows * self.lines)]
        self.sym_level = {n: 0.0 for n in self.symbols}
        self.set_fps(30)

    def lcd_box(self) -> tuple[int, int, int, int]:
        """机を含めた絵の中で、液晶のドットと表示記号を囲む枠(録画で拡大する範囲)"""
        x0, y0 = self.mat_x, self.mat_y
        x1, y1 = x0 + self.mat_w, y0 + self.mat_h
        for sx, sy, imgs, _shadows, _ghost in self.symbols.values():
            w, h = imgs[0].get_size()
            x0, y0 = min(x0, sx), min(y0, sy)
            x1, y1 = max(x1, sx + w), max(y1, sy + h)
        # PC-1261は液晶のすぐ下に記号の名前が刷ってあるので、下は狭くする
        return (MARGIN + x0 - 16, MARGIN + y0 - 6, MARGIN + x1 + 16, MARGIN + y1 + 4)

    def set_fps(self, fps: float, persist: float = 1.0) -> None:
        dt = 1000.0 / fps
        if persist <= 0:
            self.rise = self.fall = 1.0
        else:
            self.rise = 1.0 - math.exp(-dt / (TAU_RISE_MS * persist))
            self.fall = 1.0 - math.exp(-dt / (TAU_FALL_MS * persist))

    def _col_x(self, x: int) -> int:
        """左からx列目のドットの左端(マトリクスの左端から)"""
        cw = self.cw
        return int(round((x // cw) * self.cell_pitch)) + (x % cw) * self.pitch_x

    def _row_y(self, y: int) -> int:
        """上からy行目のドットの上端"""
        r = self.line_rows
        return (y // r) * self.line_pitch + (y % r) * self.pitch_y

    # ---- 下ごしらえ ----
    def _desk(self) -> Image.Image:
        """机の上に置いた本体の影"""
        ow, oh = self.out_w, self.out_h
        im = Image.new("RGB", (ow, oh), (46, 47, 50))
        d = ImageDraw.Draw(im)
        for y in range(oh):
            t = y / (oh - 1)
            d.line([(0, y), (ow, y)], fill=(int(58 - 16 * t), int(59 - 16 * t), int(63 - 16 * t)))
        sh = Image.new("L", (ow, oh), 0)
        ImageDraw.Draw(sh).rounded_rectangle(
            [MARGIN + 4, MARGIN + 10, MARGIN + self.img_w + 4, MARGIN + self.img_h + 12],
            radius=self.corner,
            fill=200,
        )
        sh = sh.filter(ImageFilter.GaussianBlur(11))
        im.paste(Image.new("RGB", im.size, (8, 8, 10)), (0, 0), sh)
        return im

    def _rim(self) -> Image.Image:
        """本体の角の外側(机の色)と、縁の面取りの光と影"""
        img_w, img_h, corner = self.img_w, self.img_h, self.corner
        desk = self._desk().crop((MARGIN, MARGIN, MARGIN + img_w, MARGIN + img_h)).convert("RGBA")
        inside = Image.new("L", (img_w, img_h), 0)
        ImageDraw.Draw(inside).rounded_rectangle(
            [0, 0, img_w - 1, img_h - 1], radius=corner, fill=255
        )
        out = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        out.paste(desk, (0, 0), ImageChops.invert(inside))
        # 面取りは上と左が明るく、下と右が暗い
        edge = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        ed = ImageDraw.Draw(edge)
        ed.rounded_rectangle(
            [0, 0, img_w - 1, img_h - 1], radius=corner, outline=(250, 250, 248, 120), width=1
        )
        ed.rounded_rectangle(
            [1, 1, img_w - 2, img_h - 2], radius=corner - 1, outline=(255, 255, 255, 40), width=1
        )
        low = Image.linear_gradient("L").resize((img_w, img_h))  # 下ほど濃い影
        dark = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        ImageDraw.Draw(dark).rounded_rectangle(
            [0, 0, img_w - 1, img_h - 1], radius=corner, outline=(60, 60, 58, 170), width=2
        )
        dark.putalpha(ImageChops.multiply(dark.getchannel("A"), low))
        edge = Image.alpha_composite(edge, dark)
        edge.putalpha(ImageChops.multiply(edge.getchannel("A"), inside))
        return Image.alpha_composite(out, edge)

    def _glass(self) -> Image.Image:
        mx, my = self.mat_x, self.mat_y
        box = (mx - 4, my - 4, mx + self.mat_w + 4, my + self.mat_h + 4)
        return self.body.crop(box).convert("RGB")

    def _grid(self) -> pygame.Surface:
        """消灯ドットの薄い格子(電源が入っているあいだだけ重ねる)"""
        ov = Image.new("RGBA", (self.mat_w + 8, self.mat_h + 8), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        dw, dh = self.dot_w, self.dot_h
        for y in range(self.line_rows * self.lines):
            for x in range(self.w):
                px = 4 + self.col_x[x]
                py = 4 + self._row_y(y)
                d.rectangle([px, py, px + dw - 1, py + dh - 1], fill=DOT_INK + (OFF_ALPHA,))
        return _surface(ov)

    def _dot(self, k: int) -> pygame.Surface:
        a = int(OFF_ALPHA + (ON_ALPHA - OFF_ALPHA) * k / (LEVELS - 1))
        dw, dh = self.dot_w, self.dot_h
        im = Image.new("RGBA", (dw, dh), DOT_INK + (a,))
        # 角はわずかに丸い
        for x, y in ((0, 0), (dw - 1, 0), (0, dh - 1), (dw - 1, dh - 1)):
            im.putpixel((x, y), DOT_INK + (int(a * 0.55),))
        return _surface(im)

    @staticmethod
    def _blurred(mask: Image.Image, k: int, bottom: int | None = None) -> pygame.Surface:
        """maskの形の影(濃さの段k)。まわりに3pxの余白をつけてぼかす。bottomがあれば、
        その高さで下を切る"""
        a = int(SHADOW_ALPHA * k / (LEVELS - 1))
        m = Image.new("L", (mask.width + 6, mask.height + 6), 0)
        m.paste(mask, (3, 3))
        m = m.filter(ImageFilter.GaussianBlur(1.1)).point(lambda v: v * a // 255)
        if bottom is not None:
            m = m.crop((0, 0, m.width, bottom))
        im = Image.new("RGBA", m.size, SHADOW_INK + (0,))
        im.putalpha(m)
        return _surface(im)

    def _shadow(self, k: int) -> pygame.Surface:
        return self._blurred(Image.new("L", (self.dot_w, self.dot_h), 255), k)

    def _sym_shadow(self, mask: Image.Image, k: int) -> pygame.Surface:
        """表示記号の影。下は貼り直す下地の範囲で切る"""
        return self._blurred(mask, k, 3 - SHADOW_DY + self.ann_h + ANN_SHADOW_PAD)

    # ---- 1フレーム ----
    def key_at(self, x: float, y: float) -> str | None:
        for name, (x0, y0, x1, y1) in self.key_rects.items():
            if x0 <= x < x1 and y0 <= y < y1:
                return name
        return None

    def draw(
        self,
        columns: list[int],
        symbols: set[str],
        on: bool,
        mode: str,
        pressed: set[str] | frozenset[str] = frozenset(),
        powered: bool = True,
        duty: dict[int, list[float]] | None = None,
    ) -> pygame.Surface:
        """1フレームぶん描く。dutyは、このフレームのあいだに中身が変わった列の、各ドット
        (ビット0〜7)が点いていた時間の割合。その列のドットは、割合を目当てにして明るさを
        近づける(書き換えの途中の短い中身が、1フレームまるごと出ないように)。ほかの列は
        columnsで描く"""
        dst = self.canvas
        dst.blit(self.switch[mode], self.sw_xy)
        rects = self.key_rects
        pressed = {k for k in pressed if k in rects}
        if pressed != self.shown_down:
            for k in self.shown_down - pressed:
                dst.blit(self.key_up[k], rects[k][:2])
            for k in pressed - self.shown_down:
                dst.blit(self.key_down[k], rects[k][:2])
            self.shown_down = pressed
        mx, my = self.mat_x, self.mat_y
        dst.blit(self.glass, (mx - 4, my - 4))
        rise, fall = self.rise, self.fall
        g = self.grid_level
        g = g + (1.0 - g) * rise if powered else g - g * fall
        self.grid_level = g = 0.0 if g < 0.01 else g
        if g:
            self.grid.set_alpha(int(255 * g + 0.5))
            dst.blit(self.grid, (mx - 4, my - 4))
        opacity = OPACITY
        level = self.level
        todo = []
        w = self.w
        col_x = self.col_x
        r = self.line_rows
        mixed = duty if on and duty else None
        for y in range(r * self.lines):
            lrow = level[y]
            bit = 1 << (y % r)
            base = (y // r) * w
            py = my + self._row_y(y)
            for x in range(w):
                v = lrow[x]
                share = mixed.get(base + x) if mixed else None
                if share is not None:
                    t = share[y % r]
                    v += (t - v) * (rise if t > v else fall)
                    if v < 0.004:
                        v = 0.0
                elif on and columns[base + x] & bit:
                    v += (1.0 - v) * rise
                else:
                    v -= v * fall
                    if v < 0.004:
                        v = 0.0
                lrow[x] = v
                k = opacity[int(v * 255)]
                if k:
                    todo.append((mx + col_x[x], py, k))
        sh = self.shadows
        for px, py, k in todo:  # 影を先に、ドットを後に重ねる
            dst.blit(sh[k], (px - 3 + SHADOW_DX, py - 3 + SHADOW_DY))
        dots = self.dots
        for px, py, k in todo:
            dst.blit(dots[k], (px, py))

        for bg, pos in self.sym_bg:
            dst.blit(bg, pos)
        lit = []
        for name, (x, y, imgs, shadows, ghost) in self.symbols.items():
            v = self.sym_level[name]
            if on and name in symbols:
                v += (1.0 - v) * rise
            else:
                v -= v * fall
            self.sym_level[name] = v
            if g:
                ghost.set_alpha(int(255 * g + 0.5))
                dst.blit(ghost, (x, y))
            k = OPACITY[int(v * 255)]
            if k:
                lit.append((x, y, imgs[k], shadows[k]))
        for x, y, _img, shadow in lit:
            dst.blit(shadow, (x - 3 + SHADOW_DX, y - 3 + SHADOW_DY))
        for x, y, img, _shadow in lit:
            dst.blit(img, (x, y))
        self.out.blit(dst, (MARGIN, MARGIN))
        self.out.blit(self.rim, (MARGIN, MARGIN))
        return self.out

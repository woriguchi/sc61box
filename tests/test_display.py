"""本体の絵(display.Panel)の描き方"""

import random

import helpers  # noqa: F401 (SDLを画面なしにする)
import pygame
import pytest

from sc61box import display

MODELS = ["1251", "1245", "1250", "1255", "1260", "1261", "1262", "1350"]


@pytest.fixture(autouse=True)
def _window():
    pygame.init()
    pygame.display.set_mode((8, 8))
    yield
    pygame.quit()


@pytest.mark.parametrize("model", MODELS)
def test_rim_is_clear_inside_bands(model):
    """縁の絵は、四辺の帯(rim_parts)の外では透明。帯だけを重ねても同じ絵になる"""
    p = display.Panel(model)
    w, h = p.rim.get_size()
    clear = pygame.Surface((w, h), pygame.SRCALPHA)
    for part, (x, y) in p.rim_parts:
        clear.blit(part, (x - display.MARGIN, y - display.MARGIN))
    assert pygame.image.tobytes(clear, "RGBA") == pygame.image.tobytes(p.rim, "RGBA")


@pytest.mark.parametrize("model", ["1251", "1262", "1350"])
def test_skipped_frames_match_full_redraw(model):
    """見え方が前のフレームと同じなら描き直さないが、毎回描き直したときと同じ絵になる
    (液晶の中身、表示記号、押したキー、スイッチ、電源、ドットの並べ方を変えながら)"""
    a, b = display.Panel(model), display.Panel(model)
    rng = random.Random(model)
    n = a.w * a.lines
    cols = [0] * n
    syms: set[str] = set()
    pressed: set[str] = set()
    mode, on, powered = a.switch_stops[0][0], True, True
    skipped = 0
    for _ in range(150):
        r = rng.random()
        if r < 0.2:
            cols[rng.randrange(n)] = rng.randrange(256)
        elif r < 0.25:
            syms = set(rng.sample(list(a.symbols), 2))
        elif r < 0.3:
            pressed = set(rng.sample(list(a.key_rects), 1))
        elif r < 0.33:
            mode = rng.choice(a.switch_stops)[0]
        elif r < 0.36:
            on = not on
        elif r < 0.38:
            powered = not powered
        elif r < 0.4 and a.can_pack:
            a.set_packed(not a.packed)
            b.set_packed(a.packed)
        b.shown = None  # bは毎回描き直す
        before = a.shown
        out_a = a.draw(cols, syms, on, mode, pressed, powered)
        skipped += a.shown is before
        out_b = b.draw(cols, syms, on, mode, pressed, powered)
        assert pygame.image.tobytes(out_a, "RGB") == pygame.image.tobytes(out_b, "RGB")
    assert skipped > 20


def _dot_level(p: display.Panel) -> int:
    """左上のドットの濃さの段(0〜LEVELS-1)"""
    xy = (p.mat_x + p.col_x[0], p.mat_y + p.row_y[0])
    return next((k for x, y, k in p.shown[2] if (x, y) == xy), 0) if p.shown else 0


def _blink(
    p: display.Panel, period: float, frames: int, fps: int = 30, phase: float = 0.0
) -> list[int]:
    """左上のドットを period msごとに点け消しして、フレームごとの濃さを返す。phaseは点滅を
    フレームの区切りからずらす時間(ms)"""
    cols = [0] * (p.w * p.lines)
    dt = 1000 / fps
    out = []
    for n in range(frames):
        # 区切りは整数のマイクロ秒で数える(浮動小数点の端数で止まらないように)
        t, t1, lit, per = (
            round((n * dt + phase) * 1000),
            round(((n + 1) * dt + phase) * 1000),
            0.0,
            round(period * 1000),
        )
        while t < t1:
            nxt = min(t1, (t // per + 1) * per)
            if t // per % 2 == 0:
                lit += (nxt - t) / (dt * 1000)
            t = nxt
        p.draw(cols, set(), True, p.switch_stops[0][0], duty={0: [lit] + [0.0] * 7})
        out.append(_dot_level(p))
    return out


@pytest.mark.parametrize("phase", [0.0, 1000 / 60])
@pytest.mark.parametrize("period", [33.3, 33.33, 40, 50])
def test_alternate_frames_do_not_flicker(period, phase):
    """1フレームおきに描くゲーム(20〜30fps)を30fpsで描いても、ドットの濃さがフレームの区切りとの
    ずれで大きく揺れない(実機の液晶は応答が遅いので、落ち着いた絵に見える)。周期がフレームに
    近い点滅は、区切りとの位置関係がゆっくり変わるので、長く動かし、半フレームずらしても調べる。
    点いていた時間の割合をそのまま目当てにすると、3〜7段で揺れていた"""
    levels = _blink(display.Panel("1350"), period, 600, phase=phase)[30:]
    assert max(levels) - min(levels) <= 2 and min(levels) >= 5


def test_duty_over_one_is_clamped():
    """点いていた時間の割合が1を超えても(状態の復元などで)、描くときに範囲の外を引かない"""
    p = display.Panel("1350")
    cols = [0] * (p.w * p.lines)
    for _ in range(10):
        p.draw(cols, set(), True, p.switch_stops[0][0], duty={0: [1.38] + [0.0] * 7})


def _pulse(p: display.Panel, share: float, frames: int = 6) -> list[int]:
    """左上のドットを1フレームのあいだだけshareの割合で点け、そのフレームからの濃さを返す"""
    cols = [0] * (p.w * p.lines)
    mode = p.switch_stops[0][0]
    for _ in range(10):
        p.draw(cols, set(), True, mode)
    out = []
    for n in range(frames):
        p.draw(cols, set(), True, mode, duty={0: [share if n == 0 else 0.0] + [0.0] * 7})
        out.append(_dot_level(p))
    return out


def test_single_short_pulse_is_faint():
    """11 msだけ1回点けたドットは、続けて11 ms点けたときと同じく見えない(速く点滅するときの
    落ち着く値を目当てにすると、濃さ2で描いていた)"""
    assert max(_pulse(display.Panel("1350"), 11 / (1000 / 30))) == 0


def test_duty_without_persistence_is_raw_share():
    """残像を描かないときは、点いていた時間の割合をそのまま傾きにする"""
    p = display.Panel("1350")
    p.set_fps(30, 0)
    _pulse(p, 0.5, frames=1)
    assert p.level[0][0] == 0.5


def test_tiny_persistence_does_not_break_duty():
    """残像をごく短くして点く・消える速さが無限大になっても、途中の点灯を描ける"""
    p = display.Panel("1350")
    p.set_fps(30, 1e-309)
    _pulse(p, 0.5, frames=1)
    assert p.level[0][0] == pytest.approx(
        0.5 / (0.5 + 0.5 * display.TAU_RISE_MS / display.TAU_FALL_MS)
    )


def test_duty_column_rises_like_others_with_long_persistence():
    """残像を長くしても(persist=300)、別のビットを書いたので記録の対象になった列の点きっぱなしの
    ドットが、ほかの列のドットと同じように立ち上がる(小さい傾きを0に丸めていた)"""
    p = display.Panel("1350")
    p.set_fps(30, 300)
    mode = p.switch_stops[0][0]
    cols = [0] * (p.w * p.lines)
    cols[0] = cols[1] = 0x01
    for _ in range(100):
        p.draw(cols, set(), True, mode, duty={0: [1.0, 0.5] + [0.0] * 6})
    assert p.level[0][0] > 0.3 and p.level[0][0] == pytest.approx(p.level[0][1])


def test_moving_dot_trail_is_short():
    """点けたドットは2フレームで濃くなり、消したドットは5フレームで見えなくなる"""
    p = display.Panel("1350")
    cols = [0] * (p.w * p.lines)
    mode = p.switch_stops[0][0]
    for _ in range(10):
        p.draw(cols, set(), True, mode)
    cols[0] = 1
    lit = []
    for _ in range(3):
        p.draw(cols, set(), True, mode)
        lit.append(_dot_level(p))
    assert lit[1] >= display.LEVELS - 2
    cols[0] = 0
    off = []
    for _ in range(6):
        p.draw(cols, set(), True, mode)
        off.append(_dot_level(p))
    assert off[4] == 0

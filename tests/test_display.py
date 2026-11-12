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

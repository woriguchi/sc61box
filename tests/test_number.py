"""数の読み書き・切り捨て・計算・角度・乱数・数と字の並びの変換"""

import math
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace

from sc61box.machine import new_machine
from sc61box.number import (
    angle_turn,
    arc_value,
    compute,
    cut,
    get_num,
    leading_text,
    number_text,
    power,
    put_num,
    random_value,
    to_degrees,
    to_dms,
    trig_value,
)


def test_num_round_trip():
    ram = bytearray(8)
    for v in ("1", "-0.5", "123456789012", "9.99999999999E99", "-1E-99"):
        put_num(ram, 0, Decimal(v))
        assert get_num(ram, 0) == Decimal(v), v
    ram[2] = 0xA0  # 仮数がBCDでなければ0
    assert get_num(ram, 0) == 0


def test_cut():
    assert cut(Decimal("-1.99999999999999")) == Decimal("-1.99999999999")
    assert cut(Decimal("0.66666666666666"), 10, ROUND_HALF_UP) == Decimal("0.6666666667")


def test_compute_range():
    """1E100以上と計算できないものはNone、1E−99より小さければ0"""
    assert compute(lambda: Decimal(1) / 3) == Decimal("0.333333333333")
    assert compute(lambda: Decimal("1E99") * 10) is None
    zero = Decimal(0)
    assert compute(lambda: Decimal(1) / zero) is None
    assert compute(lambda: None) is None
    assert compute(lambda: Decimal("1E-99") / 10) == 0


def test_power():
    assert power(Decimal(-2), Decimal(3)) == -8
    assert power(Decimal(0), Decimal(0)) is None
    assert power(Decimal(-2), Decimal("0.5")) is None


def test_angle_turn_from_lcd_symbols():
    m = new_machine("1251", rom=False)
    m.mem[0xF83C], m.mem[0xF83D] = 0x00, 0x00
    assert angle_turn(m) == 360
    m.mem[0xF83C], m.mem[0xF83D] = 0x00, 0x04
    assert angle_turn(m) is None
    m.mem[0xF83C] = 0x04
    assert angle_turn(m) == 400
    m = new_machine("1261", rom=False)
    m.mem[0x207C] = 0x02
    assert angle_turn(m) is None
    m.mem[0x207C] = 0x04
    assert angle_turn(m) == 400


def test_trig_and_arc():
    sin = (math.sin, (0, 1, 0, -1))
    assert trig_value(*sin, Decimal(90), Decimal(360)) == 1
    assert trig_value(*sin, Decimal(30), Decimal(360)) == Decimal("0.5")
    assert trig_value(*sin, Decimal("1E10"), Decimal(360)) is None
    assert trig_value(math.tan, (0, None, 0, None), Decimal(100), Decimal(400)) is None
    assert arc_value(math.atan, Decimal(1), Decimal(360)) == 45
    assert arc_value(math.atan, Decimal(1), None) == Decimal("0.785398163397448")


def test_degrees_and_dms():
    assert to_degrees(Decimal("30.3")) == Decimal("30.5")
    assert to_degrees(Decimal("-12.3")) == Decimal("-12.5")
    assert to_dms(Decimal("30.5")) == Decimal("30.3")


def test_random_value():
    m = SimpleNamespace(rnd_seed=1)
    assert {int(random_value(m, Decimal(6))) for _ in range(200)} == set(range(1, 7))
    assert all(0 < random_value(m, Decimal("0.5")) < 1 for _ in range(20))
    other = SimpleNamespace(rnd_seed=12345)
    assert random_value(m, Decimal(-3)) == random_value(other, Decimal(-3))


def test_number_text():
    """10桁までは小数、越えれば指数(空白か−のあとに2桁)"""
    assert number_text(Decimal(0)) == ["0"]
    assert number_text(Decimal("-12.5")) == list("-12.5")
    assert number_text(Decimal("12345678901")) == [*"1.23456789", "[E]", " ", "1", "0"]
    assert number_text(Decimal("0.000000000012")) == [*"1.2", "[E]", "-", "1", "1"]


def test_leading_text_exponent():
    """exp_spacesなら指数の中の空白を飛ばし、loose_expなら指数の符号はいくつ続いてもよく、数字の
    あいだのEも飛ばす"""
    assert leading_text(["1", "[E]", " ", "2"]) == 1
    assert leading_text(["1", "[E]", " ", "2"], exp_spaces=True) == 100
    assert leading_text(["1", "[E]", "-", "-", "2"]) == 1
    assert leading_text(["1", "[E]", "-", "-", "2"], loose_exp=True) == 100
    assert leading_text(["1", "[E]", "1", "[E]", "2"]) == 10
    assert leading_text(["1", "[E]", "1", "[E]", "2"], loose_exp=True) == Decimal("1E12")
    assert leading_text(["-", "-", ".", "5"]) == Decimal("0.5")
    assert leading_text(["[E]", "3"]) == 1000

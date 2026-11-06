"""ROMなしで動くCPUコアの試験"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sc61box.sc61860 import SC61860, A, B, Bus  # noqa: E402


class FlatBus(Bus):
    """64KBをすべてRAMとして見せるだけのバス"""

    def __init__(self, code: bytes, at: int = 0):
        self.mem = bytearray(0x10000)
        self.mem[at : at + len(code)] = code

    def read(self, a: int) -> int:
        return self.mem[a]

    def write(self, a: int, v: int) -> None:
        self.mem[a] = v


def run(code: bytes, steps: int, extra: dict[int, bytes] | None = None):
    bus = FlatBus(code)
    for at, data in (extra or {}).items():
        bus.mem[at : at + len(data)] = data
    cpu = SC61860(bus)
    for _ in range(steps):
        cpu.step()
    return cpu, bus


def test_load_and_exchange():
    # LIA 12 / LP 10 / EXAM / LIA 00 / LDM / INCA
    cpu, _ = run(bytes([0x02, 0x12, 0x90, 0xDB, 0x02, 0x00, 0x59, 0x42]), 6)
    assert cpu.ram[0x10] == 0x12  # EXAMで(P)に12が入る
    assert cpu.ram[A] == 0x13  # LDMで12を読み戻して1足した


def test_call_and_return():
    # CALL 0010 / (0010) LIA 2A / RTN
    cpu, _ = run(bytes([0x78, 0x00, 0x10]), 3, {0x10: bytes([0x02, 0x2A, 0x37])})
    assert cpu.ram[A] == 0x2A
    assert cpu.pc == 3


def test_count_down_loop():
    # LIB 03 / LIA 00 / INCA / DECB / JRNZM (INCAへ)
    code = bytes([0x03, 0x03, 0x02, 0x00, 0x42, 0xC3, 0x29, 0x03])
    cpu, _ = run(code, 2 + 3 * 3)
    assert cpu.ram[A] == 3 and cpu.ram[B] == 0
    assert cpu.pc == 8


def test_external_memory():
    # LIDP 1234 / LIA 99 / STD / LIA 00 / LDD
    code = bytes([0x10, 0x12, 0x34, 0x02, 0x99, 0x52, 0x02, 0x00, 0x57])
    cpu, bus = run(code, 5)
    assert bus.mem[0x1234] == 0x99
    assert cpu.ram[A] == 0x99


def test_cycles_from_manual():
    # IYS / DYS / IXL
    cpu = SC61860(FlatBus(bytes([0x26, 0x27, 0x24])))
    cpu.ram[4:8] = bytes([0x00, 0x20, 0x00, 0x30])  # X=2000、Y=3000(命令を書き換えないように)
    assert [cpu.step() for _ in range(3)] == [6, 6, 7]


def test_case_table():
    # LIA 07 / PTC 2,0100 / DTC 05:0200, 07:0300, それ以外:0400
    code = bytes(
        [0x02, 0x07, 0x7A, 0x02, 0x01, 0x00, 0x69, 0x05, 0x02, 0x00, 0x07, 0x03, 0x00, 0x04, 0x00]
    )
    cpu = SC61860(FlatBus(code))
    cpu.r = 0x5C
    cycles = [cpu.step() for _ in range(3)]
    assert cycles == [4, 8, 5 + 7 * 2]
    assert cpu.pc == 0x0300
    assert (cpu.ram[0x5B], cpu.ram[0x5A]) == (0x01, 0x00)  # 戻る先の0100


def test_anid_uses_r_minus_1():
    # LIDP 1234 / ANID 0F。(R-1)に書き換える前の(DP)が入る
    bus = FlatBus(bytes([0x10, 0x12, 0x34, 0xD4, 0x0F]))
    bus.mem[0x1234] = 0xAB
    cpu = SC61860(bus)
    cpu.r = 0x5C
    cpu.step()
    cpu.step()
    assert bus.mem[0x1234] == 0x0B
    assert cpu.ram[0x5B] == 0xAB
    assert cpu.r == 0x5C


def test_liih_is_two_bytes():
    # LII 55 / LIIH 00 / LIIH 00 / LIB 25。LIIHはI=H、H=nの2バイト命令で、
    # 2つ続けるとIが0になる
    cpu, _ = run(bytes([0x00, 0x55, 0x72, 0x00, 0x72, 0x00, 0x03, 0x25]), 4)
    assert cpu.ram[0] == 0  # I
    assert cpu.ram[B] == 0x25
    assert cpu.pc == 8


def test_readm_is_one_byte():
    # LP 0F / READM / LII FF。READMは次のバイト(00)を(P)に読み、そのバイトは
    # 命令(LII FF)として残す
    cpu, _ = run(bytes([0x8F, 0x54, 0x00, 0xFF, 0x03, 0x25]), 4)
    assert cpu.ram[0x0F] == 0x00
    assert cpu.ram[0] == 0xFF  # I
    assert cpu.ram[B] == 0x25
    assert cpu.pc == 6


def test_bcd_non_decimal_digits_like_real_machine():
    """ADN・SBNに10進でない桁(A〜F)を与えたときの答えとキャリーが、実機と同じ"""
    for op, before, a, after, carry in (
        (0x0D, 0xF0, 0x10, 0x80, 1),  # SBN
        (0x0D, 0x0F, 0x01, 0x08, 0),
        (0x0D, 0xA0, 0x00, 0x40, 1),
        (0x0D, 0x0A, 0x00, 0x04, 0),
        (0x0D, 0x00, 0x10, 0x90, 1),
        (0x0D, 0x00, 0xE0, 0xC0, 1),
        (0x0D, 0x10, 0x0F, 0xFB, 0),  # 6を引くときに借りが出ても、キャリーは立てない
        (0x0D, 0x20, 0x1F, 0xFB, 0),
        (0x0D, 0x10, 0x0C, 0xFE, 0),
        (0x0D, 0x10, 0x0B, 0xFF, 0),
        (0x0D, 0x15, 0x0F, 0x00, 0),
        (0x0D, 0x00, 0x0F, 0x8B, 1),
        (0x0C, 0xF0, 0x10, 0x60, 1),  # ADN
        (0x0C, 0x0A, 0x00, 0x10, 0),
        (0x0C, 0x9F, 0x01, 0x06, 1),
        (0x0C, 0xAA, 0x00, 0x10, 1),
        (0x0C, 0x95, 0x10, 0x05, 1),
    ):
        # LII 00 / LP 08 / ADNかSBN
        cpu = SC61860(FlatBus(bytes([0x00, 0x00, 0x88, op])))
        cpu.ram[8] = before
        cpu.ram[A] = a
        for _ in range(3):
            cpu.step()
        assert (cpu.ram[8], cpu.c) == (after, carry), (hex(op), hex(before), hex(a))


def test_bcd_decimal_digits():
    """10進の値どうしなら、10進で足し引きした答えになる"""
    from sc61box.sc61860 import _bcd_add, _bcd_sub

    def dec(v):
        return (v >> 4) * 10 + (v & 0x0F)

    def bcd(n):
        return (n // 10) << 4 | n % 10

    for x in range(100):
        for y in range(100):
            for c in (0, 1):
                s, k = divmod(x + y + c, 100)
                assert _bcd_add(bcd(x), bcd(y), c) == (bcd(k), s)
                d = x - y - c
                assert _bcd_sub(bcd(x), bcd(y), c) == (bcd(d % 100), int(d < 0))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

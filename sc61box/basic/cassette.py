"""カセットの記録の形のうち、系統によらない部分(ROMのある本体がCポートに出した音の切り替えを
読んで決めた)

1ビットは2msで、1は4kHz、0は2kHzの音。初めに1を4000ビット(8秒)続ける。1バイトは上位の
4ビット、下位の4ビットの順に、0のビットのあと4ビットを下位から送り、そのあとに1のビットを
いくつか続ける(数は系統と、頭か中身かで違う)。ファイルは、種類の1バイト、名前の8バイトと
チェックサムの1バイト、中身の順。名前は「F5h、名前の字(7字まで)、00h」の8バイトを逆に並べ、
各バイトの上位と下位の4ビットを入れ替えたもの。チェックサムは4ビットずつ足した和(上位の
4ビットを足してキャリーが出たら1を足す)。中身の形とチェックサムの置き方は、系統ごとの
cassette.py(pc1251/、pc1261/)にある。
"""

from dataclasses import dataclass

from ..machine import CLOCK

BIT = CLOCK * 2 // 1000  # 1ビットのサイクル
LEADER = 4000  # 初めの1のビットの数
NAME_SIZE = 7
HEAD = 10  # 種類、名前、名前のチェックサムのバイト数
ONE, ZERO, QUIET = 3, 2, 0  # Cポートの上位4ビット: 4kHz、2kHz、音なし


def swap(b: int) -> int:
    return (b >> 4) | (b & 0x0F) << 4


def add(check: int, b: int) -> int:
    """チェックサムにバイトbを足す"""
    check += b >> 4
    if check > 0xFF:
        check = (check + 1) & 0xFF
    return (check + (b & 0x0F)) & 0xFF


def checksum(data: bytes, start: int = 0) -> int:
    for b in data:
        start = add(start, b)
    return start


def name_field(name: bytes) -> bytes:
    """名前の8バイト(nameは本体の字のコード)"""
    plain = bytes([0xF5]) + name[:NAME_SIZE]
    plain += bytes(8 - len(plain))
    return bytes(swap(b) for b in reversed(plain))


def read_name(field: bytes) -> bytes:
    plain = bytes(swap(b) for b in reversed(field))
    return plain[1:].split(b"\x00")[0] if plain[:1] == b"\xf5" else b""


def nibble_bits(b: int, stops: tuple[int, int]) -> list[int]:
    """1バイトのビット。stopsは上位・下位の4ビットのあとに続ける1の数"""
    out: list[int] = []
    for nibble, n in ((b >> 4, stops[0]), (b & 0x0F, stops[1])):
        out += [0] + [(nibble >> k) & 1 for k in range(4)] + [1] * n
    return out


@dataclass
class Received:
    """テープから読んだバイトと、読み終えた時刻(再生を始めてからのサイクル)"""

    data: bytes
    times: list[float]

    def at(self, i: int) -> float:
        """i番目のバイトを読み終えた時刻(終わりを越えれば最後のバイトの時刻)"""
        return self.times[min(i, len(self.times) - 1)]


def demodulate(edges: list[float], length: float) -> tuple[list[int], list[float]]:
    """波形の値が変わる時刻から、ビットとその終わりの時刻の並びを作る。半周期が短い(4kHz)
    あいだは1、長い(2kHz)あいだは0とし、続いた時間を2msで割ってビットの数にする"""
    out: list[int] = []
    times: list[float] = []
    run_bit, run_start, last = -1, 0.0, 0.0
    for a, b in zip(edges, edges[1:], strict=False):
        half = b - a
        bit = 1 if half < BIT / 12 else 0 if half < BIT / 4 else -1  # -1は音なし
        if bit != run_bit:
            _flush(out, times, run_bit, run_start, a)
            run_bit, run_start = bit, a
        last = b
    _flush(out, times, run_bit, run_start, last)
    return out, times


def _flush(out: list[int], times: list[float], bit: int, start: float, end: float) -> None:
    if bit < 0:
        return
    n = round((end - start) / BIT)
    for k in range(n):
        out.append(bit)
        times.append(start + (k + 1) * BIT)


def read_bytes(bits_: list[int], times: list[float], start: int = 0) -> tuple[Received, int]:
    """startから、初めの1のビットのあとのバイトを、ビットが途切れるまで読む。(読んだもの,
    次に読み始める位置)"""
    i = start
    n = len(bits_)
    while i < n and bits_[i] == 1:
        i += 1
    data = bytearray()
    at: list[float] = []
    while i + 5 <= n and bits_[i] == 0:
        hi = sum(bits_[i + 1 + k] << k for k in range(4))
        i += 5
        while i < n and bits_[i] == 1:
            i += 1
        if i + 5 > n or bits_[i] != 0:
            break
        lo = sum(bits_[i + 1 + k] << k for k in range(4))
        data.append(hi << 4 | lo)
        at.append(times[i + 4])
        i += 5
        stops = 0
        while i < n and bits_[i] == 1 and stops < 8:
            i += 1
            stops += 1
        if stops >= 8:
            break
    return Received(bytes(data), at), i


def files(tape) -> list[Received]:
    """テープ(tape.TapeIn)にあるファイルを、初めから順に読む"""
    bits_, times = demodulate(tape.edges, tape.length)
    out: list[Received] = []
    i = 0
    while i < len(bits_):
        rec, j = read_bytes(bits_, times, i)
        if rec.data:
            out.append(rec)
        i = max(j, i + 1)
    return out


class ChecksumError(Exception):
    """チェックサムの合わないところ(位置)と、そこまでに読んだ中身。cutなら、チェックサムが
    合わないのではなく、テープが途中で切れている"""

    def __init__(self, at: int, data: bytes = b"", cut: bool = False) -> None:
        super().__init__(at)
        self.at = at
        self.data = data
        self.cut = cut

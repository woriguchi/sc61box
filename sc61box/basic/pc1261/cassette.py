"""PC-1261系とPC-1350のカセットの記録の形(ROMのある本体がCポートに出した音の切り替えを
読んで決めた。共通の部分は..cassette)

- 1バイトは、上位の4ビットのあとに1を1つ。下位の4ビットのあとは、ヘッダ(種類、名前と
  チェックサム、置く場所とチェックサム)では1を5つ、中身では2つ。最後のバイトのあとは1を4つ
  送って音を止める
- ファイルの種類はBASICが70h、マシン語が76h。名前の字はASCII
- マシン語の置く場所は、0、0、0、0、始めの番地(上位、下位)、バイト数−1(上位、下位)の
  8バイトの上位と下位の4ビットを入れ替えたものと、そのチェックサム
- 中身は、BASICならプログラムの行(行番号の上位、下位、長さ、中身、0Dh。MERGEで分けた
  プログラムの区切りのFFhも含む)、マシン語ならデータのあとに、FFhを足したもの。120バイト
  ごとに、その120バイトのチェックサムをはさむ。終わりの120バイトに満たないところは、その
  あとに終わりのマークFFhと、チェックサムを置く
"""

from ..cassette import (  # noqa: F401  (ほかのモジュールがここから使う)
    BIT,
    HEAD,
    NAME_SIZE,
    ONE,
    QUIET,
    ZERO,
    ChecksumError,
    Received,
    checksum,
    files,
    name_field,
    nibble_bits,
    read_name,
    swap,
)

LEADER = 4001  # 初めの1のビットの数(観察)
BASIC, MACHINE = 0x70, 0x76
END = 0xFF  # 中身の終わりのマーク
BLOCK = 120  # 中身にチェックサムをはさむバイト数
HEAD_STOPS, DATA_STOPS, LAST_STOPS = (1, 5), (1, 2), (1, 4)
HEAD_BITS, DATA_BITS = 16, 13  # ヘッダと中身の1バイトのビット数
# CSAVEで、中身の1バイトの何ビット目を送る前にBRKを見るか(下位の4ビットと1つ目の1のあと。観察)
BRK_AT = 12


def place_field(start: int, size: int) -> bytes:
    """マシン語の置く場所の8バイト(始めの番地と、バイト数−1)"""
    last = size - 1
    plain = bytes([0, 0, 0, 0, start >> 8, start & 0xFF, last >> 8, last & 0xFF])
    return bytes(swap(b) for b in plain)


def blocks(data: bytes) -> bytes:
    """中身(終わりのFFhを含む)に120バイトごとにチェックサムをはさむ。終わりのチェックサムの
    前に、終わりのマークを置く"""
    out = bytearray()
    for i in range(0, len(data), BLOCK):
        chunk = data[i : i + BLOCK]
        out += chunk
        if len(chunk) < BLOCK:
            out.append(END)
        out.append(checksum(chunk))
    if len(data) % BLOCK == 0:
        out += bytes([END, 0])
    return bytes(out)


def file_bytes(kind: int, name: bytes, data: bytes, place: bytes = b"") -> bytes:
    """テープに送るバイトの並び(初めの1のビットを除く)。dataはプログラムの行の並びか、
    マシン語のデータ(どちらもFFhを足して送る)"""
    head = name_field(name)
    out = bytes([kind]) + head + bytes([checksum(head)])
    if place:
        out += place + bytes([checksum(place)])
    return out + blocks(data + bytes([END]))


def bits(data: bytes) -> list[int]:
    """送るビットの並び(初めの1のビットを含む)"""
    head = HEAD + (9 if data[:1] == bytes([MACHINE]) else 0)
    out = [1] * LEADER
    for i, b in enumerate(data):
        stops = HEAD_STOPS if i < head else LAST_STOPS if i == len(data) - 1 else DATA_STOPS
        out += nibble_bits(b, stops)
    return out


def checked(data: bytes, i: int):
    """位置iからの中身を、120バイトごとのチェックサムを確かめながら(バイト, 位置)の順に出す。
    チェックサムが合わなければ、そのチェックサムの位置でChecksumError。終わりの120バイトに
    満たないところのチェックサムは、呼ぶ側が確かめる(_ending)"""
    n = 0
    while i < len(data):
        start = i
        for _ in range(BLOCK):
            if i >= len(data):
                return
            yield data[i], i
            i += 1
            n += 1
        if i >= len(data):
            raise ChecksumError(len(data) - 1, cut=True)
        if data[i] != checksum(data[start:i]):
            raise ChecksumError(i)
        i += 1


def _ending(data: bytes, body: bytes, at: int) -> int:
    """中身の終わりのFFh(位置at)のあとの、マークとチェックサムを確かめる。最後に読んだ位置を
    返す"""
    if len(body) % BLOCK == 0:  # 120バイトのチェックサムのあとに、マークと0を置く
        if at + 1 >= len(data) or data[at + 1] != checksum(body[-BLOCK:]):
            raise ChecksumError(min(at + 1, len(data) - 1), body)
        return at + 3
    if at + 2 >= len(data):
        raise ChecksumError(len(data) - 1, body, cut=True)
    if data[at + 2] != checksum(body[len(body) - len(body) % BLOCK :]):
        raise ChecksumError(at + 2, body)
    return at + 2


def basic_body(data: bytes, i: int) -> tuple[bytes, int]:
    """BASICのファイルの中身: 行を、行の頭のFFhのあとにFFh(終わりのマーク)が来るまで読む。
    行の頭のFFhのあとに行が続けば、プログラムの区切り。(行の並び, 最後に読んだ位置)"""
    out = bytearray()
    last = i
    left = 0  # 行の中で、あと読むバイト
    head = 0  # 行の頭の3バイト(行番号と長さ)のうち、読んだ数
    ff_at: int | None = None  # 行の頭で読んだFFhの位置
    try:
        for b, at in checked(data, i):
            last = at
            if ff_at is not None:
                if b == END:
                    return bytes(out[:-1]), _ending(data, bytes(out), ff_at)
                ff_at = None
            out.append(b)
            if left == 0 and head == 0:
                if b == END:
                    ff_at = at
                    continue
                head = 1
            elif head:
                head += 1
                if head == 3:
                    left, head = b, 0
            else:
                left -= 1
    except ChecksumError as e:
        raise ChecksumError(e.at, bytes(out), e.cut) from None
    raise ChecksumError(last, bytes(out), cut=True)


def machine_start(data: bytes, i: int) -> int:
    """マシン語のファイルの、置く場所の始めの番地(途中で切れていれば0)"""
    plain = bytes(swap(b) for b in data[i : i + 8])
    return plain[4] << 8 | plain[5] if len(plain) == 8 else 0


def machine_body(data: bytes, i: int) -> tuple[int, bytes, int]:
    """マシン語のファイルの中身: (始めの番地, データ, 最後に読んだ位置)。最後のデータの
    バイトまで読み、そのあとのチェックサム、終わりのFFhとマークは見ない(観察)"""
    if i + 9 > len(data):
        raise ChecksumError(len(data) - 1, cut=True)
    field = data[i : i + 8]
    if checksum(field) != data[i + 8]:
        raise ChecksumError(i + 8)
    plain = bytes(swap(b) for b in field)
    start = machine_start(data, i)
    size = (plain[6] << 8 | plain[7]) + 1
    out = bytearray()
    last = i + 8
    try:
        for b, at in checked(data, i + 9):
            out.append(b)
            last = at
            if len(out) == size:
                return start, bytes(out), last
    except ChecksumError as e:
        raise ChecksumError(e.at, bytes(out), e.cut) from None
    raise ChecksumError(last, bytes(out), cut=True)

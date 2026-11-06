"""PC-1250・1251・1255、PC-1245のカセットの記録の形(ROMのある本体がCポートに出した音の
切り替えを読んで決めた。共通の部分は..cassette)

1バイトは、上位の4ビットのあとに1を4つ、下位の4ビットのあとに1を5つ続ける。ファイルの種類は
BASICが20h、マシン語が26h。中身のあとに終わりのマーカーF0hを置く。マシン語の中身は、置く場所の
8バイトとチェックサムの1バイトのあとにデータを続ける。中身は8バイトごとにチェックサムの1バイトを
はさむ(終わりの8バイトに満たないところには置かない)。チェックサムは、名前と置く場所は1つずつ、
データは続けて足していき、80バイトごとに0に戻す。
"""

from ..cassette import (  # noqa: F401  (ほかのモジュールがここから使う)
    BIT,
    HEAD,
    LEADER,
    NAME_SIZE,
    ONE,
    QUIET,
    ZERO,
    ChecksumError,
    Received,
    add,
    checksum,
    files,
    name_field,
    nibble_bits,
    read_name,
    swap,
)

STOPS = (4, 5)  # 上位・下位の4ビットのあとの1の数
HEAD_BITS = DATA_BITS = 19  # 1バイトのビット数(頭も中身も同じ)
BRK_AT = 14  # CSAVEで、中身の1バイトの何ビット目を送る前にBRKを見るか(下位の4ビットのあと)
BLOCK = 8  # 中身にチェックサムをはさむバイト数
BASIC, MACHINE = 0x20, 0x26
END = 0xF0
RESTART = 80  # 中身のチェックサムを0に戻すバイト数


def place_field(start: int, size: int) -> bytes:
    """マシン語の置く場所の8バイト(始めの番地と、バイト数−1)"""
    last = size - 1
    plain = bytes([0, 0, 0, 0x60, start >> 8, start & 0xFF, last >> 8, last & 0xFF])
    return bytes(swap(b) for b in plain)


def blocks(data: bytes) -> bytes:
    """8バイトごとにチェックサムをはさんだ中身。チェックサムは80バイトごとに0に戻す"""
    out = bytearray()
    check = 0
    for i in range(0, len(data), 8):
        chunk = data[i : i + 8]
        out += chunk
        check = checksum(chunk, 0 if i % RESTART == 0 else check)
        if len(chunk) == 8:
            out.append(check)
    return bytes(out)


def file_bytes(kind: int, name: bytes, data: bytes, place: bytes = b"") -> bytes:
    """テープに送るバイトの並び(初めの1のビットを除く)"""
    head = name_field(name)
    out = bytes([kind]) + head + bytes([checksum(head)])
    if place:
        out += place + bytes([checksum(place)])
    return out + blocks(data) + bytes([END])


def bits(data: bytes) -> list[int]:
    """送るビットの並び(初めの1のビットを含む)。最後の下位の4ビットのあとは1を3つで
    音を止める(観察)"""
    out = [1] * LEADER
    for b in data:
        out += nibble_bits(b, STOPS)
    if data:
        del out[-2:]
    return out


def checked(data: bytes, i: int):
    """位置iからの中身を、8バイトごとのチェックサムを確かめながら(バイト, 位置)の順に出す。
    チェックサムが合わなければ、そのチェックサムの位置でChecksumError"""
    check = 0
    n = 0
    while i < len(data):
        b = data[i]
        yield b, i
        check = add(0 if n % RESTART == 0 else check, b)
        n += 1
        i += 1
        if n % 8 == 0:
            if i >= len(data):
                raise ChecksumError(len(data) - 1, cut=True)
            if data[i] != check:
                raise ChecksumError(i)
            i += 1


def basic_body(data: bytes, i: int) -> tuple[bytes, int]:
    """BASICのファイルの中身: 行(E0h〜E9hと行番号の下2桁で始まり、00hで終わる)を、行の
    頭がE0h〜E9h以外のバイト(終わりのマーカー)になるまで読む。(行の並び, 最後に読んだ位置)"""
    out = bytearray()
    last = i
    in_line = -1  # 行の中の位置(-1は行の外)
    try:
        for b, at in checked(data, i):
            last = at
            if in_line < 0:
                if not 0xE0 <= b <= 0xE9:
                    return bytes(out), last
                in_line = 0
            out.append(b)
            in_line = -1 if b == 0x00 and in_line >= 2 else in_line + 1
    except ChecksumError as e:
        raise ChecksumError(e.at, bytes(out), e.cut) from None
    raise ChecksumError(last, bytes(out), cut=True)


def machine_start(data: bytes, i: int) -> int:
    """マシン語のファイルの、置く場所の始めの番地(途中で切れていれば0)"""
    plain = bytes(swap(b) for b in data[i : i + 8])
    return plain[4] << 8 | plain[5] if len(plain) == 8 else 0


def machine_body(data: bytes, i: int) -> tuple[int, bytes, int]:
    """マシン語のファイルの中身: (始めの番地, データ, 最後に読んだ位置)"""
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
                if size % 8 == 0:
                    last += 1  # 最後のチェックサムまで読む
                return start, bytes(out), last
    except ChecksumError as e:
        raise ChecksumError(e.at, bytes(out), e.cut) from None
    raise ChecksumError(last, bytes(out), cut=True)

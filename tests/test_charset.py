"""字のコードの表と字の形"""

from sc61box.basictext import CHARS
from sc61box.charset import ASCII, CODES, FONT, FROM_ASCII, glyph


def test_glyph_columns():
    """1バイトが縦の1列で、ビット0が上。描いていない字は空白"""
    assert glyph("A") == bytes([0x7E, 0x09, 0x09, 0x09, 0x7E])
    assert glyph("年") == bytes(5)
    assert all(len(rows) == 7 and all(len(r) == 5 for r in rows) for rows in FONT.values())
    assert all(ch in FONT for ch in CHARS.values())


def test_code_tables():
    assert CODES["A"] == 0x51 and CODES["[E]"] == 0x4B
    assert ASCII[0x51] == 0x41 and ASCII[0x4B] == 0x60 and ASCII[0x17] == 0x5C
    assert len(FROM_ASCII) == len(ASCII)
    assert all(ASCII[code] == a for a, code in FROM_ASCII.items())

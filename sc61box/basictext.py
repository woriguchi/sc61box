"""RAMにあるBASICのプログラムと文字との変換

PC-1251・PC-1245のプログラムは、B830番地(PC-1245はC000番地)のFFのあとに次の形の行が並び、
最後にまたFFが来る。

    E0+百の位  十と一の位(BCD)  中身…  00

中身は本体の文字コード(英字51h〜6Ah、数字40h〜49hなど)と、命令や関数を表す1バイトの
中間コード(7Dh以上)の並び。中間コードと綴りの対応はBASIC ROMの命令の表から読む。
空白はROMが打ち込みのときに捨てるので、文字に戻すときに命令の前後に補う。

PC-1260/1261/1262とPC-1350(S1系のBASIC)は次の形の行が並ぶ。

    行番号(2バイト、上位が先)  長さ(中身と0Dのバイト数)  中身…  0D

中身はASCIIの文字(¥は5Ch、πはFBh、√はFCh)と、1バイトの中間コード(91h〜E5h)の並び。
カナ(A1h〜DFh)は中間コードと重なるので、FEhを前に置いた2バイトで書く。
"""

PROG_START = 0xB830

# 中間コードではない文字
CHARS: dict[int, str] = {
    0x11: " ", 0x12: '"', 0x13: "?", 0x14: "!", 0x15: "#", 0x16: "%", 0x17: "¥", 0x18: "$",
    0x1A: "√", 0x1B: ",", 0x1C: ";", 0x1D: ":", 0x1E: "@", 0x1F: "&",
    0x30: "(", 0x31: ")", 0x32: ">", 0x33: "<", 0x34: "=", 0x35: "+", 0x36: "-",
    0x37: "*", 0x38: "/", 0x39: "^", 0x4A: ".",
    0x4B: "[E]",  # 指数のE(Expキー)。英字のE(55h)とは別の字。PocketToolsと同じ書き方
    0x19: "π",  # 関数のPI(中間コード)とは別の字
}  # fmt: skip
for _i in range(10):
    CHARS[0x40 + _i] = str(_i)
for _i in range(26):
    CHARS[0x51 + _i] = chr(ord("A") + _i)

# 命令の表に載っていない比較の記号
OPERATORS = {0x82: ">=", 0x83: "<=", 0x84: "<>"}

# 前後に空白を置かない中間コード(比較の記号)
_TIGHT = set(OPERATORS)
# 命令のあとにこれらが続くときは、あいだに空白を置く
_SPACE_BEFORE = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"&(-.√π') | {"[E]"}


def keyword_table(mem) -> dict[int, str]:
    """BASIC ROMの命令の表を読む。{中間コード: 綴り}

    表は「上位4ビットが種類・下位4ビットが長さ」の1バイト、綴り、中間コード、処理の番地
    (2バイト)の並び。ROMの中でこの形がいちばん長く続くところを表とみなす。
    """
    rom = bytes(mem[0x4000:0x8000])
    best: dict[int, str] = {}
    i = 0
    while i < len(rom):
        table, j = _parse_run(rom, i)
        if len(table) > len(best):
            best = table
        i = j + 1 if table else i + 1
    out = dict(OPERATORS)
    out.update(best)
    return out


def _parse_run(rom: bytes, i: int) -> tuple[dict[int, str], int]:
    table: dict[int, str] = {}
    while i < len(rom):
        n = rom[i] & 0x0F
        if not 1 <= n <= 7 or i + n + 3 >= len(rom):
            break
        name = rom[i + 1 : i + 1 + n]
        ok = all(0x51 <= c <= 0x6A or c in (0x11, 0x18) for c in name)
        if not ok or not 0x51 <= name[0] <= 0x6A:
            break
        token = rom[i + 1 + n]
        if token < 0x7D:
            break
        if 0x11 not in name:  # 空白で埋めた項目(使われていない)は飛ばす
            table.setdefault(token, "".join(CHARS[c] for c in name))
        i += n + 4
    return (table, i) if len(table) >= 20 else ({}, i)


def program_lines(mem, start: int = PROG_START) -> list[tuple[int, bytes]]:
    """(行番号, 中身)の列。プログラムがなければ空。memのROMがS1系なら、その形で読む"""
    if is_s1(mem):
        return program_lines_s1(mem, start)
    out = []
    a = start + 1 if mem[start] == 0xFF else start
    while a < 0xC800:
        hi = mem[a]
        if hi == 0xFF or not 0xE0 <= hi <= 0xE9:
            break
        lo = mem[a + 1]
        number = (hi & 0x0F) * 100 + (lo >> 4) * 10 + (lo & 0x0F)
        end = a + 2
        while end < 0xC800 and mem[end] != 0x00:
            end += 1
        out.append((number, bytes(mem[a + 2 : end])))
        a = end + 1
    return out


def line_text(body: bytes, keywords: dict[int, str]) -> str:
    """1行の中身を文字にする"""
    out: list[str] = []
    in_string = False
    rest_raw = False  # REMのあとは打ったとおり
    for i, c in enumerate(body):
        if rest_raw or in_string or c < 0x7D:
            if c == 0x12 and not rest_raw:
                in_string = not in_string
            if c >= 0x7D and c in keywords:
                # 文字列やREMの中の中間コード。実機のLISTと同じく綴りを空白で挟んで出す
                if out and not out[-1].endswith(" "):
                    out.append(" ")
                out.append(keywords[c] + " ")
                continue
            out.append(CHARS.get(c, "?"))
            continue
        word = keywords.get(c)
        if word is None:
            out.append("?")
            continue
        if c in _TIGHT:
            out.append(word)
            continue
        if out and (out[-1][-1].isalnum() or out[-1][-1] in '")$'):
            out.append(" ")
        out.append(word)
        nxt = body[i + 1] if i + 1 < len(body) else None
        if nxt is not None and (nxt >= 0x7D or CHARS.get(nxt, "?") in _SPACE_BEFORE):
            out.append(" ")
        if word == "REM":
            rest_raw = True
    return "".join(out).rstrip()


def program_text(mem, keywords: dict[int, str] | None = None, start: int = PROG_START) -> str:
    """RAMのプログラムをBASICの文字にする。startはプログラムの先頭(machine.program_start)"""
    s1 = is_s1(mem)
    if keywords is None:
        keywords = keyword_table_s1(mem) if s1 else keyword_table(mem)
    text = line_text_s1 if s1 else line_text
    return "".join(f"{n} {text(body, keywords)}\n" for n, body in program_lines(mem, start))


# 行番号の桁と中身(中間コード)を合わせて79字まで。長い行は、打ち込むと切れる
LINE_MAX = 79
# 指数のE(4Bh)は、keytype.normalizeが「[E]」をまとめた1字「€」(keytype.EXP)で届く
_CODES = {ch: c for c, ch in CHARS.items() if len(ch) == 1} | {"€": 0x4B}


def _keyword_list(keywords: dict[int, str]) -> list[tuple[str, int]]:
    """(綴り, 中間コード)を長い綴りから並べる。打ち込みと同じく、いちばん長く合うものを使う"""
    return sorted(((w, c) for c, w in keywords.items()), key=lambda x: -len(x[0]))


def encode_line(line: str, keywords: dict[int, str]) -> tuple[int, bytes] | None:
    """PC-1251・PC-1245の1行を、ROMが打ち込みで作るのと同じ中間コードにする。
    (行番号, 行の全体)を返す。行番号がないか、長すぎて入らない行はNone。
    文字列とREMのあとの外では空白を落とし、REMの直後の空白も落とす。
    lineはkeytype.typed_textを通してから渡す"""
    text = line.strip()
    k = len(text) - len(text.lstrip("0123456789"))
    if k == 0 or k > 3 or not 1 <= int(text[:k]) <= 999:
        return None
    number, rest = int(text[:k]), text[k:]
    words = _keyword_list(keywords)
    body = bytearray()
    in_string = raw = False
    j = 0
    while j < len(rest):
        ch = rest[j]
        if not (raw or in_string):
            if ch == " ":
                j += 1
                continue
            hit = next(((w, c) for w, c in words if rest.startswith(w, j)), None)
            if hit:
                body.append(hit[1])
                j += len(hit[0])
                if hit[0] == "REM":
                    raw = True
                    while j < len(rest) and rest[j] == " ":
                        j += 1
                continue
        if ch == '"' and not raw:
            in_string = not in_string
        if ch in _CODES:
            body.append(_CODES[ch])
        j += 1
    if k + len(body) > LINE_MAX:
        return None
    head = bytes([0xE0 + number // 100, (number // 10 % 10) << 4 | number % 10])
    return number, head + bytes(body) + b"\x00"


def encode_program(text: str, mem) -> bytes | None:
    """BASICのプログラムを、ROMが打ち込みで作るのと同じ中間コードの行の並びにする(先頭と
    終わりのFFは含まない)。行番号の順に並べ、同じ番号の行はあとのもので置き換え、行番号
    だけの行はその行を消す。memのROMでPC-1251系かS1系かを決める。入らない長さの行があればNone"""
    s1 = is_s1(mem)
    keywords = keyword_table_s1(mem) if s1 else keyword_table(mem)
    lines: dict[int, bytes] = {}
    for line in text.split("\n"):
        if not line.strip():
            continue
        enc = encode_line_s1(line, keywords) if s1 else encode_line(line, keywords)
        if enc is None:
            return None
        number, data = enc
        if len(data) == (4 if s1 else 3):  # 中身がない
            lines.pop(number, None)
        else:
            lines[number] = data
    return b"".join(lines[n] for n in sorted(lines))


# ---- S1系(PC-1260/1261/1262、PC-1350) ----
CHARS_S1: dict[int, str] = {c: chr(c) for c in range(0x20, 0x7F)}
CHARS_S1.update({0x5C: "¥", 0xFB: "π", 0xFC: "√"})
for _c in range(0xA1, 0xE0):
    CHARS_S1[_c] = bytes([_c]).decode("cp932")


def is_s1(mem) -> bool:
    """S1系のBASIC ROMが入っているか。文字の形の表の「A」で見分ける(PC-1350は812Fh)"""
    a = bytes.fromhex("7c1211127c")
    return bytes(mem[0x80EA:0x80EF]) == a or bytes(mem[0x812F:0x8134]) == a


def keyword_table_s1(mem) -> dict[int, str]:
    """S1系のBASIC ROMの命令の表を読む。{中間コード: 綴り}"""
    rom = bytes(mem)
    best: dict[int, str] = {}
    i = 0x8000
    while i < 0x10000:
        table, j = _parse_run_s1(rom, i)
        if len(table) > len(best):
            best = table
        i = j + 1 if table else i + 1
    return best


def _parse_run_s1(rom: bytes, i: int) -> tuple[dict[int, str], int]:
    table: dict[int, str] = {}
    while i < len(rom) - 4:
        n = rom[i] & 0x0F
        if not 1 <= n <= 8:
            break
        name = rom[i + 1 : i + 1 + n]
        if not all(0x41 <= c <= 0x5A or c in b"$#" for c in name) or not 0x41 <= name[0] <= 0x5A:
            break
        token = rom[i + 1 + n]
        if token < 0x80:
            break
        table.setdefault(token, name.decode("ascii"))
        i += n + 4
    return (table, i) if len(table) >= 20 else ({}, i)


def program_lines_s1(mem, start: int) -> list[tuple[int, bytes]]:
    """S1系の(行番号, 中身)の列。中身は終わりの0Dを含まない"""
    out = []
    a = start + 1 if mem[start] == 0xFF else start
    while a + 3 < 0x7000 and mem[a] != 0xFF:
        number = (mem[a] << 8) | mem[a + 1]
        n = mem[a + 2]
        if n == 0 or mem[a + 2 + n] != 0x0D:
            break
        out.append((number, bytes(mem[a + 3 : a + 2 + n])))
        a += 3 + n
    return out


def line_text_s1(body: bytes, keywords: dict[int, str]) -> str:
    """S1系の1行の中身を文字にする。空白の補い方はline_textと同じ"""
    out: list[str] = []
    in_string = False
    rest_raw = False
    escaped = False  # FEhのあとの字(カナ)
    for i, c in enumerate(body):
        if escaped:
            out.append(CHARS_S1.get(c, "?"))
            escaped = False
            continue
        if c == 0xFE:
            escaped = True
            continue
        word = None if (rest_raw or in_string) else keywords.get(c)
        if word is None:
            if c == 0x22 and not rest_raw:
                in_string = not in_string
            out.append(CHARS_S1.get(c, "?"))
            continue
        if out and (out[-1][-1].isalnum() or out[-1][-1] in '")$'):
            out.append(" ")
        out.append(word)
        nxt = body[i + 1] if i + 1 < len(body) else None
        if nxt is not None and (nxt in keywords or CHARS_S1.get(nxt, "?") in _SPACE_BEFORE):
            out.append(" ")
        if word == "REM":
            rest_raw = True
    return "".join(out).rstrip()


def encode_line_s1(line: str, keywords: dict[int, str]) -> tuple[int, bytes] | None:
    """S1系の1行を、ROMが打ち込みで作るのと同じ中間コードにする。(行番号, 行の全体)を返し、
    行番号がないか、長すぎて入らない行はNone。文字列とREMのあとの外では空白を落とし、いちばん長く合う命令の綴りを
    中間コードにする。lineはkeytype.typed_textを通してから渡す"""
    text = line.strip()
    k = 0
    while k < len(text) and text[k].isdigit():
        k += 1
    if k == 0 or k > 5 or not 1 <= int(text[:k]) <= 0xFEFF:
        return None
    number, rest = int(text[:k]), text[k:]
    words = _keyword_list(keywords)
    codes = {ch: c for c, ch in CHARS_S1.items()}
    body = bytearray()
    in_string = raw = False
    j = 0
    while j < len(rest):
        ch = rest[j]
        if not (raw or in_string):
            if ch == " ":
                j += 1
                continue
            hit = next(((w, c) for w, c in words if rest.startswith(w, j)), None)
            if hit:
                body.append(hit[1])
                j += len(hit[0])
                raw = hit[0] == "REM"
                continue
        if ch == '"' and not raw:
            in_string = not in_string
        c = codes.get(ch)
        if c is None:
            j += 1
            continue
        if c >= 0xA1 and c < 0xE0:
            body.append(0xFE)
        body.append(c)
        j += 1
    if k + len(body) > LINE_MAX:  # カナは2字に数える
        return None
    return number, bytes([number >> 8, number & 0xFF, len(body) + 1]) + bytes(body) + b"\r"

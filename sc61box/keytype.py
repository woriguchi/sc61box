"""文字列を各機種のキー操作に直す(貼り付けと自動入力用)"""

import unicodedata

# 指数のE。テキストでは「[E]」か「€」と書く(PocketToolsと同じ)。打つときは1字にまとめる。
# 小文字のeは指数にしない(PC-1261などでは英小文字を打てるので、英字のeと区別できない)
EXP = "€"
EXP_SPELLINGS = ("[E]", "[e]")


def normalize(text: str) -> str:
    """指数のEの書き方を、打つための1字にそろえる。ポケコンにはバックスラッシュがなく、
    同じ場所(ASCIIの5Ch)の字が¥なので、「\\」は¥にする(英語配列のキーボードや、
    ¥キーで「\\」が入る設定でも¥が打てるように)"""
    for s in EXP_SPELLINGS:
        text = text.replace(s, EXP)
    return text.replace("\\", "¥")


# SHIFTを押してから打つ記号(MAMEのキー名による)
SHIFTED = {
    ">": "-",
    "<": "*",
    "^": "/",
    "(": "DOWN",
    "#": "E",
    "!": "Q",
    "@": "3",
    '"': "W",
    ")": "UP",
    "$": "R",
    ";": "P",
    "%": "T",
    ",": "O",
    "&": "Y",
    "?": "U",
    ":": "I",
    "√": ".",
    "π": "0",
    "¥": "6",  # PC-1251・PC-1245では文字コード17h
    EXP: "+",  # 指数のE(Expキー、中間コード4Bh)。英字のEとは別の字
}
# PC-1245は括弧が1と2の上にある(↓↑ではない)
SHIFTED_1245 = {**SHIFTED, "(": "1", ")": "2"}
# PC-1260/1261/1262も括弧は1と2の上で、¥は6の上。Expのキーはなく、指数は英字のEで書く
SHIFTED_1261 = {k: v for k, v in SHIFTED_1245.items() if k != EXP} | {"¥": "6"}
MODELS_1261 = ("1260", "1261", "1262")


def _kana_table(plain_keys: str, shift_keys: str) -> dict[str, list[list[str]]]:
    """カナの入力での、字ごとの打鍵。plain_keysはキーだけで打つ字のキー、shift_keysは
    SHIFTを押してから打つ字(「・」の印のあるキーでは小さい字)のキー"""
    table = {ch: [[k]] for ch, k in zip(_KANA_PLAIN, plain_keys, strict=True)}
    table.update({ch: [["SHIFT"], [k]] for ch, k in zip(_KANA_SHIFT, shift_keys, strict=True)})
    return table


_KANA_PLAIN = "ｱｲｳｴｵｶｸｺｼｾﾀﾂﾃﾅﾇﾉﾋﾍﾏﾑﾓﾔﾕﾖﾗﾙﾛﾝ｡｣､ｰ"
_KANA_SHIFT = "ｧｨｩｪｫｷｹｻｽｿﾁｯﾄﾆﾈﾊﾌﾎﾐﾒｬｭｮﾘﾚﾜｦﾟ｢･ﾞ"
# PC-1261などのカナ。カナの入力はSHIFT+8で切り替える
KANA_1261 = _kana_table("QWERTYUIOPASDFGHJKL=ZXCVBNM.+*/-", "QWERTYUIOPASDFGHJKL=XCVBNM.+*/-")

# PC-1350。数字の側に括弧と記号のキーがあり、SHIFTで入る記号はQ〜Pの上と数字の側。
# カナはカナキーで切り替える
SHIFTED_1350 = dict(zip('!"#$%&?π√@<>¥^', "QWERTYUIOP()*-", strict=True)) | {"\\": "*"}
PLAIN_1350 = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ+-*/=.,;:()")
KANA_1350 = _kana_table("QWERTYUIOPASDFGHJKL=ZXCVBNM+-;:,", "QWERTYUIOPASDFGHJKL=XCVBNM+-;:,")


def _half_kana(text: str) -> str:
    """全角のカタカナとひらがな、濁点・半濁点のついた字を、半角カナの並びにする"""
    out = []
    for ch in text:
        if "ぁ" <= ch <= "ゖ":
            ch = chr(ord(ch) + 0x60)  # ひらがなをカタカナに
        for c in unicodedata.normalize("NFD", ch):
            if c == "\u3099":
                out.append("ﾞ")
            elif c == "\u309a":
                out.append("ﾟ")
            else:
                out.append(_FULL_TO_HALF.get(c, c))
    return "".join(out)


_FULL_TO_HALF = {
    unicodedata.normalize("NFKC", bytes([c]).decode("cp932")): bytes([c]).decode("cp932")
    for c in range(0xA1, 0xE0)
}
PLAIN = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ+-*/=.")


def keys_for(text: str, model: str = "1251") -> list[list[str]]:
    """押すキーの列。[["SHIFT"], ["I"]]のように1打鍵ずつ並べる"""
    if model in MODELS_1261:
        return _keys_for_1261(normalize(text).replace(EXP, "E"))
    if model == "1350":
        return _keys_for_1350(normalize(text).replace(EXP, "E"))
    shifted = SHIFTED_1245 if model == "1245" else SHIFTED
    out: list[list[str]] = []
    for ch in normalize(text):
        if ch.isascii():  # πを大文字にするとΠになって打てなくなるので、英字だけ大文字にする
            ch = ch.upper()
        if ch == "\n":
            out.append(["ENTER"])
        elif ch == " ":
            out.append(["SPC"])
        elif ch in PLAIN:
            out.append([ch])
        elif ch in shifted:
            out.append(["SHIFT"])
            out.append([shifted[ch]])
    return out


def typed_text(text: str, model: str = "1251") -> str:
    """打ち込んだときにROMへ届く字の並び(keys_forが打てる字だけを、打つ形で残す)"""
    if model in MODELS_1261:
        return typed_text_1261(text)
    if model == "1350":
        return typed_text_1350(text)
    shifted = SHIFTED_1245 if model == "1245" else SHIFTED
    out = []
    for ch in normalize(text):
        if ch.isascii():
            ch = ch.upper()
        if ch in PLAIN or ch in shifted or ch in " \n":
            out.append(ch)
    return "".join(out)


def typed_text_1261(text: str) -> str:
    """PC-1261などで打ち込んだときにROMへ届く字の並び(_keys_for_1261が打つ字)"""
    out = []
    for ch in _half_kana(normalize(text).replace(EXP, "E")):
        if ch.isascii():
            ch = ch.upper()
        if ch in KANA_1261 or ch in PLAIN or ch in SHIFTED_1261 or ch in " \n":
            out.append(ch)
    return "".join(out)


def typed_text_1350(text: str) -> str:
    """PC-1350で打ち込んだときにROMへ届く字の並び(_keys_for_1350が打つ字)"""
    out = []
    quoted = False
    for ch in _half_kana(normalize(text).replace(EXP, "E")):
        if ch == "\n":
            quoted = False
        elif ch == '"':
            quoted = not quoted
        if ch.isascii() and ch.isalpha():
            out.append(ch if quoted and ch.islower() else ch.upper())
        elif ch == "\\":
            out.append("¥")
        elif ch in KANA_1350 or ch in PLAIN_1350 or ch in SHIFTED_1350 or ch in " \n":
            out.append(ch)
    return "".join(out)


def _keys_for_1261(text: str) -> list[list[str]]:
    """PC-1261などのキー操作。カナはカナの入力に切り替えて打ち、終わったら戻す。
    数字と空白とENTERはどちらの入力でも同じなので、切り替えずに打つ"""
    out: list[list[str]] = []
    kana = False
    for ch in _half_kana(text):
        if ch in KANA_1261:
            if not kana:
                out += [["SHIFT"], ["8"]]
                kana = True
            out += KANA_1261[ch]
            continue
        if ch.isascii():
            ch = ch.upper()
        if kana and ch not in "0123456789 \n":
            out += [["SHIFT"], ["8"]]
            kana = False
        if ch == "\n":
            out.append(["ENTER"])
        elif ch == " ":
            out.append(["SPC"])
        elif ch in PLAIN:
            out.append([ch])
        elif ch in SHIFTED_1261:
            out += [["SHIFT"], [SHIFTED_1261[ch]]]
    if kana:
        out += [["SHIFT"], ["8"]]
    return out


def _keys_for_1350(text: str) -> list[list[str]]:
    """PC-1350のキー操作。カナはカナキー、小文字はSHIFT+カナキー(SML)で入力を切り替えて
    打ち、終わったら戻す。小文字は「"」で囲んだ文字列の中だけで、ほかは大文字にする
    (命令は大文字でないと通らない)"""
    out: list[list[str]] = []
    state = ""  # ""、"KANA"(カナ)、"SML"(小文字)
    quoted = False

    def switch(to: str) -> None:
        nonlocal state
        if state == to:
            return
        for s in (state, to):  # いったん英大文字の入力に戻してから切り替える
            if s == "KANA":
                out.append(["KANA"])
            elif s == "SML":
                out.extend([["SHIFT"], ["KANA"]])
        state = to

    for ch in _half_kana(text):
        if ch in KANA_1350:
            switch("KANA")
            out += KANA_1350[ch]
            continue
        if ch.isascii() and ch.isalpha():
            if quoted and ch.islower():
                switch("SML")
                out.append([ch.upper()])
                continue
            ch = ch.upper()
            switch("")
        elif ch not in "0123456789 \n()/*.+-=,;:":
            switch("")  # SHIFTで入る記号は、カナの入力ではカナになる
        if ch == '"':
            quoted = not quoted
        if ch == "\n":
            quoted = False
            out.append(["ENTER"])
        elif ch == " ":
            out.append(["SPC"])
        elif ch in PLAIN_1350:
            if state == "KANA" and ch in "+-,;:":  # カナの入力ではカナになるキー
                switch("")
            out.append([ch])
        elif ch in SHIFTED_1350:
            out.append(["SHIFT"])
            out.append([SHIFTED_1350[ch]])
    switch("")
    return out


# 1行に打てるのは行番号と空白を含めて79字まで。長い行は途中まで打ってENTERし、▶を80回
# 押して行末へ送ってから続きを打つ。入った部分は中間コード(命令は1字)で数えるので、
# 2回目からはその長さを見積もって、残りに収まるだけ打つ。
LINE_MAX = 79

# BASICの命令と関数の綴り(PC-1251のBASIC ROMの表から)。中間コードでは1字になる
KEYWORDS = sorted(
    """OUTSTAT RESTORE DEGREE INKEY$ INSTAT LPRINT RADIAN RANDOM RETURN RIGHT$ SETCOM
    AREAD CHAIN CLEAR CLOAD CSAVE DEBUG ERROR GOSUB INPUT LEFT$ LLIST MERGE PAUSE
    PRINT TROFF USING BEEP CALL CHR$ COM$ CONT DATA GOTO GRAD LIST MID$ NEXT PASS
    PEEK POKE READ STEP STOP STR$ THEN TRON WAIT ABS ACS AND ASC ASN ATN COS DEG
    DIM DMS END EXP FOR INT KEY LEN LET LOG MEM NEW NOT OFF REM RND ROM RUN SGN SIN
    SQR TAN VAL <= <> >= IF LN ON OR PI TO""".split(),
    key=len,
    reverse=True,
)


def stored_len(text: str) -> int:
    """打った行をROMが中間コードにしたときの長さの見積もり(行番号は数字+1字)"""
    num, _, body = text.strip().partition(" ")
    n = len(num) + 1
    i, quoted = 0, False
    while i < len(body):
        ch = body[i]
        if ch == '"':
            quoted = not quoted
        elif not quoted:
            if ch == " ":
                i += 1
                continue
            kw = next((k for k in KEYWORDS if body.startswith(k, i)), None)
            if kw:
                n += 1
                i += len(kw)
                continue
        n += 1
        i += 1
    return n


def _cuts(line: str) -> tuple[list[int], list[int]]:
    """切ってよい位置。1つ目は文字列の外の「:」のすぐ後ろ、2つ目はそれ以外に
    切ってもよい位置(文字列の外の空白・「;」・「,」のすぐ後ろ)。行番号のすぐ後ろでは
    切らない(行番号だけを打つと行が消える)"""
    head = len(line) - len(line.lstrip("0123456789"))
    head = len(line) - len(line[head:].lstrip(" "))
    good, other, quoted = [], [], False
    for i, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif i < head:
            continue
        elif not quoted and ch == ":":
            good.append(i + 1)
        elif not quoted and ch in " ;,":
            other.append(i + 1)
    return good, other


def split_line(line: str) -> list[str]:
    """79字を超える行を、打てる大きさに切り分ける。なるべく「:」(文字列の外)の
    あとで切る。切れるところがなければ、残りをそのまま最後の1つにする"""
    if len(line) <= LINE_MAX:
        return [line]
    good, other = _cuts(line)
    parts, done = [], 0
    while len(line) - done > 0:
        room = LINE_MAX if done == 0 else LINE_MAX - 1 - stored_len(line[:done])
        if len(line) - done <= room:
            parts.append(line[done:])
            break
        fit = [c for c in good if done < c <= done + room]
        if not fit:  # 「:」で切れなければ、文の途中で切る(ROMは入力のときに文法を見ない)
            fit = [c for c in other if done < c <= done + room]
        if not fit:
            parts.append(line[done:])
            break
        parts.append(line[done : fit[-1]])
        done = fit[-1]
    return parts


# ---- 後ろに足すだけでは入らない行 ----
# 行を直す欄では、入っている部分は中間コードで、打ったばかりの部分は打った字で数え、
# 79字を超えた分は行末から捨てられる。上限に近い行の後ろのほうに命令があると、綴りを
# 打った時点であふれるので、実機で打つときと同じく、打つと縮む命令の綴りを先に打ち、
# 縮まない字(変数・数・記号・文字列)をあとから途中に挿入する。
# 行を呼び出した直後(▶を1回)はカーソルが中身の先頭にあり、▶1回で1字(命令も1字)進む。
# SHIFT+▶(INS)は1回で1字あける。


def _units(body: str) -> list[str]:
    """行の中身を、ROMが中間コードにするときの区切りに分ける(命令の綴り、1字、
    文字列ひとまとまり、REMから行末まで)。文字列の外の空白は区切りなので捨てる"""
    out: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == " ":
            i += 1
            continue
        if ch == '"':
            j = body.find('"', i + 1)
            j = len(body) - 1 if j < 0 else j
            out.append(body[i : j + 1])
            i = j + 1
            continue
        kw = next((k for k in KEYWORDS if body.startswith(k, i)), None)
        if kw == "REM":  # REMのあとは打ったとおりに入る
            out.append(body[i:])
            break
        if kw:
            out.append(kw)
            i += len(kw)
            continue
        out.append(ch)
        i += 1
    return out


def _stored(unit: str) -> int:
    """区切り1つが中間コードで何字になるか"""
    if unit.startswith("REM"):
        return 1 + len(unit) - 3
    return 1 if unit in KEYWORDS else len(unit)


def _join(units: list[str]) -> str:
    """区切りを続けて打つ文字列にする。続けると別の命令に読まれるときは空白をはさむ"""
    text = "".join(units)
    return text if _units(text) == units else " ".join(units)


def insert_plan(line: str) -> list[tuple[int | None, str]] | None:
    """長い行を、命令を先に打ってから残りを挿入する手順にする。(位置, 打つ字)の列で、
    最初は行番号つきで新しく打つ(位置None)。2つ目からの位置は、中身の何字目の前に
    入れるか(行末に足すときは中身の字数)。どう打っても入らないときはNone"""
    num, _, body = line.strip().partition(" ")
    units = _units(body)
    cap = LINE_MAX - len(num)  # 中身に使える字数
    if not num.isdigit() or not units or sum(_stored(u) for u in units) > cap:
        return None
    shrink = [len(u) > _stored(u) for u in units]  # 打つと縮むもの(命令の綴り)
    steps: list[tuple[int | None, str]] = []
    done: set[int] = set()
    now = 0  # 入っている中身の字数(中間コード)

    def put(idx: list[int], pos: int | None) -> bool:
        nonlocal now
        text = _join([units[k] for k in idx])
        extra = 1 if not steps else 0  # 新しく打つときは行番号のあとの空白も数える
        if now + len(text) + extra > cap:
            return False
        steps.append((None if not steps else pos, text))
        now += sum(_stored(units[k]) for k in idx)
        done.update(idx)
        return True

    # 1. 命令の綴りを前から(行末に足していく)。入るだけまとめて打つ
    piece: list[int] = []
    for k in [k for k, s in enumerate(shrink) if s]:
        text = _join([units[x] for x in piece + [k]])
        if piece and now + len(text) + (0 if steps else 1) > cap:
            if not put(piece, now):
                return None
            piece = []
        piece.append(k)
    if piece and not put(piece, now):
        return None
    # 2. 縮まない字のひと続きを、左から順に入るべき位置へ挿入する
    k = 0
    while k < len(units):
        if k in done:
            k += 1
            continue
        run = [k]
        while run[-1] + 1 < len(units) and run[-1] + 1 not in done:
            run.append(run[-1] + 1)
        pos = sum(_stored(units[x]) for x in done if x < k)
        if not put(run, pos):
            return None
        k = run[-1] + 1
    return steps


def _append_fits(line: str, parts: list[str]) -> bool:
    """後ろに足していく打ち方(split_line)で、どの回も欄からあふれないか"""
    num = line.strip().partition(" ")[0]
    if len(parts[0]) > LINE_MAX:
        return False
    done = parts[0]
    for part in parts[1:]:
        body = done.strip().partition(" ")[2]
        if len(num) + sum(_stored(u) for u in _units(body)) + len(part) > LINE_MAX:
            return False
        done += part
    return True


def too_long(text: str, model: str = "1251") -> str | None:
    """keys_for_programで打ち込むと欠ける最初の行。どの行も欠けずに入ればNone。
    S1系はカナを2字に数え、カナを含めて79字を超える行は入らないとみる"""
    s1 = model in MODELS_1261 or model == "1350"
    for line in normalize(text).split("\n"):
        if not line.strip():
            continue
        if s1:
            typed = typed_text(line, model)
            kana = sum(1 for ch in typed if "\uff61" <= ch <= "\uff9f")
            if kana and len(typed) + kana > LINE_MAX:
                return line
        if not _append_fits(line, split_line(line)) and insert_plan(line) is None:
            return line
    return None


def typeable(text: str, model: str = "1251") -> bool:
    """keys_for_programで打ち込むと、どの行も欠けずに入るか"""
    return too_long(text, model) is None


def _upper_outside_quotes(line: str) -> str:
    """「"」で囲んだ文字列の外の英字だけを大文字にする"""
    out, quoted = [], False
    for ch in line:
        if ch == '"':
            quoted = not quoted
        out.append(ch if quoted or not ch.isascii() else ch.upper())
    return "".join(out)


def keys_for_program(text: str, model: str = "1251") -> list[list[str]]:
    """BASICのプログラムを打ち込む打鍵。長い行は分けて、2つ目からは打ったばかりの
    行を直す形で後ろに足す。後ろに足すとあふれる行は、命令を先に打ってから残りを挿入する"""
    out: list[list[str]] = []
    for line in normalize(text).split("\n"):
        if not line.strip():
            continue
        if model == "1350":  # 文字列の中の小文字はそのまま打つ(_keys_for_1350)
            line = _upper_outside_quotes(line)
        else:
            line = "".join(ch.upper() if ch.isascii() else ch for ch in line)
        parts = split_line(line)
        plan = None if _append_fits(line, parts) else insert_plan(line)
        if plan is None:
            first, *rest = parts
            out.extend(keys_for(first + "\n", model))
            for part in rest:
                out.extend([["RIGHT"]] * (LINE_MAX + 1))
                out.extend(keys_for(part + "\n", model))
            continue
        num = line.strip().partition(" ")[0]
        for pos, piece in plan:
            if pos is None:
                out.extend(keys_for(f"{num} {piece}\n", model))
                continue
            # ▶1回で呼び出し(カーソルは中身の先頭)、pos回進めて、字数だけINSであけて打つ
            out.extend([["RIGHT"]] * (1 + pos))
            if model == "1350":  # PC-1350にはINSキーがある
                out.extend([["INS"]] * len(piece))
            else:
                out.extend([["SHIFT"], ["RIGHT"]] * len(piece))
            out.extend(keys_for(piece + "\n", model))
    return out

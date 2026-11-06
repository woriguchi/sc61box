"""打っている行と、その液晶での見え方(系統によらない部分)

行は「単位」の並びで持つ。単位は本体の文字コードか、命令の中間コード(番号が系統ごとに決まった
数TOKEN以上)。中間コードは1つの単位として綴りで出し、カーソルも1つずつ動く。
空白の字などは、系統ごとの子クラス(pc1251/editor.py、pc1261/editor.py)が決める。
"""

from .screen import BLOCK, UNDERLINE

INSERT_MARK = 0x01  # SHIFT+→で入れる挿入マーク。ENTERで捨てる
MAX_UNITS = 80  # 打てる単位の数。ENTERで使うのは頭の79(観察)
# 100h以上の単位は、RAMでは2バイトで持つ字(PC-1261系とPC-1350のカナ)。液晶にはWIDEを引いた字で出す
WIDE = 0x100
NO_SEP = -1  # 行番号のあとに区切りの字を置かない(PC-1350のTEXTモード)


def pieces(
    units,
    keywords: dict[int, str],
    codes: dict[str, int],
    glued: bool = False,
    *,
    space: int,
    tight: tuple[int, ...],
    token: int,
) -> list[tuple[list[int], int]]:
    """単位ごとの(液晶の字の並び, カーソルを置く位置)。命令は、行の頭か空白のあとでなければ
    前に空白を置き、後ろにはいつも空白を置く(観察)。gluedなら、頭の命令の前にも空白を置く。
    space・tight・tokenは、空白の字、前後に空白を置かない中間コード、中間コードの最初の番号"""
    out: list[tuple[list[int], int]] = []
    after_space = not glued
    for u in units:
        if u >= WIDE:
            out.append(([u - WIDE], 0))
            after_space = False
            continue
        if u < token or u in tight or u not in keywords:
            # 中間コードの番号にある字(PC-1350のπ・√)は、そのまま出す
            word = [u] if u < token or u not in keywords else [codes[ch] for ch in keywords[u]]
            out.append((word, 0))
            after_space = word[-1] == space
            continue
        word = [codes[ch] for ch in keywords[u]] + [space]
        lead = [] if after_space else [space]
        out.append((lead + word, len(lead)))
        after_space = True
    return out


def layout(
    units, keywords, codes, head: int = 0, sep: int | None = None, glued: bool = False, **style
) -> tuple[list[int], list[int]]:
    """(字の並び, 各単位のカーソルの桁と、終わりの桁)。headは行番号の単位の数で、そのあとに
    区切りの字sepを1つ置く(区切りは単位ではないので、カーソルは止まらない)。gluedなら、
    区切りのすぐあとの命令の前にも空白を置く(リザーブの「A: PRINT」。観察)。styleは
    piecesのspace・tight・token"""
    text, cols, _ends = spans(units, keywords, codes, head, sep, glued, **style)
    return text, cols


def spans(
    units, keywords, codes, head: int = 0, sep: int | None = None, glued: bool = False, **style
) -> tuple[list[int], list[int], list[int]]:
    """layoutと同じ(字の並び, カーソルの桁)に、各単位の字の終わり(含まない)の桁を足す。
    sepを省くと空白"""
    sep = style["space"] if sep is None else sep
    text: list[int] = []
    cols: list[int] = []
    ends: list[int] = []
    head_pieces = [([u], 0) for u in units[:head]]
    if head and sep != NO_SEP:
        head_pieces[-1] = (head_pieces[-1][0] + [sep], 0)
    for word, at in head_pieces + pieces(units[head:], keywords, codes, glued, **style):
        cols.append(len(text) + at)
        text += word
        ends.append(len(text))
    cols.append(len(text))
    return text, cols, ends


class Editor:
    """打っている行。headは、登録した行を編集するときの行番号の単位の数(液晶の左に残し、
    続きだけをずらす)。sepは行番号のあとに出す字(編集では空白、エラーの行を見せるときは:)。
    字のコードはクラスの属性に持つ(PC-1251系。PC-1261系とPC-1350は子クラス)"""

    SPACE: int  # 空白の字
    TIGHT: tuple[int, ...]  # 前後に空白を置かない中間コード
    TOKEN: int  # 中間コードの最初の番号

    def __init__(
        self,
        units=(),
        cur: int | None = None,
        head: int = 0,
        sep: int | None = None,
        glued: bool = False,
    ) -> None:
        self.units = list(units)
        self.cur = len(self.units) if cur is None else cur
        self.head = head
        self.sep = self.SPACE if sep is None else sep
        self.glued = glued

    @staticmethod
    def units_of(data) -> list[int]:
        """RAMの中の行や文字列のバイトの並びを、単位の並びにする"""
        return list(data)

    @staticmethod
    def bytes_of(units) -> bytes:
        """単位の並びを、RAMに置くバイトの並びにする"""
        return bytes(units)

    @classmethod
    def style(cls) -> dict:
        """pieces・layoutに渡す字のコード"""
        return {"space": cls.SPACE, "tight": cls.TIGHT, "token": cls.TOKEN}

    def at_end(self) -> bool:
        return self.cur >= len(self.units)

    def text(self) -> bytes:
        """ENTERで渡す並び(頭の79単位から、挿入マークを除く)"""
        return self.bytes_of(u for u in self.units[: MAX_UNITS - 1] if u != INSERT_MARK)

    def type(self, code: int) -> None:
        """カーソルの単位を置き換え、行の終わりなら足す。80単位になったら、カーソルは最後の
        単位にとどまり、続けて打つと最後の単位を置き換える(観察)"""
        if self.at_end():
            self.units.append(code)
        else:
            self.units[self.cur] = code
        self.cur = min(self.cur + 1, MAX_UNITS - 1)

    def move(self, step: int) -> None:
        self.cur = max(0, min(len(self.units), self.cur + step))

    def delete(self) -> None:
        if not self.at_end():
            del self.units[self.cur]
            if self.cur < self.head:
                self.head -= 1

    def insert(self) -> None:
        """カーソルの前に挿入マークを入れる(挿入マークの上に打つと、その字になる)"""
        if not self.at_end():
            self.units.insert(self.cur, INSERT_MARK)
            if self.cur < self.head:
                self.head += 1

    def view(
        self, cells: int, keywords, codes, hide_block: bool
    ) -> tuple[list[int], int | None, bytes]:
        """液晶に出す(字の並び, カーソルの桁, カーソルの形)。カーソルのある単位(命令なら
        後ろの空白まで)が右端を越えるときは、その単位が収まるまで、行番号のあとの部分を左へ
        ずらす。ずらすのは、液晶の左が単位の頭(命令なら前の空白を除いた頭)になる数だけ
        (観察)"""
        text, cols, ends = spans(
            self.units, keywords, codes, self.head, self.sep, self.glued, **self.style()
        )
        col = cols[self.cur]
        keep = cols[self.head] if self.head else 0
        end = ends[self.cur] if self.cur < len(ends) else col + 1  # カーソルのある単位の終わり
        if end > cells:
            shift = next(
                (c - keep for c in cols[self.head : self.cur + 1] if end - (c - keep) <= cells),
                col - keep,
            )
            text = text[:keep] + text[keep + shift :]
            col -= shift
        shape = UNDERLINE if self.at_end() else BLOCK
        cursor = None if hide_block and not self.at_end() else col
        return text[:cells], cursor, shape

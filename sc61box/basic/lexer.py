"""打った行(本体の文字コードの並び)を中間コードの並びにする(系統によらない部分)"""


class Lexer:
    """命令の綴りを中間コードにする。綴りはいちばん長く合うものを選ぶ。「P.」のような省略は、
    綴りより先に見る。字のコードは系統ごとの子クラスがクラスの属性に入れる"""

    QUOTE: int
    SPACE: int
    DOT: int
    REM: int  # REMの中間コード
    LETTERS: tuple[int, int]  # 英字の文字コードの範囲
    REM_DROPS_SPACE: bool  # REMのすぐあとの空白を捨てる

    @staticmethod
    def spell(word: str) -> bytes:
        """綴りを本体の文字コードの並びにする"""
        raise NotImplementedError

    def __init__(
        self, keywords: dict[int, str], abbreviations: dict[str, str] | None = None
    ) -> None:
        pairs = [(self.spell(word), code) for code, word in keywords.items()]
        self.spellings = sorted(pairs, key=lambda p: -len(p[0]))
        self.by_spelling = dict(pairs)
        self.spelled = {code: word for word, code in pairs}
        codes = {word: code for code, word in keywords.items()}
        # 「P.」のような省略: 綴りの頭の字の並び → 中間コード
        self.short = {self.spell(head): codes[word] for head, word in (abbreviations or {}).items()}

    def tokenize(self, codes: bytes) -> bytes:
        """文字列の中とREMのあとはそのまま残し、ほかの空白は捨てる"""
        out = bytearray()
        i, in_string, raw = 0, False, False
        while i < len(codes):
            c = codes[i]
            if raw or in_string:
                out.append(c)
                in_string = in_string and c != self.QUOTE
                i += 1
                continue
            if c == self.QUOTE:
                in_string = True
                out.append(c)
                i += 1
                continue
            if c == self.SPACE:
                i += 1
                continue
            short = self._abbreviation(codes, i)
            if short is not None:
                code, i = short
                out.append(code)
            else:
                for word, code in self.spellings:
                    end = self._match(word, codes, i)
                    if end is not None:
                        out.append(code)
                        i = end
                        break
                else:
                    out.append(c)
                    i += 1
                    continue
            raw = out[-1] == self.REM
            while raw and self.REM_DROPS_SPACE and i < len(codes) and codes[i] == self.SPACE:
                i += 1  # REMのすぐあとの空白は捨てる(観察)
        return bytes(out)

    def _skip_spaces(self, codes: bytes, i: int) -> int:
        while i < len(codes) and codes[i] == self.SPACE:
            i += 1
        return i

    def _match(self, word: bytes, codes: bytes, i: int) -> int | None:
        """綴りwordが位置iから合えば、合った字の次の位置。綴りの字のあいだの空白は飛ばす
        (観察: PRI NTはPRINT、MEM #はMEM#)"""
        for k, ch in enumerate(word):
            if k:
                i = self._skip_spaces(codes, i)
            if i >= len(codes) or codes[i] != ch:
                return None
            i += 1
        return i

    def _abbreviation(self, codes: bytes, i: int) -> tuple[int, int] | None:
        """位置iからの英字の並び(あいだの空白は飛ばす)に「.」が続き、その並びが命令の省略なら、
        その中間コードと「.」の次の位置。綴りどおりの命令より先に見る(観察: DEG.はDEGREE。
        PRINT.5は、PRINTがほかの命令の頭ではないのでPRINTと.5。P R.はPRINT)。「.」のすぐ
        あとの$・#で綴りが続けばその命令にする(観察: M.#はMEM#、M. #はMEMと#、OP.$はOPEN$)"""
        letters = bytearray()
        j = i
        while True:
            k = self._skip_spaces(codes, j) if letters else j
            if k < len(codes) and self.LETTERS[0] <= codes[k] <= self.LETTERS[1]:
                letters.append(codes[k])
                j = k + 1
            else:
                break
        j = self._skip_spaces(codes, j)
        if not letters or j >= len(codes) or codes[j] != self.DOT:
            return None
        code = self.short.get(bytes(letters))
        if code is None:
            return None
        j += 1
        if j < len(codes):
            longer = self.by_spelling.get(self.spelled[code] + codes[j : j + 1])
            if longer is not None:
                return longer, j + 1
        return code, j

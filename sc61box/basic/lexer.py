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
            code = self._abbreviation(codes, i)
            if code is not None:
                out.append(code)
                i = codes.index(self.DOT, i) + 1
            else:
                for word, code in self.spellings:
                    if codes.startswith(word, i):
                        out.append(code)
                        i += len(word)
                        break
                else:
                    out.append(c)
                    i += 1
                    continue
            raw = out[-1] == self.REM
            while raw and self.REM_DROPS_SPACE and i < len(codes) and codes[i] == self.SPACE:
                i += 1  # REMのすぐあとの空白は捨てる(観察)
        return bytes(out)

    def _abbreviation(self, codes: bytes, i: int) -> int | None:
        """位置iからの英字の並びに「.」が続き、その並びが命令の省略なら、その中間コード。
        綴りどおりの命令より先に見る(観察: DEG.はDEGREE。PRINT.5は、PRINTがほかの命令の
        頭ではないのでPRINTと.5)"""
        j = i
        while j < len(codes) and self.LETTERS[0] <= codes[j] <= self.LETTERS[1]:
            j += 1
        if j == i or j >= len(codes) or codes[j] != self.DOT:
            return None
        return self.short.get(codes[i:j])

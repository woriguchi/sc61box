"""BASICの、機種ごとの細かい違い

同じ系統の機種(PC-1250・1251・1255とPC-1245、PC-1260・1261・1262)は、同じ形のBASIC(中間
コード、変数とプログラムのRAMの形、エラーの番号)を持ち、違いはここに並べた細かいふるまい
だけである。各機種の値は系統ごとのdialect.py(pc1251/、pc1261/)にある。RAMの番地と液晶の桁数は
本体の機種(machine.Model)が持つ。
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Dialect:
    name: str
    keywords: dict[int, str]  # 中間コードと綴り
    abbreviations: dict[str, str] | None  # 「.」で終わる省略の綴り(Noneなら持たない)
    error_lead: bytes  # プログラムの中のエラー「ERROR n IN 行番号」の左の空白
    reserve: bool  # RSVモードとリザーブのキーがある
    restore_colon: bool  # 「RESTORE:」でDATAを読む位置を初めに戻す
    # カセット: CSAVEで音を出す前・CLOADで読み始める前に余分に待つ時間、送り終えたあと・
    # 読み終えたあとに余分に待つ時間
    tape_before: int
    csave_after: int
    cload_after: int
    leader_brk: int  # CSAVEの初めの1のあいだ、BRKを見るビット(250ビットごとの何番目か)
    cload_busy: bool  # CLOADで読むあいだ、右端に*を出してBUSYの記号を点ける
    # PRINTの待ちで↓を押して止めると、CONTで続けられない(プログラムを終えたことになる)
    print_step_ends: bool
    pass_exact: bool  # PASSで保護を解くには、パスワードと同じ字(頭が同じだけでは解けない)
    new_when_locked: bool  # パスワードで保護しているときも、NEWでプログラムを消す
    using_zero_quirk: bool  # USINGで、小数の桁に入らず0になる数の出し方の癖(using.py)
    # USINGの数の書式で、整数の桁(10桁まで)と小数の桁の和の上限(越えるとERROR 7)
    using_limit: int | None
    using_dot_first: bool  # USINGの数の書式を「.」で始めてよい(PC-1251はERROR 1)
    val_exp_spaces: bool  # VALで、指数の中の空白を飛ばす
    # 2次元の配列の2つ目の添字に配列の要素(A(n)を除く)があると、1つ目の添字が0になる
    subscript_quirk: bool
    # ←・→・↑・↓を押し続けたとき、1回目の繰り返しまでと、そのあとの間(サイクル)
    repeat_delay: int
    repeat_every: int
    # RSVモードのない機種で、SHIFTのあとリザーブの位置のキーで打つ命令(キーと中間コード)
    shift_keywords: dict[str, int] | None = None
    # PRINTの最初の項目が文字列で、;のあとに数があるとき、代入した値の写しの場所に数を置く
    print_copy_number: bool = False
    # 字の形の表にない文字コードを出したときの液晶の5列(観察)。ROMは表の外の番地を読んで、
    # たまたまそこにあるバイトを字の形として出す。よく知られたもの(3Eh、「メロン」)だけを置く
    stray_glyphs: dict[int, bytes] = field(default_factory=dict)
    # 文で名前を書いたA(i,j)(代入、INPUT、FORなど。式の中で読むものは除く)を、A(n)が固定の
    # 変数の続きのときにどう扱うか。"error"なら「,」でERROR 1、"last"なら1つ目の添字を見ずに
    # A(j)とする(観察)
    a_pair: str | None = None
    # INPUTの文を始めてから、?か字を出すまでに余分にかかる時間
    input_cost: int = 0


_ALL: dict[str, Dialect] = {}  # 機種の名前 → 違い(系統ごとのdialect.pyから集める)


def of(m) -> Dialect:
    """本体mの機種のBASIC"""
    if not _ALL:
        from .pc1251 import dialect as pc1251
        from .pc1261 import dialect as pc1261

        _ALL.update(pc1251.DIALECTS | pc1261.DIALECTS)
    return _ALL[m.model.name]

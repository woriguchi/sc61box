"""ROMなしのBASICの時間。文と式にかかる時間(Timing)は系統ごとに、ROMのある本体でFORの
繰り返しの1回にかかる時間を測って決める。PC-1251系の値はこのファイルに、PC-1261系とPC-1350の
値はpc1261/timing.pyに置く。PC-1251系の計算のルーチンの時間は、代替ROMルーチン(norom)と
同じ値を使う
"""

from dataclasses import dataclass, field

from .. import norom
from ..machine import CLOCK


def ms(t: float) -> int:
    """ミリ秒をサイクルにする"""
    return round(CLOCK * t / 1000)


def routine(name: str) -> int:
    """代替ROMルーチン(norom)にかかるサイクル数"""
    return norom.ROUTINES[name][1]


class Meter:
    """かかった時間をためておき、BASICが進めるときにまとめて使う"""

    def __init__(self) -> None:
        self.cycles = 0

    def add(self, cycles: int) -> None:
        self.cycles += cycles

    def take(self) -> int:
        c, self.cycles = self.cycles, 0
        return c


@dataclass(frozen=True)
class Timing:
    """文と式にかかる時間(サイクル)"""

    # 文と行
    STATEMENT: int  # 文を1つ始める
    NEXT_LINE: int  # 次の行へ移る
    ASSIGN: int  # 代入
    NEXT_LOOP: int  # NEXTで増分を足して調べ、FORへ戻る(戻らないときも同じ)
    FOR: int
    IF: int  # IF(条件が成り立たず、行の残りを飛ばすときも同じ)
    JUMP: int  # GOTO・GOSUB・THENの行番号で跳ぶ
    JUMP_PER_LINE: int  # 跳ぶ先を探すとき、いまの行と跳ぶ先の行のあいだの行1つごと
    LABEL: int  # ラベルの行へ跳ぶ
    LABEL_PER_CHAR: int  # ラベルの1字ごと
    LABEL_PER_LINE: int  # ラベルを探すとき、跳ぶ先より前の行1つごと
    LABEL_PER_MARK: int  # そのうちラベルの行1つごとに足す時間
    RETURN: int
    STOPPED: int  # 終わるか止まってから、液晶に>やメッセージを出すまで
    PRINT: int  # PRINT・PAUSEで液晶に書く
    PRINT_NUMBER: int  # 出す数1つを字にする
    PAUSE: int  # PAUSEで出しておく時間
    POKE: int
    LPRINT: int  # LPRINTで、プリンタに送り始めるまで
    BEEP_ON: int  # BEEPの1回の鳴る時間
    BEEP_OFF: int  # 鳴らしたあとの間

    # 式
    DIGIT: int  # 数の2字目からの1字ごと
    OPERATOR: int  # 2つの値の演算(計算のルーチンの時間のほかに)
    RELATION: int  # 比較(比べるルーチンの時間のほかに)
    PAREN: int
    MINUS: int  # 符号の−
    FUNCTION: int  # 関数(計算のルーチンの時間のほかに)
    NOT: int
    # 掛け算と割り算は、数の桁の値で時間が変わる(観察: 0*Bは17.6ms、3*7は22.2ms、4/2は
    # 28.6ms、1/7は45.5ms、2/3は51ms)。掛ける数の仮数の桁の和、割り算の答えの仮数の桁の和に
    # 比例してかかるとみる
    MUL: int
    MUL_PER_DIGIT: int
    DIV: int
    DIV_PER_DIGIT: int
    # 配列の要素を読むか書く(添字を計算する時間のほかに)。A(n)の固定の変数は別
    ARRAY: int
    ARRAY_PER_SUBSCRIPT: int  # 2つ目からの添字1つごと
    FIXED_ARRAY: int
    READ_ITEM: int  # READで値を1つ読んで入れる
    RESTORE_LINE: int  # RESTOREで行を指定したとき
    # 計算のルーチン(FADD、FSINなど。romsyms.ROUTINES_1251の名前)にかかる時間
    routines: dict[str, int] = field(default_factory=dict)

    def routine(self, name: str) -> int:
        return self.routines.get(name, 0)


def digit_sum(v) -> int:
    """数の仮数(12桁)の桁の和"""
    t = v.as_tuple()
    return sum(t.digits[:12]) if isinstance(t.exponent, int) else 0


# PC-1251系の時間(PC-1251のBASIC ROM F0版で測った)
PC1251 = Timing(
    STATEMENT=ms(9.0),
    NEXT_LINE=ms(0.45),
    ASSIGN=ms(6.4),
    NEXT_LOOP=ms(31.4),
    FOR=ms(14.3),
    IF=ms(2.7),
    JUMP=ms(10.3),
    JUMP_PER_LINE=ms(1.13),
    LABEL=ms(1.4),  # GOSUB "B"で、すぐ次の行へのGOSUBより0.2ms長い
    LABEL_PER_CHAR=ms(1.11),  # "B"を"BCDEFG"にすると5.6ms長い
    LABEL_PER_LINE=ms(0.31),  # 前に空の行を20足すと6.2ms長い
    LABEL_PER_MARK=ms(4.0),  # 前にほかのラベルの行を1つ足すと4.3ms長い
    RETURN=ms(0.3),
    STOPPED=ms(45.0),
    PRINT=ms(68.0),
    PRINT_NUMBER=ms(9.5),
    PAUSE=ms(847.0),
    POKE=ms(17.0),
    LPRINT=ms(35.0),
    BEEP_ON=ms(188.66),
    BEEP_OFF=ms(192.9),
    DIGIT=ms(0.45),
    OPERATOR=ms(8.5),
    RELATION=ms(9.3),
    PAREN=ms(4.2),
    MINUS=ms(3.8),
    FUNCTION=ms(2.0),
    NOT=ms(4.0),
    MUL=ms(17.6),
    MUL_PER_DIGIT=ms(0.38),
    DIV=ms(27.95),
    DIV_PER_DIGIT=ms(0.325),
    ARRAY=ms(14.7),  # A=T(1)はA=Bより14.4ms、T(1)=Aは15.3ms、A$=S$(1)は14.7ms長い
    ARRAY_PER_SUBSCRIPT=ms(9.2),  # A=U(1,2)はA=Bより23.8ms長い
    FIXED_ARRAY=ms(8.3),  # A=A(2)はA=Bより8.2ms長い
    READ_ITEM=ms(12.9),  # RESTOREのあとREAD Aで22.2ms、READ A,B,Cで48.1ms
    RESTORE_LINE=ms(9.5),  # RESTORE 20はRESTOREより10.9ms長い
    routines={name: routine(name) for name in norom.ROUTINES},
)

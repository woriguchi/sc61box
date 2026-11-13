"""PC-1251・PC-1245、PC-1260/1261/1262、PC-1350のROMのルーチンの入口の名前

よく知られた入口に、ROMのある本体で呼んで働きを確かめた入口を加えたもの。番地はPC-1250/1251/1255
(BASIC ROMのどの版でも)とPC-1245で同じ。DEGとRNDは、BASIC ROMのどの版でも同じ番地の入口に
した。

アセンブラ(tools/asm61860.py)に`--rom 1251`を付けると、ここの名前が使える(routines.symbols)。

    LIDP &C698      ; 変数A
    LP   FY
    LII  7
    MVWD            ; 演算Y ← A
    ...
    CAL  FADD       ; 演算X ← 演算Y + 演算X

演算X(内部RAMの20〜27番地)と演算Y(28〜2F番地)は、BASICの変数と同じ8バイトの数。
計算のルーチンは、エラーのときキャリーを1、内部RAMの14番地(ERRNO)を2にして戻る。

よく知られた番地と違うところ(ROMのある本体で呼んで確かめた)
- 減算は0B67(0B69から呼ぶと、負の数で答えが狂う)
- 表示ONは11E0(11EDを呼んでも表示がつかない)
- 2進→10進は0D42(符号つき)・0D3B(符号なし)。10E0は数→整数の範囲を決めるだけで、
  続けて1737(F2I)を呼ぶと、演算Xの数が28・29番地の16ビットになる
- キースキャン1F44は、Aにキーの番号ではなく本体の文字コードを返す

J_ONEのルーチンは、Jが1でないと正しく動かない(ROMのある本体で呼んで確かめた)。
BASICのCALLで入ったときJは1なので、Jを書き換えなければそのまま呼べる。

SHOWRAMは走れ!セコイラインのコンパイルしたプログラム、PRINTBUFはボンバーが版ごとの表で選ぶ入口(F0版では
56C4、03版では5673。ROMなしの本体は7FFF番地が00なので00版の番地を呼ぶ。働きはF0版で確かめた)、
NOISEはPC-1245用のもぐらたたきが呼ぶ入口。

PC-1260/1261/1262の入口(ROUTINES_1261)は、ゲームのFENSCER、コンパイラLC-3、まうりさんの麻雀ゲーム
『M・MON KITT』が呼ぶ入口を、PC-1350の入口(ROUTINES_1350)は、PiO 1986年6月号のCHANGER mkIIと、
けいくん＠ちたの漢字表示システム(kanji-system)が呼ぶ入口を、ROMのある本体で呼んで働きを確かめたもの。
「J+1バイト」と書いたものは、Jが1なら2バイトを写す。
"""

# 名前と番地(働きは messages の rom.系統.名前)
ROUTINES_1251: dict[str, int] = {
    # 2つの数の計算(演算Y 演算 演算X → 演算X)
    "FADD": 0x0B50,
    "FSUB": 0x0B67,
    "FMUL": 0x0B76,
    "FDIV": 0x0B7F,
    "FPOW": 0x0B88,
    # 1つの数の関数(演算X → 演算X)
    "FSIN": 0x0B96,
    "FCOS": 0x0B9C,
    "FTAN": 0x0BA2,
    "FASN": 0x0BAF,
    "FACS": 0x0BB5,
    "FATN": 0x0BBB,
    "FEXP": 0x0BC1,
    "FLN": 0x0BC7,
    "FLOG": 0x0BCD,
    "FSQR": 0x0B8F,
    "FABS": 0x0B26,
    "FSGN": 0x0B2B,
    "FINT": 0x0CDE,
    "FDMS": 0x0A3A,
    "FDEG": 0x44E6,
    "FRND": 0x4018,
    "FROUND": 0x0D01,
    # 数の比較(演算Y 比較 演算X → 演算Xが1か0)
    "FEQ": 0x0C9F,
    "FNE": 0x0CCC,
    "FLT": 0x0CAD,
    "FGT": 0x0CA9,
    "FLE": 0x0CB9,
    "FGE": 0x0CDA,
    # 文字列の比較(24〜27番地と2C〜2F番地にD0・番地・長さ)
    "SEQ": 0x0BE0,
    "SNE": 0x0BD7,
    "SLT": 0x0C54,
    "SGT": 0x0C56,
    "SLE": 0x0C46,
    "SGE": 0x0C3D,
    # 文字列
    "FASC": 0x0F6A,
    "FVAL": 0x0F1C,
    "FCHRS": 0x0F8C,
    "FSTRS": 0x0EBE,
    # 整数と数
    "I2F": 0x0D42,
    "U2F": 0x0D3B,
    "RANGE16": 0x10E0,
    "F2I": 0x1737,
    # キー、表示、時間、字の形
    "KEYSCAN": 0x1F44,
    "KEYWAIT": 0x1D17,
    "KEYWAIT2": 0x1D23,
    "DISPON": 0x11E0,
    "DISPOFF": 0x11E5,
    "WAIT2MS": 0x1113,
    "WAIT4MS": 0x110F,
    "WAIT6MS": 0x110B,
    "GLYPH": 0x1FBC,
    "KEYWAIT0": 0x1D0D,
    "SWAPC": 0x1FB1,
    # 作業場所と、レジスタの受け渡し(PC-インタープリタが使う)
    "PRGTOP": 0x118F,
    "SHOWBUF": 0x11AF,
    "TEXTBUF": 0x11F9,
    "BA2Y": 0x11EE,
    "BA2YM": 0x11F5,
    "X1C": 0x1899,
    "PUSHX": 0x11C7,
    "POPX": 0x11D2,
    # レジスタの受け渡し(走れ!セコイラインのCOR版が使う)
    "BA2XM": 0x11F1,
    "LCDXM": 0x1184,
    "EXBAY": 0x18BB,
    "Y2DP": 0x18E7,
    "SAVEX": 0x1118,
    "LOADX": 0x1125,
    # レジスタの受け渡しと表示(PiOのゲームとMUSICサブルーチンが使う)
    "BA2X": 0x11E9,
    "EXX1C": 0x1ACF,
    "TEXTXM": 0x119C,
    "TEXTX": 0x119A,
    "COPYB": 0x1FB6,
    "SHOWRAM": 0x400C,
    "PRINTBUF": 0x567C,
    "NOISE": 0x6F40,
}

# PC-1251系の入口のうち、BASIC ROMが機種や版で違うため、一部の機種にしかないもの
ONLY_1251: dict[str, tuple[str, ...]] = {
    "PRINTBUF": ("1250", "1251", "1255"),
    "NOISE": ("1245",),
}

# BASIC ROMの版(7FFF番地)で番地の違う入口の、版ごとの番地(ROMのある本体と比べるときに使う)
BY_VERSION: dict[str, dict[int, int]] = {
    "PRINTBUF": {0xF0: 0x56C4, 0x00: 0x567C, 0x03: 0x5673},
}

# PC-1260/1261/1262の名前と番地
ROUTINES_1261: dict[str, int] = {
    # レジスタの受け渡し
    "BA2X": 0x0225,
    "BA2Y": 0x0222,
    "BA2XM": 0x022E,
    "BA2YM": 0x0242,
    "LCDYM": 0x0248,
    "Y664F": 0x1BE0,
    "X664F": 0x1C05,
    "B66Y": 0x1BE2,
    "BA2RP": 0x0226,
    "EXRPR0C": 0x13A4,
    "RCSLBA": 0x1559,
    "SLBA": 0x155A,
    "R382X": 0x133B,
    "X2R38": 0x134E,
    "R3A2X": 0x1A19,
    "X2R3A": 0x1A26,
    "EXXR38": 0x0F65,
    "EXXR28": 0x1953,
    # コンパイラLC-3が呼ぶもの
    "B67XM": 0x022C,
    "B67YM": 0x0240,
    "Y2RP": 0x134A,
    "R3A2RP": 0x1A1A,
    "EXXR0C": 0x13A3,
    "EXAY": 0x1549,
    "EXYRP": 0x154A,
    "YINC2R15": 0x0F7A,
    "POPX": 0x1039,
    "PUSHX": 0x102E,
    "SUBY": 0x1543,
    "LDSUBY": 0x1541,
    # メモリ
    "DP203D": 0x1353,
    "DP662B": 0x1357,
    "COPYB": 0x1047,
    "SET662E": 0x14E2,
    "MV6619": 0x1B6A,
    "FILL67B0": 0x1BA7,
    "FILL6650": 0x1B31,
    "CLR6650": 0x1B2F,
    "LDX66E1": 0x13BD,
    "STYDP": 0x156E,
    "PEEKBA": 0x0F30,
    "SKIPLINE": 0xC2CF,
    "SET662B": 0x19EE,
    "WAIT2MS": 0x08CF,
    "WAIT2MSZ": 0x08D5,
    "INC66E1": 0x07C0,
    # 液晶と字の形
    "DISPOFF": 0x0437,
    "DISPON": 0x043B,
    "GLYPH": 0x135F,
    "GLYPHX": 0x1367,
    "CURSOR": 0x10A7,
    # キーと電源
    "KEYNUM": 0x03C1,
    "INKEY": 0x1138,
    "MODESW": 0x18DA,
    "POWEROFF": 0x0458,
    # テープ(FENSCERが呼ぶもの。BASIC ROMの番地)
    "CLOAD": 0x9695,
}

# PC-1350の名前と番地
ROUTINES_1350: dict[str, int] = {
    "BA2XM": 0x0297,
    "BA2YM": 0x02B5,
    "COPYB": 0x1175,
    "FILL6EB0": 0x1C1C,
    "SHOWTEXT": 0x1DD9,
    "KEYNUM": 0x0436,
    "BA2Y": 0x027D,
    "BA2X": 0x0282,
    "SWAPC": 0x04B3,
    "WAIT6MS": 0x09E8,
    "PUSHX": 0x115C,
    "POPX": 0x1167,
    "R382X": 0x140B,
    "X2R38": 0x141E,
    "COPY5R": 0x1DB0,
    "EVAL": 0x0AB8,
    "NUMCHK": 0x1410,
    "F2I": 0x163A,
}

# 内部RAMの番地
RAM_1251: dict[str, tuple[int, str]] = {
    "FX": (0x20, "演算X(20〜27番地)"),
    "FY": (0x28, "演算Y(28〜2F番地)"),
    "ERRNO": (0x14, "エラーの番号"),
}

# Jが1でないと正しく動かないルーチン(系統ごと)
J_ONE = {
    "1251": {
        "SEQ",
        "SNE",
        "FCHRS",
        "F2I",
        "KEYSCAN",
        "KEYWAIT",
        "KEYWAIT2",
        "KEYWAIT0",
        "GLYPH",
        "SHOWRAM",
        "PRINTBUF",
    },
    "1261": {"GLYPH", "INKEY", "PUSHX"},
    "1350": {"SHOWTEXT", "PUSHX", "POPX", "F2I"},
}

# BASIC ROMの版(7FFF番地のバイト)
VERSIONS = {
    0xF0: "PC-1250/1251/1255 F0版",
    0x00: "PC-1250/1251/1255 00版",
    0x03: "PC-1250/1251/1255 03版",
    0x01: "PC-1245",
}


def entries(family: str) -> dict[str, int]:
    """系統(routines.FAMILIESの名前)の入口の表(名前と番地)"""
    return {"1251": ROUTINES_1251, "1261": ROUTINES_1261, "1350": ROUTINES_1350}[family]

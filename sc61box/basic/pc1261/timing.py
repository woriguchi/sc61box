"""PC-1261系とPC-1350のBASICの時間。ROMのある本体で、FORの繰り返しの1回にかかる時間を測って
決めた(繰り返しを100回と300回にした差から1回の時間を出す)

PC-1251系より、文を始める時間とNEXTがずっと短い(空のFOR・NEXTの1回が7.5ms)。計算の
ルーチンの時間は、PC-1251系の値に、測った関数の比(SIN 0.57、SQR 0.62、LOG 0.68、
RND 0.64、^ 0.72)から決めた倍率を掛けた。まだ測っていない値(IF、跳ぶ先を探す時間
など)は、PC-1251系の値かその比にした
"""

from dataclasses import replace

from ..timing import PC1251, ms

_SLOW = {"FADD", "FSUB", "FABS", "FINT", "FEQ", "FNE", "FLT", "FGT", "FLE", "FGE", "SEQ", "SNE",
         "SLT", "SGT", "SLE", "SGE", "FVAL", "FASC", "FCHRS", "FSTRS"}  # fmt: skip
_ROUTINES = {
    name: round(c * (0.72 if name == "FPOW" else 0.8 if name in ("F2I", "I2F") else 0.62))
    if name not in _SLOW
    else c
    for name, c in PC1251.routines.items()
}

PC1261 = replace(
    PC1251,
    STATEMENT=ms(3.9),  # TROFFを1つ足すと3.9ms
    NEXT_LOOP=ms(3.6),  # 空のFOR・NEXTの1回が7.5ms
    ASSIGN=ms(8.9),  # A=1で12.8ms
    FOR=ms(16.6),  # FOR J=1 TO 1:NEXT Jで28.0ms
    JUMP=ms(4.0),  # すぐ次の行へのGOTOで8.6ms
    GOSUB=ms(2.1),  # GOSUBとRETURNで11.6ms
    # 先の行へは、いまの行から探す。前の行(いまの行も)へは、プログラムの頭から探す。行の長さには
    # よらない(観察: 行1つで、GOTOとGOSUBで前へは0.34ms、先へはGOTOで0.34ms、GOSUBで0.52ms)
    JUMP_PER_LINE=ms(0.34),
    GOSUB_PER_LINE=ms(0.52),
    JUMP_BACK_PER_LINE=ms(0.34),
    JUMP_PER_BYTE=0,
    RETURN_PER_LINE=ms(0.19),  # 戻る行より前に行を40足すと、7.6ms長い
    LABEL=ms(3.0),  # GOSUB "B"で、すぐ次の行へのGOSUBより5.1ms長い
    LABEL_PER_CHAR=ms(0.67),  # "B"を"BCDEFG"にすると3.5ms長い
    LABEL_PER_LINE=ms(0.57),  # 前に空の行を20足すと11.4ms長い
    LABEL_PER_MARK=ms(2.8),  # 前にほかのラベルの行を1つ足すと3.2〜3.5ms長い
    LABEL_PER_BYTE=0,  # 行の長さにはよらない
    PRINT=ms(72.2),  # WAIT 0のあとPRINT "A"で76.1ms、PRINT 1で99.4ms
    PRINT_NUMBER=ms(23.3),
    LPRINT=0,  # 送らずにためるLPRINT "A";は、PRINTの字を作る時間だけ(送り始めはprinter.py)
    DIGIT=ms(0.38),  # A=12345はA=1より1.5ms長い
    OPERATOR=ms(6.7),  # +で11.0ms(FADDの4.3msを含む)
    RELATION=ms(7.1),  # >で12.3ms(FGTの5.2msを含む)
    PAREN=ms(3.6),
    MINUS=ms(3.6),
    FUNCTION=ms(3.3),  # ABSで3.4ms
    MUL=ms(12.7),  # A=I*3で13.8ms
    DIV=ms(18.3),  # A=I/3で25.1ms(答えの仮数の桁の和の平均が41)
    DIV_PER_DIGIT=ms(0.166),
    # BEEPの1回は、PC-1261で205.2ms鳴って209.3ms休む(PC-1350は203.8msと207.1ms)
    BEEP_ON=ms(204.5),
    BEEP_OFF=ms(208.2),
    # A=T(1)はA=Bより12.7ms、T(1)=Aは13.0ms、A=U(1,2)は20.2ms、A=A(2)は7.7ms長い(PC-1350も
    # ほぼ同じ)
    ARRAY=ms(11.4),
    ARRAY_PER_SUBSCRIPT=ms(7.3),
    FIXED_ARRAY=ms(6.2),
    READ_ITEM=ms(11.2),  # READ Aで15.3ms、READ A,B,Cで37.7ms、6つで71.3ms
    RESTORE_LINE=ms(9.0),  # RESTORE 30:A=BはA=Bより14.4ms長い
    routines=_ROUTINES,
)

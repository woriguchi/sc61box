# title: LC-3 サンプル1 文字を流す
# norom: basic
# help: 字が右へ流れたあと、液晶いっぱいに字が次々に出る。BRKで止める
# hex: lc3.hex
# setup: EQU#43
# mode: PRO
# run: CALL &4000
# run: CALL &4900
# LC-3コンパイラの記事(ポケコン・ジャーナル1989年6月号)のリスト3。「*COMPILER LC-3*」の
# 字をドット単位で右へ流してから、液晶いっぱいに文字を出していく。組のlc3.hexとEQU#43を使い、
# PROモードでCALL &4000(コンパイル)、CALL &4900(実行)と打つ。
10 REM LIST-2 ｻﾝﾌﾟﾙ.1
20 REM ﾓｼﾞﾋｮｳｼﾞ
30 #A WAIT 1: CURSOR A
40 " *COMPILER LC-3*"
50 A=A+1: IF A<240 GOTO #A
60 CURSOR 0
70 WAIT 9: CLEAR RND 128: CHR$ C:C=C+1: IF C¥0 GOTO ^

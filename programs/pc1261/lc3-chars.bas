# title: LC-3 サンプル3 定義文字
# norom: basic
# help: 自分で形を決めた字(定義文字)を出す。止まったら、何かキーを押すと終わる
# hex: lc3.hex
# setup: EQU#43
# mode: PRO
# run: CALL &4000
# run: CALL &4900
# LC-3コンパイラの記事のリスト5。配列に16進で字の形を書いて定義文字を作り(√101;〜)、
# 文字列の中のπで囲んだ字として出す。
10 REM LIST-4 ｻﾝﾌﾟﾙ.3
20 REM ﾃｲｷﾞﾓｼﾞ
30 CLS 0: CLEAR 0
40 √101;4E593F1F0E
50 "πAAπ LC-3 πAA"
60 WAIT 255
70 CHR$ 1:A=A+1: IF A<38 GOTO ^
80 STOP

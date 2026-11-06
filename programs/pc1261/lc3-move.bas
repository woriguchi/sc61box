# title: LC-3 サンプル2 キーで丸を動かす
# norom: basic
# help: 8・2・4・6で丸を上下左右に動かす(2つ同時に押すと斜め。Cmd+K・Ctrl+Kで矢印キーでも)。BRK(Esc)で止める
# hex: lc3.hex
# setup: EQU#43
# mode: PRO
# run: CALL &4000
# run: CALL &4900
# LC-3コンパイラの記事のリスト4。丸を8・2・4・6のキーで上下左右に動かす(INTで同時に
# 押したキーも読めるので、斜めにも動く)。BRKで止める。
10 REM LIST-3 ｻﾝﾌﾟﾙ.2
20 REM ﾄﾞｳｼﾞKEYﾆｭｳﾘｮｸ
30 REM -(2)(4)(6)(8)-
40 CLS 0
50 #A COS 224,4:K= INT
60 IF K AND 2 IF Y¥252:Y=Y-1
70 IF K AND 4 IF Y¥13:Y=Y+1
80 IF K AND 8 IF X:X=X-1
90 IF K AND 128 IF X<115:X=X+1
100 ON X,Y GRAD 0E1F1F1F0E
110 WAIT 5: GOTO #A

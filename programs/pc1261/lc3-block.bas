# title: LC-3 ブロック崩し
# norom: basic
# help: 何かキーを押すと始まる。8で上、2で下へパドルを動かして、右のブロックを消す
# help: パドルの端で打つと斜め、まんなかで打つとまっすぐ返る。BRK(Esc)で止める
# hex: lc3.hex
# setup: EQU#43
# mode: PRO
# run: CALL &4000
# run: CALL &4900
# コンパイラLC-3で書いたブロック崩し(このエミュレータの見本として書いたもの)。液晶の左端の
# パドル(縦4ドット)でボールを打ち返し、右側の8列×5段のブロック(2×2ドット)を消す。
# パドルの上端で打つと右上へ、下端で打つと右下へ、まんなかの2ドットで打つとまっすぐ返る
# (まっすぐ来たボールをまんなかで打つと、斜めのどちらかへ返る)。
# ボールは3つ。全部消すか、ボールがなくなると点数が出て、キーを押すともう一度始まる。
# 座標は横0〜119、縦0〜13(1行目が0〜6、2行目が7〜13)。TRONで点け、TROFFで消し、PIで点を調べる。
10 REM LC-3 BLOCK
20 CLS 0:CURSOR 0:"LC-3 BLOCK":CURSOR 120:"8:UP 2:DOWN  KEY?":STOP
30 CLS 0:J=0
40 #B I=0
50 #C X=I*3+90:Y=J*3:TRON X,Y:TRON X+1,Y:TRON X,Y+1:TRON X+1,Y+1
60 I=I+1:IF I<8 GOTO #C
70 J=J+1:IF J<5 GOTO #B
80 L=3:S=0:N=40:P=5:GOSUB $P
90 #S X=10:Y=RND 12)+1:U=1:V=1:TRON X,Y
100 #M WAIT 12:K=INT
110 IF K AND 2 IF P:GOSUB $E:P=P-1:GOSUB $P
120 IF K AND 4 IF P<10:GOSUB $E:P=P+1:GOSUB $P
130 A=X+U:B=Y+V
135 IF A=1 IF B>=P IF B<P+4 GOSUB $R
140 IF B>=14:V=0-V:B=Y+V
150 IF A>=120:U=255:A=X+U
170 IF A>=90 IF PI A,B:GOSUB $H
180 IF A=0 GOTO #O
190 TROFF X,Y:X=X+U:Y=Y+V:TRON X,Y
200 IF N GOTO #M
210 CLS 0:CURSOR 0:"CLEAR! ":PRINT S:STOP:RUN
220 #O SIN 200,20:TROFF X,Y:L=L-1:IF L GOTO #S
230 CLS 0:CURSOR 0:"GAME OVER ":PRINT S:STOP:RUN
240 $H I=A-90/3:J=B/3
250 C=I*3+90:D=J*3:TROFF C,D:TROFF C+1,D:TROFF C,D+1:TROFF C+1,D+1
260 U=0-U:A=X+U:S=S+1:N=N-1:SIN 40,2:RETURN
270 $P TRON 1,P:TRON 1,P+1:TRON 1,P+2:TRON 1,P+3:RETURN
280 $E TROFF 1,P:TROFF 1,P+1:TROFF 1,P+2:TROFF 1,P+3:RETURN
290 $R C=B-P:D=V:V=0
295 IF D=0:V=RND 2)*2-1
300 IF C=0:V=255
305 IF C=3:V=1
310 U=1:A=X+U:B=Y+V:SIN 100,2:RETURN

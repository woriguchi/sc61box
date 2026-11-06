# title: 動く線(PC-1350のグラフィック)
# help: 2つの端が液晶の縁で跳ね返りながら動く線を、10本ぶん残して描く。BRKで止める
# LINEの「,X」で点を反転して描き、10本前の線をもう一度「,X」で描いて消す。
# 線の端の位置はP〜S(10本ぶん)にためておく。
10 CLS:WAIT 0:RANDOM:DIM P(9),Q(9),R(9),S(9)
20 A=RND 149:B=RND 31:C=RND 149:D=RND 31
30 E=RND 3+1:F=RND 2:G=-RND 3-1:H=-RND 2:K=0:M=0
40 IF M LINE (P(K),Q(K))-(R(K),S(K)),X
50 LINE (A,B)-(C,D),X:P(K)=A:Q(K)=B:R(K)=C:S(K)=D
60 K=K+1:IF K>9 LET K=0:M=1
70 A=A+E:IF A<0 OR A>149 LET E=-E:A=A+2*E
80 B=B+F:IF B<0 OR B>31 LET F=-F:B=B+2*F
90 C=C+G:IF C<0 OR C>149 LET G=-G:C=C+2*G
100 D=D+H:IF D<0 OR D>31 LET H=-H:D=D+2*H
110 GOTO 40

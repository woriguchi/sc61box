# title: ヘビ(PC-1350のグラフィック)
# help: 8・2・4・6(ゲームパッドは十字キー)でヘビの向きを変え、点々のえさを食べる。体は消えずに伸び続ける
# help: 壁か自分の体にぶつかると終わり。ENTERで得点を出す
# pad: dpup=8 dpdown=2 dpleft=4 dpright=6 start=ENTER select=BRK
# 体は2×2ドットの四角(LINEのBF)、えさは2×2の斜めの2点。進む先の左上の点が点いているか
# 液晶の外なら(POINTが1か-1)、えさか、壁か体にぶつかった。IFは負の数を成り立たないとするので、
# <>0で調べる。しっぽを消さないのは、体の位置を配列にためて消すと、1歩にかかる時間が倍ほどに
# なるため。
10 CLS:WAIT 0:RANDOM
20 LINE (0,0)-(149,31),B
30 X=21:Y=15:E=2:F=0:S=0
40 LINE (X,Y)-(X+1,Y+1),BF:GOSUB 400
50 K$=INKEY$:IF K$<>"" GOSUB 200
60 X=X+E:Y=Y+F:IF POINT (X,Y)<>0 GOTO 300
70 LINE (X,Y)-(X+1,Y+1),BF:GOTO 50
200 IF K$="8" AND F=0 LET E=0:F=-2:RETURN
210 IF K$="2" AND F=0 LET E=0:F=2:RETURN
220 IF K$="4" AND E=0 LET E=-2:F=0:RETURN
230 IF K$="6" AND E=0 LET E=2:F=0
240 RETURN
300 IF X<>P OR Y<>Q GOTO 500
310 S=S+1:BEEP 1:GOTO 40
400 P=2*RND 74-1:Q=2*RND 15-1
410 IF POINT (P,Q) OR ABS (P-X)+ABS (Q-Y)<8 GOTO 400
420 PSET (P,Q):PSET (P+1,Q+1):RETURN
500 BEEP 3:WAIT:CLS
510 CURSOR 7,1:PRINT "GAME OVER"
520 CURSOR 7,2:PRINT "SCORE ";STR$ S
530 END

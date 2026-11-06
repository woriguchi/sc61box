"""PC-1261系のリザーブの置き方。固定の変数のすぐ上の65D0h〜65FFhに置く。キーのマークは、
A〜Oは80h+アルファベットの順(A=1)、P〜ZはE0h+アルファベットの順、=はF4h、空白はF1h
(観察: Aは81h、Sは0F3h)"""

from ..reserve import KEYS, Reserve

MARKS = {k: (0x80 if k <= "O" else 0xE0) + ord(k) - 0x40 for k in KEYS if k.isalpha()}
MARKS |= {"=": 0xF4, "SPC": 0xF1}
PC1261 = Reserve(lambda m: 0x65D0, MARKS)

"""PC-1251系のリザーブの置き方。プログラムの領域の手前の48バイト(PC-1251ではB800h〜B82Fh)に
置く。マークは、英字はE0h+アルファベットの順(A=1)、=はF4h、空白はF1h(観察)"""

from ..reserve import KEYS, SIZE, Reserve

MARKS = {k: 0xE0 + ord(k) - 0x40 for k in KEYS if k.isalpha()} | {"=": 0xF4, "SPC": 0xF1}
PC1251 = Reserve(lambda m: m.model.prog_start - SIZE, MARKS)

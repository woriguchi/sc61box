"""PC-1261系とPC-1350の機種ごとの違い"""

from dataclasses import replace

from .. import timing
from ..dialect import Dialect
from . import tokens

# PC-1261系。字のコードと字の形の違いはpc1261/の子クラスが受け持ち、ここには細かい違いを置く。
# まだ観察していないところは、PC-1251にならう
PC1261 = Dialect(
    name="1261",
    keywords=tokens.KEYWORDS_1261,
    abbreviations=tokens.ABBREVIATIONS_1261,
    error_lead=b"  ",  # 「  ERROR 1 IN 30」(観察)
    reserve=True,
    restore_colon=False,
    tape_before=timing.ms(584.0),  # CSAVEで音を出し始めるまで(観察)
    csave_after=timing.ms(907.0),  # 送り終えてから(BRKで止めたときも)>を出すまで(観察)
    cload_after=timing.ms(900.0),  # 読み終えてから>を出すまで(観察)
    leader_brk=0,  # 音を出し始めてから約500ms、1000ms、…(観察)
    cload_busy=True,  # 読むファイルが見つかると右下に*(観察)
    print_step_ends=True,
    pass_exact=True,  # 観察
    new_when_locked=False,  # 観察
    using_zero_quirk=True,
    using_limit=None,
    using_dot_first=False,
    val_exp_spaces=True,  # 観察
    subscript_quirk=False,
    repeat_delay=timing.ms(730.0),
    repeat_every=timing.ms(115.6),
    a_pair="last",
)

# PC-1350。命令の表とカセットの時間が違う。ほかはPC-1261にならう
PC1350 = replace(
    PC1261,
    name="1350",
    keywords=tokens.KEYWORDS_1350,
    abbreviations=tokens.ABBREVIATIONS_1350,
    reserve=False,
    tape_before=timing.ms(102.0),  # CSAVEで音を出し始めるまで(観察)
    csave_after=0,  # 観察
    cload_after=timing.ms(49.0),  # 読み終えてから>やERROR 8を出すまで(観察)
    cload_busy=False,  # 読むファイルが見つかっても*は出さない(観察)
)

DIALECTS = {"1260": PC1261, "1261": PC1261, "1262": PC1261, "1350": PC1350}

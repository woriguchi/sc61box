"""PC-1251系の機種ごとの違い"""

from .. import timing
from ..dialect import Dialect
from . import tokens

PC1251 = Dialect(
    name="1251",
    keywords=tokens.KEYWORDS_1251,
    abbreviations=tokens.ABBREVIATIONS_1251,
    error_lead=b"\x11\x11",
    reserve=True,
    restore_colon=False,
    tape_before=0,
    csave_after=0,
    cload_after=0,
    leader_brk=249,
    cload_busy=False,
    print_step_ends=True,
    pass_exact=False,
    new_when_locked=True,
    using_zero_quirk=True,
    using_limit=None,
    using_dot_first=False,
    val_exp_spaces=False,
    subscript_quirk=True,
    repeat_delay=timing.ms(730.0),
    repeat_every=timing.ms(115.6),
)


# PC-1245で、SHIFTのあとリザーブの位置のキーで打つ命令(観察)。「キー:命令」を並べる
SHIFT_1245 = (
    "A:INPUT S:IF D:THEN F:GOTO G:FOR H:TO J:STEP K:NEXT L:LIST =:RUN "
    "Z:PRINT X:USING C:GOSUB V:RETURN B:DIM N:END M:CSAVE SPC:CLOAD"
)


def _codes(table: str) -> dict[str, int]:
    code = {name: c for c, name in tokens.KEYWORDS_1245.items()}
    return {k: code[name] for k, name in (pair.split(":") for pair in table.split())}


PC1245 = Dialect(
    name="1245",
    keywords=tokens.KEYWORDS_1245,
    abbreviations=tokens.ABBREVIATIONS_1245,
    error_lead=b"\x11",
    reserve=False,
    restore_colon=True,
    tape_before=timing.ms(300.0),
    csave_after=timing.ms(593.0),
    cload_after=timing.ms(587.0),
    leader_brk=0,
    cload_busy=True,
    print_step_ends=False,
    pass_exact=True,
    new_when_locked=False,
    using_zero_quirk=False,
    using_limit=14,
    using_dot_first=True,
    val_exp_spaces=True,
    subscript_quirk=False,
    repeat_delay=timing.ms(730.0),
    repeat_every=timing.ms(103.0),  # 実機は約100〜110ms(表示をずらすときに長い)
    shift_keywords=_codes(SHIFT_1245),
)

DIALECTS = {"1250": PC1251, "1251": PC1251, "1255": PC1251, "1245": PC1245}

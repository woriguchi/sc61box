"""プログラム(programs.Program)を読み込めるかの検査と、読み込むときにTyperに入れる手順

ROMのある本体とROMなしのBASICはopen_problemとopen_steps、作業欄だけのROMなしは
bench_problemとbench_blocksを使う。検査は、読み込めない理由の文(tr済み)と出す秒数の組を
返し、読み込めるときはNoneを返す。どの文が出るかは検査の順序で決まる
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from . import keytype, workbench
from .i18n import tr
from .machine import PC1251
from .programs import Program

Blocks = list[tuple[int, bytes]]
Problem = tuple[str, float]  # 知らせる文と、出しておく秒数


def outside_message(name: str, addr: int) -> str:
    """プログラムがRAMの外の番地addrに書くので読み込まないときのメッセージ"""
    return tr("load.not_loaded_outside_ram", name=name, addr=addr)


def outside(m: PC1251, blocks: Blocks, top: int | None) -> list[int]:
    """RAMの終わりをtopに動かしたときに、blocksのうちRAMの外になる番地(いま広げている
    所を狭めるときは、そこも外になる)"""
    now = m.model.ram[1]
    new = m.ram_top(top)

    def ok(a: int) -> bool:
        if now <= a < new:  # 広げる所
            return True
        if new <= a < now:  # 狭めて外す所
            return False
        return m.writable(a)

    return [a for at, data in blocks for a in range(at, at + len(data)) if not ok(a)]


def _errors_problem(prog: Program, name: str) -> Problem | None:
    if prog.errors:
        return tr("load.not_loaded", name=name, why=prog.errors[0]), 8
    return None


def card_problem(prog: Program, m: PC1251, name: str) -> Problem | None:
    """# card: のRAMカードを差していないとき(PC-1350)"""
    if not prog.card or m.model.family != "1350" or m.card >= prog.card:
        return None
    return tr("load.needs_kb_ram_card",
              name=name, n=prog.card), 10  # fmt: skip


def ram_problem(prog: Program, m: PC1251) -> Problem | None:
    """プログラムの# ram: の範囲にRAMを広げられないとき"""
    if prog.ram is None or m.ram_top_ok(prog.ram_top):
        return None
    lo, hi = prog.ram
    return tr("load.not_loaded_ram_overlaps",
              name=prog.title or prog.name, lo=lo, hi=hi - 1), 8  # fmt: skip


def _outside_problem(m: PC1251, blocks: Blocks, top: int | None, name: str) -> Problem | None:
    out = outside(m, blocks, top)
    return (outside_message(name, out[0]), 8) if out else None


def open_problem(prog: Program, m: PC1251, encode: Callable[[str], bytes | None]) -> Problem | None:
    """ROMのある本体かROMなしのBASICに読み込めないとき、その理由。encodeはBASICを中間コードに
    する関数(App._encoded)で、ほかの検査を通ったときだけ、BASICの大きさを見るのに呼ぶ"""
    name = prog.title or prog.name
    # RAMカードが足りないときは、機種の検査をしない(番地がRAMに収まらず、機種が違うと出るので)
    short = card_problem(prog, m, name)
    return (
        (None if short else _model_problem(prog, m))
        or _errors_problem(prog, name)
        or short
        or (_norom_problem(prog, name, basic=True) if m.norom else None)
        or ram_problem(prog, m)
        or _outside_problem(m, prog.blocks + prog.after, prog.ram_top, name)
        or _long_problem(prog, m, name)
        or _size_problem(prog, m, name, encode)
        or _empty_problem(prog)
    )


def _model_problem(prog: Program, m: PC1251) -> Problem | None:
    if prog.runs_on(m.model.name) or prog.fits(m.writable):
        return None
    return tr("load.not_loaded_program_model",
              program=prog.label(m.model.name), model=m.model.title), 5  # fmt: skip


def _long_problem(prog: Program, m: PC1251, name: str) -> Problem | None:
    long = keytype.too_long(prog.basic, m.model.name) if prog.basic else None
    if long is None:
        return None
    hit = re.match(r"\s*(\d+)", long)
    if hit:
        msg = tr(
            "load.not_loaded_line_too",
            name=name,
            line=hit[1],
        )
    else:
        msg = tr(
            "load.not_loaded_line_too_name_text",
            name=name,
            text=long.strip()[:16],
        )
    return msg, 8


def _size_problem(
    prog: Program, m: PC1251, name: str, encode: Callable[[str], bytes | None]
) -> Problem | None:
    """中間コードにしてRAMに入らないとき(# setup:で領域を動かすものと、置けないものは見ない)"""
    data = encode(prog.basic) if prog.basic and not prog.setup else None
    if data is None or len(data) <= m.program_room():
        return None
    return (
        tr("load.not_loaded_basic_bytes",
           name=name, size=len(data), room=m.program_room()),
        8,
    )  # fmt: skip


def _empty_problem(prog: Program) -> Problem | None:
    if prog.blocks or prog.basic or prog.after:
        return None
    return tr("load.empty", name=prog.name), 4


def bench_blocks(prog: Program) -> tuple[Blocks, int | None]:
    """作業欄に書くダンプ(呼び出し用のBASICから拾ったPOKEを含む)と、最後のCALLの番地"""
    pokes, start = workbench.basic_hints(f"{prog.basic}\n{prog.run}")
    return prog.blocks + pokes + prog.after, start


def bench_problem(prog: Program, m: PC1251) -> Problem | None:
    """作業欄だけのROMなしで読み込めないとき、その理由。機種、行の長さ、BASICの大きさは
    見ない(BASICは打ち込まない)"""
    name = prog.title or prog.name
    return (
        _errors_problem(prog, name)
        or card_problem(prog, m, name)
        or _norom_problem(prog, name, basic=False)
        or ram_problem(prog, m)
        or _outside_problem(m, bench_blocks(prog)[0], prog.ram_top, name)
    )


def _norom_problem(prog: Program, name: str, basic: bool) -> Problem | None:
    """ROMなしで動かせないとき(一覧と同じProgram.without_romで決める)。basicならROMなしのBASIC"""
    if prog.without_rom(basic):
        return None
    if basic:
        why = tr("load.needs_rom", name=name)
    elif prog.blocks:
        why = tr("load.uses_basic_rom_routines", name=name)  # fmt: skip
    else:
        why = tr("load.basic_program_so_needs", name=name)
    return why, 6


@dataclass
class Step:
    """Typerに入れる手順の1つ。kindは mode(スイッチを動かす)、text(打つ)、idle(入力待ちに
    戻るのを待つ)、write(ダンプを書く)、basic(BASICを置く。App.store_basic)"""

    kind: str
    text: str = ""
    blocks: Blocks = field(default_factory=list)
    title: str = ""


def needs_new(prog: Program) -> bool:
    """PROモードでNEWしてからダンプを書くか。BASICも# setup:もなければ、ダンプはすぐ書く"""
    return bool(prog.basic or prog.setup)


def back_mode(m: PC1251) -> str:
    """BASICを置いたあと、実行しないときに戻すモード"""
    if m.model.family == "1350":
        return "PRO" if "PRO" in m.symbols() else "RUN"
    return m.mode if m.mode in ("RUN", "PRO") else "RUN"


def open_steps(prog: Program, run: bool, back: str) -> list[Step]:
    """ROMのある本体かROMなしのBASICに読み込む手順。needs_newでなければ、prog.blocksは
    この手順の前にすぐ書く。backはback_mode。runなら実行の命令も打つ"""
    new = needs_new(prog)
    steps: list[Step] = []
    if new:
        steps += [Step("mode", "PRO"), Step("text", "NEW\n")]
    if prog.setup:
        # BASICのプログラムの領域を動かす命令などを打ってから、空いたところにダンプを書く
        steps.append(Step("text", prog.setup + "\n"))
    if new:
        # NEWは固定変数も消すので、ダンプはNEWのあとで書く
        steps.append(Step("write", blocks=prog.blocks))
    if prog.basic:
        # 打ち込むかわりに、ROMが作るのと同じ中間コードをRAMに置く
        steps.append(Step("basic", prog.basic, title=prog.title or prog.name))
    if run and prog.run_command:
        steps.append(Step("mode", prog.mode.upper() or "RUN"))
        for i, line in enumerate(prog.run_command.split("\n")):
            if i:
                steps.append(Step("idle"))  # 前の命令が終わって入力待ちに戻るのを待つ
            steps.append(Step("text", line + "\n"))
    elif prog.basic and not prog.after:
        steps.append(Step("mode", back))
    if prog.after:
        steps.append(Step("write", blocks=prog.after))
    return steps

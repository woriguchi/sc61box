"""代替ROMルーチンを、ROMのある本体と比べる(--check-routines)

ROMのある本体とROMなしの本体に同じ値を与えて入口を呼び、戻ったときの内部RAM(00h〜4Fhと5Fh)、
フラグ、P・Q・DP、ポート、RAMと液晶RAM、かかったCPUのサイクル数を比べる。与える値は乱数で決め、
代替ROMルーチンのinputsがあれば、それで書き換える(番地を指すレジスタを読み書きしてよい所に向けるなど)。
比べないものは代替ROMルーチンのignoreに書く(100h未満の数は内部RAMの番地、100h以上はメモリの番地、名前は
routines.COMPARED)。サイクル数の違ってよい割合はtoleranceに書く。

ROMのある本体の文字の形の表は、ROMなしの本体と同じもの(エミュレータで描いたもの)に置き換えてから
呼ぶ。字の形の違いでは違いにならない。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import norom, romsyms, routines
from .basic import attach
from .i18n import tr
from .machine import CLOCK, RomNotFound, new_machine
from .routines import Routine, Stalled

RAM_COMPARED = (*range(0x50), 0x5F)  # 比べる内部RAMの番地(50h〜5Bhはスタック)
LIMIT = 3 * CLOCK  # 戻るまで待つCPUのサイクル数
SHOWN = 12  # 違いを書く数


@dataclass
class Case:
    """1回の呼び出しで与える値。代替ROMルーチンのinputs(case, rnd)が書き換えてよい"""

    ram: bytearray  # 内部RAMの00h〜5Bh。ram[1]がJ
    c: int
    z: int
    p: int
    q: int
    dp: int
    port: int  # Cポート(5Fh番地にも置く)
    mem: dict[int, bytes] = field(default_factory=dict)  # 呼ぶ前にメモリに書くもの
    held: set[str] = field(default_factory=set)  # 押しているキー(machine.KEYSの名前)
    mode: str = "RUN"  # モードスイッチ
    brk: bool = False  # BRK(ON)を押している
    presses: list[tuple[float, set[str]]] = field(default_factory=list)  # (秒, 押すキー)の順
    # 戻り番地を2つ積む(呼び出し元の戻り番地を取り出して、その先へ戻るルーチンを比べるとき)
    outer: bool = False


class Stray(Exception):
    """ROMなしの本体が、代替ROMルーチンのない番地へ進んだ"""

    def __init__(self, addr: int) -> None:
        super().__init__(tr("check.went_which_has_no", addr=addr))


@dataclass
class Report:
    routine: Routine
    cases: int
    failed: int
    first: list[str]  # 初めに違った回の違い

    @property
    def ok(self) -> bool:
        return not self.failed


def _ranges(m) -> list[tuple[int, int]]:
    return [m.model.ram, *m.model.lcd]


def _rom_ranges(m) -> list[tuple[int, int]]:
    ba = m.model.bas_addr
    return [(0, 0x2000), (ba, ba + m.model.bas_size)]


def machines(model: str):
    """(ROMのある本体, ROMなしの本体)。ROMがなければRomNotFound"""
    rom = new_machine(model)
    rom.mode = "RUN"
    rom.run(CLOCK)
    hle = new_machine(model, rom=False)
    norom.install(hle)
    attach(hle)  # 代替ROMルーチンの中には、ROMなしのBASICでPRINTの字を作るものがある
    for a in font_table(model):
        rom.mem[a] = hle.mem[a]  # 文字の形の表を同じにする
    return rom, hle


def font_table(model: str) -> list[int]:
    """ROMなしの本体が文字の形の表を置くROMの番地(norom.installが書く番地)"""
    marks = []
    for fill in (0x00, 0xFF):
        m = new_machine(model, rom=False)
        for lo, hi in _rom_ranges(m):
            m.mem[lo:hi] = bytes([fill]) * (hi - lo)
        norom.install(m)
        marks.append({a for lo, hi in _rom_ranges(m) for a in range(lo, hi) if m.mem[a] != fill})
    return sorted(marks[0] | marks[1])


def new_case(m, r: Routine, rnd: random.Random) -> Case:
    lo, hi = m.model.ram
    ram = bytearray(rnd.randrange(256) for _ in range(0x5C))
    ram[1] = 1 if r.j_one else rnd.choice((0, 1, 2, 7))
    case = Case(
        ram, rnd.randrange(2), rnd.randrange(2), rnd.randrange(0x5C), rnd.randrange(0x5C),
        rnd.randrange(lo, hi), rnd.choice((0, 1, 5)),
    )  # fmt: skip
    if r.inputs is not None:
        r.inputs(case, rnd)
    return case


def _sync(rom, hle) -> None:
    """ポートの出力とタイマ、内部RAMの5Ch〜5Eh(スタックの上を読むルーチンがある)をそろえる。
    2msのタイマは刻みの頭から数える(電源を切るルーチンなどは、途中で刻みが来るかで、止まるまでに
    進む命令が変わる)"""
    rom.t2 = 0
    rom.cpu._frac = hle.cpu._frac = 0  # 比べるときは時刻の端数なし(速さを1/1にして呼ぶ)
    for name in ("pa", "pb", "ko", "t2", "t2ms", "t512", "t512cnt"):
        if hasattr(rom, name):
            setattr(hle, name, getattr(rom, name))
    hle.cpu.ram[0x5C:0x5F] = rom.cpu.ram[0x5C:0x5F]


def _prepare(m, case: Case) -> None:
    cpu = m.cpu
    m.power, m.brk, m.mode = True, case.brk, case.mode
    m.held.clear()
    m.held.update(case.held)
    cpu.ram[0:0x5C] = case.ram
    cpu.ram[0x5F] = m.pc_out = case.port
    cpu.c, cpu.z, cpu.p, cpu.q, cpu.dp = case.c, case.z, case.p, case.q, case.dp
    for a, data in case.mem.items():
        m.mem[a : a + len(data)] = data


def call(m, addr: int, presses=(), limit: int = LIMIT, outer: bool = False) -> int | None:
    """戻り番地を積んでaddrを呼び、戻るまでのCPUのサイクル数を返す。ROMのある本体はROMを動かし、
    ROMなしの本体は登録簿の代替ROMルーチンを動かす(outerなら戻り番地を2つ積む)。電源が切れたら、
    そこまでのサイクル数。limitまでに戻らなければNone。ROMなしの本体が代替ROMルーチンのない番地へ
    進んだらStray、代替ROMルーチンが時間を進めずに入口にとどまり続けたらStalled"""
    cpu = m.cpu
    ret = m.model.ram[0]
    cpu.ratio, ratio = (1, 1), cpu.ratio
    cpu.r = 0x5C
    for _ in range(2 if outer else 1):
        cpu.push(ret >> 8)
        cpu.push(ret & 0xFF)
    cpu.pc = addr
    m.halted = False
    guard = bytearray(0x10000)
    guard[ret] = 1
    c0, i = cpu.cycles, 0
    try:
        while cpu.pc != ret:
            t = (cpu.cycles - c0) / CLOCK
            while i < len(presses) and t >= presses[i][0]:
                m.held.clear()
                m.held.update(presses[i][1])
                i += 1
            if m.norom:
                if not routines.call(m, cpu.pc):
                    raise Stray(cpu.pc)
            else:
                m.run(64, guard)
            if not m.power:
                break
            if cpu.cycles - c0 >= limit:
                return None
    finally:
        cpu.ratio = ratio
    return cpu.cycles - c0


def rom_entry(rom, r: Routine) -> int:
    """ROMのある本体で呼ぶ番地。BASIC ROMの版で番地の違う入口は、その本体の版の番地(入口の
    番地で決める。利用者が記述した代替ROMルーチンも同じ)"""
    if r.family == "1251":
        for name, addr in romsyms.ROUTINES_1251.items():
            if addr == r.addr and name in romsyms.BY_VERSION:
                return romsyms.BY_VERSION[name].get(rom.mem[0x7FFF], r.addr)
    return r.addr


def state(m) -> dict:
    cpu = m.cpu
    out: dict = {i: cpu.ram[i] for i in RAM_COMPARED}
    out.update(c=cpu.c, z=cpu.z, p=cpu.p, q=cpu.q, dp=cpu.dp, pa=m.pa, pb=m.pb, pc=m.pc_out,
               ko=getattr(m, "ko", 0), power=m.power)  # fmt: skip
    out["mem"] = [(lo, bytes(m.mem[lo:hi])) for lo, hi in _ranges(m)]
    return out


def differences(rom: dict, hle: dict, r: Routine) -> list[str]:
    """2つのstateの違い(ignoreのものは比べない)"""
    out = []
    for k, v in rom.items():
        if k in r.ignore or k == "mem" or v == hle[k]:
            continue
        if isinstance(k, int):
            text = tr("check.internal_ram_rom_stand", at=k, rom=v, hle=hle[k])
        else:
            text = tr("check.rom_stand", name=k, rom=int(v), hle=int(hle[k]))
        out.append(text)
    if "mem" not in r.ignore:
        for (lo, a), (_lo, b) in zip(rom["mem"], hle["mem"], strict=True):
            diff = [i for i in range(len(a)) if a[i] != b[i] and lo + i not in r.ignore]
            for i in diff[:3]:
                at, rom_v, hle_v = lo + i, a[i], b[i]
                out.append(tr("check.rom_stand_at_hle", at=at, rom=rom_v, hle=hle_v))
            if len(diff) > 3:
                out.append(tr("check.more_bytes", n=len(diff) - 3))
    return out


def check_routine(rom, hle, r: Routine, trials: int = 30, seed: object = 0) -> Report:
    """代替ROMルーチンrを、ROMのある本体romとROMなしの本体hleでtrials回比べる"""
    rnd = random.Random(f"{r.name}:{seed}")
    failed, first = 0, []
    for _ in range(trials):
        case = new_case(hle, r, rnd)
        for lo, hi in _ranges(hle):
            hle.mem[lo:hi] = rom.mem[lo:hi]
        _sync(rom, hle)
        results = []
        error: str | Stalled | None = None
        for m in (rom, hle):
            _prepare(m, case)
            try:
                cycles = call(m, r.addr if m is hle else rom_entry(rom, r), case.presses,
                              outer=case.outer)  # fmt: skip
            except Stalled as e:
                error = e
                break
            except Exception as e:  # 利用者が記述した代替ROMルーチンの誤り
                error = str(e) if isinstance(e, Stray) else f"{type(e).__name__}: {e}"
                break
            finally:
                m.brk, m.mode = False, "RUN"
            results.append((cycles if m.power else -1, state(m)))
            m.held.clear()
        if isinstance(error, Stalled):
            diff = [str(error)]
        elif error is not None:
            diff = [tr("check.stand_stopped", error=error)]
        else:
            (rom_cycles, rom_state), (cycles, hle_state) = results
            if rom_cycles is None:
                diff = [tr("check.does_not_return_machine")]
            elif cycles is None:
                diff = [tr("check.stand_does_not_return")]
            else:
                diff = differences(rom_state, hle_state, r)
                if "cycles" not in r.ignore and abs(cycles - rom_cycles) > r.tolerance * rom_cycles:
                    text = tr("check.cycles_rom_stand", rom=rom_cycles, hle=cycles)
                    diff.append(text)
        if diff:
            failed += 1
            if not first:
                first = diff
        rom.power = True
    return Report(r, trials, failed, first)


def select(model: str, which: str) -> list[Routine]:
    """比べる代替ROMルーチン。whichはuser(利用者が記述したもの)、all、または名前をコンマで
    区切ったもの"""
    family = routines.family_of(model)
    if family is None:
        raise ValueError(tr("common.model_has_no_rom", model=model))
    found = sorted(routines.for_model(model).values(), key=lambda r: r.addr)
    if which == "user":
        return [r for r in found if not r.builtin]
    if which == "all":
        return found
    # 名前は、アセンブラと同じ名前の表(routines.symbols)で引く
    names = [n.strip() for n in which.split(",") if n.strip()]
    chosen = {n: routines.by_name(model, n) or routines.by_name(model, n.upper()) for n in names}
    missing = [n for n, r in chosen.items() if r is None]
    if missing:
        raise ValueError(tr("check.no_entry_name", names=", ".join(missing)))
    return [r for r in chosen.values() if r is not None]


def check(model: str, which: str = "user", trials: int = 30) -> list[Report]:
    """機種modelの代替ROMルーチンをROMのある本体と比べる。ROMがなければRomNotFound"""
    chosen = select(model, which)
    if not chosen:
        return []
    rom, hle = machines(model)
    return [
        check_routine(rom, hle, r, trials) if comparable(r) else Report(r, 0, 0, []) for r in chosen
    ]


def comparable(r: Routine) -> bool:
    """ROMのある本体と比べる代替ROMルーチンか(組み込みで、比べ方を決めていないものは比べない)"""
    return not r.builtin or r.inputs is not None


def report_text(reports: list[Report]) -> str:
    lines = []
    for rep in reports:
        r = rep.routine
        where = tr("common.builtin") if r.builtin else r.source
        if not rep.cases:
            lines.append(tr("check.not_compared_only_reproduces",
                            name=r.name, addr=r.addr, where=where))  # fmt: skip
        elif rep.ok:
            lines.append(tr("check.ok_calls", name=r.name, addr=r.addr,
                            n=rep.cases, where=where))  # fmt: skip
        else:
            lines.append(tr("check.ng_calls_differ", name=r.name,
                            addr=r.addr, n=rep.cases, bad=rep.failed, where=where))  # fmt: skip
            lines += ["    " + d for d in rep.first[:SHOWN]]
            if len(rep.first) > SHOWN:
                lines.append("    " + tr("check.more_differences", n=len(rep.first) - SHOWN))
    return "\n".join(lines)


__all__ = [
    "Case", "Report", "RomNotFound", "Stalled", "Stray", "check", "check_routine", "report_text",
]  # fmt: skip

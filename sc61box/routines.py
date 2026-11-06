"""代替ROMルーチンの登録簿

ROMなしの本体で、ROMのルーチンの入口に飛んできたら、登録した代替ROMルーチンで働きをまねて、
呼んだ所へ戻す。入口は機種の系統(FAMILIES)ごとに、番地・名前・働きと関数で登録する。組み込みの
代替ROMルーチン(norom.py、norom1261.py、norom1350.py)も、利用者が記述した代替ROMルーチン
(データのフォルダのroutinesの中の.pyファイル)も、同じ形で登録する。

代替ROMルーチンの関数は本体mを受け取り、使ったCPUのサイクル数を返す。Noneを返すと、まだ待っている
(キーを待つルーチンなど)ので、戻らずに入口にとどまり、次にまた呼ばれる。待つあいだの時間は
関数がspend(m, CPUのサイクル数)で進める。どちらもCPUのサイクル数で、本体の比(PC-1261系と
PC-1350は3対4)で時刻に直す。

利用者が記述した代替ROMルーチンは、次のように書く。

    from sc61box.routines import routine

    @routine("1261", 0x1234, "TWICE", "Aを2倍にする", mode="fallback")
    def twice(m):
        m.cpu.ram[2] = m.cpu.ram[2] * 2 & 0xFF
        return 20

modeは、同じ番地に組み込みの代替ROMルーチンがあるときの扱い。fallback(足りないものを補う)なら
組み込みを使い、override(置き換える。書かなければこれ)なら利用者のものを使う。どちらも知らせる。
組み込みが一部の機種にしかないときは、機種ごとに決める。利用者が記述した代替ROMルーチンどうしで
番地が同じものと、名前が同じで番地が違うもの(組み込みとも)は、どれも使わずに知らせる。名前は
作業欄の逆アセンブルとアセンブラ(--rom)で使える。--check-routinesで、ROMのある本体と比べられる
(routinecheck.py)。--list-routinesで、使うものと使わないものの一覧を出す。
"""

from __future__ import annotations

import importlib.util
import keyword
import os
import sys
import traceback
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from weakref import WeakKeyDictionary

from . import paths, romsyms
from .i18n import Joined, Text, language

# 系統の名前と、その系統の機種(ROMの入口の番地が同じ機種)
FAMILIES: dict[str, tuple[str, ...]] = {
    "1251": ("1245", "1250", "1251", "1255"),
    "1261": ("1260", "1261", "1262"),
    "1350": ("1350",),
}

# 比べるもの(routinecheck)の名前。ほかに、数で内部RAMとメモリの番地を書く
COMPARED = ("c", "z", "p", "q", "dp", "pa", "pb", "pc", "ko", "power", "mem", "cycles")

Key = int | str
# 組み込みの代替ROMルーチンの比べ方(与える値, 比べないもの, サイクル数の違ってよい割合)
CheckSpec = tuple[Callable[..., None], tuple[Key, ...], float]


@dataclass(frozen=True)
class Routine:
    """ROMのルーチンの入口1つと、その代替ROMルーチン"""

    family: str
    addr: int
    name: str
    what: str  # 働き(作業欄に出す)。組み込みはmessagesのID、利用者が記述したものは文そのもの
    fn: Callable[[Any], int | None]  # 代替ROMルーチン。使ったCPUのサイクル数か、待っているならNone
    j_one: bool = False  # Jが1でないと正しく動かない
    source: str = ""  # 書いたファイル(組み込みなら空)
    mode: str = ""  # 利用者が記述した代替ROMルーチンの、組み込みとの扱い(MODES)
    models: tuple[str, ...] | None = None  # 系統の中でこの入口のある機種(Noneならどれも)
    # routinecheckで使うもの。inputsはCaseを書き換えて、与える値を決める関数。ignoreは比べない
    # もの(100h未満は内部RAMの番地、100h以上はメモリの番地、またはCOMPAREDの名前)。toleranceは、
    # サイクル数の違ってよい割合
    inputs: Callable[..., None] | None = None
    ignore: frozenset[Key] = frozenset()
    tolerance: float = 0.05

    @property
    def builtin(self) -> bool:
        return not self.source

    def on(self, model: str) -> bool:
        """機種の名前(か系統の名前)modelに、この入口があるか"""
        return self.models is None or model in self.models or model not in _MODELS


MODES = ("override", "fallback")

_builtin: dict[str, dict[int, Routine]] = {}
# 利用者が記述した代替ROMルーチン
_candidates: list[Routine] = []  # 読めたファイルで登録したもの
_pending: list[Routine] | None = None  # 読んでいるファイルで登録したもの(読み終えたら確定)
_decision: _Decision | None = None  # 候補から決めた使うもの(候補が変わるたびに作り直す)
_notices: list[str | Text] = []  # 出すときに訳す
_loaded: str | None = None  # 読んだフォルダ
_NONE: dict[int, Routine] = {}
_MODELS = {model for models in FAMILIES.values() for model in models}


def family_of(model: str) -> str | None:
    """機種の名前(1251など)か系統の名前から、系統の名前。ROMの入口の表のない機種はNone"""
    for family, models in FAMILIES.items():
        if model == family or model in models:
            return family
    return None


def _keys(keys: Iterable[Key | range]) -> frozenset[Key]:
    out: set[Key] = set()
    for k in keys:
        if isinstance(k, range):
            out.update(k)
        elif isinstance(k, str) and k not in COMPARED:
            raise ValueError(Text("routines.not_compared_name", name=k))
        else:
            out.add(k)
    return frozenset(out)


def routine(
    family: str,
    addr: int,
    name: str,
    what: str = "",
    *,
    j_one: bool = False,
    inputs: Callable[..., None] | None = None,
    ignore: Iterable[Key | range] = (),
    tolerance: float = 0.05,
    mode: str = "override",
) -> Callable[[Callable[[Any], int | None]], Callable[[Any], int | None]]:
    """利用者が記述した代替ROMルーチンを登録するデコレータ。familyは系統か機種の名前(1251、
    1261、1350など)。modeは組み込みとの扱い(fallbackかoverride)"""
    fam = family_of(family)
    # 読み込んだときのエラーは、利用者に出す(出すときの言語で出せるようにTextで持たせる)
    if fam is None:
        raise ValueError(Text("routines.not_family", model=family))
    if not 0 <= addr <= 0xFFFF:
        raise ValueError(Text("routines.address_out_of_range", addr=addr))
    if not name.isidentifier():
        raise ValueError(Text("routines.bad_name", name=name))
    if mode not in MODES:
        raise ValueError(Text("routines.bad_mode", mode=mode))

    def wrap(fn: Callable[[Any], int | None]) -> Callable[[Any], int | None]:
        code = getattr(fn, "__code__", None)
        source = code.co_filename if code is not None else "?"
        r = Routine(fam, addr, name, what, fn, j_one, source, mode,
                    inputs=inputs, ignore=_keys(ignore), tolerance=tolerance)  # fmt: skip
        if _pending is not None:
            _pending.append(r)  # ファイルを読み終えたら確定する
        else:
            _candidates.append(r)
            _resolve()
        return fn

    return wrap


def _builtin_names(family: str) -> dict[str, int]:
    """組み込みの名前と番地(内部RAMの名前も)"""
    out = dict(romsyms.entries(family))
    if family == "1251":
        out.update({name: a for name, (a, _) in romsyms.RAM_1251.items()})
    return out


@dataclass(frozen=True)
class _Choice:
    """機種(か系統)で使う代替ROMルーチン"""

    entries: dict[int, Routine]  # 入口の番地と、使う代替ROMルーチン
    unused: list[tuple[Routine, str | Text]]  # 利用者が記述したもののうち使わないものと、その理由


class _Decision:
    """利用者が記述した代替ROMルーチンの候補と組み込みから決めた、使うものと使わないもの。
    一部の機種にしかない組み込みとのfallbackは、機種ごとの答え(choice)で決める"""

    def __init__(self, candidates: list[Routine]) -> None:
        self.user: dict[str, dict[int, Routine]] = {}  # 番地も名前もぶつからないもの
        self.unused: dict[str, list[tuple[Routine, str | Text]]] = {}
        self.notices: list[str | Text] = []
        self._choices: dict[tuple[str, str | None], _Choice] = {}
        for family in FAMILIES:
            self._decide(family, [r for r in candidates if r.family == family])

    def _decide(self, family: str, found: list[Routine]) -> None:
        builtin = _builtins().get(family, {})
        names = _builtin_names(family)
        by_addr: dict[int, list[Routine]] = {}
        by_name: dict[str, set[int]] = {}
        for r in found:
            by_addr.setdefault(r.addr, []).append(r)
            by_name.setdefault(r.name, set()).add(r.addr)
        user: dict[int, Routine] = {}
        unused: list[tuple[Routine, str | Text]] = []
        self.user[family] = user
        self.unused[family] = unused
        for r in found:
            why: str | Text
            if len(by_addr[r.addr]) > 1:
                files = Joined(sorted({str(_where(x)) for x in by_addr[r.addr]}))
                why = Text("routines.have_more_than_one", files=files, addr=r.addr)
            elif r.name in names and names[r.name] != r.addr:
                why = Text("routines.name_used_built", name=r.name, addr=names[r.name])
            elif len(by_name[r.name]) > 1:
                where = Joined(f"{a:04X}" for a in sorted(by_name[r.name]))
                why = Text("routines.name_used", name=r.name, addrs=where)
            elif r.addr in builtin and r.mode == "fallback" and builtin[r.addr].models is None:
                why = _shadowed(r, builtin[r.addr])
            else:
                if r.addr in builtin and r.mode != "fallback":
                    self.notices.append(
                        Text("routines.replaces_built",
                             file=_where(r), name=r.name, addr=r.addr, old=builtin[r.addr].name)
                    )  # fmt: skip
                user[r.addr] = r
                continue
            unused.append((r, why))
            self.notices.append(
                Text("routines.not_used", file=_where(r), name=r.name, addr=r.addr, why=why)
            )

    def choice(self, family: str, model: str | None) -> _Choice:
        """系統familyの機種modelで使うもの。modelがNoneなら系統の表(どの機種の入口も含み、
        fallbackは組み込みに負ける)。初めて引くときに作って覚える"""
        found = self._choices.get((family, model))
        if found is None:
            entries = {a: r for a, r in _builtins().get(family, {}).items()
                       if model is None or r.on(model)}  # fmt: skip
            unused = list(self.unused.get(family, []))
            for a, r in self.user.get(family, {}).items():
                if model is not None and not r.on(model):
                    continue
                if r.mode == "fallback" and a in entries:
                    unused.append((r, _shadowed(r, entries[a])))
                else:
                    entries[a] = r
            found = self._choices[(family, model)] = _Choice(entries, unused)
        return found


def _resolve() -> None:
    """候補から使うものを決め直し、知らせることを足す"""
    global _decision
    _decision = _Decision(_candidates)
    _notices.extend(_decision.notices)


def _current() -> _Decision:
    """使うもの。初めて使うときに、利用者が記述した代替ROMルーチンを読む"""
    if _loaded is None:
        load_user()
    return _decision if _decision is not None else _Decision([])  # 初めて読んでいる途中


def _shadowed(r: Routine, old: Routine) -> Text:
    return Text("routines.there_built", addr=r.addr, old=old.name)


def _where(r: Routine) -> str | Text:
    return os.path.basename(r.source) if r.source else Text("common.builtin")


class _Raised:
    """例外の型の名前と中身(「ValueError: …」)。中身がTextなら、出すときの言語の文にする"""

    def __init__(self, e: BaseException) -> None:
        self.e = e

    def __format__(self, spec: str) -> str:
        return format(f"{type(self.e).__name__}: {self.e}", spec)


def _builtins() -> dict[str, dict[int, Routine]]:
    """組み込みの代替ROMルーチン(初めに使うときに作る)"""
    if not _builtin:
        from . import norom, norom1261, norom1350

        sets = (
            ("1251", romsyms.ROUTINES_1251, norom.routine_fns(), norom.CHECK),
            ("1261", romsyms.ROUTINES_1261, norom1261.ROUTINES, norom1261.CHECK),
            ("1350", romsyms.ROUTINES_1350, norom1350.ROUTINES, norom1350.CHECK),
        )
        for family, entries, fns, check in sets:
            table = _builtin[family] = {}
            for name, addr in entries.items():
                what = f"rom.{family}.{name.lower()}"  # messagesのID
                if name in fns:
                    inputs, ignore, tolerance = check.get(name, (None, (), 0.0))
                    table[addr] = Routine(
                        family, addr, name, what, fns[name], name in romsyms.J_ONE[family],
                        models=romsyms.ONLY_1251.get(name) if family == "1251" else None,
                        inputs=inputs, ignore=_keys(ignore), tolerance=tolerance,
                    )  # fmt: skip
    return _builtin


def user_folder() -> str:
    """利用者が記述した代替ROMルーチンを置くフォルダ"""
    return os.path.join(paths.data_dir(), "routines")


def load_user(folder: str | None = None, force: bool = False) -> list[str]:
    """フォルダ(なければuser_folder())の.pyファイルを読んで、利用者が記述した代替ROMルーチンを
    登録する。同じフォルダを読んだことがあれば、forceでなければ読み直さない。知らせることの一覧を
    返す"""
    global _loaded, _pending
    folder = folder or user_folder()
    if _loaded == folder and not force:
        return [str(n) for n in _notices]
    _candidates.clear()
    _notices.clear()
    _loaded = folder
    if not os.path.isdir(folder):
        _resolve()
        return []
    for entry in sorted(os.listdir(folder)):
        if not entry.endswith(".py") or entry.startswith((".", "_")):
            continue
        path = os.path.join(folder, entry)
        module = f"sc61box_routines.{entry[:-3]}"
        _pending = []
        try:
            spec = importlib.util.spec_from_file_location(module, path)
            assert spec is not None and spec.loader is not None
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module] = mod
            spec.loader.exec_module(mod)
            _candidates.extend(_pending)  # 最後まで読めたファイルの登録だけを使う
        except Exception as e:
            sys.modules.pop(module, None)
            if isinstance(e, SyntaxError):
                line = e.lineno or 0
            else:
                frames = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == path]
                line = frames[-1].lineno if frames else 0
            _notices.append(Text("routines.cannot_load", file=entry, line=line, error=_Raised(e)))
        finally:
            _pending = None
    _resolve()
    return [str(n) for n in _notices]


def listing(model: str) -> list[tuple[Routine, str]]:
    """機種modelの代替ROMルーチンの一覧(番地の順)。使うものは空の文字列と、利用者が記述した
    もののうち使わないものは理由と組にする"""
    family = family_of(model)
    if family is None:
        return []
    choice = _current().choice(family, model)
    used = [(r, "") for r in choice.entries.values()]
    unused = [(r, str(why)) for r, why in choice.unused]
    return sorted(used + unused, key=lambda x: (x[0].addr, x[1] != ""))


def notices() -> list[str]:
    """利用者が記述した代替ROMルーチンを読んだときに知らせること(置き換え、読めなかったファイル)"""
    if _loaded is None:
        load_user()
    return [str(n) for n in _notices]


def table(family: str) -> dict[int, Routine]:
    """系統の入口の番地と代替ROMルーチン。利用者が記述したものは、fallbackでなければ組み込みに
    勝つ。初めて使うときに、利用者が記述したものを読む。返す表は書き換えない"""
    return _current().choice(family, None).entries


def for_model(model: str) -> dict[int, Routine]:
    """機種modelの入口の番地と代替ROMルーチン(系統の表から、その機種にない入口を除き、
    fallbackを機種ごとに決めたもの)。返す表は書き換えない"""
    family = family_of(model)
    if family is None:
        return _NONE
    return _current().choice(family, model).entries


def for_machine(m) -> dict[int, Routine]:
    """本体mで使う代替ROMルーチン(ROMなしの本体だけ)"""
    if not m.norom:
        return _NONE
    return for_model(m.model.name)


def find(model: str, addr: int) -> Routine | None:
    """機種modelの番地addrの入口(ROMがあってもなくても引ける)"""
    return for_model(model).get(addr)


def by_name(model: str, name: str) -> Routine | None:
    """名前nameの入口の代替ROMルーチン(アセンブラと同じ名前の表で引く)"""
    if family_of(model) is None:
        return None
    addr = symbols(model).get(name)
    return None if addr is None else for_model(model).get(addr)


STALLED = 1000  # 時間を進めずに入口にとどまる呼び出しが、この回数続いたらStalled


class Stalled(Exception):
    """代替ROMルーチンが、時間を進めずに入口にとどまり続けた(待つあいだにspendを呼んでいない)"""

    def __init__(self, r: Routine) -> None:
        self.text = Text("routines.keeps_waiting_without_advancing", name=r.name, addr=r.addr)
        super().__init__(self.text)
        self.routine = r


_still: WeakKeyDictionary[Any, tuple[int, int, int]] = WeakKeyDictionary()  # (番地, サイクル, 回数)


def call(m, addr: int) -> bool:
    """addrが代替ROMルーチンのある入口なら、代替ROMルーチンを動かして呼んだ所へ戻し、Trueを返す(待っている
    ルーチンは入口にとどまる)。時間を進めずに入口にとどまる呼び出しがSTALLED回続いたらStalled"""
    r = for_machine(m).get(addr)
    if r is None:
        return False
    cpu = m.cpu
    before = cpu.cycles
    spent = r.fn(m)
    if spent is None:
        if cpu.pc == addr and cpu.cycles == before:
            last = _still.get(m)
            n = last[2] + 1 if last is not None and last[:2] == (addr, before) else 1
            if n >= STALLED:
                _still.pop(m, None)
                raise Stalled(r)
            _still[m] = (addr, before, n)
        elif _still:
            _still.pop(m, None)
        return True
    if _still:
        _still.pop(m, None)
    lo = cpu.pop()
    cpu.pc = lo | cpu.pop() << 8  # RTNと同じ
    spend(m, spent)
    return True


def spend(m, cycles: int) -> None:
    """CPUのサイクル数cyclesぶん時間を進める(本体の比で時刻に直す)。待っている代替ROMルーチンは、
    待つあいだの時間をこれで進める"""
    m.pass_time(m.cpu._ticks(cycles))


def symbols(model: str = "1251") -> dict[str, int]:
    """アセンブラに渡す名前と値。modelは系統か機種の名前"""
    family = family_of(model)
    if family is None:
        raise ValueError(Text("routines.no_rom_names", model=model))
    out = {name: a for name, a in _builtin_names(family).items() if name not in romsyms.ONLY_1251
           or model in romsyms.ONLY_1251[name] or model not in _MODELS}  # fmt: skip
    out.update({r.name: r.addr for r in for_model(model).values()})
    return out


def template(model: str, addr: int, name: str = "") -> str:
    """番地addrの代替ROMルーチンを書き始めるファイルの中身"""
    family = family_of(model)
    if family is None:
        raise ValueError(Text("routines.not_family", model=model))
    name = name or f"R{addr:04X}"
    if not 0 <= addr <= 0xFFFF or not name.isidentifier():
        raise ValueError(Text("routines.bad_address_or_name", addr=addr, name=name))
    fn = name.lower() + ("_" if keyword.iskeyword(name.lower()) else "")
    if language() == "en":
        return f'''"""Stand-in for the ROM routine at {addr:04X}

Decide what it does by calling it on a machine with the ROM: give it values, then look at the
internal RAM, memory, flags and cycle count when it returns. Do not copy the ROM's instructions or
tables. When it is written, compare it with the machine with the ROM:

    sc61box --model {model} --check-routines {name}
"""

from sc61box.routines import routine, spend


# mode="fallback": if a later version of sc61box brings a built-in stand-in for this address,
# the built-in one is used (you are told). mode="override" keeps using this one
@routine("{family}", 0x{addr:04X}, "{name}", "what it does", mode="fallback")
def {fn}(m):
    cpu = m.cpu
    ram = cpu.ram  # internal RAM: ram[2] is A, ram[3] is B, ram[4] and ram[5] are X
    # do the work here (m.read and m.write for memory, cpu.c and cpu.z for flags).
    # To wait (for a key, say), pass the time with spend(m, CPU cycles) and return None;
    # the routine is called again:
    #     if not m.held:
    #         spend(m, 100)
    #         return None
    return 0  # CPU cycles used
'''
    return f'''"""ROMの{addr:04X}番地の代替ROMルーチン

ROMのある本体で値を与えて呼び、戻ったときの内部RAM、メモリ、フラグと、かかったサイクル数を見て
働きを決める。ROMの命令の並びや表を写さない。書いたら次で、ROMのある本体と比べられる。

    sc61box --model {model} --check-routines {name}
"""

from sc61box.routines import routine, spend


# mode="fallback": sc61boxの新しい版に、この番地の組み込みの代替ROMルーチンが入ったら、
# 組み込みを使う(知らせる)。mode="override"なら、このファイルの代替ROMルーチンを使い続ける
@routine("{family}", 0x{addr:04X}, "{name}", "働き", mode="fallback")
def {fn}(m):
    cpu = m.cpu
    ram = cpu.ram  # 内部RAM。ram[2]がA、ram[3]がB、ram[4]・ram[5]がX
    # ここに働きを書く(m.read・m.writeでメモリ、cpu.c・cpu.zでフラグ)。
    # キーを待つときなどは、待つあいだの時間をspend(m, CPUのサイクル数)で進めてNoneを返す
    # (また呼ばれる)。例:
    #     if not m.held:
    #         spend(m, 100)
    #         return None
    return 0  # 使ったCPUのサイクル数
'''


def write_template(model: str, addr: int, name: str = "", folder: str | None = None) -> str:
    """templateの中身をフォルダ(なければuser_folder())に書き、そのパスを返す。同じ名前の
    ファイルがあれば書かない(FileExistsError)"""
    text = template(model, addr, name)
    folder = folder or user_folder()
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{(name or f'R{addr:04X}').lower()}.py")
    with open(path, "x", encoding="utf-8") as f:
        f.write(text)
    return path

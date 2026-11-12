"""代替ROMルーチンの登録簿(routines.py)と、ROMのある本体との比べ(routinecheck.py)"""

import re

import pytest
from conftest import HAVE_ROM, HAVE_ROM_1245, HAVE_ROM_1260

from sc61box import cli, norom, romsyms, routinecheck, routines, workbench
from sc61box.machine import new_machine
from sc61box.routines import routine

TWICE = """
from sc61box.routines import routine


@routine("1261", 0x5F00, "TWICE", "Aを2倍にする")
def twice(m):
    m.cpu.ram[2] = m.cpu.ram[2] * 2 & 0xFF
    return 20
"""

# ROMのBA2X(0225h)と同じ働きを、利用者が書いたもの
BA2X = """
from sc61box.routines import routine


@routine("1261", 0x0225, "MYBA2X", "AからJ+1バイトをXへ")
def my_ba2x(m):
    cpu = m.cpu
    j = cpu.ram[1]
    for k in range(j + 1):  # 重なっていれば、写したバイトをまた写す
        cpu.ram[4 + k] = cpu.ram[2 + k]
    cpu.p, cpu.q = 4 + j + 1, 2 + j + 1
    return 15 + 2 * j
"""


# 待っていると答えて、時間を進めない(spendを呼び忘れた)もの。組み込みのDISPONに代わる
STUCK = """
from sc61box.routines import routine


@routine("1251", {addr}, "STUCK", "時間を進めずに待つ")
def stuck(m):
    return None
"""


@pytest.fixture
def folder(tmp_path):
    """利用者が記述した代替ROMルーチンを置くフォルダ。試験のあとは空のフォルダを読み直す"""
    yield tmp_path
    empty = tmp_path / "empty"
    empty.mkdir(exist_ok=True)
    routines.load_user(str(empty), force=True)


def _hle(model):
    m = new_machine(model, rom=False)
    norom.install(m)
    return m


def _call(m, addr):
    """戻り番地を積んでaddrを登録簿で呼ぶ。(戻ったか, 進んだ時刻)"""
    cpu = m.cpu
    cpu.r = 0x5C
    cpu.push(0x60)
    cpu.push(0x00)
    cpu.pc = addr
    c0 = cpu.cycles
    done = routines.call(m, addr)
    return done and cpu.pc == 0x6000, cpu.cycles - c0


@pytest.mark.parametrize("family", list(routines.FAMILIES))
def test_builtins_cover_entry_tables(family):
    """組み込みの代替ROMルーチンは、romsymsの入口の表のすべての入口にあり、どの機種でも同じ表を引く
    (BASIC ROMが機種で違う入口は、その機種だけ)"""
    table = routines.table(family)
    entries = romsyms.entries(family)
    assert {r.name: r.addr for r in table.values()} == entries
    assert all(r.builtin and r.family == family for r in table.values())
    assert {r.name for r in table.values() if r.j_one} == romsyms.J_ONE[family]
    for model in routines.FAMILIES[family]:
        assert routines.family_of(model) == family
        names = {r.name for r in routines.for_model(model).values()}
        only = {n for n, models in romsyms.ONLY_1251.items() if model not in models}
        assert names == set(entries) - (only if family == "1251" else set())
        assert set(routines.symbols(model)) >= names and not only & set(routines.symbols(model))


def test_entries_only_on_some_models():
    """PRINTBUFはPC-1250/1251/1255だけ、NOISEはPC-1245だけにある"""
    assert routines.find("1251", 0x567C) is not None and routines.find("1245", 0x567C) is None
    assert routines.find("1245", 0x6F40) is not None and routines.find("1255", 0x6F40) is None
    m = _hle("1245")
    assert not routines.call(m, 0x567C) and 0x6F40 in routines.for_machine(m)


def test_only_rom_less_machines_use_stand_ins():
    m = _hle("1251")
    assert routines.for_machine(m) is routines.for_model("1251")
    m.norom = False
    assert not routines.for_machine(m) and not routines.call(m, routines.symbols()["FADD"])
    assert routines.family_of("1250") == "1251" and routines.family_of("9999") is None
    with pytest.raises(ValueError):
        routines.symbols("9999")
    assert routines.symbols()["FX"] == 0x20  # PC-1251系は内部RAMの名前も


def test_cycles_are_cpu_cycles():
    """代替ROMルーチンが返すのはCPUのサイクル数で、本体の比で時刻に直す(PC-1251は1対1、PC-1261は3対4)"""
    m = _hle("1251")
    assert _call(m, routines.symbols()["FADD"]) == (True, 830)
    m = _hle("1261")
    done, ticks = _call(m, routines.symbols("1261")["DP203D"])
    assert done and ticks == 9 and m.cpu.dp == 0x203D  # 12サイクル × 3/4


def test_user_routine_is_loaded_and_called(folder):
    """データのフォルダのroutinesの.pyに記述した代替ROMルーチンは、ROMなしの本体で呼ばれ、名前は作業欄と
    アセンブラで使える"""
    (folder / "twice.py").write_text(TWICE, encoding="utf-8")
    assert routines.load_user(str(folder), force=True) == []
    m = _hle("1262")
    m.cpu.ram[2] = 0x21
    assert _call(m, 0x5F00) == (True, 15) and m.cpu.ram[2] == 0x42
    r = routines.find("1261", 0x5F00)
    assert r is not None and not r.builtin and r.source.endswith("twice.py")
    assert routines.symbols("1261")["TWICE"] == 0x5F00
    assert workbench.rom_name(0x5F00, "1261") == "TWICE(Aを2倍にする)"
    assert routines.find("1251", 0x5F00) is None  # ほかの系統には置かない


def test_user_routine_replaces_builtin_with_notice(folder):
    (folder / "ba2x.py").write_text(BA2X, encoding="utf-8")
    notices = routines.load_user(str(folder), force=True)
    assert notices == ["ba2x.py: MYBA2X(0225)が、組み込みのBA2Xに代わります"]
    r = routines.find("1261", 0x0225)
    assert r is not None and r.name == "MYBA2X"
    assert routines.symbols("1261")["BA2X"] == 0x0225  # 組み込みの名前もそのまま使える


def test_broken_user_file_is_reported(folder):
    """読めないファイルは知らせて飛ばし、ほかのファイルは読む"""
    (folder / "bad.py").write_text("x = (\n", encoding="utf-8")
    (folder / "wrong.py").write_text(
        "from sc61box.routines import routine\nroutine('1500', 0x100, 'A')\n", encoding="utf-8"
    )
    (folder / "twice.py").write_text(TWICE, encoding="utf-8")
    notices = routines.load_user(str(folder), force=True)
    assert len(notices) == 2
    assert notices[0].startswith("bad.py:") and "SyntaxError" in notices[0]
    assert notices[1].startswith("wrong.py:2: 読めません(ValueError")
    assert routines.find("1261", 0x5F00) is not None


def test_template_is_a_routine(folder):
    """--new-routineのファイルは、そのまま読める代替ROMルーチン(働きは書いていない)"""
    path = routines.write_template("1350", 0x1234, "", str(folder))
    assert path.endswith("r1234.py")
    text = open(path, encoding="utf-8").read()
    assert '@routine("1350", 0x1234, "R1234", "働き", mode="fallback")' in text
    assert "--model 1350 --check-routines R1234" in text
    with pytest.raises(FileExistsError):
        routines.write_template("1350", 0x1234, "", str(folder))
    with pytest.raises(ValueError):
        routines.write_template("1350", 0x1234, "1BAD", str(folder))
    assert not (folder / "1bad.py").exists()
    assert routines.load_user(str(folder), force=True) == []
    r = routines.find("1350", 0x1234)
    assert r is not None and r.name == "R1234"


def test_new_routine_option(folder, monkeypatch, capsys):
    monkeypatch.setattr(routines, "user_folder", lambda: str(folder))
    cli._routine_tool("1261", None, "&5F10:Blink")
    assert (folder / "blink.py").exists()
    assert capsys.readouterr().out.strip().endswith("blink.py")
    with pytest.raises(cli.typer.Exit):
        cli._routine_tool("1261", None, "5F10:Blink")
    with pytest.raises(cli.typer.Exit):
        cli._routine_tool("1100", None, "5F10")


@pytest.mark.skipif(not HAVE_ROM_1260, reason="PC-1260のROMがない")
def test_check_finds_right_and_wrong_user_routines(folder):
    """--check-routinesは、ROMと同じ働きの代替ROMルーチンをOK、違う代替ROMルーチンをNGにし、違いを書く"""
    (folder / "ba2x.py").write_text(BA2X, encoding="utf-8")
    (folder / "bad.py").write_text(
        BA2X.replace("0x0225", "0x0222").replace("MYBA2X", "BADBA2Y"), encoding="utf-8"
    )
    routines.load_user(str(folder), force=True)
    reports = routinecheck.check("1261", "user", trials=10)
    assert [(r.routine.name, r.ok) for r in reports] == [("BADBA2Y", False), ("MYBA2X", True)]
    text = routinecheck.report_text(reports)
    assert "NG  BADBA2Y(0222) 10回のうち" in text and "内部RAMの04" in text
    assert "OK  MYBA2X(0225) 10回" in text


@pytest.mark.skipif(not HAVE_ROM, reason="PC-1251のROMがない")
def test_check_builtins_of_pc1251():
    """PC-1251系の組み込みのうち、レジスタまでROMに合わせたものはROMと同じ。ほかは比べない"""
    reports = routinecheck.check("1251", "all", trials=20)
    assert all(r.ok for r in reports)
    compared = {r.routine.name for r in reports if r.cases}
    assert {"DISPON", "DISPOFF", "Y2DP", "SWAPC", "BA2X", "EXX1C", "TEXTX", "TEXTXM", "COPYB",
            "SHOWRAM", "PRINTBUF"} <= compared and "FADD" not in compared  # fmt: skip
    with pytest.raises(ValueError):
        routinecheck.select("1251", "FADD,NOSUCH")


@pytest.mark.skipif(not HAVE_ROM_1245, reason="PC-1245のROMがない")
def test_check_builtins_of_pc1245():
    """PC-1245でも同じ。NOISEはPC-1245のBASIC ROMの入口"""
    reports = routinecheck.check("1245", "all", trials=20)
    assert all(r.ok for r in reports)
    compared = {r.routine.name for r in reports if r.cases}
    assert {"NOISE", "SHOWRAM", "COPYB"} <= compared and "PRINTBUF" not in compared


BROKEN = """
from sc61box.routines import routine


@routine("1261", 0x0225, "MYBA2X", "AからJ+1バイトをXへ")
def my_ba2x(m):
    return 15


raise RuntimeError("初期化に失敗")
"""


def test_broken_file_registers_nothing(folder):
    """読み込みの途中で失敗したファイルの代替ROMルーチンは、登録の前でもあとでも使わない"""
    (folder / "broken.py").write_text(BROKEN, encoding="utf-8")
    notices = routines.load_user(str(folder), force=True)
    assert len(notices) == 1 and notices[0].startswith("broken.py:10: 読めません(RuntimeError")
    r = routines.find("1261", 0x0225)
    assert r is not None and r.builtin and r.name == "BA2X"


def _routine_file(folder, file: str, addr: int, name: str, mode: str = "", family="1261") -> None:
    arg = f', mode="{mode}"' if mode else ""
    (folder / file).write_text(
        f"from sc61box.routines import routine\n\n\n"
        f'@routine("{family}", 0x{addr:04X}, "{name}", "働き"{arg})\n'
        f"def f(m):\n    return 10\n",
        encoding="utf-8",
    )


def test_conflicting_names_and_addresses_are_not_used(folder):
    """組み込みと同じ名前で番地が違うもの、利用者が記述した代替ROMルーチンどうしで番地が同じもの・
    名前が同じで番地が違うものは、どれも使わずに知らせる。名前はアセンブラと検査で同じ表を引く"""
    _routine_file(folder, "a.py", 0x0100, "BA2X")
    _routine_file(folder, "b.py", 0x0200, "TWIN")
    _routine_file(folder, "c.py", 0x0200, "OTHER")
    _routine_file(folder, "d.py", 0x0300, "SAME")
    _routine_file(folder, "e.py", 0x0310, "SAME")
    _routine_file(folder, "f.py", 0x0400, "GOOD")
    notices = routines.load_user(str(folder), force=True)
    assert len(notices) == 5 and all("は使いません" in n for n in notices)
    assert "組み込みで0225に使っています" in notices[0]
    used = {r.addr: r.name for r in routines.for_model("1261").values() if not r.builtin}
    assert used == {0x0400: "GOOD"}
    assert routines.symbols("1261")["BA2X"] == 0x0225 and "SAME" not in routines.symbols("1261")
    picked = routinecheck.select("1261", "BA2X")
    assert [(r.addr, r.builtin) for r in picked] == [(0x0225, True)]
    unused = {(r.name, r.addr) for r, why in routines.listing("1261") if why}
    assert unused == {("BA2X", 0x100), ("TWIN", 0x200), ("OTHER", 0x200), ("SAME", 0x300),
                      ("SAME", 0x310)}  # fmt: skip


def test_fallback_gives_way_to_builtin(folder):
    """mode="fallback"の代替ROMルーチンは、同じ番地に組み込みがあれば使わない。overrideなら使う。
    組み込みの名前を、置き換えた代替ROMルーチンでも引ける"""
    _routine_file(folder, "a.py", 0x0225, "MINE", "fallback")
    _routine_file(folder, "b.py", 0x0222, "MINE2", "override")
    _routine_file(folder, "c.py", 0x0500, "NEW", "fallback")
    notices = routines.load_user(str(folder), force=True)
    assert notices[0] == "a.py: MINE(0225)は使いません。0225には組み込みのBA2Xがあります"
    assert notices[1] == "b.py: MINE2(0222)が、組み込みのBA2Yに代わります"
    table = routines.for_model("1261")
    assert table[0x0225].builtin and table[0x0222].name == "MINE2" and table[0x0500].name == "NEW"
    assert routines.by_name("1261", "BA2Y") is table[0x0222]
    text = cli.routine_list_text("1261")
    assert "OK  0222 MINE2 override" in text and "--  0225 MINE fallback" in text


def test_fallback_decided_per_model(folder):
    """一部の機種にしかない組み込みとのfallbackは、機種ごとに決める。PC-1245にはPRINTBUF(567Ch)が
    ないので、567Chのfallbackを使う。PC-1251では組み込みを使い、一覧に理由を出す"""
    _routine_file(folder, "p.py", 0x567C, "MYPB", "fallback", family="1251")
    assert routines.load_user(str(folder), force=True) == []
    assert routines.for_model("1245")[0x567C].name == "MYPB"
    assert routines.by_name("1245", "MYPB") is routines.find("1245", 0x567C)
    assert routines.for_model("1251")[0x567C].name == "PRINTBUF"
    assert ("MYPB", "567Cには組み込みのPRINTBUFがあります") in [
        (r.name, why) for r, why in routines.listing("1251")
    ]
    assert all(r.name != "MYPB" or why == "" for r, why in routines.listing("1245"))


def test_rom_entry_follows_address(folder):
    """ROMのある本体と比べるときの、BASIC ROMの版ごとの番地は、入口の番地で決める(利用者が記述した
    代替ROMルーチンでPRINTBUFを置き換えても、F0版では56C4hを呼ぶ)"""
    from types import SimpleNamespace

    _routine_file(folder, "p.py", 0x567C, "MYPB", "override", family="1251")
    routines.load_user(str(folder), force=True)
    r = routines.find("1251", 0x567C)
    assert r is not None and r.name == "MYPB"
    rom = SimpleNamespace(mem=bytearray(0x10000))
    for version, addr in ((0xF0, 0x56C4), (0x00, 0x567C), (0x03, 0x5673)):
        rom.mem[0x7FFF] = version
        assert routinecheck.rom_entry(rom, r) == addr


def test_spend_counts_cpu_cycles(folder):
    """待つあいだの時間(spend)も、戻るときに返すサイクル数も、CPUのサイクル数で、本体の比で
    時刻に直す(PC-1261は3対4)"""
    m = _hle("1261")
    c0 = m.cpu.cycles
    routines.spend(m, 100)
    assert m.cpu.cycles - c0 == 75
    (folder / "w.py").write_text(
        "from sc61box.routines import routine, spend\n\n\n"
        '@routine("1261", 0x5F00, "WAITKEY", "キーを待つ", mode="fallback")\n'
        "def f(m):\n    if not m.held:\n        spend(m, 100)\n        return None\n"
        "    return 100\n",
        encoding="utf-8",
    )
    routines.load_user(str(folder), force=True)
    assert _call(m, 0x5F00) == (False, 75) and m.cpu.pc == 0x5F00  # 待っている(入口にとどまる)
    m.held.add("A")
    done = routines.call(m, 0x5F00)
    assert done and m.cpu.pc == 0x6000


@pytest.mark.skipif(not HAVE_ROM_1260, reason="PC-1260のROMがない")
def test_check_copies_the_whole_font_table():
    """ROMのある本体の字の形の表は、0のバイトも含めてROMなしの本体と同じにする"""
    rom, hle = routinecheck.machines("1261")
    table = routinecheck.font_table("1261")
    assert any(hle.mem[a] == 0 for a in table)
    assert all(rom.mem[a] == hle.mem[a] for a in table)


def _stuck(folder) -> int:
    addr = routines.symbols()["DISPON"]
    (folder / "stuck.py").write_text(STUCK.format(addr=addr), encoding="utf-8")
    routines.load_user(str(folder), force=True)
    return addr


def test_check_stops_routine_waiting_without_time(folder):
    """時間を進めずに入口にとどまり続ける代替ROMルーチンは、比べる上限を待たずにStalledでやめる
    (上限のサイクル数はCPUのサイクルで数えるので、時間が進まなければ届かない)"""
    addr = _stuck(folder)
    with pytest.raises(routinecheck.Stalled, match=r"STUCK\(.+spend\(\)"):
        routinecheck.call(_hle("1251"), addr, limit=1)


@pytest.mark.skipif(not HAVE_ROM, reason="PC-1251のROMがない")
def test_check_reports_routine_waiting_without_time(folder):
    """--check-routinesは、時間を進めずに待ち続ける代替ROMルーチンをNGにし、入口とファイルを書く"""
    addr = _stuck(folder)
    text = routinecheck.report_text(routinecheck.check("1251", "user", trials=2))
    assert f"NG  STUCK({addr:04X}) 2回のうち2回が違う" in text and "stuck.py" in text
    assert "時間を進めずに待ち続けています" in text


def test_listing_agrees_with_calls(folder):
    """どの機種でも、一覧で使うとしたものが実行で呼ぶもの(for_model)と同じで、利用者が記述した
    代替ROMルーチンはどれも一覧に1度だけ出る"""
    _routine_file(folder, "a.py", 0x567C, "MYPB", "fallback", family="1251")
    _routine_file(folder, "b.py", 0x6F40, "MYNOISE", "override", family="1251")
    _routine_file(folder, "c.py", 0x0225, "MINE", "fallback")
    _routine_file(folder, "d.py", 0x0222, "MINE2")
    _routine_file(folder, "e.py", 0x0300, "SAME")
    _routine_file(folder, "f.py", 0x0310, "SAME")
    routines.load_user(str(folder), force=True)
    written = {
        "1251": ["MYNOISE", "MYPB"],
        "1261": ["MINE", "MINE2", "SAME", "SAME"],
        "1350": [],
    }
    for family, models in routines.FAMILIES.items():
        for model in models:
            listed = routines.listing(model)
            used = {r.addr: r for r, why in listed if not why}
            table = routines.for_model(model)
            assert used.keys() == table.keys()
            assert all(used[a] is r for a, r in table.items())
            assert sorted(r.name for r, _ in listed if not r.builtin) == written[family]
    assert routines.for_model("1251")[0x6F40].name == "MYNOISE"


def test_tables_are_rebuilt_when_registrations_change(folder):
    """機種の表と系統の表は、登録が変わるまで同じものを返し、読み直したら作り直す(前の表は
    そのまま)"""
    first, whole = routines.for_model("1261"), routines.table("1261")
    assert routines.for_model("1261") is first and routines.table("1261") is whole
    (folder / "twice.py").write_text(TWICE, encoding="utf-8")
    routines.load_user(str(folder), force=True)
    assert 0x5F00 not in first and 0x5F00 not in whole
    assert routines.for_model("1261")[0x5F00] is routines.table("1261")[0x5F00]


def test_routine_registered_outside_files(folder):
    """ファイルを読むときでなくても、@routineで登録したものはすぐ使う"""
    routines.load_user(str(folder), force=True)
    before = routines.for_model("1261")
    routines.routine("1261", 0x5F20, "DIRECT", "働き")(lambda m: 10)
    r = routines.find("1261", 0x5F20)
    assert r is not None and r.name == "DIRECT" and not r.builtin and 0x5F20 not in before


def test_call_raises_when_waiting_without_time(folder):
    """routines.callは、時間を進めずに入口にとどまる呼び出しがSTALLED回続くとStalledを出す。
    時間を進めて待つものは、何回呼んでも出さない"""
    addr = _stuck(folder)
    m = _hle("1251")
    cpu = m.cpu
    cpu.push(0x60)
    cpu.push(0x00)
    cpu.pc = addr
    for _ in range(routines.STALLED - 1):
        assert routines.call(m, addr) and cpu.pc == addr
    with pytest.raises(routines.Stalled, match=r"STUCK\("):
        routines.call(m, addr)
    (folder / "w.py").write_text(
        "from sc61box.routines import routine, spend\n\n\n"
        '@routine("1251", 0x5F00, "WAITS", "待つ", mode="fallback")\n'
        "def f(m):\n    spend(m, 10)\n",
        encoding="utf-8",
    )
    routines.load_user(str(folder), force=True)
    for _ in range(routines.STALLED + 5):
        assert routines.call(m, 0x5F00)


@pytest.mark.parametrize("line", ["CALL &C000", "RUN"])
def test_basic_call_stops_routine_waiting_without_time(folder, line):
    """ROMなしのBASICのCALLから、時間を進めずに待ち続ける代替ROMルーチンへ入ると、CALLをやめて
    BASICに戻り(プログラムの中ならBREAKで、CONTで次から続く)、basic.stalledで知らせる"""
    from basic_diff import basic_machine, lcd, play

    addr = _stuck(folder)
    m = basic_machine("1251")
    basic = m.basic
    assert basic is not None
    m.mem[0xC000:0xC003] = bytes([0x78, addr >> 8, addr & 0xFF])  # CALL addr
    steps: list[tuple[str, object]] = []
    if line == "RUN":
        steps += [("mode", "PRO"), ("wait", 1.5), ("type", "NEW\n")]
        steps += [("type", "10 CALL &C000\n"), ("type", "20 PRINT 7\n"), ("mode", "RUN")]
        steps += [("wait", 1.5)]
    play(m, [*steps, ("type", line + "\n"), ("wait", 1)])
    assert basic.stalled is not None and basic.stalled.name == "STUCK" and basic.notice is None
    if line == "RUN":
        assert lcd(m).strip() == "BREAK IN 10"
        play(m, [("type", "CONT\n"), ("wait", 1)])
        assert lcd(m).strip() == "7."
    else:
        assert lcd(m).strip() == ">"


def test_workbench_pauses_routine_waiting_without_time(folder):
    """作業欄の実行が、時間を進めずに待ち続ける代替ROMルーチンへ入ると、入口で一時停止して知らせる"""
    from test_workbench import bench, run_until_stop

    addr = _stuck(folder)
    m, b = bench()
    m.mem[0xC000:0xC004] = bytes([0x78, addr >> 8, addr & 0xFF, 0x37])  # CALL addr、RTN
    b.run(0xC000)
    run_until_stop(m, b, seconds=6)  # 1回の呼び出しごとにCLOCK // 200を数える
    assert b.state == "pause" and m.cpu.pc == addr
    assert "STUCK" in b.reason and "spend()" in b.reason


def test_outside_ram_guard_covers_all_but_ram():
    """RAMの外を止める番地の列は、RAMとそのミラーだけが0(PC-1255はミラーがある)"""
    for model in ("1251", "1255", "1245", "1261", "1350"):
        m = new_machine(model, rom=False)
        g = m.outside_ram()
        lo, hi = m.model.ram
        mirror = m.model.mirror
        for a in (0, lo - 1, lo, hi - 1, hi, 0xFFFF):
            inside = lo <= a < hi or bool(mirror and mirror[0] <= a < mirror[1])
            assert g[a] == (0 if inside else 1), (model, hex(a))
        if mirror:
            assert g[mirror[0]] == 0 and g[mirror[1] - 1] == 0


def test_app_tells_routine_waiting_without_time(folder):
    """BASICのCALLが時間を進めない代替ROMルーチンでやめたら、アプリはファイルの名前を添えて知らせ、
    spend()で時間を進めるように注意を出す"""
    from helpers import make_app

    addr = _stuck(folder)
    a = make_app(norom=True, frames=5)
    basic = a.m.basic
    assert basic is not None
    basic.stalled = routines.find("1251", addr)
    a.frame()
    assert "STUCK" in a.status and "stuck.py" in a.status
    assert "spend()" in a.warning and basic.stalled is None
    a.close()


def test_bad_arguments_follow_language(folder):
    """routine()の引数の誤りも、画面の言語で知らせる(読んだあとで言語を切り替えても)"""
    from sc61box import i18n

    (folder / "typo.py").write_text(
        "from sc61box.routines import routine\n"
        "@routine('1261', 0x5F10, 'TT', mode='typo')\n"
        "def tt(m):\n"
        "    return 0\n",
        encoding="utf-8",
    )
    assert routines.load_user(str(folder), force=True) == [
        "typo.py:2: 読めません(ValueError: modeはoverrideかfallbackです: typo)"
    ]
    i18n.set_language("en")
    assert routines.notices() == [
        "typo.py:2: cannot load (ValueError: mode must be override or fallback: typo)"
    ]
    calls = (
        lambda: routine("1500", 0x5F10, "TT"),  # 置けない機種
        lambda: routine("1261", 0x10000, "TT"),  # 番地
        lambda: routine("1261", 0x5F10, "1X"),  # 名前
        lambda: routine("1261", 0x5F10, "TT", ignore=["Q"])(lambda m: 0),  # 比べるもの
        lambda: routines.symbols("1500"),
        lambda: routines.template("1261", 0x10000),
    )
    for call in calls:
        with pytest.raises(ValueError) as e:
            call()
        assert not re.search(r"[぀-ヿ一-鿿]", str(e.value)), str(e.value)

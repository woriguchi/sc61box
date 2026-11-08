"""プログラムを読み込めるかの検査と、読み込む手順(sc61box.loading。Appを作らずに試す)"""

import pytest

from sc61box import loading
from sc61box.loading import Step
from sc61box.machine import SYMBOLS_1350, new_machine
from sc61box.programs import Program

LONG = '10 PRINT "' + "A" * 90 + '"'  # 打ち込むと途中で切れる行
ROM_ADDR = 0x0100  # どの機種でもCPUのROM
RAM_1251 = 0xB800


def machine(model="1251", card=0):
    return new_machine(model, card, rom=False)


def never(text):
    raise AssertionError("encodeは呼ばない")


def opened(prog, m, encode=never):
    """open_problemの文と秒数(読み込めないはずのとき)"""
    found = loading.open_problem(prog, m, encode)
    assert found is not None
    return found


def benched(prog, m):
    """bench_problemの文と秒数(読み込めないはずのとき)"""
    found = loading.bench_problem(prog, m)
    assert found is not None
    return found


# ---- ROMのある本体とROMなしのBASIC ----
def test_open_checks_model_first():
    prog = Program("p", title="P", model="1350", errors=["3行: 読めない"])
    text, secs = opened(prog, machine())
    assert "PC-1251では読み込めません" in text and secs == 5


def test_open_errors_before_card():
    prog = Program("p", title="P", card=16, errors=["3行: 読めない"])
    assert loading.open_problem(prog, machine("1350"), never) == (
        "Pを読み込めません。3行: 読めない",
        8,
    )


def test_open_card_before_model_without_card():
    """# card: 16のプログラムの番地は、カードを差していないとRAMに収まらない。機種が違うとは言わず、
    カードが要ると言う"""
    prog = Program("p", title="P", card=16, blocks=[(0x2032, b"\x00")])
    text, secs = opened(prog, machine("1350"))
    assert text == "Pには16KBのRAMカードが要ります。--card 16をつけて起動してください"


def test_open_card_before_ram():
    prog = Program("p", title="P", card=16, ram=(0x7000, 0xA000))
    text, secs = opened(prog, machine("1350"))
    assert text == "Pには16KBのRAMカードが要ります。--card 16をつけて起動してください"
    assert secs == 10


def test_open_ram_before_outside():
    prog = Program("p", title="P", model="1251", ram=(0xC800, 0xF900), blocks=[(ROM_ADDR, b"\0")])
    text, secs = opened(prog, machine())
    assert text == "Pを読み込めません。# ram: のC800-F8FFがROMか液晶RAMに重なっています"
    assert secs == 8


def test_open_outside_before_long_line():
    prog = Program("p", title="P", model="1251", basic=LONG, after=[(ROM_ADDR, b"\1\2")])
    assert loading.open_problem(prog, machine(), never) == (
        loading.outside_message("P", ROM_ADDR),
        8,
    )


def test_open_long_line_before_size():
    prog = Program("p", title="P", basic=LONG)
    text, _ = opened(prog, machine())
    assert text.startswith("Pを読み込めません。10行が長すぎて")
    prog = Program("p", title="P", basic=LONG[3:])
    text, _ = opened(prog, machine())
    assert text.startswith('Pを読み込めません。「PRINT "AAAAAAAAA」の行が長すぎて')


def test_open_size_uses_encoded_basic():
    m = machine()
    room = m.program_room()
    prog = Program("p", title="P", basic="10 A=1")
    text, secs = opened(prog, m, lambda text: bytes(room + 1))
    assert text == (
        f"Pを読み込めません。BASICのプログラムが{room + 1}バイトあり、"
        f"RAMに入りません(空きは{room}バイト)"
    )
    assert loading.open_problem(prog, m, lambda text: bytes(room)) is None
    assert loading.open_problem(prog, m, lambda text: None) is None
    prog.setup = "POKE &C000,0"  # 領域を動かすものは大きさを見ない
    assert loading.open_problem(prog, m, never) is None


def test_open_empty_uses_file_name():
    assert loading.open_problem(Program("p", title="P"), machine(), never) == ("pは空です", 4)


def test_open_accepts_program():
    prog = Program("p", title="P", basic="10 A=1", blocks=[(RAM_1251, b"\1")])
    assert loading.open_problem(prog, machine(), lambda text: b"") is None


# ---- 作業欄だけのROMなし ----
def test_bench_errors_before_card_and_norom():
    prog = Program("p", title="P", basic="10 A=1", card=16, errors=["3行: 読めない"])
    assert loading.bench_problem(prog, machine("1350")) == ("Pを読み込めません。3行: 読めない", 8)
    prog.errors = []
    assert benched(prog, machine("1350"))[1] == 10


def test_bench_needs_machine_code():
    text, secs = benched(Program("p", title="P", basic="10 A=1"), machine())
    assert text == "PはBASICのプログラムなので、ROMなしでは使えません" and secs == 6
    prog = Program("p", title="P", blocks=[(RAM_1251, b"\1")], norom_use="off")
    assert benched(prog, machine())[0] == (
        "PはBASICとROMのルーチンを使うプログラムなので、ROMなしでは使えません"
    )


def test_bench_norom_before_ram():
    prog = Program("p", title="P", basic="10 A=1", ram=(0xC800, 0xF900))
    assert benched(prog, machine())[1] == 6
    prog.blocks = [(RAM_1251, b"\1")]
    assert "# ram: のC800-F8FF" in benched(prog, machine())[0]


def test_bench_outside_includes_pokes():
    prog = Program("p", title="P", blocks=[(RAM_1251, b"\1")], basic=f"10 POKE &{ROM_ADDR:X},1")
    assert loading.bench_problem(prog, machine()) == (loading.outside_message("P", ROM_ADDR), 8)
    prog.basic = f"10 IF A POKE &{ROM_ADDR:X},1"  # IFのあとは拾わない
    assert loading.bench_problem(prog, machine()) is None


def test_bench_skips_model_and_basic_checks():
    prog = Program("p", title="P", model="1245", basic=LONG, blocks=[(RAM_1251, b"\1")])
    assert loading.bench_problem(prog, machine()) is None


def test_bench_blocks_order_and_start():
    prog = Program(
        "p",
        blocks=[(0xC000, b"\1")],
        after=[(0xC100, b"\3")],
        basic="10 POKE &C080,2:CALL &C000",
        run="CALL &C010",
    )
    assert loading.bench_blocks(prog) == (
        [(0xC000, b"\1"), (0xC080, b"\2"), (0xC100, b"\3")],
        0xC010,
    )


def test_outside_when_ram_moves():
    m = machine()
    hi = m.model.ram[1]
    assert loading.outside(m, [(hi - 1, b"\0\0")], None) == [hi]
    assert loading.outside(m, [(hi - 1, b"\0\0")], hi + 0x100) == []


# ---- 読み込む手順 ----
def test_steps_new_then_dump_then_basic():
    blocks = [(0xC000, b"\1")]
    prog = Program("p", title="P", basic="10 CALL &C000", blocks=blocks)
    assert loading.needs_new(prog)
    assert loading.open_steps(prog, False, "RUN") == [
        Step("mode", "PRO"),
        Step("text", "NEW\n"),
        Step("write", blocks=blocks),
        Step("basic", "10 CALL &C000", title="P"),
        Step("mode", "RUN"),
    ]


def test_steps_setup_before_dump():
    blocks = [(0xC000, b"\1")]
    prog = Program("p", setup="POKE &C000,0", blocks=blocks)
    assert loading.open_steps(prog, False, "PRO") == [
        Step("mode", "PRO"),
        Step("text", "NEW\n"),
        Step("text", "POKE &C000,0\n"),
        Step("write", blocks=blocks),
    ]


def test_steps_run_command_and_after():
    after = [(0xC100, b"\2")]
    prog = Program("p", basic="10 A=1", run="CALL &C000\nCALL &C010", mode="pro", after=after)
    assert loading.open_steps(prog, True, "RUN")[4:] == [
        Step("mode", "PRO"),
        Step("text", "CALL &C000\n"),
        Step("idle"),
        Step("text", "CALL &C010\n"),
        Step("write", blocks=after),
    ]
    # 実行しないときは、# after: があれば戻すモードにしない
    assert loading.open_steps(prog, False, "RUN")[4:] == [Step("write", blocks=after)]


def test_steps_run_basic():
    prog = Program("p", basic="10 A=1")
    assert loading.open_steps(prog, True, "PRO")[4:] == [Step("mode", "RUN"), Step("text", "RUN\n")]


def test_steps_dump_only():
    prog = Program("p", blocks=[(0xC000, b"\1")], run="CALL &C000")
    assert not loading.needs_new(prog)
    assert loading.open_steps(prog, False, "RUN") == []
    assert loading.open_steps(prog, True, "RUN") == [
        Step("mode", "RUN"),
        Step("text", "CALL &C000\n"),
    ]


def test_back_mode():
    m = machine()
    for mode, back in (("RUN", "RUN"), ("PRO", "PRO"), ("RSV", "RUN"), ("OFF", "RUN")):
        m.mode = mode
        assert loading.back_mode(m) == back
    m = machine("1350")
    assert loading.back_mode(m) == "RUN"
    a, bit = SYMBOLS_1350["PRO"]
    m.mem[a] |= bit
    assert loading.back_mode(m) == "PRO"


def test_norom_use_is_not_a_note(tmp_path):
    """# norom: off・basic はROMなしでの扱いで、説明ではない。同じ名前の.hexと.basの両方に
    書いても同じ。一覧と読み込みは同じ判定(Program.without_rom)で決める"""
    from sc61box import programs

    (tmp_path / "a.hex").write_text("# norom: off\nC000 37\n", encoding="utf-8")
    (tmp_path / "a.bas").write_text("# norom: off\n# norom: 遅い\n10 A=1\n", encoding="utf-8")
    prog = programs.load_program(str(tmp_path / "a.bas"))
    assert (prog.norom_use, prog.norom) == ("off", "遅い")
    assert not prog.norom_ok and not prog.without_rom(basic=True)
    assert opened(prog, machine())[0] == "aはROMが要るプログラムなので、ROMなしでは使えません"
    assert benched(prog, machine())
    head = programs.header_lines(prog)
    assert "# norom: off" in head and "# norom: 遅い" in head
    (tmp_path / "b.hex").write_text("# norom: basic\nC000 37\n", encoding="utf-8")
    basic = programs.load_program(str(tmp_path / "b.hex"))
    assert (basic.norom_use, basic.norom) == ("basic", "")  # 読み込んだときに「basic」と出さない
    assert basic.without_rom(basic=True) and not basic.without_rom(basic=False)
    assert loading.open_problem(basic, machine(), lambda text: None) is None


# 保護のフラグの番地(ROMなしのBASIC)
LOCK_FLAGS = {"1245": 0xC6D9, "1251": 0xC6D9, "1261": 0x66D9, "1350": 0x6F14}


def _locked(model):
    from basic_diff import basic_machine

    m = basic_machine(model)
    m.mem[LOCK_FLAGS[model]] |= 0x20
    assert m.basic is not None and m.basic.PASSWORD.locked(m)
    return m


def test_open_refuses_basic_into_locked_program():
    """ROMなしのBASICでプログラムを保護していると、NEWで消せない機種ではBASICを読み込まない
    (行を打ち込んでも登録されず、何も出ないままになるので)"""
    prog = Program("p", title="P", basic="10 END")
    want = ("プログラムがパスワードで保護されています", 8)
    for model in ("1245", "1261", "1350"):
        assert opened(prog, _locked(model)) == want, model


def test_open_allows_locked_program_when_new_clears_it():
    """PC-1251はNEWで保護ごと消すので、保護していても読み込む。BASICのないダンプだけのものも
    行を打ち込まないので読み込む"""
    basic = Program("p", basic="10 END")
    assert loading.open_problem(basic, _locked("1251"), lambda t: b"") is None
    dump = Program("p", blocks=[(0x4800, b"\x37")])
    assert loading.open_problem(dump, _locked("1261"), never) is None


def _locked_with_rom(model):
    """ROMのある本体で、プログラムを入れてPASSで保護したもの"""
    from helpers import boot, finish

    from sc61box.machine import CLOCK

    m, t = boot(model)
    t.add_mode("PRO")
    for line in ("10 PRINT 11", 'PASS "A"'):
        t.add_text(line + "\n")
    finish(m, t)
    m.run(CLOCK // 2)
    return m


@pytest.mark.parametrize(("model", "refused"), [("1245", True), ("1251", False), ("1261", True),
                                                ("1350", True)])  # fmt: skip
def test_open_checks_password_with_rom(model, refused):
    """ROMのある本体でも、PASSで保護したプログラムには、NEWで消せない機種ではBASICを読み込まない
    (読み込むと、保護したまま置き換わる)。保護のフラグの番地はROMなしのBASICと同じ"""
    from conftest import HAVE_ROM, HAVE_ROM_1245, HAVE_ROM_1260, HAVE_ROM_1350

    have = {"1245": HAVE_ROM_1245, "1251": HAVE_ROM, "1261": HAVE_ROM_1260, "1350": HAVE_ROM_1350}
    if not have[model]:
        pytest.skip("ROMがない")
    m = _locked_with_rom(model)
    assert m.basic is None and m.mem[LOCK_FLAGS[model]] & 0x20
    found = loading.open_problem(Program("p", basic="10 PRINT 77"), m, lambda t: b"")
    if refused:
        assert found == ("プログラムがパスワードで保護されています", 8)
    else:
        assert found is None

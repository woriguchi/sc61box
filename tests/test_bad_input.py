"""壊れたファイルや、上限を越える入力で、いまの状態を壊さないこと"""

import json

import pygame
import pytest
from helpers import boot, make_app, settle, typed_and_stored

from sc61box import basictext, keytype, programs
from sc61box.app import export_program
from sc61box.overlay import Popup, ProgramMenu


def _broken_states(path):
    """正しく保存した状態から、1か所ずつ壊したものを作る"""
    good = json.loads(open(path).read())
    bad = []
    for change in ("mem", "cpu.p", "cpu.ram", "mode", "rom", "list", "port"):
        s = json.loads(json.dumps(good))
        if change == "mem":
            s["mem"] = ""
        elif change == "cpu.p":
            del s["cpu"]["p"]
        elif change == "cpu.ram":
            s["cpu"]["ram"] = "00"
        elif change == "mode":
            s["machine"]["mode"] = "XYZ"
        elif change == "rom":
            s["rom"] = "0" * 40
        elif change == "list":
            s = []
        elif change == "port":
            s["machine"]["pb"] = 256
        bad.append((change, s))
    return bad


def test_broken_state_changes_nothing(tmp_path):
    """壊れた状態のファイルは読み込まず、いまのRAMとレジスタはそのまま"""
    path = str(tmp_path / "state.json")
    m, _ = boot()
    m.save_state(path)
    m.mem[0xC100] = 0xA5
    m.cpu.p = 0x12
    before = bytes(m.mem), bytes(m.cpu.ram), m.cpu.state()
    for change, state in _broken_states(path):
        bad = str(tmp_path / f"{change}.json")
        with open(bad, "w") as f:
            json.dump(state, f)
        with pytest.raises(ValueError):
            m.load_state(bad)
        assert (bytes(m.mem), bytes(m.cpu.ram), m.cpu.state()) == before, change


def test_save_state_keeps_previous(tmp_path):
    """保存し直すと、前の状態は.bakに残る"""
    path = str(tmp_path / "state.json")
    m, _ = boot()
    m.save_state(path)
    first = open(path).read()
    m.mem[0xC100] = 0x5A
    m.save_state(path)
    assert open(path + ".bak").read() == first
    assert not (tmp_path / "state.json.tmp").exists()


def test_program_with_errors_is_not_loaded():
    """読めない行のあるプログラムは、NEWも書き込みもせずに知らせる"""
    app = make_app()
    app.open_program(programs.Program(name="a", title="a", basic="10 PRINT 123\n"))
    settle(app)
    broken = programs.Program(
        name="b", title="b", basic="10 PRINT 7\n", errors=["# hex: x.hexが見つからない"]
    )
    app.open_program(broken)
    settle(app)
    assert basictext.program_text(app.m.mem, start=app.m.program_start()) == "10 PRINT 123\n"
    assert "読み込みません" in app.status


def test_dump_outside_ram_is_not_loaded():
    """RAMの外に書くダンプがあれば、何も書かずに知らせる。FFFFを越える行は読めない行になる"""
    blocks, errors = programs.parse_hex("FFFF 1122")
    assert not blocks and errors
    app = make_app()
    app.m.mem[0xC000] = 0x5A
    dumps = [(0xC000, b"\x01"), (0x3000, b"\x02")]
    prog = programs.Program(name="x", title="x", model="1251", blocks=dumps)
    app.open_program(prog)
    settle(app)
    assert app.m.mem[0xC000] == 0x5A
    assert "3000番地" in app.status


def test_no_model_fits():
    """番地がどの機種のRAMにも収まらないものは、どの機種でも使えないとみる"""
    p = programs.Program(name="x", blocks=[(0x3000, b"\x55")])
    assert p.inferred == []
    assert not p.runs_on("1251") and not p.runs_on("1350")
    assert programs.Program(name="y", basic="10 PRINT 1\n").runs_on("1350")


def test_line_number_alone_deletes_the_line():
    """行番号だけの行は、その行を消す(打ち込みと同じ)"""
    src = "10 PRINT 7\n10\n20 PRINT 8\n"
    for model in ("1251", "1245"):
        typed, stored = typed_and_stored(model, src)
        start = typed.program_start()
        assert basictext.program_text(typed.mem, start=start) == "20 PRINT 8\n"
        assert basictext.program_text(stored.mem, start=start) == "20 PRINT 8\n"


@pytest.mark.parametrize("model", ["1251", "1261", "1350"])
def test_long_lines_are_typed(model):
    """打ち込みで欠ける長さの行は、中間コードで置かずに打ち込みに回す"""
    m, _ = boot(model)
    huge = '10 PRINT "' + "A" * 300 + '"\n'
    assert basictext.encode_program(keytype.typed_text(huge, model), m.mem) is None
    many = "10 " + ":".join("PRINT A" for _ in range(27)) + "\n"  # 中間コードで80字
    assert basictext.encode_program(keytype.typed_text(many, model), m.mem) is None
    assert not keytype.typeable('10 A$="' + "A" * 72 + '"\n', model)
    assert keytype.typeable("10 " + ":".join("PRINT A" for _ in range(26)) + "\n", model)


def test_kana_counts_twice_on_s1():
    """S1系の入力欄ではカナが2字ぶんになる"""
    assert keytype.typeable('10 A$="' + "ｱ" * 35 + '"\n', "1261")
    assert not keytype.typeable('10 A$="' + "ｱ" * 36 + '"\n', "1261")


def test_long_line_typed_and_stored_on_s1():
    """S1系でも、長い行を打ち込んだ結果と中間コードで置いた結果が同じ"""
    src = "10 " + ":".join("PRINT A" for _ in range(26)) + "\n20 END\n"
    typed, stored = typed_and_stored("1261", src)
    start = typed.program_start()
    assert basictext.program_text(typed.mem, start=start) == basictext.program_text(
        stored.mem, start=start
    )


def test_export_keeps_directives(tmp_path):
    """書き出したファイルに、# after:・# model:・# help:などの指示が残る"""
    folder = tmp_path / "lib"
    folder.mkdir()
    (folder / "code.hex").write_text("C400 55\n")
    (folder / "late.hex").write_text("C500 66\n")
    (folder / "game.bas").write_text(
        "# model: 1251,1245\n# hex: code.hex\n# after: late.hex\n# help: 8と2で動く\n"
        "# run: RUN\n10 PRINT 7\n"
    )
    prog = programs.load_program(str(folder / "game.bas"))
    app = make_app()
    app.open_program(prog)
    settle(app)
    path = export_program(app.m, str(tmp_path / "out"), prog)
    assert path is not None
    text = open(path, encoding="utf-8").read()
    for line in (
        "# model: 1251,1245",
        "# hex: code.hex",
        "# after: late.hex",
        "# help: 8と2で動く",
    ):
        assert line in text.splitlines(), line


def test_focus_lost_releases_keys():
    """ほかのウィンドウに移ると、押していたキーを離す"""
    app = make_app()
    app.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a, mod=0, unicode="a"))
    for _ in range(10):
        app.frame()
    assert "A" in app.m.held
    app.handle(pygame.event.Event(pygame.WINDOWFOCUSLOST))
    for _ in range(30):
        app.frame()
    assert not app.typer.physical and not app.m.held


def test_overlays_fit_small_window():
    """小さく表示しても、一覧の行と右クリックのメニューが窓に収まる"""
    app = make_app(scale=0.5)
    h = app.window.get_height()
    app.help = 0
    app.menu = ProgramMenu(programs.for_model(programs.scan(), "1251"))
    app.frame()
    assert app.menu.visible < ProgramMenu.ROWS
    assert all(0 <= r.top and r.bottom <= h for _, r in app.menu.rows)
    app.menu.page(1)
    assert app.menu.sel == min(app.menu.visible, len(app.menu.items) - 1)
    app.menu = None
    for kind in ("program", "machine", "view", "speed", "context"):
        app.popup = Popup((20, h - 40), kind, above=True)
        app.frame()
        assert len(app.popup.rows) == sum(1 for it in app.popup_items() if it[2] is not None)
        assert all(0 <= r.top and r.bottom <= h for _, r in app.popup.rows)


def _keep(app):
    """いまのBASICとA、C700番地を返す(読み込みに失敗したあとで変わっていないかを見る)"""
    m = app.m
    return basictext.program_text(m.mem, start=m.program_start()), m.mem[0xC700]


def _too_big(model="1250"):
    """各行は正しいが、合わせるとRAMに入らないBASIC"""
    body = "".join(f"{n} A=A+1:B=B+1:C=C+1:D=D+1:E=E+1:F=F+1:G=G+1\n" for n in range(10, 600, 10))
    return programs.Program(
        name="big", title="big", basic=body, run="A=99", after=[(0xC700, b"\x5a")], model=model
    )


def test_too_big_basic_is_refused_before_new():
    """中間コードにしてRAMに入らないと分かるBASICは、NEWもせずに断る"""
    app = make_app("1250")
    app.open_program(programs.Program(name="a", title="a", basic="10 PRINT 123\n"))
    settle(app)
    before = _keep(app)
    app.open_program(_too_big(), run=True)
    settle(app)
    assert _keep(app) == before and "RAMに入りません" in app.status
    app.close()


def test_typed_basic_that_does_not_fit_stops(monkeypatch):
    """打ち込みで入れたBASICが入りきらなかったら、そのあとの実行と書き込みをしない"""
    app = make_app("1250")
    monkeypatch.setattr(app, "_encoded", lambda text: None)  # 打ち込みで入れる
    app.m.mem[0xC700] = 0
    app.open_program(_too_big(), run=True)
    settle(app, limit=20000)
    m = app.m
    assert "入りきりませんでした" in app.status
    assert m.mem[0xC700] == 0
    typ_a = basictext.program_text(m.mem, start=m.program_start())
    assert typ_a and not app.typer.busy


def test_unreadable_dependency(tmp_path, monkeypatch):
    """読めない依存のダンプがあっても、一覧は開け、そのプログラムは読み込まない"""
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "broken.hex").write_bytes(b"\xff")
    (lib / "uses.bas").write_text("# hex: broken.hex\n10 PRINT 1\n")
    prog = programs.load_program(str(lib / "uses.bas"))
    assert prog.errors and "broken.hex" in prog.errors[0]
    monkeypatch.setenv("SC61BOX_PROGRAMS", str(lib))
    app = make_app()
    app.open_menu()
    assert app.menu is not None and any(p.name == "uses" for p in app.menu.items)
    app.menu = None
    app.open_program(prog)
    assert "読み込みません" in app.status and not app.typer.busy
    app.close()


def test_ram_card_programs():
    """PC-1350のRAMカードの番地に書くものは、カードを差しているときだけ読み込める"""
    prog = programs.Program(name="c", title="c", blocks=[(0x3000, b"\x55")])
    with_card = make_app("1350", card=16)
    assert with_card.m.writable(0x3000) and prog.fits(with_card.m.writable)
    with_card.open_program(prog)
    settle(with_card)
    assert with_card.m.mem[0x3000] == 0x55
    with_card.close()
    without = make_app("1350")
    without.open_program(prog)
    assert "読み込みません" in without.status
    without.close()


def test_line_too_long_to_type_is_refused():
    """打ち込むと欠ける長い行があれば、NEWもせずに行番号を出して断る"""
    for model in ("1251", "1261"):
        app = make_app(model)
        app.open_program(programs.Program(name="a", title="a", basic="10 PRINT 123\n"))
        settle(app)
        before = _keep(app)
        src = "10 A=1:" + ":".join("B=B+1" for _ in range(20)) + ":Z=7\n"
        app.open_program(programs.Program(name="b", title="b", basic=src, run="A=99"), run=True)
        settle(app)
        assert _keep(app) == before and "10行が長すぎて" in app.status, model
        app.close()


def test_typed_line_that_differs_stops(monkeypatch):
    """打ち込んだ行の中身が欠けていたら、そのあとの実行と書き込みをしない"""
    from sc61box import app as app_module

    real = app_module.keys_for_program
    monkeypatch.setattr(app_module, "keys_for_program", lambda t, m: real(t.replace(":Z=7", ""), m))
    app = make_app()
    monkeypatch.setattr(app, "_encoded", lambda text: None)  # 打ち込みで入れる
    app.m.mem[0xC700] = 0
    prog = programs.Program(
        name="b", title="b", basic="10 A=1:Z=7\n", run="A=99", after=[(0xC700, b"\x5a")]
    )
    app.open_program(prog, run=True)
    settle(app)
    assert "10行が、思ったとおりに入りませんでした" in app.status
    assert app.m.mem[0xC700] == 0
    app.close()


def test_progress_stays_between_0_and_100(monkeypatch):
    """打ち込みに切り替わっても、読み込みの進み具合は0〜100%の中にある"""
    app = make_app()
    monkeypatch.setattr(app, "_encoded", lambda text: None)
    text = "".join(f"{n} PRINT {n}\n" for n in range(10, 200, 10))
    app.open_program(programs.Program(name="p", title="p", basic=text))
    seen = []
    for _ in range(3000):
        app.frame()
        if app.fast:
            seen.append(1 - len(app.typer.queue) / app.load_total)
        if not app.typer.busy:
            break
    assert seen and app.load_typing  # 打ち込みに切り替わった
    assert all(0 <= v <= 1 for v in seen)
    app.close()


@pytest.mark.parametrize("model", ["1251", "1245", "1261", "1350"])
def test_yen_and_backslash(model):
    """ポケコンにはバックスラッシュがないので、「\\」は¥として打つ。PC-1251・PC-1245の¥
    (SHIFT+6、文字コード17h)も打てて、打ち込んだものと直に置いたものが同じになり、
    書き出すと¥に戻る"""
    from sc61box import basictext, keytype

    assert keytype.keys_for("\\", model) == keytype.keys_for("¥", model) != []
    typed, stored = typed_and_stored(model, '10 A$="\\1¥"\n')
    s = typed.program_start()
    e = s + 40
    assert bytes(typed.mem[s:e]) == bytes(stored.mem[s:e])
    text = basictext.program_text(typed.mem, start=s) if model in ("1251", "1245") else None
    if text is not None:
        assert text == '10 A$="¥1¥"\n'


def test_small_e_is_letter():
    """小文字のeは、数のあとでも英字のまま(指数は[E]か€で書く。PC-1261などでは英小文字を
    打てるので、指数とは決められない)"""
    from sc61box.keytype import EXP, normalize

    assert normalize("10 A=1e-8:B=1[E]-8:C=1€-8") == f"10 A=1e-8:B=1{EXP}-8:C=1{EXP}-8"


@pytest.mark.parametrize("model", ["1251", "1261", "1350"])
def test_euro_stores_like_exp(model):
    """€で書いた指数は、[E]で書いたものと同じ中間コードになる"""
    from sc61box import basictext, keytype

    m, _ = boot(model)
    one = basictext.encode_program(keytype.typed_text("10 A=1€-8\n", model), m.mem)
    two = basictext.encode_program(keytype.typed_text("10 A=1[E]-8\n", model), m.mem)
    assert one is not None and one == two

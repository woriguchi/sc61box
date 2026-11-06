"""本体の下の操作欄、一覧で探す、読み込みをやめる"""

import pygame
import pytest
from helpers import make_app

from sc61box import app as appmod
from sc61box import programs
from sc61box.machine import CLOCK

ev = pygame.event.Event


def _click(app, pos):
    app.handle(ev(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    app.handle(ev(pygame.MOUSEBUTTONUP, button=1, pos=pos))


def test_bar_buttons():
    """操作欄の目的ごとのボタンで、そのボタンのすぐ上にメニューが出る。メニューにある操作は
    ボタンとして重ねて置かない(キーの説明は「表示・入力」から。録画は「録画」のボタンだけ)"""
    app = make_app(scale=0.6)
    app.frame()
    labels = [b[0] for b in app.bar.buttons]
    for name, kind in (("プログラム", "program"), ("本体", "machine"), ("表示・入力", "view")):
        r = app.bar.rects[labels.index(name)]
        assert r.top >= app.body_size[1]
        _click(app, r.center)
        assert app.popup is not None and app.popup.kind == kind
        app.frame()
        assert all(row.bottom <= r.top for _i, row in app.popup.rows)  # ボタンの上
        app.popup = None
    _click(app, app.bar.rects[labels.index("プログラム")].center)
    app.frame()
    assert app.popup is not None
    first = app.popup.rows[0][1]
    _click(app, first.center)  # 「プログラムの一覧…」
    assert app.menu is not None
    app.menu = None
    assert "?" not in labels and "録画" in labels
    every = [
        it[0] for kind in ("program", "machine", "view", "speed") for it in app.popup_items(kind)
    ]
    assert not any("録画" in t for t in every)
    _click(app, app.bar.rects[labels.index("表示・入力")].center)
    app.frame()
    assert app.popup is not None
    _click(app, app.popup.rows[0][1].center)  # 「キーの説明」
    assert app.help
    assert app.m.model.title in app.bar_info()
    app.close()


def test_search_in_list():
    """一覧で「/」を打ってから名前の一部を打つと、合うものだけになる。Escで元に戻る"""
    app = make_app()
    app.open_menu()
    assert app.menu is not None
    every = len(app.menu.items)
    app.handle(ev(pygame.TEXTINPUT, text="/"))
    app.handle(ev(pygame.TEXTINPUT, text="素数"))
    assert app.menu is not None and [p.name for p in app.menu.items] == ["primes"]
    app.handle(ev(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="", scancode=0))
    assert app.menu is not None and len(app.menu.items) == every
    app.handle(ev(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="", scancode=0))
    assert app.menu is None
    app.close()


def test_escape_cancels_loading():
    """読み込み(打ち込み)の途中でEscを押すと、そこでやめる"""
    app = make_app()
    text = "".join(f"{n} PRINT {n}\n" for n in range(10, 400, 10))
    prog = programs.Program(name="long", title="long", basic=text)
    app.open_program(prog)
    app.typer.add_text("10 REM" + " A" * 200 + "\n")  # 打ち込みを残しておく
    app.fast = True
    app.handle(ev(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="", scancode=0))
    assert not app.typer.busy and not app.fast and not app.m.brk
    assert "中止しました" in app.status
    app.close()


def test_record_buttons(tmp_path, monkeypatch):
    """操作欄の「録画」を押すと録画の形のメニューが出て、選ぶと録り始める。録画中はボタンが
    録画中のマークと経過時間になり、押すと、そのすぐ上に止めるか一時停止するかのメニューが出る。
    録画の一時停止のあいだは動画に入らず、実行は止まらない"""
    monkeypatch.setenv("SC61BOX_PROGRAMS", str(tmp_path))
    app = make_app()
    app.frame()

    def rec_button():
        return next(i for i, b in enumerate(app.bar.buttons) if b[0].startswith("録画"))

    def choose(label, kind="rec"):
        _click(app, app.bar.rects[rec_button()].center)
        app.frame()
        assert app.popup is not None and app.popup.kind == kind
        labels = [it[0] for it in app.popup_items()]
        _click(app, next(r for i, r in app.popup.rows if labels[i] == label).center)
        app.frame()

    choose("液晶の拡大と本体", "recstart")
    assert app.recorder is not None
    for _ in range(30):
        app.frame()
    assert app.bar.buttons[rec_button()][0].startswith("録画中")
    choose("録画を一時停止する")
    before = app.recorder.seconds
    for _ in range(30):
        app.frame()
    assert app.recorder.seconds == before
    assert app.bar.buttons[rec_button()][0].startswith("録画を一時停止中")
    assert not app.halted  # 実行は止まらない
    app.handle(ev(pygame.KEYDOWN, key=pygame.K_p, mod=pygame.KMOD_SHIFT | pygame.KMOD_CTRL))
    assert not app.rec_paused
    for _ in range(15):
        app.frame()
    assert app.recorder.seconds > before
    choose("録画を止めて保存")
    assert app.recorder is None and len(list(tmp_path.glob("rec-*.mp4"))) == 1
    assert "録画" in [b[0] for b in app.bar.buttons]
    app.close()


def test_bar_fits_narrow_window():
    """ウィンドウが狭いときは、操作欄のボタンを短い表示にしてウィンドウに収める(入らなければ「速さ」の
    ボタンを省く。実行の一時停止は省かない)"""
    app = make_app(scale=0.35)
    app.recorder = type("R", (), {"seconds": 75.0})()  # 録画中の操作欄を見る
    app.rec_paused = True
    app.halted = True
    app.frame()
    assert all(r.right <= app.window.get_width() for r in app.bar.rects)
    labels = [b[0] for b, r in zip(app.bar.buttons, app.bar.rects, strict=True) if r.width]
    assert "実行を再開" in labels and "本体" in labels
    app.recorder = None
    app.close()


def test_tooltip_on_bar():
    """操作欄のボタンにマウスを載せると、ボタンの上に説明とショートカットが出る"""
    app = make_app(scale=0.35)
    app.frame()
    r = app.bar.rects[0]
    app.handle(ev(pygame.MOUSEMOTION, pos=r.center, rel=(0, 0), buttons=(0, 0, 0)))
    before = app.window.copy()
    app.frame()
    above = pygame.Rect(0, r.y - 40, app.window.get_width(), 34)
    assert app.bar.hover == 0 and "O" in app.bar.buttons[0][4]
    changed = any(
        app.window.get_at((x, y)) != before.get_at((x, y))
        for x in range(above.left, above.right, 3)
        for y in range(above.top, above.bottom, 3)
    )
    assert changed
    app.handle(ev(pygame.WINDOWLEAVE))
    assert app.bar.hover == -1
    app.close()


def test_halt_stops_machine():
    """⌘Pで実行を一時停止すると、CPUも打ち込みも進まない。操作欄の「実行を再開」で続く"""
    app = make_app()
    for _ in range(5):
        app.frame()
    app.handle(ev(pygame.KEYDOWN, key=pygame.K_p, mod=pygame.KMOD_CTRL, unicode="", scancode=0))
    assert app.halted
    app.typer.add_text("PRINT 1\n")
    cycles = app.m.cpu.cycles
    for _ in range(5):
        app.frame()
    assert app.m.cpu.cycles == cycles and app.typer.busy
    labels = [b[0] for b in app.bar.buttons]
    _click(app, app.bar.rects[labels.index("実行を再開")].center)
    assert not app.halted
    app.frame()
    assert app.m.cpu.cycles > cycles
    app.close()


def test_undo_loading(tmp_path, monkeypatch):
    """プログラムを読み込むと、直前の状態を取っておき、メニューから戻せる"""
    monkeypatch.setenv("SC61BOX_PROGRAMS", str(tmp_path))
    app = make_app()
    for _ in range(20):
        app.frame()
    mine = app.m.snapshot()["mem"]
    prog = programs.Program(name="p", title="見本", basic="10 PRINT 1\n20 PRINT 2\n")
    app.open_program(prog)
    while app.fast:
        app.frame()
    assert app.m.snapshot()["mem"] != mine
    app.open_bar_popup("machine")
    items = app.popup_items()
    i = next(i for i, it in enumerate(items) if it[0] == "プログラムを読み込む前に戻す")
    assert items[i][3] == "見本を読み込む前"
    app.popup_run(i)
    assert app.m.snapshot()["mem"] == mine and app.undo_state is None
    labels = [it[0] for it in app.popup_items("machine")]
    assert "プログラムを読み込む前に戻す" not in labels
    app.close()


def test_saved_state_time_in_menu(tmp_path, monkeypatch):
    """状態を保存すると、メニューの「保存した状態に戻す」に保存した日時が出る"""
    app = make_app()
    monkeypatch.setattr(app, "state_file", str(tmp_path / "state.json"))
    assert app.saved_when() == "まだ保存していません"
    app.save_state()
    assert app.saved_when().endswith("に保存") and ":" in app.saved_when()
    items = app.popup_items("machine")
    assert any(it[0] == "保存した状態に戻す" and it[3] == app.saved_when() for it in items)
    app.close()


def test_undo_restores_program_info(tmp_path, monkeypatch):
    """読み込む前に戻すと、書き出しに使うプログラムの情報(名前、# run:、# hex:)も戻る"""
    monkeypatch.setenv("SC61BOX_PROGRAMS", str(tmp_path))
    app = make_app()
    alpha = programs.Program(name="alpha", title="アルファ", basic="10 PRINT 111\n")
    beta = programs.Program(name="beta", title="ベータ", basic="10 PRINT 222\n", run="CALL &C300")
    beta.help, beta.links = "ベータの説明", ["hex: beta.hex"]
    for prog in (alpha, beta):
        app.open_program(prog)
        while app.fast:
            app.frame()
    assert app.last_prog is beta
    app.undo_loading()
    assert app.last_prog is alpha and app.loading == "アルファ" and app.load_help == ""
    app.export_program()
    text = next(tmp_path.glob("alpha-*.bas")).read_text(encoding="utf-8")
    assert "beta" not in text and "C300" not in text and "10 PRINT 111" in text
    app.close()


def test_state_file_keeps_program(tmp_path, monkeypatch):
    """状態のファイルには、読み込んだプログラムの書き出し用の情報(題名、# run:、# help:、
    ダンプの指示など)を中身ごと書く。保存したあとで元のファイルを書き換えても、戻すと
    保存したときの情報で書き出す。情報のない古い状態のファイルでは、前の情報を使わない"""
    import json

    monkeypatch.setenv("SC61BOX_PROGRAMS", str(tmp_path))
    src = tmp_path / "example.bas"
    src.write_text("# title: Alpha\n# run: RUN\n# help: Alpha help\n10 PRINT 111\n", "utf-8")
    app = make_app()
    state = tmp_path / "state.json"
    monkeypatch.setattr(app, "state_file", str(state))
    app.open_program(programs.load_program(str(src)))
    while app.fast:
        app.frame()
    app.save_state()
    src.write_text("# title: Beta\n# run: CALL &C300\n# help: Beta help\n10 PRINT 222\n", "utf-8")
    other = programs.Program(name="delta", title="デルタ", basic="10 PRINT 4\n", run="RUN 5")
    app.open_program(other)
    while app.fast:
        app.frame()
    app.load_state()
    assert app.last_prog is not None and app.last_prog.title == "Alpha"
    assert app.load_help == "Alpha help"
    app.export_program()
    text = next(tmp_path.glob("example-*.bas")).read_text(encoding="utf-8")
    assert "Alpha" in text and "# run: RUN" in text and "Beta" not in text and "C300" not in text
    assert "10 PRINT 111" in text
    # 情報を書いていない(前の版の)状態のファイル
    data = json.loads(state.read_text(encoding="utf-8"))
    del data["app"]
    state.write_text(json.dumps(data), encoding="utf-8")
    app.open_program(other)
    while app.fast:
        app.frame()
    app.load_state()
    assert app.last_prog is None and app.loading == "" and app.load_help == ""
    app.close()


def _pro(app, model):
    if model == "1350":
        app.typer.add_mode("PRO")
    else:
        app.set_mode("PRO")
    for _ in range(40):
        app.frame()


@pytest.mark.parametrize("model", ["1251", "1261", "1350"])
def test_fast_typing_keeps_up(model):
    """パソコンのキーを速く(1フレームに1字)打っても、ROMの入力待ちに届けるあいだは速く回す
    ので、取りこぼさずに遅れもたまらない"""
    from sc61box import basictext
    from sc61box.keytype import keys_for

    app = make_app(model=model)
    _pro(app, model)
    app.typer.add_text("NEW\n")
    while app.typer.busy:
        app.frame()
    for ch in "10 PRINT 12345\n20 A=A+1\n":
        if ch in "=+":
            app.typer.add_live_keys(keys_for(ch, model))
            app.frame()
            continue
        name = {" ": "SPC", "\n": "ENTER"}.get(ch, ch)
        app.typer.press_live(name)
        app.frame()
        app.typer.release_live(name)
    for _ in range(10):
        app.frame()
    assert not app.typer.busy
    m = app.m
    text = basictext.program_text(m.mem, start=m.program_start())
    assert text == "10 PRINT 12345\n20 A=A+1\n"
    app.close()


def test_held_key_repeats_at_real_speed(monkeypatch):
    """押し続けたキーの繰り返し(ROMが数える)は、速く回さずに実時間のまま。速く回さない
    ときと、液晶が変わる回数と、繰り返しが始まるまでの時間がそろう"""
    from sc61box import app as app_module
    from sc61box.lcdtext import lcd_text

    def changes(rush):
        monkeypatch.setattr(app_module, "RUSH", rush)
        app = make_app()
        _pro(app, "1251")
        app.typer.add_text("10 PRINT 1234567890")
        while app.typer.busy:
            app.frame()
        app.typer.press_live("LEFT")
        last, out = lcd_text(app.m), []
        for f in range(45):
            app.frame()
            if lcd_text(app.m) != last:
                out.append(f)
                last = lcd_text(app.m)
        app.typer.release_live("LEFT")
        app.close()
        return out

    slow, fast = changes(1), changes(8)
    assert fast[0] <= slow[0]  # 1回目は同じか早く動く
    assert fast[1] >= 18 and abs(fast[1] - slow[1]) <= 3  # 繰り返しまで0.6秒以上
    assert abs(len(fast) - len(slow)) <= 2


def _running(app):
    """10 GOTO 10を動かし、ROMが入力待ちで止まっていない状態にする"""
    app.typer.add_text("NEW\n")
    app.set_mode("PRO")
    app.typer.add_text("10 GOTO 10\n")
    app.typer.add_mode("RUN")
    app.typer.add_text("RUN\n")
    while app.typer.busy:
        app.frame()
    for _ in range(20):
        app.frame()
    assert not app.m.halted


@pytest.mark.parametrize("model", ["1251", "1261"])
def test_keys_during_program_are_held_together(model):
    """プログラムが動いているあいだのパソコンのキーは、押したときにすぐ押され、同時に押した
    キーもそのまま伝わる(DEFを押したまま6や8を押すゲームのため)"""
    m = (app := make_app(model=model)).m
    _running(app)
    app.typer.press_live("DEF")
    assert "DEF" in m.held  # フレームを待たずに押されている
    app.frame()
    app.typer.press_live("6")
    app.typer.press_live("8")
    for _ in range(5):
        app.frame()
    assert {"DEF", "6", "8"} <= m.held
    m.pb = 0x04  # DEFと8は同じストローブ(IBのビット2)で読める
    assert m.in_a() & 0x12 == 0x12
    app.typer.release_live("6")
    app.frame()
    assert "6" not in m.held and {"DEF", "8"} <= m.held
    for name in ("DEF", "8"):
        app.typer.release_live(name)
    app.frame()
    assert not m.held and not app.typer.busy
    app.close()


def test_short_tap_during_program_is_held_long_enough():
    """プログラムが動いているあいだに短く押したキーも、DIRECT_MINのあいだは押しておき、
    それより長く押したキーは離した時点で離す"""
    m = (app := make_app(model="1261")).m
    _running(app)
    app.typer.press_live("6")
    app.typer.release_live("6")
    assert "6" in m.held
    start = m.cpu.cycles
    while "6" in m.held:
        app.frame()
    held = m.cpu.cycles - start
    assert app.typer.DIRECT_MIN <= held < app.typer.DIRECT_MIN + CLOCK // 30
    app.typer.press_live("4")
    for _ in range(3):
        app.frame()
    app.typer.release_live("4")
    assert "4" not in m.held
    app.close()


def test_frame_polls_between_substeps():
    """runはフレームの本体の実行をSUBSTEPSに分け、合間にpollを呼ぶ(キーの遅れを小さくする)。
    分けても1フレームで進むサイクルは同じで、分け方はほぼ均等"""
    from sc61box.app import SUBSTEPS

    app = make_app(frames=3)
    calls: list[int] = []
    c0 = app.m.cpu.cycles
    app.frame(lambda: calls.append(app.m.cpu.cycles))
    assert len(calls) == SUBSTEPS - 1
    gaps = [b - a for a, b in zip([c0, *calls], [*calls, app.m.cpu.cycles], strict=True)]
    assert max(gaps) - min(gaps) <= 2 * (CLOCK // 200)
    assert abs(sum(gaps) - CLOCK // 30) <= CLOCK // 200
    app.close()


def test_frame_stops_after_pause_or_restore_between_substeps():
    """合間の操作で一時停止したら、そのフレームの残りは動かさない。状態を復元したら、復元前の
    目標のサイクルまで動かさず、復元した所で止まる"""
    app = make_app(frames=3)
    m = app.m
    c0 = m.cpu.cycles

    def pause() -> None:
        app.halted = True

    app.frame(pause)
    assert 0 < m.cpu.cycles - c0 <= CLOCK // 30 // 3  # 4分割の1つめで止まる
    app.halted = False
    for _ in range(3):
        app.frame()
    snap = m.snapshot()
    saved = m.cpu.cycles
    for _ in range(3):
        app.frame()

    def restore() -> None:
        m.restore(snap)

    app.frame(restore)
    assert m.cpu.cycles == saved
    app.close()


def test_sound_after_restore_between_substeps_is_short():
    """合間に状態を復元しても、そのフレームの音は復元した所から先だけ(復元前の時刻からの差で
    何秒ぶんもの音を作らない)"""
    from sc61box.audio import FRAME_SAMPLES, TARGET

    class Ear:
        keep_silent = True

        def __init__(self) -> None:
            self.pcm: list[bytes] = []

        def level(self) -> int:
            return TARGET

        def push(self, pcm: bytes) -> None:
            self.pcm.append(pcm)

        def clear(self) -> None:
            pass

        def close(self) -> None:
            pass

    app = make_app(frames=3)
    m = app.m
    snap = m.snapshot()
    for _ in range(60):  # 2秒先へ
        app.frame()
    ear = Ear()
    app.speaker = ear  # pyrefly: ignore

    def restore() -> None:
        m.restore(snap)

    app.frame(restore)
    assert all(len(p) <= 2 * FRAME_SAMPLES for p in ear.pcm)
    app.close()


def test_keys_after_restoring_state(tmp_path, monkeypatch):
    """状態を戻したあとも、戻した本体に合わせてキーを届ける。プログラムが動いている状態に
    戻せば同時押しがすぐ伝わり、入力待ちの状態に戻せばキューに入る"""
    m = (app := make_app(model="1261")).m
    monkeypatch.setattr(app, "state_file", str(tmp_path / "state.json"))
    app.save_state()  # 入力待ち
    _running(app)
    running = str(tmp_path / "running.json")
    monkeypatch.setattr(app, "state_file", running)
    app.save_state()
    m.brk = True  # 止めて入力待ちのまましばらく待つ(サイクルが保存したときより先へ進む)
    for _ in range(5):
        app.frame()
    m.brk = False
    for _ in range(60):
        app.frame()
    assert m.halted
    app.load_state()
    for name in ("DEF", "6", "8"):
        app.typer.press_live(name)
    assert {"DEF", "6", "8"} <= m.held and not app.typer.queue
    for name in ("DEF", "6", "8"):
        app.typer.release_live(name)
    for _ in range(5):
        app.frame()
    app.load_state(str(tmp_path / "state.json"))
    assert m.halted
    app.typer.press_live("A")
    assert app.typer.queue and not app.typer.direct
    app.close()


def test_keys_at_prompt_are_still_queued():
    """ROMが入力を待っているときのキーは、これまでどおりキューに入れて1つずつ届ける"""
    app = make_app(model="1261")
    assert app.m.halted
    app.typer.press_live("A")
    app.typer.press_live("B")
    assert [e[2:] if isinstance(e, list) else e for e in app.typer.queue] == [["A"], ["B"]]
    assert not app.typer.direct
    app.close()


def test_keys_during_program_are_not_rushed():
    """プログラムが動いているあいだに押したキー(INKEY$などで読まれる)では速く回さない"""
    app = make_app()
    app.typer.add_text("NEW\n")
    app.set_mode("PRO")
    app.typer.add_text("10 GOTO 10\n")
    app.typer.add_mode("RUN")
    app.typer.add_text("RUN\n")
    while app.typer.busy:
        app.frame()
    for _ in range(10):
        app.frame()
    assert not app.m.halted
    app.typer.press_live("A")
    app.frame()
    assert not app.typer.rush and not app.typer.rushing
    app.typer.release_live("A")
    app.close()


def test_rush_does_not_stretch_recording(tmp_path, monkeypatch):
    """キーを速く届けたあいだは音にしないので、録画の長さは実際に動かしたフレームの数と
    そろう(速く回した分だけ動画が引き延ばされない)"""
    monkeypatch.setenv("SC61BOX_PROGRAMS", str(tmp_path))
    app = make_app()
    _pro(app, "1251")
    app.typer.add_text("NEW\n")
    while app.typer.busy:
        app.frame()
    app.toggle_recording()
    frames = 0
    for ch in "10 PRINT 12345\n20 A=1\n":
        name = {" ": "SPC", "\n": "ENTER"}.get(ch, ch)
        app.typer.press_live(name)
        app.frame()
        app.typer.release_live(name)
        frames += 1
    for _ in range(10):
        app.frame()
        frames += 1
    assert app.recorder is not None
    seconds = app.recorder.seconds
    app.toggle_recording()
    assert abs(seconds - frames / 30) < 0.15, (seconds, frames)
    app.close()


def test_switch_menus_with_one_click():
    """メニューを開いたまま操作欄のほかのボタンを押すと、閉じてそのボタンの操作をする。
    同じボタンなら閉じるだけ。←→で隣のメニューへ移る"""
    app = make_app(scale=0.6)
    app.frame()
    labels = [b.label for b in app.bar.buttons]
    rect = {name: app.bar.rects[labels.index(name)] for name in labels}
    _click(app, rect["プログラム"].center)
    assert app.popup is not None and app.popup.kind == "program"
    _click(app, rect["本体"].center)
    assert app.popup is not None and app.popup.kind == "machine"
    _click(app, rect["本体"].center)
    assert app.popup is None
    _click(app, rect["表示・入力"].center)
    _click(app, rect["実行を一時停止"].center)
    assert app.popup is None and app.halted
    app.toggle_halt()
    app.frame()
    _click(app, rect["プログラム"].center)
    for key, kind in ((pygame.K_RIGHT, "machine"), (pygame.K_RIGHT, "view"),
                      (pygame.K_LEFT, "machine")):  # fmt: skip
        app.handle(ev(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))
        assert app.popup.kind == kind
    app.close()


def test_same_key_from_two_sources():
    """同じ本体のキーを2つの入力元から押しているときは、片方を離しても押したまま。
    2つの入力元は、↑を8にしたときの↑と数字の8や、パソコンのキーボードとマウス"""
    m = (app := make_app()).m
    _running(app)
    app.toggle_arrows()
    for key in (pygame.K_UP, pygame.K_8):
        app.handle(ev(pygame.KEYDOWN, key=key, mod=0, unicode=""))
    app.frame()
    app.handle(ev(pygame.KEYUP, key=pygame.K_UP, mod=0, unicode=""))
    for _ in range(3):
        app.frame()
    assert "8" in m.held and "8" in app.typer.physical
    app.handle(ev(pygame.KEYUP, key=pygame.K_8, mod=0, unicode=""))
    for _ in range(3):
        app.frame()
    assert "8" not in m.held
    # キーボードの8を押したまま、本体の8をマウスで押して離す
    app.handle(ev(pygame.KEYDOWN, key=pygame.K_8, mod=0, unicode=""))
    app.typer.press_mouse("8")
    app.frame()
    app.typer.release_mouse("8")
    for _ in range(3):
        app.frame()
    assert "8" in m.held
    # マウスで押したまま、キーボードの8を押して離す
    app.typer.press_mouse("8")
    app.handle(ev(pygame.KEYUP, key=pygame.K_8, mod=0, unicode=""))
    for _ in range(3):
        app.frame()
    assert "8" in m.held
    app.typer.release_mouse("8")
    app.frame()
    assert "8" not in m.held
    app.close()


def test_brk_from_two_sources():
    """BRKキーも、EscキーとマウスでBRKを押しているときは、片方を離しても押したまま"""
    from sc61box import display

    app = make_app()
    m = app.m
    x0, y0, x1, y1 = app.panel.key_rects["BRK"]
    pos = (
        int(((x0 + x1) / 2 + display.MARGIN) * app.scale),
        int(((y0 + y1) / 2 + display.MARGIN) * app.scale),
    )
    esc_down = ev(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="")
    esc_up = ev(pygame.KEYUP, key=pygame.K_ESCAPE, mod=0, unicode="")
    mouse_down = ev(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)
    mouse_up = ev(pygame.MOUSEBUTTONUP, button=1, pos=pos)
    app.handle(esc_down)
    app.handle(mouse_down)
    assert app.mouse_key == "BRK"
    app.handle(mouse_up)
    assert m.brk
    app.handle(esc_up)
    assert not m.brk
    app.handle(mouse_down)
    app.handle(esc_down)
    app.handle(esc_up)
    assert m.brk
    app.handle(mouse_up)
    assert not m.brk
    app.close()


@pytest.mark.parametrize("shape", ["both", "body", "lcd"])
def test_record_shapes(tmp_path, monkeypatch, shape):
    """録画の形(液晶の拡大と本体、本体だけ、液晶だけ)は、どれも1280×720の動画になる。選んだ形を
    覚え、⇧⌘R(toggle_recording)はその形で始め、メニューではその形に●をつける"""
    import subprocess

    from PIL import Image

    from sc61box import recorder

    monkeypatch.setenv("SC61BOX_PROGRAMS", str(tmp_path))
    app = make_app()
    app.start_recording(shape)
    assert app.recorder is not None and app.rec_shape == shape
    for _ in range(40):
        app.frame()
    app.toggle_recording()
    files = sorted(tmp_path.glob("rec-*.mp4"))
    assert len(files) == 1, app.status
    shot = tmp_path / "frame.png"
    subprocess.run(
        [recorder.ffmpeg_exe(), "-loglevel", "error", "-ss", "1", "-i", str(files[0]),
         "-frames:v", "1", str(shot)],
        check=True,
    )  # fmt: skip
    img = Image.open(shot).convert("RGB")
    assert img.size == (recorder.W, recorder.H)

    def looks(y: int) -> str:
        """高さyの帯の色(lcdは灰緑の液晶の地、bgは動画の地、otherはほか)"""
        band = img.crop((340, y - 4, 1240, y + 4))
        r, g, b = band.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))  # type: ignore[misc]
        if 140 < g < 220 and g > b + 8 and abs(r - g) < 20:
            return "lcd"
        return "bg" if max(r, g, b) < 40 else "other"

    # 液晶の拡大は、bothでは題名のすぐ下、lcdでは題名の下の中ほど(上下は地)。bodyは下まで本体
    x0, y0, x1, y1 = app.panel.lcd_box()
    lcd_h = round((y1 - y0) * recorder.LCD_W / (x1 - x0) / 2) * 2
    room = recorder.H - 20 - recorder.LCD_TOP
    under_title, bottom = recorder.LCD_TOP + 6, recorder.H - 60
    if shape == "both":
        assert looks(recorder.LCD_TOP + lcd_h // 2) == "lcd"
    elif shape == "lcd":
        assert looks(recorder.LCD_TOP + (room - lcd_h) // 2 + lcd_h // 2) == "lcd"
        assert looks(under_title) == looks(bottom) == "bg"
    else:
        assert looks(bottom) == "other"
    # 次に⇧⌘Rで始めるのも同じ形。メニューの●もその形
    app.toggle_recording()
    assert app.recorder is not None and app.rec_shape == shape
    app.open_bar_popup("recstart")
    assert app.popup_mark() == str(appmod.REC_SHAPE_NAMES[shape])
    app.popup = None
    app.recorder.abort()
    app.recorder = None
    app.close()


def test_record_graph_fits():
    """録画の形ごとのffmpegのフィルタ。絵は題名の下(LCD_TOPから下の余白20まで)に、左右の
    中央に収まる。形の名前が違えば断る"""
    from sc61box import display, recorder

    size = (display.OUT_W, display.OUT_H)
    for shape in recorder.SHAPES:
        assert "[v]" in recorder.graph(shape, size)
    with pytest.raises(ValueError):
        recorder.graph("big", size)


def test_record_stop_without_frames(tmp_path):
    """本体の絵を1枚も渡さずに録画を終えても(録り始めてすぐ止めたときなど)、ffmpegを待ち続け
    ない(題名の画像を繰り返す入力にしていたので、終わらずに止まっていた)"""
    import threading

    from sc61box import recorder

    for shape in recorder.SHAPES:
        rec = recorder.Recorder(str(tmp_path / f"{shape}.mp4"), "T", "S", shape=shape)
        done: list[str] = []

        def finish(rec=rec, done=done):
            try:
                done.append(rec.close())
            except OSError as e:
                done.append(str(e))

        t = threading.Thread(target=finish, daemon=True)
        t.start()
        t.join(30)
        if not done:
            rec.proc.kill()
        assert done, shape

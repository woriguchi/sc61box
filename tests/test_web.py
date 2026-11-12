"""ブラウザ版(web.py)のページとのやりとりと、ブラウザで使うアプリの動かし方(ページのjsは偽物)"""

import asyncio
import importlib
import os
import sys
import types

import pytest
from helpers import make_app, settle

from sc61box import audio, host


class FakeAudio:
    def __init__(self) -> None:
        self.state = -1  # 音を出せない(利用者がまだ操作していない)
        self.pushed: list[bytes] = []

    def open(self) -> bool:
        return True

    def queued(self) -> int:
        return self.state

    def push(self, data: bytes) -> None:
        self.pushed.append(data)
        self.state += len(data) // 2

    def clear(self) -> None:
        self.state = 0

    def close(self) -> None:
        pass


@pytest.fixture
def web(monkeypatch):
    """偽物のjsとpyodideでweb.pyを読む"""
    page = types.SimpleNamespace(audio=FakeAudio(), copied=[], synced=0)
    page.copyText = page.copied.append

    def sync() -> None:
        page.synced += 1

    page.sync = sync
    page.chosen = 0
    page.downloads = []

    def choose() -> None:
        page.chosen += 1

    page.chooseFiles = choose
    page.clipboard = "456"  # ブラウザのClipboard APIで読める文字(Noneなら読めない)
    page.readClipboard = lambda done: done(page.clipboard)
    page.download = lambda name, data: page.downloads.append((name, bytes(data)))
    js = types.ModuleType("js")
    js.sc61box = page  # pyrefly: ignore[missing-attribute]
    js.location = types.SimpleNamespace(  # pyrefly: ignore[missing-attribute]
        origin="https://sc61box.github.io", host="sc61box.github.io", pathname="/"
    )
    ffi = types.ModuleType("pyodide.ffi")
    ffi.create_proxy = lambda f: f  # pyrefly: ignore[missing-attribute]
    ffi.JsException = type("JsException", (Exception,), {})  # pyrefly: ignore[missing-attribute]
    ffi.create_once_callable = lambda f: f  # pyrefly: ignore[missing-attribute]
    ffi.to_js = lambda x: x if isinstance(x, list) else bytes(x)  # pyrefly: ignore[missing-attribute]
    monkeypatch.setitem(sys.modules, "js", js)
    monkeypatch.setitem(sys.modules, "pyodide", types.ModuleType("pyodide"))
    monkeypatch.setitem(sys.modules, "pyodide.ffi", ffi)
    monkeypatch.delitem(sys.modules, "sc61box.web", raising=False)
    module = importlib.import_module("sc61box.web")
    yield module, page
    sys.modules.pop("sc61box.web", None)


def test_web_audio_waits_for_page(web):
    """音を出せるまでは積まずに捨て、たまり具合は目標どおりと見なす(本体の速さを変えない)。
    出せるようになったら、SDLのキューと同じく鳴り始めに無音を足して目標までためる"""
    module, page = web
    out = module.WebAudio()
    pcm = bytes(2 * 100)
    out.push(pcm)
    assert page.audio.pushed == [] and out.level() == audio.TARGET
    page.audio.state = 0
    out.push(pcm)
    assert len(page.audio.pushed) == 1 and len(page.audio.pushed[0]) == 2 * audio.TARGET
    out.push(pcm)
    assert len(page.audio.pushed[1]) == len(pcm)


def test_clipboard_goes_through_page(web, monkeypatch):
    module, page = web
    monkeypatch.setattr(host, "WEB", True)
    host.copy_text("# pad: a=5")
    assert page.copied == ["# pad: a=5"]
    got: list[str | None] = []
    module.paste("10 PRINT 1\n")  # ⌘Vのpasteのイベント
    host.read_clipboard(got.append)
    host.read_clipboard(got.append)  # 2回目はイベントがないので、クリップボードを読みに行く
    assert got == ["10 PRINT 1\n", "456"]
    host.reveal("/")  # ブラウザには開くフォルダがない(何も起きない)


def test_menu_paste_reads_current_clipboard(web, monkeypatch):
    """メニューから貼り付けると、前の⌘Vの文字ではなく、いまのクリップボードを読む。読めなければ
    ⌘Vを使うように知らせる"""
    module, page = web
    monkeypatch.setattr(host, "WEB", True)
    app = make_app(norom=True)
    typed: list[str] = []
    monkeypatch.setattr(app.typer, "add_text", typed.append)
    module.paste("123")
    app.paste()  # ⌘Vのキー
    now = module.time.monotonic()
    module.paste("999")  # 古いpasteのイベント(このあとのメニューでは使わない)
    monkeypatch.setattr(module.time, "monotonic", lambda: now + 5)
    app.paste()  # メニュー
    assert typed == ["123", "456"]
    page.clipboard = None
    app.paste()
    assert typed == ["123", "456"] and "Vで貼り付けてください" in app.status
    app.close()


def test_run_async_runs_frames_until_closed(monkeypatch):
    app = make_app(frames=0, norom=True)
    count = [0]
    frame = app.frame

    def counted() -> None:
        frame()
        count[0] += 1
        if count[0] == 5:
            app.closing = True

    monkeypatch.setattr(app, "frame", counted)
    closed = []
    monkeypatch.setattr(app, "close", lambda: closed.append(True))
    asyncio.run(app.run_async())
    assert count[0] == 5 and closed == [True]


def test_store_ram_while_running_keeps_machine(tmp_path, monkeypatch):
    """ページを隠したときの保存(running)は、RAMを書いても本体を動かし続け、内部RAMも変えない"""
    from sc61box import app as app_module

    monkeypatch.setattr(app_module, "STATE_DIR", str(tmp_path))
    app = make_app(norom=True)
    app.typer.add_mode("PRO")
    app.typer.add_text('10 PRINT "HIDE"\n')
    for _ in range(300):
        app.frame()
    iram = bytes(app.m.cpu.ram)
    app.ram_file = str(tmp_path / "ram.bin")
    app.store_ram(running=True)
    assert app.m.power and bytes(app.m.cpu.ram) == iram
    again = make_app(norom=True)
    assert again.m.load_ram(app.ram_file)
    lo, hi = app.m.model.ram
    assert again.m.mem[lo:hi] == app.m.mem[lo:hi] != bytes(hi - lo)
    app.close()
    again.close()


def test_received_files_open_and_stay_in_program_folder(web, monkeypatch):
    """選んだ.basと.hexはプログラムのフォルダに置き、.basを開く(.hexも一緒に読み込む)"""
    from sc61box import programs

    module, page = web
    app = make_app(norom=True)
    opened = []
    monkeypatch.setattr(app, "open_program", lambda prog, run=False: opened.append(prog))
    here = os.path.join(os.path.dirname(__file__), "..", "programs", "pc1251")
    files = []
    for name in ("ball.hex", "ball.bas"):
        with open(os.path.join(here, name), "rb") as f:
            files.append((name, f.read()))
    module.received(app, files)
    assert os.path.exists(os.path.join(programs.user_dir(), "ball.bas"))
    assert len(opened) == 1 and opened[0].title == "弾むボール(マシン語)"
    assert any(p.endswith("ball.hex") for p in opened[0].paths)
    assert page.synced == 1
    app.close()


def test_browser_folder_and_exports(web, monkeypatch, tmp_path):
    """ブラウザでは、フォルダを開く代わりにファイルを選んでもらい、書き出したファイルは
    ダウンロードで渡す(画面の写しはブラウザの保存領域に残さない)"""
    from sc61box import app as app_module

    _module, page = web
    monkeypatch.setattr(host, "WEB", True)
    monkeypatch.setattr(app_module, "STATE_DIR", str(tmp_path))
    app = make_app(norom=True)
    items = [it.label for it in app.popup_items("program")]
    assert "ファイルから読み込む" in items and "プログラムのフォルダを開く" not in items
    app.open_menu()
    app.menu_action("folder")
    assert page.chosen == 1
    app.screenshot()
    name, data = page.downloads[-1]
    assert name.startswith("shot") and data.startswith(b"\x89PNG")
    assert not os.listdir(tmp_path)
    assert app.status == "shot001.pngをダウンロードしました"
    app.close()


def test_web_build_uses_only_public_files(tmp_path):
    """ブラウザ版の組み立ては、公開用のリポジトリにあるものだけを使う(doc/fontsは公開しない)。
    ROMと公開しないプログラムは入れない"""
    import importlib.util
    import zipfile

    root = os.path.join(os.path.dirname(__file__), "..")
    spec = importlib.util.spec_from_file_location(
        "web_build", os.path.join(root, "web", "build.py")
    )
    assert spec is not None and spec.loader is not None
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    web_dir = os.path.abspath(os.path.join(root, "web"))
    assert all(os.path.abspath(p).startswith(web_dir + os.sep) for p in build.FONTS)
    build.build(str(tmp_path), cdn=True)
    names = zipfile.ZipFile(tmp_path / "app.zip").namelist()
    assert "sc61box/web.py" in names and "fonts/SourceCodePro-Regular.otf" in names
    assert "programs/anime.bas" in names
    assert not [n for n in names if n.startswith(("rom/", "programs/private/", "programs/src/"))]
    for name in ("favicon.ico", "icon.png", "logo.png", "logo-light.png", "manifest.webmanifest",
                 *build.HOME_ICONS.values()):  # fmt: skip
        assert (tmp_path / name).exists(), name
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "{{" not in page and build.PYODIDE_CDN in page
    files = _worker_files(tmp_path)
    assert files and not [f for f in files if f.startswith("pyodide/")]  # CDNのPyodideは持たない


def _worker_files(out) -> list[str]:
    """組み立てたsw.jsが持っておくファイル"""
    import json
    import re

    worker = (out / "sw.js").read_text(encoding="utf-8")
    assert "{{" not in worker
    m = re.search(r"const FILES = (.*);", worker)
    assert m is not None
    return json.loads(m.group(1))


def _web_build():
    import importlib.util

    root = os.path.join(os.path.dirname(__file__), "..")
    spec = importlib.util.spec_from_file_location(
        "web_build", os.path.join(root, "web", "build.py")
    )
    assert spec is not None and spec.loader is not None
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    return build


def _fake_pyodide(folder) -> list[str]:
    """本体と、pygame-ce・Pillow(Pillowは依存を1つ持つ)だけのPyodideのフォルダ。置くはずの名前を返す"""
    import json

    wheels = {"pygame-ce": ("pygame_ce-1.whl", []), "pillow": ("pillow-1.whl", ["extra"]),
              "extra": ("extra-1.whl", []), "numpy": ("numpy-1.whl", [])}  # fmt: skip
    lock = {n: {"file_name": f, "depends": d} for n, (f, d) in wheels.items()}
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "pyodide-lock.json"), "w", encoding="utf-8") as f:
        json.dump({"packages": lock}, f)
    names = ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip"]
    names += ["pygame_ce-1.whl", "pillow-1.whl", "extra-1.whl", "numpy-1.whl"]
    for name in names:
        with open(os.path.join(folder, name), "wb") as f:
            f.write(name.encode())
    return [*names[:4], "pyodide-lock.json", *names[4:7]]


def test_web_build_keeps_pyodide_for_offline_use(tmp_path):
    """Pyodideは、使う分(本体と、pygame-ce・Pillowとその依存)だけを一緒に置き、sw.jsは、置いた
    ファイルをすべて持っておく。中身が変われば、sw.jsの名前(VERSION)も変わる"""
    import re

    build = _web_build()
    want = _fake_pyodide(tmp_path / "pyodide")
    out = tmp_path / "out"
    build.build(str(out), str(tmp_path / "pyodide"))
    folder = (
        f"pyodide/{build.PYODIDE_VERSION}"  # 版を上げても、前の版のページが前のファイルを読める
    )
    assert sorted(os.listdir(out / folder)) == sorted(want)
    page = (out / "index.html").read_text(encoding="utf-8")
    assert f'loadPyodide({{ indexURL: "./{folder}/" }})' in page
    worker = (out / "sw.js").read_text(encoding="utf-8")
    files = _worker_files(out)
    assert {f"{folder}/{n}" for n in want} <= set(files) and "./" in files
    assert any(f.startswith("app.zip?") for f in files)
    for name in files:
        assert (out / ("index.html" if name == "./" else name.split("?")[0])).exists(), name
    first = re.search(r'const VERSION = "(\w+)"', worker)
    (tmp_path / "pyodide" / "pyodide.asm.wasm").write_bytes(b"changed")
    build.build(str(out), str(tmp_path / "pyodide"))
    again = re.search(r'const VERSION = "(\w+)"', (out / "sw.js").read_text(encoding="utf-8"))
    assert first is not None and again is not None and first.group(1) != again.group(1)


def test_web_build_fetches_pyodide_once(tmp_path, monkeypatch):
    """Pyodideのフォルダを渡さなければ、CDNから使う分だけを取ってきてPYODIDE_CACHEに残し、
    次からはそれを使う"""
    build = _web_build()
    source = tmp_path / "cdn"
    want = _fake_pyodide(source)
    fetched = []

    def download(name: str, dest: str) -> None:
        fetched.append(name)
        with open(source / name, "rb") as f, open(dest, "wb") as g:
            g.write(f.read())

    monkeypatch.setattr(build, "_download", download)
    monkeypatch.setattr(build, "PYODIDE_CACHE", str(tmp_path / "cache"))
    build.build(str(tmp_path / "out"))
    assert sorted(fetched) == sorted(want)
    build.build(str(tmp_path / "out"))
    assert len(fetched) == len(want)
    folder = tmp_path / "out" / "pyodide" / build.PYODIDE_VERSION
    assert sorted(os.listdir(folder)) == sorted(want)


def test_browser_says_ram_loaded_without_fresh_option(monkeypatch):
    """ブラウザでは、保存したRAMを読み込んだときに--freshを案内しない(コマンドの引数がない)"""
    monkeypatch.setattr(host, "WEB", True)
    app = make_app(norom=True, fresh=False)
    app.store_ram()
    app.close()
    again = make_app(norom=True, fresh=False, frames=1)
    assert "前回のRAMを読み込みました" in again.status and "--fresh" not in again.status
    again.close()


def test_save_returns_written_files(web):
    """ページは、保存で書いたファイルの写しをIndexedDBに書き終わるまで持つので、名前を返す。
    --freshで起動したとき(保存しない)は何も返さない"""
    module, _page = web
    app = make_app(norom=True, fresh=False)
    paths = module.save(app)
    assert len(paths) == 2 and all(os.path.exists(p) for p in paths)
    app.close()
    fresh = make_app(norom=True)
    assert module.save(fresh) == []
    fresh.close()


def test_fit_page_scales_body_only(monkeypatch):
    """ブラウザでは、ページのあいている所いっぱいに本体を拡大・縮小し、操作欄の高さは変えない"""
    from sc61box.overlay import BAR_H

    monkeypatch.setattr(host, "WEB", True)
    app = make_app(norom=True, frames=1)
    w, h = app.out_w, app.out_h
    app.fit_page(2 * w, 2 * h + BAR_H)  # 広いページでは拡大する
    assert app.body_size == (2 * w, 2 * h)
    assert app.window.get_size() == (2 * w, 2 * h + BAR_H)
    app.fit_page(w // 2, h)  # 狭いページでは縮める(幅で決まる)
    assert app.body_size[0] == w // 2 and app.window.get_height() == app.body_size[1] + BAR_H
    app.close()


def test_scaled_body_is_reused_while_panel_is_unchanged(monkeypatch):
    """本体の絵を描き直したフレームでだけ拡大・縮小し直し、同じ見え方のフレームでは前の結果を使う"""
    import pygame

    monkeypatch.setattr(host, "WEB", True)
    app = make_app(norom=True, frames=30)
    app.fit_page(app.out_w, app.out_h)  # 等倍より少し小さい(操作欄のぶん)
    calls = []
    real = pygame.transform.smoothscale
    monkeypatch.setattr(pygame.transform, "smoothscale", lambda *a: calls.append(1) or real(*a))
    redrawn = 0
    for i in range(60):
        if i == 30:
            app.m.held.add("A")
        before = app.panel.shown
        app.frame()
        redrawn += app.panel.shown is not before
    assert len(calls) == redrawn and 0 < redrawn < 60
    app.close()


def test_card_message_points_to_page(monkeypatch):
    """RAMカードが足りないプログラムは、ブラウザでは--cardではなくページで選ぶように知らせる"""
    from sc61box import loading
    from sc61box.programs import Program

    app = make_app("1350", norom=True, frames=1)
    prog = Program(name="kanji", paths=["kanji.hex"], card=16)
    text, _seconds = loading.card_problem(prog, app.m, "kanji") or ("", 0)
    assert "--card 16" in text
    monkeypatch.setattr(host, "WEB", True)
    text, _seconds = loading.card_problem(prog, app.m, "kanji") or ("", 0)
    assert "ページの上でRAMカードを選んでください" in text
    app.close()


def test_body_only_fills_page_with_body(monkeypatch):
    """本体だけでは、操作欄・作業欄を隠し、机を切り詰めた本体の絵をページいっぱいに出す。
    キーの位置は、切り詰めた範囲に合わせて読む。戻すと作業欄も戻る"""
    from sc61box import benchview, display

    monkeypatch.setattr(host, "WEB", True)
    app = make_app(norom=True, frames=1)
    app.toggle_pane(True)
    app.fit_page(1000, 600)
    app.toggle_body_only(True)
    assert not app.pane_open
    box = app.view_box()
    cut = display.MARGIN - app.BODY_ROOM
    assert box == (cut, cut, app.out_w - 2 * cut, app.out_h - 2 * cut)
    assert app.scale == min(1000 / box.w, 600 / box.h)
    assert app.window.get_size() == app.body_size
    app.toggle_pane(True)  # 本体だけのあいだは出さない
    app.toggle_pad_panel(True)
    app.toggle_lcd(True)
    assert not app.pane_open and app.pad_panel is None and not app.lcd_only
    x0, y0, x1, y1 = app.panel.key_rects["A"]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    pos = ((cx + display.MARGIN - box.x) * app.scale, (cy + display.MARGIN - box.y) * app.scale)
    assert app.panel.key_at(*app._body_point(pos)) == "A"
    app.frame()
    app.fit_page(390, 664)  # 縦に持ったスマートフォンの幅にも入れる
    assert app.body_size[0] <= 390
    app.toggle_body_only(False)
    assert app.pane_open and app.window.get_width() == app.body_size[0] + benchview.PANE_W
    app.close()


def test_page_switches_body_only_and_opens_menu(web, monkeypatch):
    """ページのボタンで本体だけにし、「メニュー」で右クリックと同じメニューを出し入れする"""
    module, _page = web
    monkeypatch.setattr(host, "WEB", True)
    app = make_app(norom=True, frames=1)
    module.body_only(app, True, 800, 400)
    assert app.body_only and app.page_size == (800, 400)
    module.context_menu(app)
    assert app.popup is not None and app.popup.kind == "context"
    module.context_menu(app)
    assert app.popup is None
    module.body_only(app, False, 800, 360)
    assert not app.body_only and app.page_size == (800, 360)
    app.close()


def test_erase_ram_removes_saved_ram_and_restarts_page(web, monkeypatch):
    """ブラウザの「本体」のメニューでRAMを消すと、確かめてから保存したファイルを消し、
    保存をやめてページを読み直させる(パソコン版の--freshにあたる)"""
    from sc61box.app import bench_file

    _module, page = web
    page.restarted = []

    def restart(paths, failed) -> None:
        page.restarted.append(paths)

    page.restart = restart
    monkeypatch.setattr(host, "WEB", True)
    app = make_app(norom=True, frames=1)
    app.store_ram(running=True)
    assert os.path.exists(app.ram_file) and os.path.exists(bench_file(app.ram_file))
    labels = [it.label for it in app.popup_items("machine")]
    assert labels[-1] == "RAMを消して初期状態から始める…"
    app.ask_erase_ram()
    assert app.popup is not None and app.popup.kind == "erase" and app.popup.source == -1
    app.popup_run(1)  # やめる
    assert os.path.exists(app.ram_file) and page.restarted == []
    app.ask_erase_ram()
    app.popup_run(0)
    assert not os.path.exists(app.ram_file) and not os.path.exists(bench_file(app.ram_file))
    assert page.restarted == [[app.ram_file, bench_file(app.ram_file)]] and not app.save_ram
    app.close()
    assert not os.path.exists(app.ram_file)  # 閉じても書き戻さない


def test_body_only_makes_room_for_program_list(monkeypatch):
    """本体だけで本体がとても低いとき(縦に持ったスマートフォンのPC-1350)、一覧を開いている
    あいだはページの高さまでウィンドウを広げ、閉じれば本体の高さに戻す"""
    monkeypatch.setattr(host, "WEB", True)
    app = make_app("1350", norom=True, frames=1)
    app.toggle_body_only(True)
    app.fit_page(390, 844)
    low = app.window.get_size()
    assert low[1] < 200
    app.open_menu()
    app._open_window()
    assert app.window.get_size() == (390, app.MENU_ROOM)
    app.menu = None
    app._open_window()
    assert app.window.get_size() == low
    app.fit_page(750, 342)  # 横向きでは、ページの高さまで
    app.open_menu()
    app._open_window()
    assert app.window.get_height() == 342
    app.close()


def test_erase_ram_keeps_saving_when_browser_cannot_save(web, monkeypatch):
    """ブラウザの保存に反映できなければ、ページは読み直さず、RAMの保存を戻して知らせる
    (本体のRAMはそのままなので、次の保存でファイルを書き直す)"""
    _module, page = web
    page.restart = lambda paths, failed: failed()
    monkeypatch.setattr(host, "WEB", True)
    app = make_app(norom=True, frames=1)
    app.store_ram(running=True)
    app.erase_ram()
    assert app.save_ram and not os.path.exists(app.ram_file)
    assert app.status == "ブラウザの保存を書き換えられなかったため、RAMを消せませんでした"
    assert _module.save(app) and os.path.exists(app.ram_file)
    app.close()


def test_esc_does_not_press_brk_in_browser(monkeypatch):
    """ブラウザでは、Escは全画面を抜けるのに使うので、BRKを押さない(BRKは本体のキーを押す)。
    キーの説明にもEscのBRKを出さない"""
    import pygame

    from sc61box.app import help_lines

    esc = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="")
    app = make_app(norom=True, frames=1)
    app.key_down(esc)
    assert app.m.brk  # パソコンではBRK
    app.key_up(pygame.event.Event(pygame.KEYUP, key=pygame.K_ESCAPE, mod=0))
    monkeypatch.setattr(host, "WEB", True)
    app.key_down(esc)
    assert not app.m.brk
    for lines in (help_lines(), help_lines(is1350=True), help_lines(norom=True)):
        assert not any("Esc: BRK" in line for line in lines)
    app.close()


class FakeResponse:
    """pyodide.http.pyfetchが返すものの偽物"""

    def __init__(self, data: bytes, ok: bool = True, size: int | None = None) -> None:
        self.data, self.ok, self.status = data, ok, 200 if ok else 404
        self.headers = {} if size is None else {"content-length": str(size)}

    async def bytes(self) -> bytes:
        return self.data


def _serve(monkeypatch, module, files: dict[str, object]) -> list:
    """pyfetchとasyncio.ensure_futureを偽物にする。filesはURLごとに、返すFakeResponseか、
    投げる例外。ensure_futureに渡されたものは、その場で最後まで動かす"""
    import asyncio

    fetched = []

    async def pyfetch(url: str):
        fetched.append(url)
        answer = files[url]
        if isinstance(answer, Exception):
            raise answer
        return answer

    http = types.ModuleType("pyodide.http")
    http.pyfetch = pyfetch  # pyrefly: ignore[missing-attribute]
    monkeypatch.setitem(sys.modules, "pyodide.http", http)
    monkeypatch.setattr(module.asyncio, "ensure_future", asyncio.run)
    return fetched


def test_link_asks_then_loads_and_runs_program(web, monkeypatch):
    """?load=のリンクのファイルは、サイトと名前を出して確かめてから取ってきて開く。&runなら実行まで。
    「やめる」なら取ってこない"""
    from sc61box.lcdtext import lcd_text

    module, _page = web
    url = "https://example.com/dir/hello%20pc.bas"
    fetched = _serve(monkeypatch, module, {url: FakeResponse(b"10 PRINT 4321\n")})
    app = make_app(norom=True, frames=30)
    module.offer_link(app, url, run=True)
    assert app.popup is not None and app.popup.kind == "link"
    first = app.popup_items("link")[0]
    assert first.label == "example.comのhello pc.basを読み込む"
    assert first.note == "今のRAMの中身は置き換わります"
    app.popup_run(1)  # やめる
    assert fetched == []
    module.offer_link(app, url, run=True)
    app.popup_run(0)
    assert fetched == [url]
    settle(app)
    for _ in range(60):
        app.frame()
    assert lcd_text(app.m).strip().startswith("4321")
    app.close()


def test_link_tape_is_loaded_with_cload_and_run(web, monkeypatch, tmp_path):
    """テープ(.wav)のリンクは、&runならCLOADで読んで、読み終えたらRUNを打つ。&runがなければ
    セットするだけで、RAMは置き換わらない"""
    from basic_diff import basic_machine

    from sc61box import tape
    from sc61box.autotype import Typer
    from sc61box.lcdtext import lcd_text

    m = basic_machine("1251")
    t = Typer(m)
    t.add_mode("PRO")
    t.add_program("10 PRINT 4321\n")
    while t.busy:
        t.step()
        m.run(2000)
    path = str(tmp_path / "p.wav")
    tape.write_wav(path, tape.record(m, "CSAVE"))
    with open(path, "rb") as f:
        data = f.read()
    module, _page = web
    url = "https://example.com/p.wav"
    _serve(monkeypatch, module, {url: FakeResponse(data)})
    app = make_app(norom=True, frames=30)
    module.offer_link(app, url, run=False)
    assert app.popup_items("link")[0].note == ""
    app.popup_run(0)
    assert app.m.tape is not None and not app.typer.busy
    app.m.tape = None
    module.offer_link(app, url, run=True)
    app.popup_run(0)
    for _ in range(6000):  # CLOADで読み終えて、RUNで出すまで
        app.frame()
        if lcd_text(app.m).strip().startswith("4321"):
            break
    assert lcd_text(app.m).strip().startswith("4321")
    app.close()


def test_link_refuses_bad_files(web, monkeypatch):
    """http・https以外、読めない種類、取れない(ほかのサイトからの読み込みを許していないなど)、
    大きすぎるファイルは、読み込まずに知らせる"""
    module, _page = web
    big = "https://example.com/big.bas"
    gone = "https://example.com/gone.hex"
    blocked = "https://example.com/blocked.bas"
    _serve(monkeypatch, module, {
        big: FakeResponse(b"", size=2 << 20),
        gone: FakeResponse(b"", ok=False),
        blocked: OSError("Failed to fetch"),
    })  # fmt: skip
    app = make_app(norom=True, frames=1)
    module.offer_link(app, "file:///etc/passwd.bas", run=False)
    assert app.popup is None and app.status == "リンクのファイルの場所(URL)が正しくありません"
    module.offer_link(app, "https://example.com/routine.py", run=False)
    assert app.popup is None
    assert app.status == "リンクで読み込めるのは.bas・.hex・.wavのファイルだけです"
    for url, name in ((big, "big.bas"), (gone, "gone.hex"), (blocked, "blocked.bas")):
        module.offer_link(app, url, run=False)
        app.popup_run(0)
        assert name in app.status and app.status != f"{name}を読み込んでいます"
    assert app.status.startswith("blocked.basを読み込めませんでした")
    app.close()


def test_program_link_round_trip(web, monkeypatch):
    """「プログラムをリンクにしてコピー」は、RAMのBASICのプログラム(と題)を縮めて#bas=に入れた
    リンクをコピーする。そのリンクを開くと、確かめてから読み込んで実行する"""
    from sc61box.lcdtext import lcd_text

    module, page = web
    monkeypatch.setattr(host, "WEB", True)
    page.shared = []
    page.shareLink = lambda url, done: (page.shared.append(url), done(True))
    app = make_app(norom=True, frames=30)
    app.share_program()
    assert app.status == "リンクにするプログラムがありません" and page.shared == []
    module.received(app, [("hello.bas", "# title: こんにちは\n10 PRINT 4321\n".encode())])
    settle(app)
    labels = [it.label for it in app.popup_items("program")]
    assert "プログラムをリンクにしてコピー" in labels
    app.share_program()
    (url,) = page.shared
    head = "https://sc61box.github.io/?model=1251#run&bas="
    assert url.startswith(head)
    assert app.status == f"プログラムのリンクをコピーしました({len(url)}字)"
    text = module.unpack(url[len(head) :])
    assert text.startswith("# title: こんにちは\n") and "10 PRINT 4321" in text
    page.shareLink = lambda url, done: done(False)  # コピーできなければ、ページのアドレスにする
    app.share_program()
    assert app.status.startswith("クリップボードにコピーできなかったため")
    app.close()

    other = make_app(norom=True, frames=30)
    module.offer_shared(other, url[len(head) :], run=True)
    assert other.popup_items("link")[0].label == "リンクのプログラムを読み込む"
    other.popup_run(0)
    settle(other)
    for _ in range(60):
        other.frame()
    assert lcd_text(other.m).strip().startswith("4321")
    assert other.last_prog is not None and other.last_prog.title == "こんにちは"
    other.close()


def test_program_link_refuses_broken_or_huge_data(web):
    """リンクのプログラムが読めないか、ほどくと大きすぎれば、読み込まずに知らせる"""
    module, _page = web
    with pytest.raises(ValueError):
        module.unpack(module.pack("A" * (module.SHARED_LIMIT + 1)))
    with pytest.raises(ValueError):
        module.unpack(module.pack("10 PRINT 1")[:-4])
    app = make_app(norom=True, frames=1)
    module.offer_shared(app, "not*base64", run=True)
    assert app.popup is None and app.status == "リンクのプログラムを読めませんでした"
    app.close()


def test_link_with_broken_address_does_not_stop_start(web):
    """URLとして読めないリンク(角括弧が閉じていないなど)でも、知らせるだけで、起動を止めない"""
    module, _page = web
    app = make_app(norom=True, frames=1)
    module.offer_link(app, "http://[::1/p.bas", run=True)
    assert app.popup is None and app.status == "リンクのファイルの場所(URL)が正しくありません"
    module.dropped_link(app, "http://[::1/p.bas")
    assert app.popup is None
    app.close()


def test_broken_tape_link_does_not_load_previous_tape(web, tmp_path):
    """&runのテープが読めなければ、前にセットしていたテープをCLOADしない"""
    from sc61box import tape

    module, _page = web
    app = make_app(norom=True, frames=1)
    good = str(tmp_path / "good.wav")
    tape.write_wav(good, tape.record(app.m, "CSAVE"))
    assert app.insert_tape(good)
    before = app.m.tape
    module.received(app, [("broken.wav", b"not a wave file")], run=True)
    assert app.m.tape is before and not app.typer.busy
    assert app.status.startswith("broken.wav")
    app.close()


def test_dropped_link_opens_like_the_link(web):
    """ページに落としたリンクは、このページの?load=・#bas=のリンクならそれを開いたときと同じに、
    ほかはそのファイルのリンクとして、確かめてから読み込む"""
    module, _page = web
    app = make_app(norom=True, frames=1)
    data = module.pack("10 PRINT 1\n")
    module.dropped_link(app, f"https://sc61box.github.io/?model=1251#run&bas={data}")
    assert app.popup_items("link")[0].label == "リンクのプログラムを読み込む"
    app.popup = None
    module.dropped_link(app, "https://sc61box.github.io/?load=https://example.com/a.hex&run")
    assert app.popup_items("link")[0].label == "example.comのa.hexを読み込む"
    app.popup = None
    module.dropped_link(app, "https://example.org/games/b.bas")
    assert app.popup_items("link")[0].label == "example.orgのb.basを読み込む"
    app.close()


def test_tape_link_runs_only_after_cload_finishes(web, monkeypatch):
    """&runのテープは、ROMなしのBASICがCLOADを読み終えたと知らせたときだけRUNを打つ。BRKで
    止めたら打たない(テープが残っているかでは見ない)"""
    module, _page = web
    app = make_app(norom=True, frames=30)
    typed = []
    add_text = app.typer.add_text
    monkeypatch.setattr(app.typer, "add_text", lambda text: (typed.append(text), add_text(text)))
    module.cload_and_run(app)  # テープがないので、CLOADは入れられるまで待つ
    for _ in range(300):
        app.frame()
    assert typed == ["CLOAD\n"]
    app.press_brk("key")
    for _ in range(30):
        app.frame()
    app.release_brk("key")
    for _ in range(100):
        app.frame()
    assert typed == ["CLOAD\n"] and app.m.on_cload is None
    app.close()


def test_restore_forgets_cload_listener(web):
    """状態を戻すと、CLOADの知らせ先は消える。戻す前に読んでいたCLOADは、あとで置いた知らせ先を
    使わない"""
    import gc

    module, _page = web
    app = make_app(norom=True, frames=30)
    snap = app.m.snapshot()
    module.cload_and_run(app)  # テープがないので、CLOADは入れられるまで待つ
    for _ in range(300):
        app.frame()
    app.m.restore(snap)
    called = []
    app.m.on_cload = called.append
    for _ in range(100):
        app.frame()
    gc.collect()
    for _ in range(10):
        app.frame()
    assert called == []
    app.m.restore(snap)
    assert app.m.on_cload is None
    app.close()


def test_dropped_link_for_other_model_reopens_page(web):
    """機種かRAMカードの違うページへのリンクを落としたら、その場では読まず、RAMを保存してから
    そのリンクを開き直してもらう(機種とRAMカードの指定を失わない)"""
    module, page = web
    page.navigated = []
    page.navigate = page.navigated.append
    app = make_app(norom=True, frames=1)
    data = module.pack("10 PRINT 1\n")
    for url in (
        f"https://sc61box.github.io/?model=1350&card=16#run&bas={data}",
        "https://sc61box.github.io/?model=1261&load=https://example.com/a.bas",
    ):
        module.dropped_link(app, url)
        assert app.popup is None and page.navigated[-1] == url
    module.dropped_link(app, f"https://sc61box.github.io/#bas={data}")  # 書かなければPC-1251
    assert app.popup is not None and len(page.navigated) == 2
    app.close()


def test_offline_files_ready_or_failed(web, monkeypatch):
    """オフラインで使うためのファイルを初めて持てたら、出ているメッセージに続けて知らせる。
    持てなかったら知らせ、「本体」のメニューで試し直せる(試し直すと、その項目は消える)"""
    module, page = web
    page.kept = 0

    def keep() -> None:
        page.kept += 1

    page.keepOffline = keep
    monkeypatch.setattr(host, "WEB", True)
    app = make_app(norom=True, frames=1)
    app.say("起動しました", 5)
    module.offline_state(app, "ready")
    assert app.status == "起動しました\n次からは、ネットにつながっていなくても開けます"
    retry = "オフライン用に保存し直す"
    assert retry not in [it.label for it in app.popup_items("machine")]
    module.offline_state(app, "failed")
    assert "オフラインで使うためのファイルを保存できませんでした" in app.status
    items = {it.label: it for it in app.popup_items("machine")}
    assert retry in items
    action = items[retry].action
    assert action is not None
    action()
    assert page.kept == 1 and app.status == "オフラインで使うためのファイルを保存しています"
    assert retry not in [it.label for it in app.popup_items("machine")]
    app.close()

"""画面の言語(日本語と英語)の試験。英語の表の抜けと差し込みの名前、言語の決め方、
動かしているあいだの切り替え、英語の画面を描けるか"""

import ast
import glob
import os
import re
import string
import subprocess
import sys
import types

import pygame
import pytest
from conftest import HAVE_ROM, HAVE_ROM_1245, HAVE_ROM_1260, HAVE_ROM_1350
from helpers import make_app

from sc61box import i18n, romsyms
from sc61box.i18n import tr
from sc61box.messages import MESSAGES

SRC = os.path.join(os.path.dirname(__file__), "..", "sc61box")
JAPANESE = re.compile(r"[぀-ヿ一-鿿]")


def templates() -> dict[str, str]:
    """ソース(basic/の下も)のtr()とText()に、文字列のまま渡しているIDと、その場所"""
    found: dict[str, str] = {}
    for path in sorted(glob.glob(os.path.join(SRC, "**", "*.py"), recursive=True)):
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id not in ("tr", "Text") or not node.args:
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                where = os.path.relpath(path, SRC)
                found.setdefault(arg.value, f"{where}:{node.lineno}")
    return found


def rom_ids() -> set[str]:
    """作業欄に出すROMのルーチンの働きのID(tr(r.what)で引くもの)"""
    return {f"rom.{family}.{name.lower()}" for family in ("1251", "1261", "1350")
            for name in romsyms.entries(family)}  # fmt: skip


def forms(text: str | tuple[str, str]) -> tuple[str, ...]:
    return text if isinstance(text, tuple) else (text,)


def fields(text: str) -> set[str]:
    return {name for _lit, name, _spec, _conv in string.Formatter().parse(text) if name}


def test_every_id_is_in_table():
    missing = [f"{where}: {key}" for key, where in templates().items() if key not in MESSAGES]
    missing += [f"romsyms: {key}" for key in rom_ids() if key not in MESSAGES]
    assert not missing, "表にないID:\n" + "\n".join(missing)


def test_every_message_has_all_languages():
    for key, texts in MESSAGES.items():
        assert set(texts) == set(i18n.LANGUAGES), key
        assert all(forms(texts[lang]) for lang in i18n.LANGUAGES), key


def test_languages_use_same_placeholders():
    for key, texts in MESSAGES.items():
        ja = texts["ja"]
        assert isinstance(ja, str), key
        for lang in i18n.LANGUAGES:
            for form in forms(texts[lang]):
                assert fields(form) == fields(ja), (key, lang, form)


def test_plural_forms_take_n():
    for key, texts in MESSAGES.items():
        ja = texts["ja"]
        assert isinstance(ja, str), key
        for lang in i18n.LANGUAGES:
            if isinstance(texts[lang], tuple):
                assert len(texts[lang]) == 2 and "n" in fields(ja), key


def test_no_unused_messages():
    used = set(templates()) | rom_ids()
    unused = [key for key in MESSAGES if key not in used]
    assert not unused, "使っていないID:\n" + "\n".join(unused)


def test_tr_picks_language_and_plural():
    assert tr("app.wrote_bytes", n=3) == "3バイトを書き込みました"
    i18n.set_language("en")
    assert tr("app.wrote_bytes", n=1) == "Wrote 1 byte"
    assert tr("app.wrote_bytes", n=3) == "Wrote 3 bytes"
    assert tr("common.start_address_set", addr=0xC012) == "Start address set to C012"
    # 表にない文字列(利用者が記述した代替ROMルーチンの働きなど)は、そのまま
    assert tr("表にない文 {x}", x=5) == "表にない文 5"
    with pytest.raises(ValueError):
        i18n.set_language("fr")


def test_choose_language_order():
    choose = i18n.choose
    none = lambda: None  # noqa: E731
    linux = {"platform": "linux", "mac": none}
    assert choose(environ={}, **linux) == "ja"
    assert choose(environ={"LANG": "en_US.UTF-8"}, **linux) == "en"
    assert choose(environ={"LANG": "ja_JP.UTF-8"}, **linux) == "ja"
    assert choose(environ={"LANG": "C"}, **linux) == "en"
    assert choose(environ={"LANG": ""}, **linux) == "ja"
    # LC_ALL、LC_MESSAGES、LANGの順
    env = {"LC_ALL": "ja_JP.UTF-8", "LC_MESSAGES": "en_US", "LANG": "en_US"}
    assert choose(environ=env, **linux) == "ja"
    env = {"LC_MESSAGES": "en_US", "LANG": "ja_JP.UTF-8"}
    assert choose(environ=env, **linux) == "en"
    # メニューで選んだものはロケールより先、SC61BOX_LANGと--langはメニューより先
    assert choose(remembered="en", environ={"LANG": "ja_JP"}, **linux) == "en"
    assert choose(remembered="ja", environ={"SC61BOX_LANG": "en", "LANG": "ja"}, **linux) == "en"
    assert choose("ja", remembered="en", environ={"SC61BOX_LANG": "en"}, **linux) == "ja"
    assert choose(remembered="xx", environ={"LANG": "ja_JP"}, **linux) == "ja"
    # macOSでロケールがなければ、言語の設定を見る。読めなければja
    assert choose(environ={}, platform="darwin", mac=lambda: "en") == "en"
    assert choose(environ={}, platform="darwin", mac=none) == "ja"
    assert choose(environ={"LANG": "ja_JP.UTF-8"}, platform="darwin", mac=lambda: "en") == "ja"


def test_mac_language(monkeypatch):
    def fake(out: str, code: int = 0):
        def run(*_a, **_k):
            return types.SimpleNamespace(stdout=out, returncode=code)

        return run

    monkeypatch.setattr(subprocess, "run", fake('(\n    "en-JP",\n    "ja-JP"\n)\n'))
    assert i18n.mac_language() == "en"
    monkeypatch.setattr(subprocess, "run", fake("(\n    ja,\n    en\n)\n"))
    assert i18n.mac_language() == "ja"
    monkeypatch.setattr(subprocess, "run", fake("", 1))
    assert i18n.mac_language() is None

    def fail(*_a, **_k):
        raise OSError("no defaults")

    monkeypatch.setattr(subprocess, "run", fail)
    assert i18n.mac_language() is None


def test_wrap_keeps_words():
    from sc61box.overlay import load_help_font, wrap_text

    pygame.init()
    font = load_help_font(15)
    text = "Set a breakpoint at the instruction under the cursor (C000), or remove it"
    lines = wrap_text(font, text, 200)
    assert len(lines) > 1
    assert " ".join(lines) == text
    assert all(font.size(line)[0] <= 200 for line in lines)
    # 日本語は字ごとに折り返せる
    ja = "カーソルの命令(C000番地)にブレークポイントを設定・解除する"
    assert "".join(wrap_text(font, ja, 120)) == ja


def _view_labels(app) -> list[str]:
    return [it.label for it in app.popup_items("view") if it.action is not None]


def test_switch_language_from_menu(monkeypatch):
    """表示・入力のメニューで英語にすると、メニューの名前が英語になり、次の起動でも英語"""
    app = make_app("1251", frames=3, norom=True)
    assert "キーの説明" in _view_labels(app)
    item = next(it for it in app.popup_items("view") if it.label == "English")
    assert item.action is not None
    item.action()
    assert i18n.language() == "en"
    labels = _view_labels(app)
    assert "Key help" in labels and "日本語" in labels
    assert app.bar_buttons()[0].label == "Programs"
    app.frame()
    # 覚えた言語は、ロケールより先、SC61BOX_LANGより後
    monkeypatch.delenv("SC61BOX_LANG")
    monkeypatch.setenv("LANG", "ja_JP.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    i18n.set_language("ja")
    make_app("1251", frames=1, norom=True)
    assert i18n.language() == "en"
    monkeypatch.setenv("SC61BOX_LANG", "ja")
    make_app("1251", frames=1, norom=True)
    assert i18n.language() == "ja"
    make_app("1251", frames=1, norom=True, lang="en")
    assert i18n.language() == "en"


def test_kept_messages_follow_language(tmp_path):
    """止まった理由、注意、代替ROMルーチンの知らせのように覚えておいてあとで出す文は、言語を
    切り替えると新しい言語で出る"""
    from sc61box import routines
    from sc61box.i18n import Joined, Text

    app = make_app("1251", frames=3, norom=True)
    b = app.bench
    b.pause()
    app.warning = Text("app.routine_rom_address_not", addr=0x4000)
    folder = tmp_path / "routines"
    folder.mkdir()
    (folder / "dup.py").write_text(
        "from sc61box.routines import routine\n"
        "@routine('1261', 0x5F00, 'BA2X')\n"
        "def f(m):\n"
        "    return 0\n",
        encoding="utf-8",
    )
    try:
        routines.load_user(str(folder), force=True)
        assert b.reason == "一時停止しました"
        warning = app.warning
        app.set_language("en")
        assert b.reason == "Paused"
        assert app.warning != warning
        assert app.warning == tr("app.routine_rom_address_not", addr=0x4000)
        why = "the name BA2X is used by the built-in at 0225"
        assert routines.notices() == [f"dup.py: BA2X (5F00) is not used: {why}"]
        assert [w for _r, w in routines.listing("1261") if w] == [why]
        assert str(Joined(["A", "B"])) == "A, B" and f"{Text('common.builtin'):>10}" == "  built-in"
    finally:
        i18n.set_language("ja")
        routines.load_user(str(tmp_path / "none"), force=True)
    app.close()


def test_pad_source_follows_language():
    """割り当ての出どころ(「初期設定」など)も、言語を切り替えると新しい言語で出る。状態の
    ファイルには訳した文ではなくIDで書き、前の版の状態(訳した文)も読める"""
    import json

    app = make_app("1251", frames=3, norom=True, lang="ja")
    assert app.pad_map.source == "初期設定"
    app.set_language("en")
    assert app.pad_map.source == "factory mapping"
    app.save_state()
    with open(app.state_file, encoding="utf-8") as f:
        state = json.load(f)
    assert state["app"]["pad"]["source"] == {"id": "app.factory_mapping", "args": {}}
    i18n.set_language("ja")
    app.load_state()
    assert app.pad_map.source == "初期設定"
    old, dirty = app._saved_pad_map({"keys": {}, "source": "前の版"}, None)
    assert old.source == "前の版" and not dirty
    broken, _ = app._saved_pad_map({"keys": {}, "source": {"id": "app.wrote_bytes"}}, None)
    assert broken.source == ""
    # 壊れた出どころは読むときに断る(割り当ての画面を描くときになって例外にしない)
    app.toggle_pad_panel(True)
    for bad in (
        {"id": [], "args": {}},  # IDが文字列でない
        {"id": "app.saved", "args": {"other": "x"}},  # 差し込みの名前が違う
        {"id": "app.saved", "args": {}},  # 差し込みが足りない
        {"id": "app.saved", "args": {"name": "x", "more": 1}},  # 多い
        {"id": "app.saved", "args": {"name": ["x"]}},  # 値が文字列か数でない
        {"id": "app.saved", "args": []},
    ):
        pad_map, _ = app._saved_pad_map({"keys": {}, "source": bad}, None)
        assert pad_map.source == "", bad
        app.set_pad_map(pad_map)
        app.frame()
    good, _ = app._saved_pad_map(
        {"keys": {}, "source": {"id": "app.saved", "args": {"name": "game"}}}, None
    )
    assert "game" in good.source
    app.close()


def test_switch_mark_in_english():
    """スイッチの位置の●は、英語の画面でも、いまのスイッチの項目につく"""
    from sc61box.overlay import Popup

    app = make_app("1251", frames=1, norom=True, lang="en")
    app.popup = Popup((10, 10), "machine")
    labels = [it.label for it in app.popup_items()]
    assert app.popup_mark() in labels
    app.popup = Popup((10, 10), "speed")
    assert app.popup_mark() in [it.label for it in app.popup_items()]


def test_start_field_message_in_english():
    """開始番地の欄に4桁打つと、英語の画面でも済んだメッセージ(緑)になる"""
    app = make_app("1251", frames=1, norom=True, lang="en")
    b, v = app.bench, app.bench_view
    b.start_buf = ""
    for ch in "C010":
        ev = types.SimpleNamespace(key=0, unicode=ch, mod=0)
        app.bench_key(ev)
    assert b.start == 0xC010
    assert v.flash == "Start address set to C010" and v.flash_ok


def test_export_hex_in_english_reads_back(tmp_path, monkeypatch):
    """英語の画面で書き出した.hexも、読み込める"""
    from sc61box import programs

    monkeypatch.setenv("SC61BOX_PROGRAMS", str(tmp_path))
    app = make_app("1251", frames=1, norom=True, lang="en")
    app.bench.paste("C000 02 7F 10 F8 00 52 37")
    app.bench_export()
    assert app.bench_view.flash.startswith("Exported dump-")
    (path,) = glob.glob(str(tmp_path / "pc1251" / "dump-*.hex"))
    text = open(path, encoding="utf-8").read()
    assert text.startswith("; C000-C006 (exported from the machine-code workbench)\n")
    prog = programs.load_program(path)
    assert not prog.errors
    assert prog.blocks == [(0xC000, b"\x02\x7f"), (0xC002, b"\x10\xf8\x00"), (0xC005, b"\x52"),
                           (0xC006, b"\x37")]  # fmt: skip
    assert prog.run == "CALL &C000"


def test_cli_help_follows_language():
    from typer.testing import CliRunner

    from sc61box.app import make_cli

    i18n.set_language("en")
    result = CliRunner().invoke(make_cli(), ["--help"])
    assert result.exit_code == 0
    assert "Window scale" in result.output and "--lang" in result.output
    i18n.set_language("ja")
    result = CliRunner().invoke(make_cli(), ["--help"])
    assert "拡大率" in result.output
    result = CliRunner().invoke(make_cli(), ["--lang", "fr", "--fresh"])
    assert result.exit_code == 2


def test_cli_reads_lang_before_typer(monkeypatch):
    from sc61box import app

    assert app._asked_language(["--scale", "2", "--lang", "en"]) == "en"
    assert app._asked_language(["--lang=ja"]) == "ja"
    assert app._asked_language(["prog.bas"]) is None


def _draw_everything(app) -> None:
    """メニュー、キーの説明、プログラムの一覧、紙、作業欄を、英語で描いてみる"""
    from sc61box.overlay import Popup

    app.frame()
    for code in b"TEST\r":
        app.m.printer.put(code)
    app.frame()
    for kind in ("program", "machine", "view", "speed", "rec", "context", "paper"):
        app.popup = Popup((20, 20), kind)
        app.frame()
    app.popup = None
    app.help = 5
    app.frame()
    app.help = 0
    app.open_menu()
    app.frame()
    app.menu = None
    if not app.norom:
        app.toggle_pane(True)
    app.bench_menu((app.body_size[0] + 60, 300))
    app.frame()
    app.popup = None
    for i in range(4):
        app.bench_view.hover = i
        app.frame()


@pytest.mark.parametrize(
    "model,norom,have",
    [
        ("1251", True, True),
        ("1251", False, HAVE_ROM),
        ("1245", False, HAVE_ROM_1245),
        ("1261", False, HAVE_ROM_1260),
        ("1350", False, HAVE_ROM_1350),
    ],
)
def test_english_screens(model, norom, have, tmp_path, monkeypatch):
    if not have:
        pytest.skip(f"PC-{model}のROMがない")
    monkeypatch.setenv("SC61BOX_PROGRAMS", str(tmp_path))
    app = make_app(model, frames=5, norom=norom, lang="en")
    assert i18n.language() == "en"
    assert app.bar_buttons()[0].label == "Programs"
    _draw_everything(app)
    for kind in ("program", "machine", "view", "speed", "rec", "context", "paper", "bench"):
        for it in app.popup_items(kind):
            assert not JAPANESE.search(it.label + it.note) or it.label == "日本語", it


def test_cli_language_from_environment():
    """コマンドの説明は、SC61BOX_LANGで英語になる(ロケールによらない)"""
    env = {**os.environ, "SC61BOX_LANG": "en", "PYTHONIOENCODING": "utf-8"}
    code = "import sys; sys.argv = ['pc1251', '--help']; from sc61box.app import cli; cli()"
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        encoding="utf-8",
        env=env,
        cwd=os.path.join(SRC, ".."),
        timeout=60,
    )
    assert "Window scale" in out.stdout, out.stderr


@pytest.mark.skipif(not HAVE_ROM, reason="ROMがない")
def test_english_bar_fits_narrow_window():
    """英語の操作欄も、狭いウィンドウでは短い表示で収まる(実行の一時停止は省かない)"""
    app = make_app(scale=0.35, lang="en")
    app.recorder = type("R", (), {"seconds": 75.0})()
    app.rec_paused = True
    app.halted = True
    app.frame()
    assert all(r.right <= app.window.get_width() for r in app.bar.rects)
    labels = [b[0] for b, r in zip(app.bar.buttons, app.bar.rects, strict=True) if r.width]
    assert "Resume" in labels and "Machine" in labels
    app.recorder = None
    app.close()


def test_undo_names_follow_language():
    """取り消しの説明は、書き込んだあとで言語を切り替えても、切り替えた言語で出す"""
    app = make_app(scale=0.5, frames=2, norom=True)
    b = app.bench
    b.paste("C000 02 7F 37")
    i18n.set_language("en")
    assert "貼り付け" not in b.undo_note()[0]
    assert "貼り付け" not in b.undo()
    i18n.set_language("ja")
    assert b.redo() == "貼り付け(3バイト)をやり直しました"
    app.close()


def test_windows_language():
    """Windowsでロケールがなければ、表示の言語を見る。読めなければja"""
    choose = i18n.choose
    assert choose(environ={}, platform="win32", win=lambda: "en") == "en"
    assert choose(environ={}, platform="win32", win=lambda: None) == "ja"
    assert choose(environ={"LANG": "ja_JP"}, platform="win32", win=lambda: "en") == "ja"
    assert i18n.windows_language() in (None, "ja", "en")

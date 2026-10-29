"""pytestで動かすときの設定。ROMやPC-インタープリタのダンプがなければ、それを使う試験を飛ばす"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 試験は日本語の画面で確かめる(動かすパソコンのロケールによらない)
os.environ["SC61BOX_LANG"] = "ja"

from sc61box.machine import RomNotFound, find_rom  # noqa: E402


def _have(model: str) -> bool:
    try:
        find_rom(f"cpu-{model}.rom")
        find_rom(f"bas-{model}.rom")
        return True
    except RomNotFound:
        return False


HAVE_ROM = _have("1251")
HAVE_ROM_1245 = _have("1245")
HAVE_ROM_1260 = _have("1260")
HAVE_ROM_1350 = _have("1350")

# ROMがなくても動く試験(「モジュール::名前」。同じ名前でもROMの要る試験がほかのモジュールにある)
NO_ROM_NEEDED = {
    "test_smoke::test_switch_knob_matches_label",
    "test_smoke::test_version",
    "test_smoke::test_lcd_ram_mirrors",
    "test_smoke::test_sound_queue_keeps_up",
}


@pytest.fixture(autouse=True)
def _own_state_dir(tmp_path_factory, monkeypatch):
    """RAM、どこでもセーブ、作業欄の見え方などの置き場所と、プログラムの置き場所を、試験ごとに
    空のフォルダにする(使う人の~/.sc61boxにあるものに試験の結果が左右されず、試験がそこへ
    書くこともない)"""
    from sc61box import app, paths

    monkeypatch.setattr(app, "STATE_DIR", str(tmp_path_factory.mktemp("pc1251")))
    # 起動のときのデータのフォルダの引っ越しも、使う人のホームには触れない
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setattr(paths, "DATA_DIR", str(home / ".sc61box"))
    monkeypatch.setattr(
        paths, "OLD_DATA_DIRS", (str(home / ".sc61860player"), str(home / ".pc1251"))
    )
    monkeypatch.setenv("SC61BOX_PROGRAMS", str(tmp_path_factory.mktemp("programs")))


@pytest.fixture(autouse=True)
def _japanese():
    """画面の言語を、試験ごとに日本語に戻す(英語に切り替える試験のあとに残さない)"""
    from sc61box import i18n

    i18n.set_language("ja")
    yield
    i18n.set_language("ja")


def pytest_collection_modifyitems(config, items):
    from test_basic import DUMP

    for item in items:
        if (
            item.module.__name__ in ("test_cpu", "test_workbench", "test_i18n", "test_paths")
            or f"{item.module.__name__}::{item.name}" in NO_ROM_NEEDED
        ):
            continue
        if item.module.__name__ == "test_pc1261":
            if not HAVE_ROM_1260:
                item.add_marker(
                    pytest.mark.skip(reason="PC-1260/1261/1262のROMがない(rom/cpu-1260.romなど)")
                )
            continue
        if item.module.__name__ == "test_pc1350":
            if not HAVE_ROM_1350:
                item.add_marker(pytest.mark.skip(reason="PC-1350のROMがない(rom/cpu-1350.romなど)"))
            continue
        if item.module.__name__ == "test_pc1245":
            if not HAVE_ROM_1245:
                item.add_marker(pytest.mark.skip(reason="PC-1245のROMがない(rom/cpu-1245.romなど)"))
            elif "interpreter" in item.name and not os.path.exists(DUMP):
                item.add_marker(pytest.mark.skip(reason="PC-インタープリタのダンプがない"))
            continue
        if not HAVE_ROM:
            item.add_marker(pytest.mark.skip(reason="ROMがない(実機から読み出してrom/に置く)"))
        elif item.name == "test_pc_interpreter" and not os.path.exists(DUMP):
            item.add_marker(pytest.mark.skip(reason="PC-インタープリタのダンプがない"))

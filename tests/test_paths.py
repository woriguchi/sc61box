"""データのフォルダと環境変数の名前(前の名前のpc1251-emulatorのころのものからの引き継ぎ)"""

import os

from helpers import make_app

from sc61box import i18n, paths, programs


def test_migrate_moves_old_folder():
    """前のフォルダ~/.pc1251があり新しいフォルダがなければ、中身ごと新しい名前に移し、前の
    名前には新しいフォルダへのリンクを置く。前の場所を指すパスはそのまま読み書きできる"""
    old, new = paths.OLD_DATA_DIRS[1], paths.DATA_DIR  # ~/.pc1251
    os.makedirs(os.path.join(old, "programs", "mine"))
    with open(os.path.join(old, "ram.bin"), "wb") as f:
        f.write(b"\x01\x02")
    assert paths.data_dir() == old  # 移す前は前のフォルダを使う
    assert paths.migrate()
    assert os.path.islink(old) and not os.path.islink(new)
    assert os.path.isdir(os.path.join(new, "programs", "mine"))
    assert open(os.path.join(old, "ram.bin"), "rb").read() == b"\x01\x02"  # 前のパスで読める
    with open(os.path.join(old, "programs", "mine", "a.bas"), "w") as f:  # 前のパスで書ける
        f.write("10 END\n")
    assert os.path.isfile(os.path.join(new, "programs", "mine", "a.bas"))
    assert paths.data_dir() == new
    assert not paths.migrate()  # 2回目は何もしない


def test_migrate_keeps_old_folder_without_link(monkeypatch):
    """リンクを作れないとき(Windowsで権限がないときなど)は、移したものを戻し、前のフォルダを
    使い続ける"""

    def no_link(*_a, **_k):
        raise OSError("symlink not allowed")

    monkeypatch.setattr(os, "symlink", no_link)
    old = paths.OLD_DATA_DIRS[1]
    os.makedirs(old)
    assert not paths.migrate()
    assert os.path.isdir(old) and not os.path.lexists(paths.DATA_DIR)
    assert paths.data_dir() == old


def test_migrate_keeps_both_when_new_exists():
    """新しいフォルダがもうあれば、前のフォルダには触れない"""
    os.makedirs(paths.OLD_DATA_DIRS[1])
    os.makedirs(paths.DATA_DIR)
    assert not paths.migrate()
    assert os.path.isdir(paths.OLD_DATA_DIRS[1]) and paths.data_dir() == paths.DATA_DIR


def test_migrate_prefers_newer_old_folder():
    """~/.sc61860player(公開前の名前)と~/.pc1251の両方があれば、新しいほうを移す"""
    newer, older = paths.OLD_DATA_DIRS
    os.makedirs(newer)
    os.makedirs(older)
    assert paths.data_dir() == newer
    assert paths.migrate()
    assert os.path.islink(newer) and os.path.isdir(older) and not os.path.islink(older)
    assert paths.data_dir() == paths.DATA_DIR


def test_migrate_without_old_folder():
    assert not paths.migrate()
    assert paths.data_dir() == paths.DATA_DIR


def test_old_environment_names(monkeypatch):
    """環境変数は新しい名前を先に見て、なければ前の名前(SC61860PLAYER_、PC1251_)を読む"""
    assert paths.env("ROM", {"PC1251_ROM": "/a"}) == "/a"
    assert paths.env("ROM", {"PC1251_ROM": "/a", "SC61860PLAYER_ROM": "/b"}) == "/b"
    both = {"PC1251_ROM": "/a", "SC61860PLAYER_ROM": "/b", "SC61BOX_ROM": "/c"}
    assert paths.env("ROM", both) == "/c"
    assert paths.env("ROM", {}) == ""
    linux = {"platform": "linux", "mac": lambda: None}
    assert i18n.choose(environ={"PC1251_LANG": "en"}, **linux) == "en"
    assert i18n.choose(environ={"SC61860PLAYER_LANG": "en"}, **linux) == "en"
    assert i18n.choose(environ={"SC61860PLAYER_LANG": "en", "PC1251_LANG": "ja"}, **linux) == "en"
    assert i18n.choose(environ={"SC61BOX_LANG": "ja", "SC61860PLAYER_LANG": "en"}, **linux) == "ja"
    monkeypatch.delenv("SC61BOX_PROGRAMS", raising=False)
    monkeypatch.setenv("PC1251_PROGRAMS", "/tmp/old-programs")
    assert programs.library_dirs()[0] == os.path.abspath("/tmp/old-programs")
    monkeypatch.delenv("PC1251_PROGRAMS")
    assert os.path.join(paths.data_dir(), "programs") in programs.library_dirs()


def test_moved_message():
    """フォルダを移したときは、画面の下に1回知らせる"""
    app = make_app(scale=0.5, frames=1, norom=True, moved_data="~/.sc61860player")
    assert "~/.sc61box" in app.status and "~/.sc61860player" in app.status
    app.close()

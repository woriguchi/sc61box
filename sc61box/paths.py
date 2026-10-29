"""データを置くフォルダと、環境変数の名前

データ(RAM、どこでもセーブ、置き場所のプログラム、表示の設定など)は~/.sc61boxに置く。
前の名前のころの~/.pc1251(pc1251-emulator)や~/.sc61860player(公開前の名前)があり、新しい
フォルダがまだなければ、起動したときにそのまま新しい名前に移し、前の名前には新しいフォルダへの
リンクを置く(migrate)。前の場所を指す引数や環境変数、利用者のスクリプトは、リンクを通って
そのまま使える。リンクを作れないとき(Windowsで権限がないときなど)は移さずに、前のフォルダを
使い続ける。環境変数はSC61BOX_で始まる名前を使い、前の名前のSC61860PLAYER_、PC1251_で始まる
ものも読む。
"""

import os
from collections.abc import Mapping

DATA_DIR = os.path.expanduser("~/.sc61box")
# 前の名前のころのデータのフォルダ(新しいほうから順に)
OLD_DATA_DIRS = (os.path.expanduser("~/.sc61860player"), os.path.expanduser("~/.pc1251"))
ENV_PREFIXES = ("SC61BOX_", "SC61860PLAYER_", "PC1251_")


def old_data_dir() -> str | None:
    """前の名前のフォルダのうち、残っているもの(リンクではなく本物のフォルダ)。なければNone"""
    for d in OLD_DATA_DIRS:
        if os.path.isdir(d) and not os.path.islink(d):
            return d
    return None


def data_dir() -> str:
    """データのフォルダ。新しいフォルダがなく、前のフォルダがあれば(移せなかったときなど)
    前のフォルダを使う"""
    old = old_data_dir()
    if not os.path.isdir(DATA_DIR) and old is not None:
        return old
    return DATA_DIR


def migrate() -> bool:
    """前の名前のフォルダを新しい名前~/.sc61boxに移し、前の名前には新しいフォルダへのリンクを
    置く。移したらTrue。新しいフォルダがもうあるとき、前のフォルダがないとき、移せないときや
    リンクを作れないとき(移したものは元に戻す)は何もしない"""
    old = old_data_dir()
    if os.path.lexists(DATA_DIR) or old is None:
        return False
    try:
        os.rename(old, DATA_DIR)
    except OSError:
        return False
    try:
        # 同じフォルダの中のリンクなので、相手は名前だけで指す(ホームの場所が変わっても通る)
        os.symlink(os.path.basename(DATA_DIR), old, target_is_directory=True)
    except OSError:
        try:
            os.rename(DATA_DIR, old)
        except OSError:
            pass  # 戻せなければ新しいフォルダを使う(data_dirが選ぶ)
        return False
    return True


def env(name: str, environ: Mapping[str, str] | None = None) -> str:
    """環境変数SC61BOX_name。なければ前の名前のSC61860PLAYER_name、PC1251_name。どれもなければ空"""
    e = os.environ if environ is None else environ
    for prefix in ENV_PREFIXES:
        value = e.get(prefix + name)
        if value:
            return value
    return ""


def unused_file(folder: str, stem: str, ext: str) -> str:
    """folderの中に、まだないファイル(stem+ext、あればstem-2+extなど)を空で作って名前を返す。
    作るのと確かめるのを1度に行うので、ほかのエミュレータと同じ名前を取り合わない"""
    path, n = os.path.join(folder, stem + ext), 2
    while True:
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return path
        except FileExistsError:
            path = os.path.join(folder, f"{stem}-{n}{ext}")
            n += 1

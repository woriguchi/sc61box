"""パソコンのOSとブラウザで違う、外とのやりとり(クリップボード、フォルダを開くこと、Macかどうか、
ブラウザでのファイルの受け渡し)

パソコンではpygame.scrapとOSのコマンドを使う。ブラウザ(Pyodide)ではweb.pyに任せる。
"""

import subprocess
import sys
from collections.abc import Callable

import pygame

WEB = sys.platform == "emscripten"


def _mac() -> bool:
    if WEB:
        import js  # pyrefly: ignore[missing-import]

        return "Mac" in str(js.navigator.platform)
    return sys.platform == "darwin"


MAC = _mac()  # ショートカットを⌘で書くか(ブラウザでは、ブラウザを動かしているOSで決める)


def copy_text(text: str) -> None:
    if WEB:
        from . import web

        web.copy_text(text)
        return
    try:
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        pygame.scrap.put(pygame.SCRAP_TEXT, text.encode("utf-8"))
        return
    except (pygame.error, NotImplementedError):
        pass
    cmds = {"darwin": ["pbcopy"], "win32": ["clip"]}
    cmd = cmds.get(sys.platform, ["xclip", "-selection", "clipboard"])
    try:
        subprocess.run(cmd, input=text, text=True, check=False)
    except OSError:
        pass


def paste_text() -> str:
    """クリップボードの文字(パソコンで。ブラウザではすぐには読めないので、read_clipboard)"""
    text = ""
    try:
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        raw = pygame.scrap.get(pygame.SCRAP_TEXT)
        if raw:
            text = raw.decode("utf-8", "ignore").rstrip("\x00")
    except (pygame.error, NotImplementedError):
        pass
    if not text:
        try:
            text = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
        except OSError:
            text = ""
    return text


def read_clipboard(use: Callable[[str | None], None]) -> None:
    """ブラウザで、クリップボードの文字をuseに渡す(あとのフレームになることがある)。
    読めなければNoneを渡す"""
    from . import web

    web.read_clipboard(use)


def reveal(path: str) -> None:
    """フォルダをFinder(など)で開く。ブラウザでは開くフォルダがないので何もしない"""
    if WEB:
        return
    cmd = {"darwin": ["open"], "win32": ["explorer"]}.get(sys.platform, ["xdg-open"])
    try:
        subprocess.Popen(cmd + [path])
    except OSError:
        pass


def choose_files() -> None:
    """ブラウザで、読み込むファイルを選んでもらう(選んだファイルはweb.receivedが開く)"""
    from . import web

    web.choose_files()


def deliver(path: str) -> None:
    """書いたファイルを利用者に渡す。ブラウザではダウンロードする。パソコンではファイルが
    フォルダにあるので何もしない"""
    if WEB:
        from . import web

        web.download(path)


def share_program(text: str, model: str, card: int, done: Callable[[bool, int], None]) -> None:
    """ブラウザで、BASICのプログラムtextを入れたリンクを作ってコピーする。doneには、コピー
    できたかと、リンクの字数を渡す(あとのフレームになることがある)"""
    from . import web

    web.share_program(text, model, card, done)


def keep_offline() -> None:
    """ブラウザで、オフラインで使うためのファイルの保存を試し直す(結果はあとで知らせる)"""
    from . import web

    web.keep_offline()


def restart(removed: list[str], failed: Callable[[], None]) -> None:
    """ブラウザで、消したファイル(removed)をブラウザの保存にも反映し、ページを読み直して
    初めから動かす。反映できなければ読み直さず、failedを呼ぶ(あとのフレームになる)"""
    from . import web

    web.restart(removed, failed)

"""ブラウザ(Pyodide)で動かすときの、ページとのやりとり

ページ(web/index.html)は、globalThis.sc61boxにクリップボード・音・保存・ファイルの受け渡しの
関数を置き、データのフォルダ(~/.sc61box)をIndexedDBにつないでからrun()を呼ぶ。ブラウザでは
ROMを使わない。
"""

import asyncio
import base64
import os
import posixpath
import tempfile
import time
import urllib.parse
import zlib
from collections.abc import Callable

import js  # pyrefly: ignore[missing-import]
from pyodide.ffi import (  # pyrefly: ignore[missing-import]
    JsException,
    create_once_callable,
    create_proxy,
    to_js,
)

from . import benchview, overlay, programs
from .app import App, Options, bench_file
from .audio import TARGET, QueueOutput
from .i18n import tr

# 同梱のフォント(web/build.pyがapp.zipのfontsに入れる)
FONTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")

# ⌘V・Ctrl+Vで、ページのpasteのイベントが渡した文字と時刻。キーのイベントより先に届くので、
# そのキーで貼り付けるときに使う。古いものは使わない(メニューからはクリップボードを読みに行く)
pasted: tuple[str, float] | None = None
PASTE_FRESH = 1.0  # 秒


def paste(text: str) -> None:
    global pasted
    pasted = (text, time.monotonic())


def read_clipboard(use) -> None:
    """クリップボードの文字をuseに渡す。読めなければNone(host.read_clipboard)"""
    global pasted
    fresh, pasted = pasted, None
    if fresh is not None and time.monotonic() - fresh[1] < PASTE_FRESH:
        use(fresh[0])
    else:
        js.sc61box.readClipboard(create_once_callable(use))


def copy_text(text: str) -> None:
    js.sc61box.copyText(text)


def choose_files() -> None:
    js.sc61box.chooseFiles()


def download(path: str) -> None:
    with open(path, "rb") as f:
        data = f.read()
    js.sc61box.download(os.path.basename(path), to_js(data))


def received(app: App, files: list[tuple[str, bytes]], run: bool = False) -> None:
    """ページで選んだか、ページに落としたファイルを置いて開く。プログラムはプログラムのフォルダに
    置き(一覧にも出る)、テープの音は一時的なフォルダに置く。.basと.hexを一緒に選んだら.basを
    開く(同じ名前の.hexも一緒に読み込む)。runなら、プログラムは実行し、テープはCLOADして実行する"""
    paths = []
    for name, data in files:
        name = os.path.basename(name)
        tape = name.lower().endswith(".wav")
        path = os.path.join(tempfile.gettempdir() if tape else programs.user_dir(), name)
        try:
            with open(path, "wb") as f:
                f.write(data)
        except OSError:
            app.say(tr("app.cannot_read_name", name=name), 4)
            continue
        paths.append(path)
    if not paths:
        return
    path = next((p for p in paths if p.lower().endswith(".bas")), paths[0])
    if run and path.lower().endswith(programs.EXTS):
        app.open_program(programs.load_program(path), run=True)
    elif run and path.lower().endswith(".wav"):
        if app.insert_tape(path):  # 読めなければ、前にセットしていたテープを読ませない
            cload_and_run(app)
    else:
        app.open_file(path)
    js.sc61box.sync()


def cload_and_run(app: App) -> None:
    """セットしたテープをCLOADで読み、読み終えたらRUNを打つ。読み終えたかは、ROMなしのBASICが
    CLOADを終えたときに知らせる(m.on_cload)。エラーやBRKで止まったら、RUNは打たない"""
    t = app.typer

    def done(loaded: bool) -> None:
        if loaded:
            t.add_text("RUN\n")

    def listen() -> None:
        app.m.on_cload = done

    t.add_mode("RUN")
    t.add_call(listen)
    t.add_text("CLOAD\n")


# リンク(ページのURLの?load=)で読み込めるファイルと、大きさの上限(バイト)
LINK_LIMITS = {".bas": 1 << 20, ".hex": 1 << 20, ".wav": 32 << 20}


def _split(url: str) -> urllib.parse.SplitResult | None:
    """http・httpsのURLを分ける。URLとして読めない(角括弧が閉じていないなど)か、サイトの
    ないものはNone"""
    try:
        parts = urllib.parse.urlsplit(url)
        site = parts.hostname
    except ValueError:
        return None
    return parts if site and parts.scheme in ("http", "https") else None


def offer_link(app: App, url: str, run: bool) -> None:
    """リンクで渡されたファイルを、読み込むか確かめる。読み込めるのはhttp・httpsの、
    LINK_LIMITSの種類のファイルだけ(名前はURLの最後の部分だけを使う)"""
    parts = _split(url)
    if parts is None or parts.hostname is None:
        app.say(tr("app.web_bad_link"), 6)
        return
    name = posixpath.basename(urllib.parse.unquote(parts.path))
    ext = os.path.splitext(name)[1].lower()
    if ext not in LINK_LIMITS:
        app.say(tr("app.web_link_types"), 6)
        return
    replaces = ext != ".wav" or run  # テープはセットするだけなら、RAMを変えない
    app.ask_link(
        tr("app.web_load_link", site=parts.hostname, name=name),
        replaces,
        lambda: asyncio.ensure_future(fetch_link(app, url, run)),
    )


# プログラムを入れたリンク(#bas=)。BASICの字をzlibで縮めて、URLに使える形のbase64にする。
# 開いたときにほどく大きさの上限(バイト)
SHARED_LIMIT = 1 << 20
SHARED_NAME = "link.bas"  # 読み込んだプログラムを置くファイル(次のリンクで置き換える)


def pack(text: str) -> str:
    return base64.urlsafe_b64encode(zlib.compress(text.encode("utf-8"), 9)).decode().rstrip("=")


def unpack(data: str) -> str:
    """packの逆。読めないか、ほどくとSHARED_LIMITを超えればValueError"""
    try:
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
        z = zlib.decompressobj()
        text = z.decompress(raw, SHARED_LIMIT)
        if z.unconsumed_tail or not z.eof:
            raise ValueError("too large or cut")
        return text.decode("utf-8")
    except zlib.error as e:
        raise ValueError(e) from e


def share_program(text: str, model: str, card: int, done: Callable[[bool, int], None]) -> None:
    """プログラムを入れたリンク(このページのアドレス?model=…#run&bas=…)を作り、ページに
    コピーしてもらう。コピーできなければ、ページは自分のアドレスをそのリンクにする"""
    query = f"?model={model}" + (f"&card={card}" if card else "")
    url = f"{js.location.origin}{js.location.pathname}{query}#run&bas={pack(text)}"
    js.sc61box.shareLink(url, create_once_callable(lambda copied: done(bool(copied), len(url))))


def offline_state(app: App, state: str) -> None:
    """オフラインで使うためのファイルをブラウザに持てたか(ページのsw.jsの登録から)。初めて
    持てたとき("ready")と、持てなかったとき("failed")に知らせる"""
    app.offline_failed = state == "failed"
    if state == "ready":
        app.say_also(tr("app.web_offline_ready"), 5)
    elif state == "failed":
        app.say_also(tr("app.web_offline_failed"), 10)


def keep_offline() -> None:
    js.sc61box.keepOffline()


def dropped_link(app: App, url: str) -> None:
    """ページに落としたリンク。このページを指すリンク(?load=や#bas=を付けたもの)なら、それを
    開いたときと同じに、ほかはそのファイルのリンクとして扱う"""
    parts = _split(url)
    here = (str(js.location.host), str(js.location.pathname))
    if parts is not None and (parts.netloc, parts.path) == here:
        query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
        fragment = urllib.parse.parse_qs(parts.fragment, keep_blank_values=True)
        model = query.get("model", ["1251"])[0]
        card = query.get("card", ["0"])[0] if model == "1350" else "0"
        if (model, card) != (app.m.model.name, str(app.m.card)):
            # 機種かRAMカードの違うリンクは、RAMを保存してから、そのリンクを開き直す
            js.sc61box.navigate(url)
            return
        if "load" in query:
            offer_link(app, query["load"][0], "run" in query)
            return
        if "bas" in fragment:
            offer_shared(app, fragment["bas"][0], "run" in fragment)
            return
    offer_link(app, url, run=False)


def offer_shared(app: App, data: str, run: bool) -> None:
    """リンクに入っていたプログラムを、読み込むか確かめてから開く(プログラムのフォルダの
    SHARED_NAMEに置く)"""
    try:
        text = unpack(data)
    except ValueError:
        app.say(tr("app.web_bad_shared"), 6)
        return
    app.ask_link(
        tr("app.web_load_shared"),
        True,
        lambda: received(app, [(SHARED_NAME, text.encode("utf-8"))], run),
    )


async def fetch_link(app: App, url: str, run: bool) -> None:
    """リンクのファイルを取ってきて、ページで選んだファイルと同じように開く。取れない(相手の
    サイトがほかのサイトからの読み込みを許していない、など)か、大きすぎれば知らせる"""
    from pyodide.http import pyfetch  # pyrefly: ignore[missing-import]

    name = posixpath.basename(urllib.parse.unquote(urllib.parse.urlsplit(url).path))
    limit = LINK_LIMITS[os.path.splitext(name)[1].lower()]
    app.say(tr("app.web_fetching_link", name=name), 30)
    try:
        response = await pyfetch(url)
        if not response.ok:
            raise OSError(response.status)
        size = response.headers.get("content-length")
        data = b"" if size is not None and int(size) > limit else await response.bytes()
    except (OSError, ValueError, JsException):
        app.say(tr("app.web_cannot_fetch", name=name), 8)
        return
    if not data or len(data) > limit:
        app.say(tr("app.web_link_too_large", name=name), 6)
        return
    app.say("", 0)
    received(app, [(name, data)], run)


class WebAudio(QueueOutput):
    """Web Audioに積む出力先。ブラウザは利用者が操作するまで音を出さないので、それまでは
    たまり具合を目標どおりと見なして、積まずに捨てる"""

    def __init__(self) -> None:
        super().__init__()
        if not js.sc61box.audio.open():
            raise OSError("Web Audio")

    def queued(self) -> int:
        n = int(js.sc61box.audio.queued())
        return TARGET if n < 0 else n

    def append(self, pcm: bytes) -> None:
        js.sc61box.audio.push(to_js(pcm))

    def push(self, pcm: bytes) -> None:
        if int(js.sc61box.audio.queued()) < 0:
            return
        super().push(pcm)

    def clear(self) -> None:
        js.sc61box.audio.clear()
        super().clear()

    def close(self) -> None:
        js.sc61box.audio.close()


def save(app: App) -> list[str]:
    """RAMを保存して、書いたファイルを返す(ページがIndexedDBに書く前に呼ぶ。ページは
    書き終わるまで、返したファイルの写しをlocalStorageに持つ)"""
    if not app.save_ram:
        return []
    app.store_ram(running=True)
    return [app.ram_file, bench_file(app.ram_file)]


def restart(removed: list[str], failed: Callable[[], None]) -> None:
    js.sc61box.restart(to_js(removed), create_once_callable(failed))


def body_only(app: App, on: bool, w: int, h: int) -> None:
    """本体だけにする・元に戻す。ページは見出しを出し入れするので、新しい大きさも受ける"""
    app.toggle_body_only(on)
    app.fit_page(w, h)


def context_menu(app: App) -> None:
    """本体だけのときの「メニュー」のボタン。右クリックと同じメニューを右上に出す(出していれば
    しまう)"""
    if app.popup is not None:
        app.popup = None
        return
    app.open_popup((app.window.get_width(), 0))


async def run(model: str, lang: str | None, card: int = 0) -> None:
    """ROMなしの本体を開いて動かす(cardはPC-1350のRAMカードのKB)"""
    overlay.HELP_FONTS.insert(0, os.path.join(FONTS, "NotoSansJP-Regular.ttf"))
    benchview.MONO_FONTS.insert(0, os.path.join(FONTS, "SourceCodePro-Regular.otf"))
    app = App(Options(model=model, card=card, norom=True, lang=lang))

    def files(items) -> None:
        """ページが渡すファイル([名前, Uint8Array]の並び)"""
        received(app, [(str(name), data.to_bytes()) for name, data in items])

    app.fit_page(*[int(n) for n in js.sc61box.pageSize()])
    js.sc61box.onResize = create_proxy(lambda w, h: app.fit_page(int(w), int(h)))
    js.sc61box.onSave = create_proxy(lambda: to_js(save(app)))
    js.sc61box.onSaveFailed = create_proxy(lambda: app.say(tr("app.web_cannot_save"), 8))
    js.sc61box.onPaste = create_proxy(paste)
    js.sc61box.onFiles = create_proxy(files)
    js.sc61box.onBodyOnly = create_proxy(lambda on, w, h: body_only(app, bool(on), int(w), int(h)))
    js.sc61box.onMenu = create_proxy(lambda: context_menu(app))
    js.sc61box.onLink = create_proxy(lambda url: dropped_link(app, str(url)))
    js.sc61box.onOffline = create_proxy(lambda state: offline_state(app, str(state)))
    if js.sc61box.offline:  # Pythonが動き出す前に、もう分かっていた
        offline_state(app, str(js.sc61box.offline))
    link = js.sc61box.link
    if link and link.url:  # リンクで渡されたファイル
        offer_link(app, str(link.url), bool(link.run))
    elif link and link.bas:  # リンクに入っていたプログラム
        offer_shared(app, str(link.bas), bool(link.run))
    if js.sc61box.bare:  # 動き出す前に選ばれていた
        body_only(app, True, *[int(n) for n in js.sc61box.pageSize()])
    await app.run_async()

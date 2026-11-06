"""画面に出す文の言語。文はmessages.MESSAGESにIDごとに置き、trでいまの言語の文を引く

数で形の変わる文は(1のときの形, ほかの形)の組にしておき、数はnの名前で渡す
(英語でtr("app.wrote_bytes", n=3)は"Wrote 3 bytes")。
"""

import os
import re
import string
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping

from . import paths
from .messages import MESSAGES

LANGUAGES = ("ja", "en")
_lang = "ja"


def set_language(lang: str) -> None:
    """画面の言語を決める(LANGUAGESのどれか)"""
    global _lang
    if lang not in LANGUAGES:
        raise ValueError(f"unknown language: {lang}")
    _lang = lang


def language() -> str:
    return _lang


def tr(key: str, /, **kw: object) -> str:
    """IDkeyの文を、いまの言語で返す。{addr:04X}のような差し込みは名前で書き、kwで値を渡す
    (語順が言語によって変わるため)。表にないkey(利用者が記述した代替ROMルーチンの働きなど)は、
    そのまま出す"""
    return _render(key, _lang, kw)


def _render(key: str, lang: str, kw: Mapping[str, object]) -> str:
    found = MESSAGES.get(key)
    text: str | tuple[str, str] = key
    if found is not None:
        text = found.get(lang) or found["ja"]
    if isinstance(text, tuple):
        text = text[0] if kw.get("n") == 1 else text[1]
    return text.format(**kw) if kw else text


def fields(key: str) -> set[str]:
    """IDkeyの文の差し込みの名前(どの言語の、どの形の文でも同じ)"""
    found = MESSAGES.get(key, {})
    forms = [f for t in found.values() for f in (t if isinstance(t, tuple) else (t,))]
    return {name for f in forms for _l, name, _s, _c in string.Formatter().parse(f) if name}


class Text:
    """IDと差し込みの値で持つ文。str()で、そのときの言語の文にする。止まった理由や読めなかった
    わけのように、覚えておいてあとで出す文はこれで持つ(言語を切り替えたあとも新しい言語で出る)。
    差し込みの値にTextを渡してもよい"""

    __slots__ = ("key", "kw")

    def __init__(self, key: str, /, **kw: object) -> None:
        self.key = key
        self.kw = kw

    def __str__(self) -> str:
        return tr(self.key, **self.kw)

    def __format__(self, spec: str) -> str:
        return format(str(self), spec)

    def __repr__(self) -> str:
        return f"Text({self.key!r}, **{self.kw!r})"

    def to_state(self) -> dict[str, object]:
        """状態のファイルに書く形(from_stateで読む)。差し込みの値は文字列か数だけにする"""
        return {"id": self.key, "args": dict(self.kw)}

    @classmethod
    def from_state(cls, saved: object, ids: Iterable[str]) -> "Text | None":
        """to_stateで書いたものを読む。IDがidsにない、差し込みの名前が文と合わない、値が文字列か
        数でない、どれかの言語の文にできない(番地の{addr:04X}に文字列など)ときはNone。出すときに
        なって例外にならないように、読むときに確かめる"""
        if not isinstance(saved, dict):
            return None
        key, args = saved.get("id"), saved.get("args", {})
        if not isinstance(key, str) or key not in set(ids) or key not in MESSAGES:
            return None
        if not isinstance(args, dict) or set(args) != fields(key):
            return None
        if not all(isinstance(k, str) and type(v) in (str, int) for k, v in args.items()):
            return None
        for lang in LANGUAGES:
            try:
                _render(key, lang, args)
            except (ValueError, TypeError, KeyError, IndexError):
                return None
        return cls(key, **args)


class Joined:
    """いまの言語の区切り(「、」か「, 」)でつないだ並び。Textの差し込みの値に渡す"""

    __slots__ = ("items",)

    def __init__(self, items: Iterable[object]) -> None:
        self.items = list(items)

    def __str__(self) -> str:
        return tr("common.ideographic_comma").join(map(str, self.items))

    def __format__(self, spec: str) -> str:
        return format(str(self), spec)


def from_locale(value: str | None) -> str | None:
    """ロケールや言語の名前(ja_JP.UTF-8、en、Cなど)から言語を決める。jaで始まればja、
    ほかの名前ならen、空ならNone"""
    name = (value or "").strip()
    if not name:
        return None
    return "ja" if name.lower().startswith("ja") else "en"


def mac_language() -> str | None:
    """macOSで選んでいる言語のいちばん上(defaults read -g AppleLanguages)。読めなければNone"""
    try:
        out = subprocess.run(
            ["defaults", "read", "-g", "AppleLanguages"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    # 「(\n    "ja-JP",\n    "en-JP"\n)」の形。最初の名前を取る
    hit = re.search(r"[A-Za-z][A-Za-z_-]*", out.stdout)
    return from_locale(hit[0]) if hit else None


def windows_language() -> str | None:
    """Windowsの表示の言語(GetUserDefaultUILanguage)。日本語ならja、ほかはen。読めなければ
    None"""
    try:
        import ctypes

        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return None
        langid = int(windll.kernel32.GetUserDefaultUILanguage())
    except (OSError, AttributeError, ValueError):
        return None
    return "ja" if langid & 0x3FF == 0x11 else "en"  # 0x11は日本語の主言語の番号


def choose(
    asked: str | None = None,
    remembered: object = None,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    mac: Callable[[], str | None] | None = None,
    win: Callable[[], str | None] | None = None,
) -> str:
    """画面の言語を決める。askedはコマンドの--lang、rememberedはメニューで前に選んだもの。
    --lang、環境変数SC61BOX_LANG(前の名前のSC61860PLAYER_LANG、PC1251_LANGも)、
    前に選んだもの、ロケール(LC_ALL、LC_MESSAGES、LANGの順)、
    macOSかWindowsの言語の設定の順に見て、決まらなければja"""
    env = os.environ if environ is None else environ
    if asked in LANGUAGES:
        return asked
    lang = from_locale(paths.env("LANG", env))
    if lang:
        return lang
    if remembered in LANGUAGES:
        assert isinstance(remembered, str)
        return remembered
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        lang = from_locale(env.get(name))
        if lang:
            return lang
    plat = sys.platform if platform is None else platform
    if plat == "darwin":
        lang = (mac or mac_language)()
        if lang:
            return lang
    if plat == "win32":
        lang = (win or windows_language)()
        if lang:
            return lang
    return "ja"

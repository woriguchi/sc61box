"""画面に出す文の言語。文は日本語で書き、trで選んだ言語の文に引き直す

英語の文はi18n_en.ENの表にある(日本語の文から英語の文を引く)。表にない文は日本語のまま
出す。数で形の変わる英語の文は(1のときの形, ほかの形)の組にしておき、数はnの名前で渡す
(tr("{n}バイト", n=3)は"3 bytes")。
"""

import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping

from . import paths
from .i18n_en import EN

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


def tr(text: str, /, **kw: object) -> str:
    """日本語の文textを、いまの言語の文にする。{addr:04X}のような差し込みは名前で書き、
    kwで値を渡す(語順が言語によって変わるため)"""
    if _lang == "en":
        found = EN.get(text)
        if isinstance(found, tuple):
            found = found[0] if kw.get("n") == 1 else found[1]
        if found is not None:
            text = found
    return text.format(**kw) if kw else text


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

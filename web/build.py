"""ブラウザ版を組み立てる(web/dist)

uv run python web/build.py                   # Pyodideも一緒に置く(初めはCDNから取ってくる)
uv run python web/build.py --pyodide DIR     # 手元のPyodide(DIRに展開したもの)を一緒に置く
uv run python web/build.py --cdn             # PyodideはCDNから読む(オフラインでは動かない)
python3 -m http.server -d web/dist           # 試すとき(http://localhost:8000/)

dist/にはページ(index.html)とアイコン、文字入りのアイコン、sc61box・同梱のプログラム・フォントをまとめたapp.zipを置く。
ROMと、公開しないプログラム(programs/private・programs/src)は入れない。ページはapp.zipを
中身のハッシュを付けて読むので、組み立て直すと、ブラウザに残っている前のapp.zipは使わない。

一度開いたあとはネットにつながっていなくても動くように、Service Worker(sw.js)が、置いた
ファイルをブラウザに持っておく。ページが読むファイルは、中身が変われば名前も変わる(app.zipは
ハッシュ、Pyodideは版のフォルダ)ので、組み立て直した直後も、前の版と新しい版のファイルが
混ざらない。ホーム画面に追加するためのmanifest.webmanifestも置く。
Pyodideは、使う分(本体とpygame-ce・Pillow)だけを置く。CDNから取ってきたものは
web/pyodide-cacheに残し、次からはそれを使う。
"""

import hashlib
import json
import os
import shutil
import urllib.request
import zipfile

import typer
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PYODIDE_VERSION = "314.0.7"
PYODIDE_CDN = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"
PYODIDE_CACHE = os.path.join(HERE, "pyodide-cache", PYODIDE_VERSION)
# Pyodideから置くもの(本体と、ページが読むパッケージ。パッケージのファイルはpyodide-lock.jsonで引く)
PYODIDE_FILES = (
    "pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip",
    "pyodide-lock.json",
)  # fmt: skip
PYODIDE_PACKAGES = ("pygame-ce", "pillow")  # index.htmlのloadPackageと同じ
SKIP_DIRS = {"__pycache__", "private", "src"}
# フォントはweb/fontsに置いたものだけを使う(公開用のリポジトリにdoc/fontsは入らない)
FONTS = tuple(
    os.path.join(HERE, "fonts", name)
    for name in (
        "NotoSansJP-Regular.ttf", "OFL-NotoSansJP.txt",
        "SourceCodePro-Regular.otf", "LICENSE-SourceCodePro.md",
    )
)  # fmt: skip


def _add_tree(z: zipfile.ZipFile, name: str) -> None:
    for folder, dirs, files in os.walk(os.path.join(ROOT, name)):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for f in sorted(files):
            if f == ".DS_Store":
                continue
            path = os.path.join(folder, f)
            z.write(path, os.path.relpath(path, ROOT))


# ホーム画面のアイコン(大きさ: ファイル名)。iPhone・iPadのapple-touch-iconと、manifestのもの
HOME_ICONS = {180: "apple-touch-icon.png", 192: "icon-192.png", 512: "icon-512.png"}


def _icons(out: str) -> None:
    """ページのアイコン。favicon.icoはアプリのアイコン(images/sc61box.ico)。ホーム画面のアイコンは、
    角をOSが丸めるので、アイコンの青い四角だけを切り出し、角の透けた所をまわりの色でうめる
    (大きいものも作るので、元はimages/sc61box.icnsの1024×1024)"""
    images = os.path.join(ROOT, "images")
    shutil.copy(os.path.join(images, "sc61box.ico"), os.path.join(out, "favicon.ico"))
    icon = Image.open(os.path.join(images, "sc61box-icon.png")).convert("RGBA")
    icon.save(os.path.join(out, "icon.png"))
    big = Image.open(os.path.join(images, "sc61box.icns")).convert("RGBA")
    square = big.crop(big.getchannel("A").getbbox())
    home = square.filter(ImageFilter.GaussianBlur(96))
    home.alpha_composite(square)
    home = Image.alpha_composite(Image.new("RGBA", home.size, (60, 80, 200, 255)), home)
    for size, name in HOME_ICONS.items():
        home.convert("RGB").resize((size, size), Image.Resampling.LANCZOS).save(
            os.path.join(out, name)
        )


NAVY = (31, 42, 107)  # 文字入りのアイコンの「sc」「box」の色
LIGHT = (228, 228, 221)  # ページの文字の色(index.htmlの--ink)


def _logos(out: str) -> None:
    """文字入りのアイコン(images/sc61box-banner.png)を縮めて置く。logo.pngはそのままの色で
    使い方の紙に、logo-light.pngは紺の文字をページの文字の色にしたもので、暗い地の見出しに使う"""
    src = Image.open(os.path.join(ROOT, "images", "sc61box-banner.png")).convert("RGBA")
    src = src.crop(src.getchannel("A").getbbox())
    logo = src.resize((src.width * 160 // src.height, 160), Image.Resampling.LANCZOS)
    logo.save(os.path.join(out, "logo.png"))
    px = bytearray(logo.tobytes())  # RGBAの並び
    w = logo.width
    for i in range(0, len(px), 4):
        if (i // 4) % w < w // 3:  # 左のアイコンには紺に近い色がある
            continue
        r, g, b, a = px[i : i + 4]
        if a and abs(r - NAVY[0]) + abs(g - NAVY[1]) + abs(b - NAVY[2]) < 90:
            px[i : i + 3] = bytes(LIGHT)
    light = Image.frombytes("RGBA", logo.size, bytes(px))
    light.save(os.path.join(out, "logo-light.png"))


def _download(name: str, dest: str) -> None:
    """CDNのPyodideのファイルnameを、destに取ってくる(途中で切れたものを残さない)"""
    part = dest + ".part"
    with urllib.request.urlopen(PYODIDE_CDN + name, timeout=60) as r, open(part, "wb") as f:
        shutil.copyfileobj(r, f)
    os.replace(part, dest)


def pyodide_names(source: str) -> list[str]:
    """sourceのpyodide-lock.jsonから、置くファイルの名前(本体と、使うパッケージとその依存)"""
    with open(os.path.join(source, "pyodide-lock.json"), encoding="utf-8") as f:
        packages = json.load(f)["packages"]
    names, want, seen = list(PYODIDE_FILES), list(PYODIDE_PACKAGES), set()
    while want:
        name = want.pop()
        if name in seen:
            continue
        seen.add(name)
        names.append(packages[name]["file_name"])
        want += packages[name].get("depends", [])
    return names


def _fetch_pyodide() -> str:
    """CDNから、置くPyodideのファイルをPYODIDE_CACHEに取ってきて(あるものは使って)、そのフォルダを返す"""
    os.makedirs(PYODIDE_CACHE, exist_ok=True)
    lock = os.path.join(PYODIDE_CACHE, "pyodide-lock.json")
    if not os.path.exists(lock):
        _download("pyodide-lock.json", lock)
    for name in pyodide_names(PYODIDE_CACHE):
        dest = os.path.join(PYODIDE_CACHE, name)
        if not os.path.exists(dest):
            print(f"Pyodideの{name}を取ってくる")
            _download(name, dest)
    return PYODIDE_CACHE


def _service_worker(out: str, files: list[str]) -> None:
    """オフラインで使えるように持っておくファイル(files)を入れたsw.jsを置く。中身が変われば
    名前(VERSION)も変わり、ブラウザは新しいものに入れ替えて、前に持っていたものを捨てる"""
    digest = hashlib.sha256()
    for name in sorted(files):
        path = os.path.join(out, name.split("?")[0] if name != "./" else "index.html")
        with open(path, "rb") as f:
            digest.update(name.encode() + hashlib.sha256(f.read()).digest())
    with open(os.path.join(HERE, "sw.js"), encoding="utf-8") as f:
        worker = f.read()
    worker = worker.replace("{{VERSION}}", digest.hexdigest()[:12])
    worker = worker.replace("{{FILES}}", json.dumps(files))
    with open(os.path.join(out, "sw.js"), "w", encoding="utf-8") as f:
        f.write(worker)


def build(out: str, pyodide: str | None = None, cdn: bool = False) -> None:
    """outに組み立てる。pyodideは手元のPyodideのフォルダ(なければCDNから取ってくる)。cdnなら
    Pyodideは置かず、CDNから読む"""
    os.makedirs(out, exist_ok=True)
    bundle = os.path.join(out, "app.zip")
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
        _add_tree(z, "sc61box")
        _add_tree(z, "programs")
        for path in FONTS:
            z.write(path, os.path.join("fonts", os.path.basename(path)))
    with open(bundle, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()[:12]
    with open(os.path.join(HERE, "index.html"), encoding="utf-8") as f:
        page = f.read()
    base, kept = PYODIDE_CDN, []
    if not cdn:
        source = pyodide if pyodide is not None else _fetch_pyodide()
        # 版ごとのフォルダに置く。版を上げても、前のページが前の版のファイルを読める(sw.js)
        base = f"./pyodide/{PYODIDE_VERSION}/"
        dest = os.path.join(out, "pyodide", PYODIDE_VERSION)
        os.makedirs(dest, exist_ok=True)
        for name in pyodide_names(source):
            shutil.copy(os.path.join(source, name), dest)
            kept.append(f"pyodide/{PYODIDE_VERSION}/{name}")
    _icons(out)
    _logos(out)
    shutil.copy(os.path.join(HERE, "manifest.webmanifest"), out)
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page.replace("{{PYODIDE}}", base).replace("{{APP}}", f"app.zip?{digest}"))
    pictures = ["favicon.ico", "icon.png", "logo.png", "logo-light.png", *HOME_ICONS.values()]
    files = ["./", "index.html", f"app.zip?{digest}", "manifest.webmanifest", *pictures]
    _service_worker(out, files + kept)


def main(
    out: str = typer.Option(os.path.join(HERE, "dist"), help="組み立てたものを置くフォルダ"),
    pyodide: str | None = typer.Option(None, help="手元のPyodideを展開したフォルダ"),
    cdn: bool = typer.Option(False, help="Pyodideを置かず、CDNから読む(オフラインでは動かない)"),
) -> None:
    build(out, pyodide, cdn)


if __name__ == "__main__":
    typer.run(main)

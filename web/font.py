"""ブラウザ版の日本語のフォント(web/fonts/NotoSansJP-Regular.ttf)を作る

ブラウザにはOSのフォントがないので、Noto Sans JP(SIL Open Font License)の太さ400から、
JIS X 0208の字と画面の文(sc61box/messages.py)の字だけを取り出して同梱する。元のフォントは
Google Fonts(https://github.com/google/fonts の ofl/notosansjp/NotoSansJP[wght].ttf)。

uv run --with fonttools python web/font.py NotoSansJP[wght].ttf
"""

import os

import typer
from fontTools import subset  # pyrefly: ignore[missing-import]
from fontTools.ttLib import TTFont  # pyrefly: ignore[missing-import]
from fontTools.varLib import instancer  # pyrefly: ignore[missing-import]

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fonts", "NotoSansJP-Regular.ttf")
MESSAGES = os.path.join(HERE, os.pardir, "sc61box", "messages.py")


def characters() -> str:
    chars = {chr(c) for c in range(0x20, 0x7F)} | {chr(c) for c in range(0xA0, 0x100)}
    for hi in range(0xA1, 0xFF):  # JIS X 0208(EUC-JPの2バイトの字)
        for lo in range(0xA1, 0xFF):
            try:
                chars.add(bytes([hi, lo]).decode("euc_jp"))
            except UnicodeDecodeError:
                pass
    with open(MESSAGES, encoding="utf-8") as f:
        chars |= set(f.read())
    return "".join(sorted(chars))


def main(
    source: str = typer.Argument(..., help="Noto Sans JPのフォント(NotoSansJP[wght].ttf)"),
) -> None:
    font = instancer.instantiateVariableFont(TTFont(source), {"wght": 400})
    opts = subset.Options()
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    sub = subset.Subsetter(opts)
    sub.populate(text=characters())
    sub.subset(font)
    font.save(OUT)
    print(OUT, os.path.getsize(OUT))


if __name__ == "__main__":
    typer.run(main)

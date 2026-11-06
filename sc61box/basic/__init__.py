"""ROMなしのBASIC(ROMのない本体で、BASICとモードをエミュレータが受け持つ)

BASICのふるまいは実機に合わせ、作りは独自にする(ROMのルーチンの分け方や手順は写さない)。

このフォルダの直下は、系統によらない部品(基底クラスと共通の関数)。字のコードと中間コードの番号、
RAMの置き方、液晶の出し方は系統ごとのフォルダにある。

- pc1251/: PC-1251系(PC-1250・1251・1255、PC-1245)
- pc1261/: PC-1261系(PC-1260・1261・1262)とPC-1350(PC-1350の液晶とキーはpc1261/pc1350.py)
"""

from .system import Basic

PC1261_MODELS = ("1260", "1261", "1262")  # PC-1261系の機種
MODELS = ("1250", "1251", "1255", "1245", *PC1261_MODELS, "1350")  # ROMなしのBASICで動かせる機種


def attach(m) -> Basic:
    """ROMなしの本体mにBASICを付ける"""
    if m.model.name == "1350":
        from .pc1261 import pc1350 as family
    elif m.model.name in PC1261_MODELS:
        from .pc1261 import system as family
    else:
        from .pc1251 import system as family
    m.basic = family.Basic(m)
    return m.basic


__all__ = ["MODELS", "Basic", "attach"]

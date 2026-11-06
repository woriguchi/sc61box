"""PC-1251系の打っている行。>=・<=・<>は1つの中間コードで、前後に空白を置かない"""

from .. import editor


class Editor(editor.Editor):
    SPACE = 0x11
    TIGHT = (0x82, 0x83, 0x84)
    TOKEN = 0x7D

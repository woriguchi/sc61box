"""BASICのエラー"""


class BasicError(Exception):
    """液晶にERROR nと出して止まるエラー。numberはERRORのあとに出す番号、posは行の中の
    エラーの位置(中間コードの並びでの位置。決まっていなければNone)"""

    def __init__(self, number: int, pos: int | None = None) -> None:
        super().__init__(f"ERROR {number}")
        self.number = number
        self.pos = pos

    def at(self, pos: int) -> "BasicError":
        """位置がまだ決まっていなければposにする"""
        if self.pos is None:
            self.pos = pos
        return self

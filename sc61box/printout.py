"""プリンタの紙1枚(出してからしまうまでの印字)と、その絵の保存

紙を出すと「print-日時.png」の名前を取り、印字がとぎれるたび、紙をしまうとき、終了するときに
その紙の印字をすべて感熱紙の絵にして書き直す。
"""

import os
import time

import pygame

from .overlay import Paper
from .paths import unused_file
from .printer import Printer

SAVE_AFTER = 1.0  # 印字がこの秒数とぎれたら保存する


class Printout:
    def __init__(self, printer: Printer, cut: tuple[int, int], folder: str) -> None:
        """cutはこの紙の始まり(printer.linesの行の番号, その行の中の字の位置)。前の紙を途中の
        行でしまったときは、その行の先の字からがこの紙になる。保存先の名前はfolderの中に取る。
        取れなければ(フォルダを作れないなど)fileはNoneで、紙は出すが保存しない"""
        self.printer = printer
        self.first, self.skip = cut
        self.file: str | None = None
        self.error: OSError | None = None  # 名前を取れなかったわけ
        try:
            self.file = unused_file(folder, f"print-{time.strftime('%Y%m%d-%H%M%S')}", ".png")
        except OSError as e:
            self.error = e
        self.saved: list[bytes] = []  # 保存した行(途中の行も含む)
        self.time = time.monotonic()  # 最後に印字した時刻

    def rows(self) -> list[bytes]:
        """この紙に印字した行(途中の行も含める)"""
        rows = self.printer.rows()[self.first :]
        if rows and self.skip:
            rows[0] = rows[0][self.skip :]
            if not rows[0] and self.first >= len(self.printer.lines):  # 途中の行に新しい字がない
                rows = rows[1:]
        return rows

    def cut(self) -> tuple[int, int]:
        """次の紙の始まり(いまの行の番号と、途中の行の字の位置)"""
        return len(self.printer.lines), len(self.printer.line)

    def close(self) -> None:
        """紙を終える。何も保存していなければ、名前を取るために作った空のファイルを消す"""
        if self.file is not None and not self.saved:
            try:
                if os.path.getsize(self.file) == 0:
                    os.remove(self.file)
            except OSError:
                pass
        self.file = None

    def touched(self) -> None:
        self.time = time.monotonic()

    def due(self) -> bool:
        """印字がとぎれたので保存するときか"""
        return self.file is not None and time.monotonic() - self.time > SAVE_AFTER

    def save(self, paper: Paper) -> bool:
        """印字を感熱紙の絵にしてfileに書く。書いたらTrue。前に保存したあとに印字していなければ
        何もしない。書けなければOSErrorかpygame.error"""
        rows = self.rows()
        if self.file is None or not rows or rows == self.saved:
            return False
        img = paper.picture(rows)
        img = pygame.transform.scale(img, (img.get_width() * 2, img.get_height() * 2))
        pygame.image.save(img, self.file)
        self.saved = rows
        return True

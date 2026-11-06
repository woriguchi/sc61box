"""PC-1261系とPC-1350のパスワードの置き方。PC-1261系では、パスワードは6640h、プログラムを
保護のフラグは66D9hのビット5(観察)。保護しているあいだは、行の登録とNEWとLISTが
効かない"""

from ..password import Password
from . import program

PC1261 = Password(0x6640, 0x66D9, program.PC1261)
PC1350 = Password(0x6F09, 0x6F14, program.PC1350)  # RAMの頭+0Fhと+1Ahにもコピーする(観察)

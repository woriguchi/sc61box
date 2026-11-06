"""PC-1251系のパスワードの置き方。パスワードはF8A8h、保護のフラグはC6D9hのビット5。NEWで
保護を解くが、パスワードは残す"""

from ..password import Password
from . import program

PC1251 = Password(0xF8A8, 0xC6D9, program.PC1251)

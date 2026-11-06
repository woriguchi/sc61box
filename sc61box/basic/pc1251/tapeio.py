"""PC-1251系のカセットの命令。テープの形はcassette.py"""

from .. import tapeio
from . import cassette


class TapeIO(tapeio.TapeIO):
    FORMAT = cassette
    T_CHAIN = 0xD9

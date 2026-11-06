"""PC-1251系(PC-1250・1251・1255、PC-1245)のROMなしのBASICの本体。1行の液晶に出す"""

from ... import charset
from .. import system
from . import (
    editor,
    evaluate,
    keyboard,
    lexer,
    password,
    printer,
    program,
    reserve,
    run,
    screen,
    tapeio,
    variables,
)

T_LIST, T_NEW, T_RUN, T_CONT, T_GOTO, T_PASS, T_LLIST = 0xB3, 0xB1, 0xB0, 0xB4, 0xD7, 0xBB, 0xBC
T_CSAVE, T_CLOAD, T_MERGE = 0xB6, 0xB7, 0xB8
T_ROM, T_INSTAT, T_INPUT = 0x9E, 0xBF, 0xC2
# RUNモードで行番号なしに打って実行できる文(観察。INPUTはERROR 9、ほかの文はERROR 1)
DIRECT = (0xCA, 0xC5, 0xCE, 0xC9, 0xC4, 0xC3, 0xC0, 0x95, 0x93, 0xB9, 0xBA, 0xDB, 0xDD)
ANGLE_MARKS = {"DEGREE": ("DE", "G"), "RADIAN": ("RAD",), "GRAD": ("G", "RAD")}


class Basic(system.Basic):
    PROMPT, COLON, SPACE, EQ, COMMA, QUOTE, AT = 0x32, 0x1D, 0x11, 0x34, 0x1B, 0x12, 0x1E
    CODES = keyboard.CODES
    USING_CODES = charset.CODES
    T_LIST, T_NEW, T_RUN, T_CONT, T_GOTO = T_LIST, T_NEW, T_RUN, T_CONT, T_GOTO
    T_PASS, T_LLIST, T_CSAVE, T_CLOAD, T_MERGE = T_PASS, T_LLIST, T_CSAVE, T_CLOAD, T_MERGE
    T_ROM, T_INSTAT, T_INPUT = T_ROM, T_INSTAT, T_INPUT
    DIRECT = DIRECT
    STATEMENTS = run.Runner.STATEMENTS
    EVALUATOR, RUNNER, SCREEN = evaluate.Evaluator, run.Runner, screen.Screen
    KEYBOARD, EDITOR, LEXER = keyboard.Keyboard, editor.Editor, lexer.Lexer
    PROGRAM, VARS = program.PC1251, variables.PC1251
    TIMES = evaluate.Evaluator.TIMES
    PRINT_BUFFER = 0xC7B0
    PASSWORD, RESERVE = password.PC1251, reserve.PC1251
    TAPEIO, PRINTOUT = tapeio.TapeIO, printer.PrintOut
    ERROR_MARK = "E"
    TEXT_POINTER = 0xC6B1

    def _power_on(self) -> None:
        self.screen.symbol("DE", True)
        self.screen.symbol("G", True)

    def _show_mode(self, mode: str) -> None:
        for name, on in (("RUN", "RUN"), ("PRO", "PRO"), ("RESERVE", "RSV")):
            self.screen.symbol(name, mode == on)

    def set_angle(self, which: str) -> None:
        for name in ("DE", "G", "RAD"):
            self.screen.symbol(name, name in ANGLE_MARKS[which])

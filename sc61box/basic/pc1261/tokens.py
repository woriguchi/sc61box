"""PC-1261系(PC-1260・1261・1262)とPC-1350のBASICの命令の中間コード

ROMのある本体で、プログラムの行に1バイトの中間コードを書いてLISTし、液晶に出る綴りを
見て決めた。ROMの中の表は読んでいない。中間コードは1バイトで、行の中のほかの字はASCII
(PC-1251系の本体の文字コードではない)。
"""

# PC-1261系とPC-1350に共通
KEYWORDS: dict[int, str] = {
    0x91: "LN", 0x92: "LOG", 0x93: "EXP", 0x94: "SQR", 0x95: "SIN", 0x96: "COS", 0x97: "TAN",
    0x98: "INT", 0x99: "ABS", 0x9A: "SGN", 0x9B: "DEG", 0x9C: "DMS", 0x9D: "ASN", 0x9E: "ACS",
    0x9F: "ATN", 0xA0: "RND", 0xA1: "AND", 0xA2: "OR", 0xA3: "NOT", 0xA4: "ASC", 0xA5: "VAL",
    0xA6: "LEN", 0xA7: "PEEK", 0xA8: "CHR$", 0xA9: "STR$", 0xAA: "MID$", 0xAB: "LEFT$",
    0xAC: "RIGHT$", 0xAD: "INKEY$", 0xAE: "PI", 0xAF: "MEM", 0xB0: "RUN", 0xB1: "NEW",
    0xB2: "CONT", 0xB3: "PASS", 0xB4: "LIST", 0xB5: "LLIST", 0xB6: "CSAVE", 0xB7: "CLOAD",
    0xB8: "MERGE", 0xC0: "RANDOM", 0xC1: "DEGREE", 0xC2: "RADIAN", 0xC3: "GRAD", 0xC4: "BEEP",
    0xC5: "WAIT", 0xC6: "GOTO", 0xC7: "TRON", 0xC8: "TROFF", 0xC9: "CLEAR", 0xCA: "USING",
    0xCB: "DIM", 0xCC: "CALL", 0xCD: "POKE", 0xCE: "CLS", 0xCF: "CURSOR", 0xD0: "TO", 0xD1: "STEP",
    0xD2: "THEN", 0xD3: "ON", 0xD4: "IF", 0xD5: "FOR", 0xD6: "LET", 0xD7: "REM", 0xD8: "END",
    0xD9: "NEXT", 0xDA: "STOP", 0xDB: "READ", 0xDC: "DATA", 0xDD: "PAUSE", 0xDE: "PRINT",
    0xDF: "INPUT", 0xE0: "GOSUB", 0xE1: "AREAD", 0xE2: "LPRINT", 0xE3: "RETURN", 0xE4: "RESTORE",
    0xE5: "CHAIN",
}  # fmt: skip

KEYWORDS_1261: dict[int, str] = KEYWORDS | {0xB9: "EQU#", 0xBA: "MEM#"}

KEYWORDS_1350: dict[int, str] = KEYWORDS | {
    0xBB: "OPEN", 0xBC: "CLOSE", 0xBD: "SAVE", 0xBE: "LOAD", 0xBF: "CONSOLE", 0xE6: "GCURSOR",
    0xE7: "GPRINT", 0xE8: "LINE", 0xE9: "POINT", 0xEA: "PSET", 0xEB: "PRESET", 0xEC: "BASIC",
    0xED: "TEXT", 0xEE: "OPEN$",
}  # fmt: skip


# 綴りの頭の字と「.」で打つ省略形。命令の綴りの頭の1字から全体より1字少ない字までを、すべて
# 「.」を付けてPROモードで打ち、RAMに入った中間コードを見て決めた
ABBREVIATIONS: dict[str, str] = {
    "A": "AREAD", "AB": "ABS", "AC": "ACS", "AN": "AND", "AR": "AREAD", "ARE": "AREAD",
    "AREA": "AREAD", "AS": "ASN", "AT": "ATN", "B": "BEEP", "BE": "BEEP", "BEE": "BEEP",
    "C": "CONT", "CA": "CALL", "CAL": "CALL", "CH": "CHR$", "CHA": "CHAIN", "CHAI": "CHAIN",
    "CHR": "CHR$", "CL": "CLEAR", "CLE": "CLEAR", "CLEA": "CLEAR", "CLO": "CLOAD", "CLOA": "CLOAD",
    "CO": "CONT", "CON": "CONT", "CS": "CSAVE", "CSA": "CSAVE", "CSAV": "CSAVE", "CU": "CURSOR",
    "CUR": "CURSOR", "CURS": "CURSOR", "CURSO": "CURSOR", "D": "DIM", "DA": "DATA", "DAT": "DATA",
    "DE": "DEGREE", "DEG": "DEGREE", "DEGR": "DEGREE", "DEGRE": "DEGREE", "DI": "DIM", "DM": "DMS",
    "E": "END", "EN": "END", "EX": "EXP", "F": "FOR", "FO": "FOR", "G": "GOTO", "GO": "GOTO",
    "GOS": "GOSUB", "GOSU": "GOSUB", "GOT": "GOTO", "GR": "GRAD", "GRA": "GRAD", "I": "INPUT",
    "IN": "INPUT", "INK": "INKEY$", "INKE": "INKEY$", "INKEY": "INKEY$", "INP": "INPUT",
    "INPU": "INPUT", "L": "LIST", "LE": "LET", "LEF": "LEFT$", "LEFT": "LEFT$", "LI": "LIST",
    "LIS": "LIST", "LL": "LLIST", "LLI": "LLIST", "LLIS": "LLIST", "LO": "LOG", "LP": "LPRINT",
    "LPR": "LPRINT", "LPRI": "LPRINT", "LPRIN": "LPRINT", "M": "MEM", "ME": "MEM", "MER": "MERGE",
    "MERG": "MERGE", "MI": "MID$", "MID": "MID$", "N": "NEXT", "NE": "NEXT", "NEX": "NEXT",
    "NO": "NOT", "O": "ON", "P": "PRINT", "PA": "PASS", "PAS": "PASS", "PAU": "PAUSE",
    "PAUS": "PAUSE", "PE": "PEEK", "PEE": "PEEK", "PO": "POKE", "POK": "POKE", "PR": "PRINT",
    "PRI": "PRINT", "PRIN": "PRINT", "R": "RUN", "RA": "RANDOM", "RAD": "RADIAN", "RADI": "RADIAN",
    "RADIA": "RADIAN", "RAN": "RANDOM", "RAND": "RANDOM", "RANDO": "RANDOM", "RE": "RETURN",
    "REA": "READ", "RES": "RESTORE", "REST": "RESTORE", "RESTO": "RESTORE", "RESTOR": "RESTORE",
    "RET": "RETURN", "RETU": "RETURN", "RETUR": "RETURN", "RI": "RIGHT$", "RIG": "RIGHT$",
    "RIGH": "RIGHT$", "RIGHT": "RIGHT$", "RN": "RND", "RU": "RUN", "S": "STOP", "SG": "SGN",
    "SI": "SIN", "SQ": "SQR", "ST": "STOP", "STE": "STEP", "STO": "STOP", "STR": "STR$",
    "T": "THEN", "TA": "TAN", "TH": "THEN", "THE": "THEN", "TR": "TRON", "TRO": "TRON",
    "TROF": "TROFF", "U": "USING", "US": "USING", "USI": "USING", "USIN": "USING", "V": "VAL",
    "VA": "VAL", "W": "WAIT", "WA": "WAIT", "WAI": "WAIT",
}  # fmt: skip

ABBREVIATIONS_1261: dict[str, str] = ABBREVIATIONS | {
    "EQ": "EQU#", "EQU": "EQU#",
}  # fmt: skip

ABBREVIATIONS_1350: dict[str, str] = ABBREVIATIONS | {
    "BA": "BASIC", "BAS": "BASIC", "BASI": "BASIC", "CLOS": "CLOSE", "CONS": "CONSOLE",
    "CONSO": "CONSOLE", "CONSOL": "CONSOLE", "GC": "GCURSOR", "GCU": "GCURSOR", "GCUR": "GCURSOR",
    "GCURS": "GCURSOR", "GCURSO": "GCURSOR", "GP": "GPRINT", "GPR": "GPRINT", "GPRI": "GPRINT",
    "GPRIN": "GPRINT", "LIN": "LINE", "LOA": "LOAD", "OP": "OPEN", "OPE": "OPEN", "POI": "POINT",
    "POIN": "POINT", "PRE": "PRESET", "PRES": "PRESET", "PRESE": "PRESET", "PS": "PSET",
    "PSE": "PSET", "SA": "SAVE", "SAV": "SAVE", "TE": "TEXT", "TEX": "TEXT",
}  # fmt: skip

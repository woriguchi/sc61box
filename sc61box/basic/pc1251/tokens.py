"""BASICの命令の綴りと中間コード(PC-1251・PC-1245)

ROMのある本体(PC-1251のBASIC ROM F0版と、PC-1245)で、次の2つの方法で確かめた対応。
ROMの中の表は読んでいない。

- PROモードで綴りを打ち、RAMに入った中間コードを見る
- プログラムの行に中間コードを書いてLISTし、液晶に出る綴りを見る

7Dh〜DFhのうち、ここにない番号(80h、8Fh、94h、97h、98h、9Ah、9Ch、9Dh、C6h〜C8h)は、
LISTで綴りが出なかった。
"""

KEYWORDS_1251: dict[int, str] = {
    0x7D: "ASC", 0x7E: "VAL", 0x7F: "LEN", 0x81: "AND", 0x82: ">=", 0x83: "<=", 0x84: "<>",
    0x85: "OR", 0x86: "NOT", 0x87: "SQR", 0x88: "CHR$", 0x89: "COM$", 0x8A: "INKEY$",
    0x8B: "STR$", 0x8C: "LEFT$", 0x8D: "RIGHT$", 0x8E: "MID$", 0x90: "TO", 0x91: "STEP",
    0x92: "THEN", 0x93: "RANDOM", 0x95: "WAIT", 0x96: "ERROR", 0x99: "KEY", 0x9B: "SETCOM",
    0x9E: "ROM", 0x9F: "LPRINT", 0xA0: "SIN", 0xA1: "COS", 0xA2: "TAN", 0xA3: "ASN",
    0xA4: "ACS", 0xA5: "ATN", 0xA6: "EXP", 0xA7: "LN", 0xA8: "LOG", 0xA9: "INT", 0xAA: "ABS",
    0xAB: "SGN", 0xAC: "DEG", 0xAD: "DMS", 0xAE: "RND", 0xAF: "PEEK", 0xB0: "RUN", 0xB1: "NEW",
    0xB2: "MEM", 0xB3: "LIST", 0xB4: "CONT", 0xB5: "DEBUG", 0xB6: "CSAVE", 0xB7: "CLOAD",
    0xB8: "MERGE", 0xB9: "TRON", 0xBA: "TROFF", 0xBB: "PASS", 0xBC: "LLIST", 0xBD: "PI",
    0xBE: "OUTSTAT", 0xBF: "INSTAT", 0xC0: "GRAD", 0xC1: "PRINT", 0xC2: "INPUT",
    0xC3: "RADIAN", 0xC4: "DEGREE", 0xC5: "CLEAR", 0xC9: "CALL", 0xCA: "DIM", 0xCB: "DATA",
    0xCC: "ON", 0xCD: "OFF", 0xCE: "POKE", 0xCF: "READ", 0xD0: "IF", 0xD1: "FOR", 0xD2: "LET",
    0xD3: "REM", 0xD4: "END", 0xD5: "NEXT", 0xD6: "STOP", 0xD7: "GOTO", 0xD8: "GOSUB",
    0xD9: "CHAIN", 0xDA: "PAUSE", 0xDB: "BEEP", 0xDC: "AREAD", 0xDD: "USING", 0xDE: "RETURN",
    0xDF: "RESTORE",
}  # fmt: skip

# PC-1245では9Bh(SETCOM)をLISTすると「S」と出る
KEYWORDS_1245: dict[int, str] = {k: v for k, v in KEYWORDS_1251.items() if k != 0x9B}


# 綴りの頭と「.」で打つ省略(P.でPRINTなど)。PC-1251で、命令の綴りの頭の1字から(全体より
# 1字少ない字まで)をすべて「.」を付けてPROモードで打ち、RAMに入った中間コードを見て決めた。
# PC-1245も同じ方法で確かめ、SETCOMのないほかは同じだった
ABBREVIATIONS_1251: dict[str, str] = {
    "A": "AREAD", "AB": "ABS", "AC": "ACS", "AN": "AND", "AR": "AREAD", "ARE": "AREAD",
    "AREA": "AREAD", "AS": "ASN", "AT": "ATN", "B": "BEEP", "BE": "BEEP", "BEE": "BEEP",
    "C": "CONT", "CA": "CALL", "CAL": "CALL", "CH": "CHAIN", "CHA": "CHAIN", "CHAI": "CHAIN",
    "CHR": "CHR$", "CL": "CLEAR", "CLE": "CLEAR", "CLEA": "CLEAR", "CLO": "CLOAD",
    "CLOA": "CLOAD", "CO": "CONT", "COM": "COM$", "CON": "CONT", "CS": "CSAVE", "CSA": "CSAVE",
    "CSAV": "CSAVE", "D": "DIM", "DA": "DATA", "DAT": "DATA", "DE": "DEGREE", "DEB": "DEBUG",
    "DEBU": "DEBUG", "DEG": "DEGREE", "DEGR": "DEGREE", "DEGRE": "DEGREE", "DI": "DIM",
    "DM": "DMS", "E": "END", "EN": "END", "ER": "ERROR", "ERR": "ERROR", "ERRO": "ERROR",
    "EX": "EXP", "F": "FOR", "FO": "FOR", "G": "GOTO", "GO": "GOTO", "GOS": "GOSUB",
    "GOSU": "GOSUB", "GOT": "GOTO", "GR": "GRAD", "GRA": "GRAD", "I": "INPUT", "IN": "INPUT",
    "INK": "INKEY$", "INKE": "INKEY$", "INKEY": "INKEY$", "INP": "INPUT", "INPU": "INPUT",
    "INS": "INSTAT", "INST": "INSTAT", "INSTA": "INSTAT", "K": "KEY", "KE": "KEY", "L": "LIST",
    "LE": "LET", "LEF": "LEFT$", "LEFT": "LEFT$", "LI": "LIST", "LIS": "LIST", "LL": "LLIST",
    "LLI": "LLIST", "LLIS": "LLIST", "LO": "LOG", "LP": "LPRINT", "LPR": "LPRINT",
    "LPRI": "LPRINT", "LPRIN": "LPRINT", "M": "MEM", "ME": "MEM", "MER": "MERGE", "MERG": "MERGE",
    "MI": "MID$", "MID": "MID$", "N": "NEXT", "NE": "NEXT", "NEX": "NEXT", "NO": "NOT", "O": "ON",
    "OF": "OFF", "OU": "OUTSTAT", "OUT": "OUTSTAT", "OUTS": "OUTSTAT", "OUTST": "OUTSTAT",
    "OUTSTA": "OUTSTAT", "P": "PRINT", "PA": "PASS", "PAS": "PASS", "PAU": "PAUSE",
    "PAUS": "PAUSE", "PE": "PEEK", "PEE": "PEEK", "PO": "POKE", "POK": "POKE", "PR": "PRINT",
    "PRI": "PRINT", "PRIN": "PRINT", "R": "RUN", "RA": "RANDOM", "RAD": "RADIAN",
    "RADI": "RADIAN", "RADIA": "RADIAN", "RAN": "RANDOM", "RAND": "RANDOM", "RANDO": "RANDOM",
    "RE": "RETURN", "REA": "READ", "RES": "RESTORE", "REST": "RESTORE", "RESTO": "RESTORE",
    "RESTOR": "RESTORE", "RET": "RETURN", "RETU": "RETURN", "RETUR": "RETURN", "RI": "RIGHT$",
    "RIG": "RIGHT$", "RIGH": "RIGHT$", "RIGHT": "RIGHT$", "RN": "RND", "RO": "ROM", "RU": "RUN",
    "S": "STOP", "SE": "SETCOM", "SET": "SETCOM", "SETC": "SETCOM", "SETCO": "SETCOM",
    "SG": "SGN", "SI": "SIN", "SQ": "SQR", "ST": "STOP", "STE": "STEP", "STO": "STOP",
    "STR": "STR$", "T": "THEN", "TA": "TAN", "TH": "THEN", "THE": "THEN", "TR": "TRON",
    "TRO": "TRON", "TROF": "TROFF", "U": "USING", "US": "USING", "USI": "USING", "USIN": "USING",
    "V": "VAL", "VA": "VAL", "W": "WAIT", "WA": "WAIT", "WAI": "WAIT",
}  # fmt: skip
ABBREVIATIONS_1245: dict[str, str] = {k: v for k, v in ABBREVIATIONS_1251.items() if v != "SETCOM"}

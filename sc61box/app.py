"""PC-1251/PC-1245/PC-1261/PC-1350エミュレータの画面とキー操作

uv run sc61box          # 起動
uv run sc61box --model 1245  # PC-1245として起動する
uv run sc61box --model 1261  # PC-1261として起動する(1260、1262も選べる)
uv run sc61box --model 1350 --card 16  # PC-1350として、16KBのRAMカードを差して起動する
uv run sc61box --type prog.bas # 起動後にファイルの中身をキー入力する
uv run sc61box --load dump.txt # 16進ダンプをRAMへ書き込む
uv run sc61box primes --run  # プログラムのフォルダのprimes.basを読み込んで実行する
"""

import json
import math
import os
import re
import subprocess
import sys
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

import pygame
import typer

from . import (
    audio,
    basictext,
    benchview,
    display,
    gamepad,
    i18n,
    keytype,
    loading,
    padmenu,
    paths,
    programs,
    recorder,
    routinecheck,
    routines,
    tape,
    workbench,
)
from . import basic as norom_basic
from . import norom as norom_hle
from .audio import (
    PRINT_CATCH_UP,
    PRINT_GAP,
    PRINT_KEEP,
    PRINT_LINE,
    RATE,
    Buzzer,
    PrinterSound,
    speed_adjust,
)
from .autotype import Typer
from .i18n import Text, tr
from .keytype import keys_for, keys_for_program
from .lcdtext import lcd_text
from .machine import CLOCK, MODELS, RomNotFound, new_machine
from .overlay import (
    BAR_H,
    SEPARATOR,
    Bar,
    BarButton,
    MenuItem,
    Paper,
    Popup,
    ProgramMenu,
    draw_halted,
    draw_help,
    draw_recording,
    draw_status,
    draw_warning,
    load_help_font,
)
from .printer import load_font
from .printout import Printout

FPS = 30
# 1フレームの本体の実行をこの数に分け、合間にもキーのイベントを受け取る(キーを押してから
# 本体に届くまでの遅れを1/(FPS*SUBSTEPS)秒以下にする。ゲームの細かいキー操作のため)
SUBSTEPS = 4
RUSH = 8  # パソコンのキーをROMの入力待ちに届けるあいだの速さ(Typer.rushing)
STATE_DIR = paths.data_dir()  # RAM、状態、作業欄の見え方などを置くところ


@dataclass
class Options:
    """起動のオプション(コマンドの引数。試験やツールからはこのまま作る)"""

    model: str = "1251"
    card: int = 0
    overseas: bool = False
    norom: bool = False
    basic: bool = True  # ROMなしで、ROMなしのBASICを付ける(付けなければ作業欄だけで動かす)
    scale: float = 1.0
    persist: float = 1.0
    fresh: bool = False
    mute: bool = False
    numpad: bool = False
    lcd: bool = False  # 本体の絵を出さず、液晶だけを見せる
    lang: str | None = None
    program: str | None = None
    run: bool = False
    type: str | None = None
    load: str | None = None
    tape: str | None = None
    state: str | None = None
    moved_data: str = ""  # 起動のときに移した前のデータのフォルダ(~/.pc1251など。paths.migrate)


def shows_prompt(m) -> bool:
    """液晶に>だけが出ているか"""
    if m.model.name in norom_hle.MODELS:  # PC-1251・PC-1245は、ROMの字の形の表で>(32h)を見る
        a = norom_hle.font_addr(0x32)
        cols = m.columns()
        return bytes(cols[:5]) == bytes(m.mem[a : a + 5]) and not any(cols[5:])
    return lcd_text(m).strip() == ">"


def pc1261_basic(m) -> bool:
    """PC-1261系かPC-1350か(BASICが同じ系列)。ROMなしでもプログラムの形を決めるのに使う"""
    return m.model.lines == 2 or m.model.family == "1350"


def basic_keywords(m) -> dict[int, str] | None:
    """ROMなしのBASICの命令の表(その機種のもの)。ROMで動いていればNone(ROMの表を読む)"""
    basic = getattr(m, "basic", None)
    return dict(basic.keywords) if basic is not None else None


def undo_hint() -> str:
    return tr("app.undo_program_load_menu")


def ram_file(model: str = "1251", card: int = 0, norom: bool = False) -> str:
    """終了時にRAMを保存するファイル。RAMの大きさが違うので機種(とRAMカード)ごとに分ける。
    ROMなしで動かしたときのRAMは、ROMで動かしたときのRAMと混ざらないように別にする"""
    if card:
        model = f"{model}-{card}k"
    if norom:
        return os.path.join(STATE_DIR, f"ram-{model}-norom.bin")
    name = "ram.bin" if model == "1251" else f"ram-{model}.bin"
    return os.path.join(STATE_DIR, name)


def open_machine(
    model: str, card: int = 0, overseas: bool = False, norom: bool = False, basic: bool = True
):
    """起動のときと同じに本体を作る。ROMがないか、noromならROMなしで作り、basicならROMなしの
    BASICを付ける。(本体, ROMなしか)を返す"""
    if not norom:
        try:
            return new_machine(model, card, overseas), False
        except RomNotFound:
            pass
    m = new_machine(model, card, overseas, rom=False)
    norom_hle.fill_data(m)
    if basic and m.model.name in norom_basic.MODELS:  # ROMなしのBASIC
        norom_hle.install(m)
        norom_basic.attach(m)
    return m, True


def bench_file(ram: str) -> str:
    """終了したときに、RAMと一緒に作業欄の情報(開始番地、ブレークポイント、書いた範囲)を保存する
    ファイル"""
    return os.path.splitext(ram)[0] + "-bench.json"


def saved_info(ram: str) -> object:
    """終了したときにRAMと一緒に保存した情報(作業欄の状態とRAMの終わり)。なければNone"""
    try:
        with open(bench_file(ram), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def apply_ram_top(m, info: object) -> None:
    """保存した情報のRAMの終わりに動かす(RAMを読む前に、同じ大きさにしておく)"""
    top = info.get("ram_top") if isinstance(info, dict) else None
    if type(top) is int and m.ram_top_ok(top):
        m.set_ram_top(top)


def view_file() -> str:
    """作業欄の見え方(内部RAMを開いておくか)と、メニューで選んだ画面の言語を覚えておくファイル"""
    return os.path.join(STATE_DIR, "bench-view.json")


def state_file(model: str = "1251", card: int = 0, norom: bool = False) -> str:
    """どこでもセーブの保存先(機種とRAMカードごとに1つ。ROMなしは別)"""
    name = f"{model}-{card}k" if card else model
    return os.path.join(STATE_DIR, f"state-{name}{'-norom' if norom else ''}.json")


# そのまま押しっぱなしで伝えるキー
DIRECT = {
    pygame.K_RETURN: "ENTER",
    pygame.K_KP_ENTER: "ENTER",
    pygame.K_SPACE: "SPC",
    pygame.K_UP: "UP",
    pygame.K_DOWN: "DOWN",
    pygame.K_LEFT: "LEFT",
    pygame.K_RIGHT: "RIGHT",
    pygame.K_TAB: "SHIFT",
    pygame.K_LALT: "DEF",
    pygame.K_RALT: "DEF",
    pygame.K_DELETE: "CL",
}
# PC-1350で名前の違うキー。DeleteとInsertはDELとINS、HomeはCLS。
# カナキーはパソコンにないので、F6の隣のF8に置く
DIRECT_1350 = {
    pygame.K_DELETE: "DEL",
    pygame.K_INSERT: "INS",
    pygame.K_HOME: "CLS",
    pygame.K_F8: "KANA",
}
DIGITS = {}
for _i in range(10):
    DIGITS[getattr(pygame, f"K_{_i}")] = str(_i)
    DIGITS[getattr(pygame, f"K_KP{_i}")] = str(_i)
LETTERS = {getattr(pygame, f"K_{_c}"): _c.upper() for _c in "abcdefghijklmnopqrstuvwxyz"}
# 矢印キーを数字キーの8・2・4・6として押すモード(テンキーのないパソコン用)
NUMPAD_ARROWS = {pygame.K_UP: "8", pygame.K_DOWN: "2", pygame.K_LEFT: "4", pygame.K_RIGHT: "6"}
# 記号はキーボードの配列で位置が違うので、打たれた文字(TEXTINPUT)で受けてキー操作に直す
PAD_EVENTS = (
    pygame.CONTROLLERDEVICEADDED, pygame.CONTROLLERDEVICEREMOVED, pygame.CONTROLLERBUTTONDOWN,
    pygame.CONTROLLERBUTTONUP, pygame.CONTROLLERAXISMOTION,
)  # fmt: skip

MAC = sys.platform == "darwin"
CMD = "⌘" if MAC else "Ctrl+"  # 画面に出すショートカットの修飾キー
SHIFT = "⇧" if MAC else "Shift+"
MIN_SCALE = 0.35  # 拡大率のいちばん小さい値(画面に合わせて縮めるときも、これより縮めない)
# 録画の形(recorder.SHAPES)の名前
REC_SHAPE_NAMES = {
    "both": Text("app.rec_lcd_and_body"),
    "body": Text("app.rec_body_only"),
    "lcd": Text("app.rec_lcd_only"),
}
# 割り当ての出どころのID(状態のファイルに書く。gamepad.PadMap.origin)
PAD_SOURCES = ("app.saved", "app.saved_default", "app.factory_mapping", "app.pad")


def speed_label(speed: float) -> str:
    return "×1/2" if speed == 0.5 else f"×{speed}"


def switch_label(name: str) -> str:
    """メニューのスイッチの項目(●をつける項目を、この名前で見分ける)"""
    return tr("app.switch", name=name)


def break_message(addr: int, on: bool) -> str:
    """ブレークポイントを設定した(on)か解除したときのメッセージ"""
    if on:
        return tr("app.breakpoint_set", addr=addr)
    return tr("app.breakpoint_removed", addr=addr)


# 表示・入力のメニューの、言語を切り替える項目の名前(切り替えた先の言語で書く)
LANGUAGE_NAMES = {"ja": "日本語", "en": "English"}


def help_lines(norom: bool = False, is1350: bool = False) -> list[str]:
    """キーの説明。パソコンのキーとポケコンのキーで対応が違うものだけを書く(英数字、記号、
    Enter、矢印、Spaceはそのまま打てるので書かない)。エミュレータの操作は操作欄のメニューに
    出る。ROMなしでは作業欄のキー"""
    c, s = CMD, SHIFT
    if norom:
        return [
            tr("app.workbench_without_rom_right"),
            tr("app.0_9_f_write"),
            tr("app.g_run_continue_g",
               c=c, s=s),
            tr("app.j_step_j_step", c=c, s=s),
            tr("app.v_paste_dump_listing",
               c=c, s=s),
            tr("app.pageup_pagedown_one_screen", c=c),
            tr("app.e_export_hex_e",
               c=c, s=s),
            tr("app.click_range_line_type", c=c),
            tr("app.while_running_keys_go"),
        ]  # fmt: skip
    head = tr("app.keys_differ_pocket_computer")
    arrows = tr("app.k_arrow_keys_press", c=c)
    menus = tr("app.emulator_commands_menus_bar")
    if is1350:
        return [
            head,
            tr("app.tab_shift_option_alt"),
            tr("app.delete_del_insert_ins"),
            tr("app.f1_f2_run_pro",
               c=c),
            arrows,
            menus,
        ]  # fmt: skip
    return [
        head,
        tr("app.tab_shift_option_alt_windows"),
        tr("app.backspace_delete_character_shift"),
        tr("app.f1_f4_mode_switch", c=c),
        arrows,
        menus,
    ]


def export_program(m, folder: str, prog: "programs.Program | None" = None) -> str | None:
    """BASICのプログラムを「名前-日時.bas」に書き出してパスを返す。なければNone

    progは最後に読み込んだプログラム。その名前を使い、組になっていたダンプなどの指示を
    書き写す(RAMのマシン語は書き出さない)。機種のフォルダにあったものなら、folderの中の
    同じ名前のフォルダに書く。
    """
    body = basictext.program_text(
        m.mem, basic_keywords(m), start=m.program_start(), pc1261=pc1261_basic(m)
    )
    if not body:
        return None
    name = prog.name if prog else "program"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    when = time.strftime("%Y-%m-%d %H:%M")
    title = prog.title if prog else "BASIC"
    head = ["# title: " + tr("app.exported", title=title, when=when)]
    if prog:
        head += programs.header_lines(prog)
    where = programs.folder_model(prog.paths[0]) if prog and prog.paths else ""
    if where:
        folder = os.path.join(folder, programs.model_dir(where))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{name}-{stamp}.bas")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(head) + "\n" + body)
    return path


class DumpError(ValueError):
    """--loadのダンプが読めない(エラーのある行がある)。メッセージはその行の説明"""


def parse_hexdump(path: str) -> list[tuple[int, bytes]]:
    """16進ダンプのファイルを読む(形はprograms.parse_hexと同じ)。ファイルがなければ
    FileNotFoundError。エラーのある行が1つでもあればDumpErrorで、何も書かない(一覧から
    読み込むときと同じに、全体を断る)"""
    if not os.path.isfile(path):
        raise FileNotFoundError(tr("app.not_found", name=path))
    try:
        text = open(path, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError) as e:
        raise DumpError(f"{path}: {e}") from e
    blocks, errors = programs.parse_hex(text, os.path.basename(path) + " ")
    if errors:
        raise DumpError("\n".join(errors))
    return blocks


def opaque(surf: pygame.Surface) -> pygame.Surface:
    """アルファのない24ビットのコピー。ウィンドウと同じ形式の絵は、アルファの成分が意味のない値の
    ことがあり、そのままPNGにすると透けてしまう"""
    out = pygame.Surface(surf.get_size(), 0, 24)
    out.blit(surf, (0, 0))
    return out


def _short(path: str) -> str:
    home = os.path.expanduser("~")
    return "~" + path[len(home) :] if path.startswith(home) else path


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("sc61box")
    except PackageNotFoundError:
        return "?"


class App:
    def __init__(self, args: Options):
        # 頼んだ形式(モノラル44.1kHz)で開き、装置への変換はSDLにまかせる
        # (2チャンネルで開かれると、渡した列が2倍の速さで鳴る)
        pygame.mixer.pre_init(RATE, -16, 1, 512, allowedchanges=0)
        i18n.set_language(i18n.choose(args.lang, self._view_pref("lang")))
        model = args.model
        card = args.card if MODELS[model].family == "1350" else 0
        # ROMがなければROMなしで動かし、マシン語の作業欄を出す
        self.m, norom = open_machine(model, card, args.overseas, args.norom, args.basic)
        self.is1350 = self.m.model.family == "1350"
        self.norom = norom
        # ROMもROMなしのBASICもない本体(作業欄だけでマシン語を動かす)
        self.bench_only = norom and self.m.basic is None
        # マシン語の作業欄。ROMなしではいつも右に出し、ROMがあればメニューで出し入れする
        self.bench = workbench.Bench(self.m)
        pygame.init()
        self.bench_view = benchview.BenchView(self.bench, load_help_font(15), CMD, SHIFT)
        # 作業欄は、ROMなしで作業欄だけのときはいつも出し、ほかは前に出していたときだけ出す
        self.pane_open = self.bench_only or self._view_pref("show_pane") is True
        self.bench_at = 0  # 作業欄の右クリックのメニューで扱う番地
        # ウィンドウの名前に、ROMのBASICか、ROMなしのBASICか、ROMなしで作業欄だけかを出す
        # (画面の言語によらず英語で書く)
        if not norom:
            how = "ROM BASIC"
        elif self.bench_only:
            how = "no ROM, workbench only"
        else:
            how = "ROM-less BASIC"
        pygame.display.set_caption(f"{self.m.model.title} ({how})")
        try:  # ウィンドウとDockのアイコン(assets/icon.png)
            pygame.display.set_icon(pygame.image.load(os.path.join(display.ASSETS, "icon.png")))
        except (pygame.error, FileNotFoundError):
            pass
        self.out_w, self.out_h = display.out_size(model)
        pane = benchview.PANE_W if self.pane_open else 0
        # 指定された拡大率(画面に入らなければ、これより縮める)。0や負の数、NaNなら、画面に
        # 合わせて縮めるときのいちばん小さい率にする(ウィンドウが作れずに落ちないように)
        self.want_scale = args.scale if args.scale >= MIN_SCALE else MIN_SCALE
        self.scale = self._fit(self.want_scale, self.out_w, self.out_h, pane, BAR_H)
        self.body_size = (int(self.out_w * self.scale), int(self.out_h * self.scale))
        self.font: pygame.font.Font | None = None
        self.small_font: pygame.font.Font | None = None
        # プリンタはいつもつないでおき、印字したときだけ紙を出す
        self.m.connect_printer()
        self.paper = Paper(load_font())
        self.printout: Printout | None = None  # 出している紙(しまっていればNone)
        self.print_cut = (0, 0)  # 次の紙の始まり(Printout.cut)
        self.paper_back = 0  # 紙を何行さかのぼって見せているか
        self.printed = 0  # 紙に出した行の数(印字は1行ずつ出す。check_printer)
        self.print_gap = 0  # 行を出し終えてから次の行を出すまでの残りのフレーム
        self.print_rate = 1.0  # 紙送りが実機の何倍の速さか(プリンタの音の速さ)
        self.print_hold = 0.0  # 溜まった行を速めて出しているときの速さ(出し切るまで保つ)
        self.paper.line_frames = round(PRINT_LINE * FPS)
        self.print_seen = 0  # 紙に反映したときのprinter.changes
        self.pads = gamepad.Pads()
        self.pad_map = self.pad_map_for(None)
        self.pad_dirty = False  # 割り当てに保存していない変更があるか
        self.pad_note = ""  # 読み込んだプログラムの# pad: の読めない語のメッセージ
        self.pad_down: dict[str, str] = {}  # パッドの入力(pad1:aなど)ごとに、押したときのキー
        self.pad_panel: padmenu.PadPanel | None = None  # 出していればゲームパッドの割り当ての画面
        # 割り当ての対象のプログラム。last_progと違い、.hexだけのプログラムでも替わる
        self.pad_prog: programs.Program | None = None
        self.bench_view.show_iram = self._iram_shown()
        self.window = pygame.display.set_mode(self._window_size())
        self.bar = Bar([])
        self.rec_paused = False
        self.panel = display.Panel(model)
        self.panel.set_fps(FPS, args.persist)
        self.panel.set_packed(self._view_pref("packed_lcd") is True)
        self.scaled_body: pygame.Surface | None = None  # 拡大・縮小の結果を置く独立した面
        self.lcd_only = False  # 本体の絵を隠して、液晶だけを見せているか
        self.pane_before_lcd = False  # 液晶だけにする前に作業欄を出していたか
        self.free_size: tuple[int, int] | None = (
            None  # 液晶だけのとき、利用者が変えたウィンドウの大きさ
        )
        self.origin = (
            0,
            0,
        )  # ウィンドウの中で中身を描く位置(ウィンドウが中身より大きいとき、まんなかに)
        self.win_flags = 0  # ウィンドウを作ったときのフラグ(液晶だけのときはRESIZABLE)
        self.window_stale = False  # ウィンドウの大きさが外から変わったので、表示面を作り直すか
        self.laid_out = (0, 0)  # 最後に中身を置いたときのウィンドウの大きさ(利用者が変えたか見る)
        self.laid_content = (0, 0)  # そのときの中身の大きさ
        self.sw_stops = self.panel.switch_stops  # スイッチの段(上から)と、その中心のy
        self.ram_file = ram_file(model, card, norom)
        self.state_file = state_file(model, card, norom)
        self.typer = Typer(self.m, self.set_mode)
        self.typer.on_write = self.write_dump
        self.fast = False  # 読み込み中は時計に合わせず全速で動かす
        self.menu: ProgramMenu | None = None
        self.status = ""  # 画面の下に出すメッセージ
        self.status_until = 0.0
        # ウィンドウの左上に、次にキーを押すか、クリックするまで出す注意。IDと値で持ち、出すときに
        # 訳す(warning)
        self._warning: str | Text = ""
        self.warning_rect = pygame.Rect(0, 0, 0, 0)  # 注意を描いた範囲(中身の中の位置)
        self.tape_out = tape.TapeOut()  # CSAVEの音を監視してwavに書き出す
        self.loading = ""
        self.load_help = ""  # 読み込み終わりに出す説明(# help:)
        self.undo_state: dict | None = None  # 最後にプログラムを読み込む直前の状態
        self.undo_title = ""
        # 読み込む直前の(last_prog, loading, load_help, pad_prog, pad_map, pad_dirty)
        self.undo_prog: tuple = (None, "", "", None, self.pad_map, False)
        self.undo_bench: dict | None = None  # 読み込む直前の作業欄
        self.load_total = 1
        self.load_typing = False  # 打ち込みで入れているところか(進み具合の表示用)
        self.popup: Popup | None = None  # 右クリックのメニュー
        self.reset_frames = 0  # RESETボタンを押している残りのフレーム
        self.speaker = None if args.mute else audio.open_output()
        self.buzzer = Buzzer()
        self.print_sound = PrinterSound()
        self.recorder: recorder.Recorder | None = None
        self.rec_buzzer = Buzzer()  # 録画の音は鳴らす音とは別に作る
        self.rec_print_sound = PrinterSound()
        self.overshoot = 0  # 前のフレームで進みすぎたサイクル
        self.closing = False  # ウィンドウを閉じる操作があった(run)
        self.rush_spans: list[tuple[int, int]] = []  # このフレームで速く回したサイクルの範囲
        # このフレームのあいだに中身が変わった液晶の列と、その列の各ドットが点いていた時間の
        # 割合(_lcd_duty)。列の番号は、その列の液晶RAMの番地から引く
        self.lcd_duty: dict[int, list[float]] = {}
        self.lcd_was_on = False  # フレームの初めに液晶を点けていたか
        self.lcd_any_on = False  # このフレームのあいだに液晶を点けていたことがあるか
        self.lcd_cols: dict[int, list[int]] = {}
        for i, a in enumerate(self.m.column_addrs()):
            self.lcd_cols.setdefault(a, []).append(i)
        self.turbo: float = 1  # 速さの倍率(SPEEDSのどれか)
        self.numpad_arrows = args.numpad
        self.dragging_switch = False
        self.mouse_key: str | None = None
        self.brk_by: set[str] = set()  # BRKキーを押している入力元(EscキーとマウスでBRK)
        self.help = 0  # キーの説明を出しておく残りのフレーム
        if self.bench_only:
            self.say(tr("app.no_rom_found_so"), 8)
        elif norom:
            self.say(tr("app.no_rom_so_running"), 8)
        else:
            self.say(tr("app.use_buttons_bar_below", c=CMD), 8)
        if args.moved_data:
            self.say(
                tr(
                    "app.moved_data_folder_sc61box",
                    old=args.moved_data,
                ),
                10,
            )
        notices = routines.notices()
        if notices and self.m.norom:
            self.say(tr("app.rom_routine_stand_ins", text=notices[0]), 10)
        self.save_ram = not args.fresh
        info = saved_info(self.ram_file) if self.save_ram else None
        apply_ram_top(self.m, info)
        if self.save_ram and self.m.load_ram(self.ram_file):
            self.m.cpu.reset()
            self.bench.prev_regs = bytes(self.m.cpu.ram)
            self._load_bench_info(info)
        self.boot_frames = FPS  # 起動してから貼り付けを始めるまで
        if args.type:
            if not os.path.isfile(args.type):
                raise FileNotFoundError(tr("app.not_found", name=args.type))
            self.typer.add_text(open(args.type, encoding="utf-8").read())
        self.pending: tuple[programs.Program, bool] | None = None
        self.last_prog: programs.Program | None = None  # 書き出しと録画の題名に使う
        if args.tape:
            self.insert_tape(args.tape)
        if args.state:
            self.load_state(args.state)
        if args.program:
            prog = programs.find(args.program, self.m.model.name)
            if prog is None:
                raise FileNotFoundError(tr("app.not_found", name=args.program))
            self.pending = (prog, args.run)
        # --loadのダンプは起動の待ちのあとで書くが、読めるかは先に調べる
        self.load_blocks = parse_hexdump(args.load) if args.load else None
        if args.lcd:
            self.toggle_lcd(True)
        pygame.key.set_repeat()  # リピートは作業欄だけで、自分で数える(_key_repeat)
        # 作業欄で押し続けているキーと、次にリピートする時刻
        self.held_key: tuple[object, float] | None = None
        pygame.key.start_text_input()

    @staticmethod
    def _fit(
        scale: float,
        out_w: int = display.OUT_W,
        out_h: int = display.OUT_H,
        pane: int = 0,
        below: int = 0,
    ) -> float:
        """拡大率。画面に収まらなければ縮める(paneは右に足す作業欄の幅、belowは本体の下に
        足す操作欄などの高さ。どちらも拡大率によらない画素数)"""
        try:
            dw, dh = pygame.display.get_desktop_sizes()[0]
        except (pygame.error, IndexError):
            return scale
        room = min((dw - 80 - pane) / out_w, (dh - 120 - below) / out_h)
        return min(scale, max(MIN_SCALE, room))

    LCD_MARGIN = 26  # 液晶だけのとき、液晶の枠のまわりに見せる本体の絵(拡大前の画素)

    def view_box(self) -> pygame.Rect:
        """本体の絵のうちウィンドウに出す範囲。液晶だけのときは、録画で拡大するのと同じ液晶の枠に、
        まわりの本体の絵を少し足したもの(ウィンドウの縁に液晶がくっつかないように)"""
        if not self.lcd_only:
            return pygame.Rect(0, 0, self.out_w, self.out_h)
        x0, y0, x1, y1 = self.panel.lcd_box()
        m = 2 * self.LCD_MARGIN
        box = pygame.Rect(x0, y0, x1 - x0, y1 - y0).inflate(m, m)
        return box.clip(pygame.Rect(0, 0, self.out_w, self.out_h))

    def _refit(self) -> None:
        """本体の下に足すもの(プリンタの紙、割り当ての欄、操作欄)と右の作業欄も合わせて画面に
        入るように、本体の拡大率を決め直してウィンドウを作り直す(すべてしまえば、指定された拡大率まで
        戻る)。割り当ての欄の高さは本体の幅で増えも減りもするので、決めた幅で測った高さが
        見込みを超えるあいだ、見込みを増やして決め直す。液晶だけのときは、本体を出すときと
        同じ幅に液晶を広げる。利用者がウィンドウの大きさを変えていれば(free_size)、その中に
        入る大きさにしてウィンドウはそのままにする"""
        pane = benchview.PANE_W if self.pane_open else 0
        vw, vh = self.view_box().size
        want = self.want_scale * self.out_w / vw
        free = self.free_size
        panel_h = 0
        for _ in range(10):
            below = BAR_H + panel_h
            if self.paper_open:
                below += self.paper.height
            if free is not None:
                # 利用者が決めた大きさに入れる。ただし操作欄のボタンが入る幅と液晶の最低の
                # 高さは保ち、紙や割り当ての欄を出して入らなくなれば、そのぶんウィンドウを広げる
                fw, fh = free
                mw, mh = self._min_size(below)
                scale = min((fw - pane) / vw, (fh - below) / vh)
                self.scale = max(scale, (mw - pane) / vw, (mh - below) / vh)
                bw, bh = int(vw * self.scale), int(vh * self.scale)
                self.free_size = (max(fw, bw + pane), max(fh, bh + below))
            else:
                self.scale = self._fit(want, vw, vh, pane, below)
            self.body_size = (int(vw * self.scale), int(vh * self.scale))
            measured = self._pad_panel_height()
            if measured <= panel_h:
                break
            panel_h = measured
        self._open_window()

    MENU_ROOM = 420  # 液晶だけの細いウィンドウで一覧やメニューを開くあいだ、ウィンドウを広げる高さ

    def _open_window(self, room: bool | None = None) -> None:
        """ウィンドウを中身の大きさ(利用者が変えていればその大きさ)で作り直す。液晶だけのときは
        大きさを変えられるウィンドウにし、一覧やメニューを開いているあいだ(room)は、入るだけの高さに
        広げる。中身より大きければ、中身はまんなかに描く"""
        content = self._window_size()
        size = self.free_size if self.free_size is not None else content
        if room is None:
            room = self.menu is not None or self.popup is not None or bool(self.help)
        if self.lcd_only and room:
            size = (size[0], max(size[1], self.MENU_ROOM))
        flags = pygame.RESIZABLE if self.lcd_only else 0
        if self.window_stale or size != self.window.get_size() or flags != self.win_flags:
            # 大きさが外から変わったあと(全画面から戻ったときなど)は、同じ大きさでも作り直す。
            # pygameが用意した現在の表示面を取り直す。
            self.window = pygame.display.set_mode(size, flags)
            self.win_flags = flags
            self.window_stale = False
        self.laid_out, self.laid_content = size, content
        self.origin = (max(0, (size[0] - content[0]) // 2), max(0, (size[1] - content[1]) // 2))

    def _min_size(self, below: int | None = None) -> tuple[int, int]:
        """ウィンドウの大きさの下限(操作欄のボタン、作業欄、本体の下に足したものが入る大きさ)。
        belowは本体の下に足すものの高さ(なければ測る)"""
        pane = benchview.PANE_W if self.pane_open else 0
        if below is None:
            below = self._window_size()[1] - self.body_size[1]
        width = max(320, Bar.min_width(self._font(), self.bar_buttons()))
        if self.pad_panel is not None:
            width = max(width, 480)
        return pane + width, below + 40

    def toggle_lcd(self, on: bool | None = None) -> None:
        """本体の絵を隠して液晶だけにする・本体を出す"""
        on = not self.lcd_only if on is None else on
        if on == self.lcd_only:
            return
        self.release_all()
        if on:
            # 液晶だけのあいだは作業欄を出さない(細いウィンドウに合わない)。戻るときに元に戻す
            self.pane_before_lcd = self.pane_open
            self.pane_open = False
        else:
            self.pane_open = self.pane_before_lcd
        # ROMなしでも一時的に隠す。通常表示での作業欄の設定は書き換えない。
        self.bench_view.focus = False
        self.lcd_only = on
        self.free_size = None
        self._refit()

    def _track_window(self) -> None:
        """表示面を取り直す(pygameが作り直していれば、そちらに描く)"""
        win = pygame.display.get_surface()
        if win is not None and win is not self.window:
            self.window = win

    def resized(self, w: int, h: int) -> None:
        """ウィンドウの大きさが外から変わった(利用者の操作、最大化、全画面の出入り)。液晶だけのときは
        その大きさに合わせて置き直す。どの場合も表示面は作り直す(_open_window)"""
        self._track_window()
        self.window_stale = True
        if self.lcd_only and (w, h) != self.laid_out:
            mw, mh = self._min_size()
            self.free_size = (max(w, mw), max(h, mh))  # 小さくしすぎたら、下限まで戻す
            self._refit()
        else:
            self._open_window()

    def _make_room(self) -> tuple[int, int]:
        """一覧やメニューを出す前にウィンドウを広げ、中身の位置のずれを返す(出す位置を直すため)"""
        bx, by = self.origin
        self._open_window(room=True)
        return self.origin[0] - bx, self.origin[1] - by

    # ---- キー ----
    def key_down(self, ev) -> None:
        m = self.m
        mods = ev.mod
        self.warning = ""  # 注意は、次にキーを押すと消す
        if self.menu is not None:
            self.menu_key(ev)
            return
        if self.popup is not None:
            self.popup_key(ev)
            return
        cmd = mods & (pygame.KMOD_META | pygame.KMOD_CTRL)
        if self.pad_panel is not None and not cmd:
            self.pad_key(ev)
            return
        if cmd and self.shortcut(ev.key, mods):
            return
        if self.pad_panel is not None:
            return
        if self.pane_keys():
            # キーを作業欄の打ち込みに使う(本体のキーには送らない)
            if not mods & (pygame.KMOD_META | pygame.KMOD_CTRL):
                self.bench_key(ev)
                # 押し続けたカーソルのキーはリピートする(ほかのキーを押したらやめる)
                at = time.monotonic() + self.REPEAT[0]
                self.held_key = (ev, at) if ev.key in self.REPEAT_KEYS else None
            return
        actions = {
            pygame.K_F6: self.open_menu,
            pygame.K_F7: self.toggle_arrows,
            pygame.K_F9: lambda: self.change_speed(-1 if mods & pygame.KMOD_SHIFT else 1),
            pygame.K_F10: self.toggle_help,
            pygame.K_F12: self.screenshot,
        }
        if ev.key in actions:
            actions[ev.key]()
            return
        if ev.key == pygame.K_ESCAPE and self.fast:  # 読み込みの途中ならやめる
            self.cancel_loading()
            return
        if ev.key == pygame.K_ESCAPE:
            self.press_brk("key")
            return
        if ev.key == pygame.K_F5:
            self.press_reset()
            self.reset_frames = 0  # F5は離したときに離す
            return
        fkeys = {pygame.K_F1: "RUN", pygame.K_F2: "PRO", pygame.K_F3: "RSV", pygame.K_F4: "OFF"}
        if ev.key in fkeys:
            mode = fkeys[ev.key]
            if self.is1350:  # F1・F2はMODEキーでRUN・PROに、F3・F4は電源スイッチ
                mode = "ON" if mode == "RSV" else mode
                if mode in ("RUN", "PRO"):
                    self.typer.add_mode(mode)
                else:
                    self.set_mode(mode)
            elif mode in m.model.modes:  # PC-1245にはRSVがない
                self.set_mode(mode)
            return
        if ev.key == pygame.K_BACKSPACE:
            if self.is1350:
                self.typer.add_live_keys([["LEFT"], ["DEL"]])
            else:
                self.typer.add_live_keys([["LEFT"], ["SHIFT"], ["LEFT"]])
            return
        if mods & (pygame.KMOD_META | pygame.KMOD_CTRL):
            return
        name = self.key_name(ev.key)
        if name is None and not mods & pygame.KMOD_SHIFT:
            name = DIGITS.get(ev.key)  # Shift付きの数字キーは記号になる
        if name:
            self.typer.press_live(name, ev.key)

    def key_name(self, key: int) -> str | None:
        """パソコンのキーを本体のキーの名前にする(数字キーを除く)"""
        if self.numpad_arrows and key in NUMPAD_ARROWS:
            return NUMPAD_ARROWS[key]
        if self.is1350 and key in DIRECT_1350:
            return DIRECT_1350[key]
        return DIRECT.get(key) or LETTERS.get(key)

    def key_up(self, ev) -> None:
        m = self.m
        if self.held_key is not None and getattr(self.held_key[0], "key", None) == ev.key:
            self.held_key = None
        if ev.key == pygame.K_ESCAPE:
            self.release_brk("key")
        elif ev.key == pygame.K_F5:
            m.reset_key = False
        name = self.key_name(ev.key) or DIGITS.get(ev.key)
        if name:
            self.typer.release_live(name, ev.key)
        if ev.key in NUMPAD_ARROWS:  # 押しているあいだにモードを切り替えたとき
            self.typer.release_live(DIRECT[ev.key], ev.key)
            self.typer.release_live(NUMPAD_ARROWS[ev.key], ev.key)

    def text_input(self, text: str) -> None:
        menu = self.menu
        if menu is not None:  # 一覧では「/」で探し始め、そのあとの字で絞る
            if menu.query is not None:
                menu.search(menu.query + text)
            elif text == "/":
                menu.search("")
            return
        if self.popup is not None:
            return
        panel = self.pad_panel
        if panel is not None:
            # 記号のキーは打った字で割り当てる。英数字はKEYDOWNで割り当てている
            alnum = text.isascii() and text.isalnum()
            if panel.selected is not None and not alnum and text in self.pad_key_names():
                self.pad_assign(text)
            return
        if self.pane_keys():
            return  # 作業欄の打ち込みはKEYDOWNで受けている
        # KEYDOWNで押しっぱなしとして伝えた英数字と空白を除いて、まとめて打つ
        rest = "".join(ch for ch in text if not (ch.isascii() and (ch.isalnum() or ch == " ")))
        if rest:
            self.typer.add_live_keys(keys_for(rest, self.m.model.name))

    # ---- ゲームパッド ----
    @staticmethod
    def pad_file(prog: "programs.Program | None") -> str:
        """保存した割り当てのファイル。progがNoneなら既定(pads/default.json)。プログラム用は
        pads/programs/の中に、プログラムのフォルダと同じく機種のフォルダで分けて置く"""
        pads = os.path.join(programs.user_dir(), "pads")
        if prog is None:
            return os.path.join(pads, "default.json")
        model = programs.folder_model(prog.paths[0]) if prog.paths else ""
        sub = programs.model_dir(model) if model else ""
        return os.path.join(pads, "programs", sub, f"{prog.name}.json")

    def pad_map_for(self, prog: "programs.Program | None") -> gamepad.PadMap:
        """プログラムprogを読み込んだときの割り当て。自分でそのプログラム用に保存したもの、
        プログラムの# pad:、自分で保存した既定、初期設定の順"""
        if prog is not None:
            saved = gamepad.PadMap.load(self.pad_file(prog), Text("app.saved", name=prog.name))
            if saved is not None:
                return saved
            if prog.pad is not None:
                return self.pad_map_of(prog)
        default = gamepad.PadMap.load(self.pad_file(None), Text("app.saved_default"))
        return (
            default if default is not None else gamepad.PadMap(source=Text("app.factory_mapping"))
        )

    def pad_key_names(self) -> frozenset[str]:
        """この機種で割り当てられるキーの名前"""
        return gamepad.key_names(self.m.model.family)

    def pad_map_of(self, prog: programs.Program) -> gamepad.PadMap:
        """プログラムの# pad: の割り当て。読めない語(この機種にないキーも)があれば知らせる"""
        source = Text("app.pad", name=prog.title or prog.name)
        found, bad = gamepad.PadMap.parse(prog.pad or "", source, self.pad_key_names())
        self.pad_note = tr("app.cannot_read_pad", text=" ".join(bad)) if bad else ""
        if bad:
            self.say(self.pad_note, 6)
        return found

    def set_pad_map(self, pad_map: gamepad.PadMap) -> None:
        """割り当てを替える。押しているパッドの入力は、前の割り当てのキーで離す"""
        self.pad_release_all()
        self.pad_map = pad_map
        self.pad_dirty = False
        self._pad_fit()

    def pad_event(self, ev) -> None:
        """ゲームパッドのイベント。割り当ての画面を出しているあいだは入力を選ぶだけで、
        本体には送らない"""
        for name, iid, pressed in self.pads.handle(ev):
            if self.pad_panel is not None:
                if pressed:
                    self.pad_panel.selected = name
                continue
            self.pad_press(name, iid, pressed)

    def pad_press(self, name: str, iid: int, pressed: bool) -> None:
        """パッドの入力nameを押した・離した。離すときは、押したときに割り当てていたキーを離す
        (そのあいだに割り当てが変わっていても)"""
        source = f"pad{iid}:{name}"
        if pressed:
            key = self.pad_map.get(name)
            if key is None:
                return
            self.pad_down[source] = key
            if key == "BRK":
                self.press_brk(source)
            else:
                self.typer.press_live(key, source)
            return
        key = self.pad_down.pop(source, None)
        if key == "BRK":
            self.release_brk(source)
        elif key is not None:
            self.typer.release_live(key, source)

    def pad_release_all(self) -> None:
        for name, iid, _ in self.pads.release_all():
            self.pad_press(name, iid, False)

    def pad_sync(self) -> None:
        """イベントを受け取れなかった回のあと、外れたパッドの入力を離す"""
        for name, iid, _ in self.pads.sync():
            self.pad_press(name, iid, False)

    def toggle_pad_panel(self, on: bool | None = None) -> None:
        """割り当ての画面を本体の下に出す・しまう(ウィンドウの高さが変わる)"""
        on = self.pad_panel is None if on is None else on
        if on == (self.pad_panel is not None):
            return
        self.release_all()
        self.pad_panel = padmenu.PadPanel() if on else None
        self._refit()

    def _pad_fit(self) -> None:
        """割り当ての欄の中身が変わったあと、欄の高さが変わっていればウィンドウを作り直す"""
        if self.pad_panel is not None and self.laid_content != self._window_size():
            self._refit()

    def _pad_panel_height(self) -> int:
        """割り当ての画面の高さ(出していなければ0)"""
        panel = self.pad_panel
        if panel is None:
            return 0
        return panel.measure(
            self._font(), self._small_font(), self.body_size[0], self.pads.names(), self.pad_map,
            *self._pad_target(),
        )  # fmt: skip

    def _pad_target(self) -> tuple[str | None, bool]:
        """割り当ての欄に出す対象のプログラムの題名(なければNone)と、# pad: の行があるか
        (値のない行も含める)"""
        prog = self.pad_prog
        if prog is None:
            return None, False
        return prog.title or prog.name, prog.pad is not None

    def pad_assign(self, key: str | None) -> None:
        """選んである入力にキーを割り当てる(Noneなら外す)。割り当てたら入力の選択を解除する"""
        panel = self.pad_panel
        if panel is None or panel.selected is None:
            return
        self.pad_release_all()
        self.pad_map.set(panel.selected, key)
        self.pad_dirty = True
        panel.selected = None
        self._pad_fit()

    def pad_key(self, ev) -> None:
        """割り当ての画面を出しているあいだのキー"""
        panel = self.pad_panel
        assert panel is not None
        if ev.key == pygame.K_ESCAPE:
            if panel.selected is None:
                self.toggle_pad_panel(False)
            panel.selected = None
            return
        if panel.selected is None:
            return
        if ev.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
            self.pad_assign(None)
            return
        name = DIRECT.get(ev.key) or LETTERS.get(ev.key)
        if name is None and not ev.mod & pygame.KMOD_SHIFT:
            name = DIGITS.get(ev.key)  # Shift付きの数字キーの記号はtext_inputで
        if self.is1350 and ev.key in DIRECT_1350:
            name = DIRECT_1350[ev.key]
        if name is not None:
            self.pad_assign(name)

    def pad_action(self, act: str) -> None:
        """割り当ての画面のボタン"""
        prog = self.pad_prog
        if act == "close":
            self.toggle_pad_panel(False)
        elif act == "reset":
            self.set_pad_map(gamepad.PadMap(source=Text("app.factory_mapping")))
        elif act == "from_prog":
            if prog is not None and prog.pad is not None:
                self.set_pad_map(self.pad_map_of(prog))
        elif act == "copy":
            self.set_clipboard(f"# pad: {self.pad_map.text()}".rstrip() + "\n")
            self.say(tr("app.copied_pad_line_clipboard"), 4)
        elif act in ("save_prog", "save_default"):
            if act == "save_prog" and prog is None:
                return
            path = self.pad_file(prog if act == "save_prog" else None)
            try:
                self.pad_map.save(path)
            except OSError as e:
                self.say(tr("app.cannot_save_mapping", error=e), 5)
                return
            if act == "save_default":
                self.pad_map.source = Text("app.saved_default")
            elif prog is not None:
                self.pad_map.source = Text("app.saved", name=prog.name)
            self.pad_dirty = False
            self.say(tr("app.saved_mapping", path=_short(path)), 5)
        self._pad_fit()

    def pad_click(self, pos) -> bool:
        """割り当ての画面を出しているあいだのクリック。画面の中なら入力かボタン、入力を選んで
        あれば本体の絵のキーをその入力に割り当てる。それ以外(操作欄など)ならFalseを返し、
        普通のクリックとして扱う"""
        panel = self.pad_panel
        assert panel is not None
        hit = panel.hit(pos)
        if hit is not None:
            kind, value = hit
            if kind == "input":
                panel.selected = None if panel.selected == value else value
            else:
                self.pad_action(value)
            return True
        if panel.top <= pos[1] < panel.top + panel.height and pos[0] < self.body_size[0]:
            return True
        if pos[1] >= self.body_size[1] or panel.selected is None or self.lcd_only:
            return False
        x = pos[0] / self.scale - display.MARGIN
        y = pos[1] / self.scale - display.MARGIN
        name = self.panel.key_at(x, y)
        if name is None:
            return False
        self.pad_assign(name)
        return True

    def set_clipboard(self, text: str) -> None:
        try:
            if not pygame.scrap.get_init():
                pygame.scrap.init()
            pygame.scrap.put(pygame.SCRAP_TEXT, text.encode("utf-8"))
            return
        except (pygame.error, NotImplementedError):
            pass
        cmds = {"darwin": ["pbcopy"], "win32": ["clip"]}
        cmd = cmds.get(sys.platform, ["xclip", "-selection", "clipboard"])
        try:
            subprocess.run(cmd, input=text, text=True, check=False)
        except OSError:
            pass

    # ---- ショートカットと右クリックのメニュー ----
    # Fキーはほかのアプリに取られることがあるので、同じ操作を⌘(Windows・LinuxはCtrl)との
    # 組み合わせと右クリックのメニューにも置く
    def shortcut(self, key: int, mods: int = 0) -> bool:
        if (self.bench_only or self.pane_keys()) and self.bench_shortcut(key, mods):
            return True
        actions = {
            pygame.K_o: self.open_menu,
            pygame.K_t: lambda: self.change_speed(-1 if mods & pygame.KMOD_SHIFT else 1),
            pygame.K_r: self.toggle_recording if mods & pygame.KMOD_SHIFT else self.press_reset,
            pygame.K_p: self.toggle_pause if mods & pygame.KMOD_SHIFT else self.toggle_halt,
            pygame.K_s: self.save_state if mods & pygame.KMOD_SHIFT else self.screenshot,
            pygame.K_l: self.load_state if mods & pygame.KMOD_SHIFT else None,
            pygame.K_e: self.export_program,
            pygame.K_v: self.paste,
            pygame.K_SLASH: self.toggle_help,
            pygame.K_k: self.toggle_arrows,
            pygame.K_d: None if self.bench_only else self.toggle_pane,
            pygame.K_UP: lambda: self.move_switch(-1),
            pygame.K_DOWN: lambda: self.move_switch(1),
        }
        act = actions.get(key)
        if act is None:
            return False
        act()
        return True

    # ---- マシン語の作業欄(ROMなし) ----
    def bench_shortcut(self, key: int, mods: int) -> bool:
        """作業欄の⌘(Ctrl)のショートカット。扱ったらTrue"""
        shift = bool(mods & pygame.KMOD_SHIFT)
        b, v = self.bench, self.bench_view
        if b.state != "run" or b.live:
            # ⌘↑↓(Ctrl+Home・End)で開始番地と書いた所の終わりへ、⌘←→で行の頭と終わりへ
            moves = {
                pygame.K_UP: lambda: b.go(b.start, v.rows),
                pygame.K_HOME: lambda: b.go(b.start, v.rows),
                pygame.K_DOWN: lambda: b.go_end(v.rows),
                pygame.K_END: lambda: b.go_end(v.rows),
                pygame.K_LEFT: b.row_home,
                pygame.K_RIGHT: b.row_end,
            }
            if key in moves:
                moves[key]()
                return True
        if b.start_buf is not None or b.span_buf is not None:
            # 開始番地か範囲の欄に打っているあいだ、貼り付けは欄へ入れる。全体にかかる⌘Aは
            # 使わず、⌘Zは欄に打った字を消す。ほかのショートカットは、欄をやめてから
            if key == pygame.K_v:
                if b.start_buf is not None:
                    self.bench_said(b.paste_start(self.clipboard()))
                else:
                    self.bench_said(b.paste_span(self.clipboard()))
                return True
            if key == pygame.K_z:
                if b.start_buf is not None:
                    b.start_buf = ""
                else:
                    b.span_buf = ""
                return True
            if key == pygame.K_a:
                return True
            b.start_buf = b.span_buf = None
        actions = {
            pygame.K_g: lambda: self.bench_do("runcursor" if shift else "go"),
            pygame.K_PERIOD: lambda: self.bench_do("pause"),
            pygame.K_j: lambda: self.bench_do("over" if shift else "step"),
            pygame.K_b: lambda: self.bench_do("break"),
            pygame.K_a: lambda: self.bench_start_at(b.cursor),
            pygame.K_v: self.bench_paste,
            pygame.K_e: lambda: self.bench_export(listing=shift),
            pygame.K_z: lambda: self.bench_undo(redo=shift),
        }
        act = actions.get(key)
        if act is None:
            return False
        act()
        return True

    def bench_do(self, what: str) -> None:
        """作業欄のボタンとショートカットの操作"""
        b, v = self.bench, self.bench_view
        if what == "go":
            what = "resume" if b.state == "pause" else "run"
        if what in ("run", "runcursor") and b.live:
            self.bench_call(what == "runcursor")
            return
        if what in ("run", "runcursor") and b.state == "run":
            return
        self.release_all()
        if what == "run":
            b.run()
        elif what == "runcursor":
            why = b.start_refusal(b.cursor)
            if why:
                v.say(why, 3)
                return
            b.set_start_at(b.cursor)
            b.run()
        elif what == "resume":
            b.resume()
        elif what == "pause":
            b.pause()
        elif what == "step":
            b.step()
        elif what == "over":
            b.step_over()
        elif what == "abandon":
            b.abandon()
        elif what in ("undo", "redo"):
            self.bench_undo(redo=what == "redo")
            return
        elif what == "break":
            a = b.ins_at(b.cursor)
            on = b.toggle_break(a)
            if on is None:
                v.say(
                    tr(
                        "app.not_usable_without_rom",
                        addr=a,
                    ),
                    3,
                )
            else:
                v.say(break_message(a, on), 2)
        self.overshoot = 0

    def bench_call(self, at_cursor: bool = False) -> None:
        """BASICのある本体の実行のボタン: BASICが次の行を打つキーを待っていれば、
        「CALL &開始番地」を打ってENTERを押したのと同じにする(at_cursorなら、カーソルの
        命令を開始番地にしてから)"""
        b, v, m = self.bench, self.bench_view, self.m
        if b.state == "pause":
            v.say(tr("app.paused_continue_first_then"), 3)
            return
        if at_cursor:
            said = b.set_start_at(b.ins_at(b.cursor))
            if not said.ok:
                v.say(said.text, 3)
                return
        if m.basic is not None:
            ok = m.basic.request_call(b.start)
        else:
            # ROMのBASICが行を打つのを待っているときだけ打つ。キーを待ってHALTしているのは、
            # PRINTやINPUTの待ちでも同じなので、液晶に>だけが出ていることも見る(PRINTの
            # 待ちでCLを打つと、プログラムを止めてしまう)
            ok = m.halted and m.mode in ("RUN", "PRO") and not self.typer.busy and shows_prompt(m)
            if ok:
                self.typer.add_text(f"CALL &{b.start:04X}\n")
        if ok:
            v.say(tr("app.typed_call", addr=b.start), 2, ok=True)
        elif m.basic is None:
            v.say(tr("app.press_cl_so_only"), 3)
        else:
            v.say(tr("app.press_while_basic_waiting"), 3)

    def bench_start_at(self, addr: int) -> None:
        """番地addrを開始番地に決める"""
        self.bench_said(self.bench.set_start_at(addr))

    def bench_said(self, said: workbench.Said) -> None:
        """開始番地か書き出す範囲を決める操作のメッセージを出す(決められたなら緑、理由なら赤)"""
        self.bench_view.say(said.text, 3, ok=said.ok)

    def bench_field_skip(self, ch: str) -> bool:
        """開始番地か範囲の欄に打っているあいだの、16進表記でない字。欄に打ったままにし
        (やめてダンプのキーにすると、続けて打った字がダンプを書き換える)、区切りの字
        (空白、-、~、,、&)でなければメッセージを出す。字でないキー(矢印など)ならFalse"""
        if len(ch) != 1 or not ch.isprintable():
            return False
        if ch not in " -~,&〜":
            self.bench_view.say(tr("app.type_addresses_hex_0"), 3)
        return True

    def bench_span_key(self, ev) -> None:
        """範囲の欄に打っているあいだのキー。始めと終わりの番地を16進表記で8桁打てば決まる。
        何も打たずにEnterで自動に戻す。Backspaceで1字消し、Escでやめる。ほかのキーの扱いは
        開始番地の欄と同じ"""
        b = self.bench
        k = ev.key
        ch = (ev.unicode or "").upper()
        if len(ch) == 1 and ch in "0123456789ABCDEF":
            said = b.type_span(int(ch, 16))
            if said.text:
                self.bench_said(said)
            return
        if k == pygame.K_BACKSPACE and b.span_buf:
            b.span_buf = b.span_buf[:-1]
            return
        if self.bench_field_skip(ch):
            return
        if k in (pygame.K_RETURN, pygame.K_KP_ENTER) and not b.span_buf:
            self.bench_view.say(b.clear_span(), 3, ok=True)
            return
        b.span_buf = None
        if k not in (pygame.K_ESCAPE, pygame.K_BACKSPACE, pygame.K_RETURN, pygame.K_KP_ENTER):
            self.bench_key(ev)

    def bench_start_key(self, ev) -> None:
        """開始番地の欄に打っているあいだのキー。16進表記の4桁を打てば決まる。Backspaceで
        1字消し、Escでやめる。16進表記でない字は欄で止め、字でないキー(矢印など)は、やめた
        うえでダンプのキーとして扱う"""
        b = self.bench
        k = ev.key
        ch = (ev.unicode or "").upper()
        if len(ch) == 1 and ch in "0123456789ABCDEF":
            said = b.type_start(int(ch, 16))
            if said.text:
                self.bench_said(said)
            return
        if k == pygame.K_BACKSPACE and b.start_buf:
            b.start_buf = b.start_buf[:-1]
            return
        if self.bench_field_skip(ch):
            return
        b.start_buf = None
        if k not in (pygame.K_ESCAPE, pygame.K_BACKSPACE, pygame.K_RETURN, pygame.K_KP_ENTER):
            self.bench_key(ev)

    def bench_key(self, ev) -> None:
        """実行していないときのキー。16進表記の字でダンプを書き、矢印で動く"""
        b, v = self.bench, self.bench_view
        if b.start_buf is not None:
            self.bench_start_key(ev)
            return
        if b.span_buf is not None:
            self.bench_span_key(ev)
            return
        k = ev.key
        if k == pygame.K_ESCAPE:
            if b.live:  # キーを本体へ戻す
                v.focus = False
            elif b.state == "pause":
                b.abandon()
            return
        ch = (ev.unicode or "").upper()
        msg = ""
        if len(ch) == 1 and ch in "0123456789ABCDEF":
            msg = b.type_hex(int(ch, 16))
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            b.next_line()
        elif k == pygame.K_SPACE:
            b.to_data()
        elif k in (pygame.K_LEFT, pygame.K_BACKSPACE):
            b.left(v.rows)
        elif k == pygame.K_RIGHT:
            b.right(v.rows)
        elif k in (pygame.K_UP, pygame.K_DOWN):
            b.move_rows(-1 if k == pygame.K_UP else 1, v.rows)
        elif k in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            b.page(-1 if k == pygame.K_PAGEUP else 1, v.rows)
        elif k == pygame.K_TAB:
            b.to_addr()
        elif k == pygame.K_HOME:
            b.row_home()
        elif k == pygame.K_END:
            b.row_end()
        if msg:
            v.say(msg)

    REPEAT = (0.45, 0.05)  # 作業欄のキーのリピート(押してから始まるまで、間隔。秒)
    # リピートするキー(カーソルを動かすもの。16進表記の字は押し続けても1字だけ)
    REPEAT_KEYS = frozenset(
        (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT, pygame.K_PAGEUP,
         pygame.K_PAGEDOWN, pygame.K_BACKSPACE)
    )  # fmt: skip

    def _key_repeat(self) -> None:
        """作業欄にキーを打っているあいだだけ、押し続けたカーソルのキーを1フレームに1回まで
        リピートさせる(pygameのリピートは、フレームが遅れるとたまった分をまとめて届け、
        離したあとにも残りが届いて行き過ぎる)"""
        held = self.held_key
        if held is None:
            return
        if not self.pane_keys() or self.menu is not None or self.popup is not None:
            self.held_key = None
            return
        ev, at = held
        now = time.monotonic()
        if now >= at:
            self.bench_key(ev)
            self.held_key = (ev, now + self.REPEAT[1])

    def bench_click(self, pos) -> None:
        b, v = self.bench, self.bench_view
        hit = v.hit(pos)
        if hit is None:
            return
        kind, a = hit
        if kind != "start":
            b.start_buf = None
        if kind != "span":
            b.span_buf = None
        if kind == "button":
            if v.buttons[a].enabled:
                self.bench_do(v.buttons[a].action)
        elif kind == "clearlcd":
            b.clear_lcd = not b.clear_lcd
        elif kind == "start":
            if b.state == "run" and not b.live:
                v.say(
                    tr("app.cannot_type_while_running",
                       c=CMD), 4
                )  # fmt: skip
            else:
                b.start_buf = "" if b.start_buf is None else None
        elif kind == "export":
            self.bench_export()
        elif kind == "listing":
            self.bench_export(listing=True)
        elif kind == "spanauto":
            v.say(b.clear_span(), 3, ok=True)
        elif kind == "span":
            if b.state == "run" and not b.live:
                v.say(tr("app.cannot_type_range_while"), 3)
            else:
                b.span_buf = "" if b.span_buf is None else None
        elif kind == "iram":
            v.show_iram = not v.show_iram
            self._save_view()
            self._refit()
        elif kind == "break":
            if b.toggle_break(a) is None:
                v.say(
                    tr(
                        "app.not_usable_without_rom",
                        addr=a,
                    ),
                    3,
                )
        elif kind in ("addr", "byte", "goto", "why") and (b.state != "run" or b.live):
            first = (b.row - 8 * b.top_rows) & 0xFFFF
            off = (a - first) & 0xFFFF
            if kind == "addr":
                b.row, b.top_rows, b.field, b.nib = a, off // 8, "addr", 0
            else:
                b.place(a, v.rows)  # バイトか逆アセンブルの行。行の並びは変えない

    def bench_open(self, prog: programs.Program, run: bool = False) -> None:
        """ROMなしでプログラムを読み込む。マシン語のダンプをRAMに書き、BASICは実行しない。
        呼び出し用のBASICから、数だけを書くPOKE(IFのあとを除く)を拾って書き、最後のCALLの
        番地を開始番地にする(CALLがなければ最初のダンプの番地)"""
        b, m = self.bench, self.m
        name = prog.title or prog.name
        problem = loading.bench_problem(prog, m)
        if problem is not None:
            self.say(*problem)
            return
        blocks, start = loading.bench_blocks(prog)
        self.undo_bench = b.save()  # 実行中・一時停止中なら、その状態のまま覚える
        if b.state != "edit":
            b.abandon()
        self.undo_state, self.undo_title = m.snapshot(), name
        self.undo_prog = self._prog_undo()
        m.set_ram_top(prog.ram_top)
        b.use_data(prog.data)
        n = b.load_blocks(blocks, start)
        b.calls = workbench.basic_calls(f"{prog.basic}\n{prog.run}")
        self.pad_prog, self.pad_note = prog, ""
        self.set_pad_map(self.pad_map_for(prog))
        self.last_prog = prog
        self.loading, self.load_help = prog.title, prog.norom
        done = tr("app.loaded_bytes_start_address",
                  name=name, n=n, addr=b.start, c=CMD)  # fmt: skip
        self.say_loaded(f"{done}\n{prog.norom}" if prog.norom else done, 12 if prog.norom else 6)
        if run:
            self.bench_do("run")

    def bench_undo(self, redo: bool = False) -> None:
        """作業欄の書き込みを取り消す(redoならやり直す)。ROMのある本体では、続けて⌘Zで
        取り消せるように、キーを作業欄で受けるようにする"""
        b, v = self.bench, self.bench_view
        done = b.can_redo() if redo else b.can_undo()
        v.say(b.redo() if redo else b.undo(), 3, ok=done)
        if done and b.live:
            v.focus = True

    def bench_paste(self) -> None:
        """クリップボードのダンプ(本のダンプリストか.hexの行)を書く"""
        b, v = self.bench, self.bench_view
        if b.state == "run" and not b.live:
            return
        start = b.start
        res = b.paste(self.clipboard())
        if not res.written:
            v.say(tr("app.no_dump_lines_pasted"), 4)
            return
        parts = [tr("app.wrote_bytes", n=res.written)]
        if res.bad_sums:
            where = tr("common.ideographic_comma").join(f"{a:04X}" for a in res.bad_sums[:4])
            parts.append(tr("app.checksum_mismatch", where=where))
        if res.outside:
            parts.append(tr("app.bytes_outside_ram_not", n=res.outside))
        if b.start != start:
            parts.append(tr("app.start_address", addr=b.start))
        v.say(tr("app.ideographic_full_stop").join(parts), 8)

    def bench_export(self, listing: bool = False) -> None:
        """書き出す範囲のマシン語を、プログラムのフォルダに.hexで書き出す。逆アセンブルつきか、listingなら
        本のダンプリストの形(8バイト:チェックサム)。どちらも読み込める"""
        b, v = self.bench, self.bench_view
        ranges = b.export_ranges()
        if not ranges:
            v.say(tr("app.no_dump_export"), 4)
            return
        where = tr("common.ideographic_comma").join(
            workbench.span_text(lo, hi) for lo, hi in ranges
        )
        try:
            folder = os.path.join(programs.user_dir(), programs.model_dir(self.m.model.name))
            os.makedirs(folder, exist_ok=True)
            stem = "dumplist" if listing else "dump"
            path = paths.unused_file(folder, f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}", ".hex")
            # 開始番地は# run:に書く(読み込むと、ROMなしではここから、ROMがあればこのCALLで動く)
            note = tr("app.exported_machine_code_workbench", where=where)
            # 自分で決めたデータの範囲は# data: に書く(読み込むと同じ指定になる)
            head = f"; {note}\n# run: CALL &{b.start:04X}\n" + programs.data_line(b.data_spans())
            head += self._ram_line()  # 広げたRAMにあるダンプを、読み込み直せるように
            dump = b.dump_list if listing else b.dump_text
            body = "".join(dump(lo, hi) for lo, hi in ranges)
            with open(path, "w", encoding="utf-8") as f:
                f.write(head + body)
        except OSError as e:
            v.say(tr("app.cannot_export", error=e), 5)
            return
        size = sum(hi - lo for lo, hi in ranges)
        name = os.path.basename(path)
        v.say(
            tr("app.exported_bytes_folder",
               name=name, n=size, folder=_short(folder)), 8
        )  # fmt: skip

    def clipboard(self) -> str:
        text = ""
        try:
            if not pygame.scrap.get_init():
                pygame.scrap.init()
            raw = pygame.scrap.get(pygame.SCRAP_TEXT)
            if raw:
                text = raw.decode("utf-8", "ignore").rstrip("\x00")
        except (pygame.error, NotImplementedError):
            pass
        if not text:
            try:
                text = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
            except OSError:
                text = ""
        return text

    SPEEDS = (0.5, 1, 2, 4, 8)

    def change_speed(self, step: int) -> None:
        """速さを1段上げる(step=1)か下げる(step=-1)。両端ではそのまま"""
        i = self.SPEEDS.index(self.turbo) + step
        self.turbo = self.SPEEDS[min(max(i, 0), len(self.SPEEDS) - 1)]
        self.say(tr("app.speed", speed=speed_label(self.turbo)), 1.5)

    def toggle_arrows(self) -> None:
        self.numpad_arrows = not self.numpad_arrows
        if self.numpad_arrows:
            self.say(tr("app.arrow_keys_number_keys"), 2.5)
        else:
            self.say(tr("app.arrow_keys"), 2.5)

    def toggle_packed(self) -> None:
        """液晶の桁と行のあいだのすきまをなくすか、実機と同じにする(次に起動したときも同じ)"""
        self.panel.set_packed(not self.panel.packed)
        self._save_view()
        if self.panel.packed:
            self.say(tr("app.gaps_between_lcd_characters"), 2.5)
        else:
            self.say(tr("app.gaps_between_lcd_characters_restored"), 2.5)

    def toggle_help(self) -> None:
        self.help = 0 if self.help else FPS * 10

    # ---- 操作欄とプリンタ ----
    def _window_size(self) -> tuple[int, int]:
        """ウィンドウの大きさ。本体の下に、プリンタの紙(印字したとき)と操作欄を足す"""
        w, h = self.body_size
        if self.paper_open:
            h += self.paper.height
        h += self._pad_panel_height() + BAR_H
        if self.pane_open:
            return w + benchview.PANE_W, max(h, self.bench_view.min_height())
        return w, h

    def bar_buttons(self) -> list[BarButton]:
        """操作欄のボタン。左に目的ごとのメニュー、続けて実行の一時停止と速さ、右端に録画。
        録画しているあいだは、録画のボタンが録画中のマークと経過時間になり、押すと止めるか
        一時停止するかのメニューが出る"""

        def menu(kind: str):
            return lambda: self.open_bar_popup(kind)

        c, s = CMD, SHIFT
        view_tip = tr("app.key_help_arrow_keys", c=c)
        buttons = [
            BarButton(tr("common.programs"), menu("program"), short=tr("common.programs"),
                      menu="program", tip=tr("app.list_export_paste_list", c=c)),
            BarButton(tr("app.machine"), menu("machine"), short=tr("app.machine"), menu="machine",
                      tip=tr("app.save_load_state_switch")),
            BarButton(tr("app.view_input"), menu("view"), short=tr("app.view"), menu="view",
                      tip=view_tip),
        ]  # fmt: skip
        if self.halted:
            tip = tr("app.resume_execution_p", c=c)
            buttons.append(
                BarButton(tr("app.resume"), self.toggle_halt, "play", tr("app.resume_short"), tip)
            )
        elif not self.bench_only:  # ROMなしでは、実行と一時停止は作業欄のボタンで行う
            tip = tr("app.pause_cpu_p_recording", c=c)
            buttons.append(
                BarButton(tr("app.pause"), self.toggle_halt, "pause", tr("app.pause_short"), tip)
            )
        if not self.bench_only and not self.lcd_only:
            # 作業欄の出し入れ。矢印は作業欄が動く向き(右へ出す・左へしまう)
            if self.pane_open:
                label, tip = tr("app.workbench_hide"), tr("app.hide_machine_code_workbench", c=c)
            else:
                label, tip = tr("app.workbench_show"), tr("app.show_machine_code_workbench", c=c)
            buttons.append(BarButton(label, self.toggle_pane, "", label, tip, True))
        if self.lcd_only:  # 液晶だけのあいだは、メニューを開かずに本体へ戻れるように
            tip = tr("app.show_calculator_window_size")
            buttons.append(
                BarButton(tr("app.calculator"), self.toggle_lcd, "", tr("app.calculator"), tip)
            )
        speed = speed_label(self.turbo)
        tip = tr("app.choose_speed_t_faster", c=c, s=s)
        label = tr("app.speed", speed=speed)
        buttons.append(BarButton(label, menu("speed"), "", speed, tip, True, "speed"))
        rec = self.recorder
        if rec is None:
            tip = tr("app.start_recording_r", c=c, s=s)
            buttons.append(BarButton(tr("app.record"), menu("recstart"), "rec", tr("app.record"),
                                     tip, menu="recstart"))  # fmt: skip
        else:
            sec = int(rec.seconds)
            clock = f"{sec // 60}:{sec % 60:02d}"
            tip = tr("app.stop_r_pause_p", c=c, s=s)
            if self.rec_paused:
                label, icon = tr("common.rec_paused", clock=clock), "recpause"
            else:
                label, icon = tr("common.recording", clock=clock), "rec"
            buttons.append(BarButton(label, menu("rec"), icon, clock, tip, menu="rec"))
        return buttons

    def bar_info(self) -> str:
        """操作欄の右に出す、いまの設定(速さと一時停止はボタンに出る)"""
        m = self.m
        parts = [m.model.title + (" " + tr("app.kb_card", n=m.card) if m.card else "")]
        if self.last_prog is not None:
            parts.append(self.last_prog.title or self.last_prog.name)
        if self.numpad_arrows:
            parts.append(tr("app.arrows_8246"))
        if m.tape is not None:
            parts.append(tr("app.tape"))
        return "   ".join(parts)

    def cancel_loading(self) -> None:
        """読み込みの打ち込みをやめる。打ち込んだところまではRAMに残る"""
        self.typer.clear()
        self.fast = False
        self.say(tr("app.loading_stopped_partly_loaded", hint=undo_hint()), 6)

    @property
    def paper_open(self) -> bool:
        return self.printout is not None

    def close_paper(self) -> None:
        """プリンタの紙をしまう(ウィンドウの高さが変わる)"""
        if self.printout is None:
            return
        self._finish_paper()
        self.paper_back = 0
        self._refit()
        # まだ出していない行は次の紙に出さない(保存はprinter.rowsから済んでいる)
        self.printed = self.m.printer.count if self.m.printer is not None else 0
        self.paper.feed, self.print_gap, self.print_hold = 0.0, 0, 0.0

    def _finish_paper(self) -> None:
        """いまの紙を終わりにする。まだ保存していない印字を保存し、次の印字は新しい紙と
        ファイルにする(途中の行なら、その先の字から)"""
        if self.printout is None:
            return
        self.save_printout()
        self.print_cut = self.printout.cut()
        self.printout.close()
        self.printout = None

    def paper_rows(self) -> list[bytes]:
        """いまの紙に出ている行のコード。まだ出していない行と、改行していない途中の行は除く
        (実機も、行の終わりを受け取ってから印字する)"""
        printer = self.m.printer
        if self.printout is None or printer is None:
            return []
        rows = self.printout.rows()
        waiting = printer.count - self.printed
        partial = 1 if bytes(printer.line).rstrip(b" ") else 0
        return rows[: max(0, len(rows) - waiting - partial)]

    def _print_next_line(self) -> None:
        """紙に出していない行があれば、前の行を出し終えたあとに次の行を出し始める。速さは
        実機の速さに速さの設定(turbo)を掛けたもの。出していない行がPRINT_KEEPより多ければ、
        PRINT_CATCH_UP秒で出し切る速さに上げて、出し切るまでその速さを保つ。1フレームに1行より
        速ければ、何行かまとめて出す(紙送りは1行ぶんにして、紙に出した行が見えなくならないように)"""
        printer = self.m.printer
        if printer is None or self.printout is None:
            return
        if self.print_gap:
            self.print_gap -= 1
            return
        if self.paper.moving or self.printed >= printer.count:
            return
        waiting = printer.count - self.printed
        rate = max(float(self.turbo), self.print_hold)
        if waiting > PRINT_KEEP:
            rate = max(rate, waiting * (PRINT_LINE + PRINT_GAP) / PRINT_CATCH_UP)
        line, gap = PRINT_LINE / rate, PRINT_GAP / rate
        lines = min(waiting, math.ceil(1 / ((line + gap) * FPS)))
        line_frames = max(1, round(lines * line * FPS))
        self.printed += lines
        self.paper_back = 0
        self.paper.line_frames = line_frames
        self.paper.fed(1)
        self.print_rate = rate
        self.print_hold = rate if rate > self.turbo and self.printed < printer.count else 0.0
        # 次の行は、印字と間のフレームが過ぎた次のフレームから
        self.print_gap = max(line_frames, round(lines * (line + gap) * FPS)) - 1

    def check_printer(self) -> None:
        """新しく印字したものがあれば紙を出し、行を1つずつ送り出す(_print_next_line)。印字が
        とぎれたら保存する"""
        printer = self.m.printer
        if printer is None:
            return
        if printer.changes == self.print_seen:
            self._print_next_line()
            if self.printout is not None and self.printout.due():
                self.save_printout()
            return
        self.print_seen = printer.changes
        if self.printout is None:  # 新しい紙
            self.printout = Printout(printer, self.print_cut, programs.user_dir())
            if self.printout.error is not None:  # 紙は出すが、印字の絵は保存しない
                self.say(tr("app.cannot_save_printout", error=self.printout.error), 5)
            self._refit()
            self.save_printout()  # 名前を取っておくため、すぐに1度保存する
        self.printout.touched()
        self._print_next_line()

    def save_printout(self) -> None:
        """いまの紙の印字を保存する(Printout.save)。保存したら、できなければ知らせる"""
        out = self.printout
        if out is None:
            return
        try:
            saved = out.save(self.paper)
        except (OSError, pygame.error) as e:
            self.say(tr("app.cannot_save_printout", error=e), 5)
            out.file = None
            return
        if saved and out.file is not None:
            self.say(tr("app.printout_saved", path=_short(out.file)), 5)

    def reveal_printout(self) -> None:
        """印字を保存したフォルダを開く"""
        self.save_printout()
        out = self.printout
        file = out.file if out is not None else None
        self.reveal(os.path.dirname(file) if file else programs.user_dir())

    def scroll_paper(self, step: int) -> None:
        """紙の上でホイールを回すと、前の行を見せる"""
        printer = self.m.printer
        y = pygame.mouse.get_pos()[1] - self.origin[1]
        h = self.body_size[1]
        if printer is None or not self.paper_open or not h <= y < h + self.paper.height:
            return
        rows = len(self.paper_rows())
        self.paper_back = min(max(self.paper_back + step, 0), max(0, rows - 1))

    def press_reset(self) -> None:
        """裏のRESETボタンを0.3秒押す。作業欄だけで動かしているときは、実行をやめて作業欄に戻る"""
        if self.bench_only:
            self.bench_do("abandon")
            return
        self.m.press_reset()
        self.reset_frames = max(1, FPS * 3 // 10)

    def move_switch(self, step: int) -> None:
        order = [name for name, _y in self.sw_stops]
        i = order.index(self.m.mode) if self.m.mode in order else order.index(order[-2])
        self.set_mode(order[min(max(i + step, 0), len(order) - 1)])

    def popup_items(self, kind: str | None = None) -> list[MenuItem]:
        """メニューの項目。kindは操作欄のボタンのメニュー(program、machine、view、speed、
        録画中のrec)か、右クリックのメニュー(context、paper)。なければいま出しているメニュー"""
        if kind is None:
            kind = self.popup.kind if self.popup is not None else "context"
        sep, item = SEPARATOR, MenuItem
        c, s = CMD, SHIFT
        stopped = self.bench.state == "pause"
        pause = item(tr("app.resume_execution") if stopped else tr("app.pause_execution"), f"{c}P",
                     self.toggle_halt)  # fmt: skip
        if kind == "program":
            # ROMなしでは、⌘E・⌘Vと同じく作業欄のダンプを書き出す・貼り付ける
            if self.bench_only:
                export = item(tr("app.export_dump_file_hex"), f"{c}E", self.bench_export,
                              self.bench.export_summary())  # fmt: skip
                listing = item(tr("app.export_dump_list"), f"{s}{c}E",
                               lambda: self.bench_export(listing=True),
                               tr("app.lines_8_bytes_checksum"))  # fmt: skip
                paste = item(tr("app.paste_dump_clipboard"), f"{c}V", self.bench_paste)
            else:
                export = item(tr("app.export_program_file"), f"{c}E", self.export_program)
                listing = None
                paste = item(tr("app.type_clipboard"), f"{c}V", self.paste)
            items = [
                item(tr("app.program_list"), f"{c}O", self.open_menu),
                export,
                *([listing] if listing else []),
                paste,
                item(tr("app.open_program_folder"), "", lambda: self.reveal(programs.user_dir())),
            ]
            if self.bench_only or self.pane_open:
                # 作業欄の書き込みの取り消しとやり直し。下に、何を取り消すか(できなければ理由)
                note, on = self.bench.undo_note()
                rnote, ron = self.bench.undo_note(redo=True)
                items += [
                    sep,
                    item(tr("app.undo_dump_edit"), f"{c}Z", self.bench_undo, note,
                         enabled=on),
                    item(tr("app.redo_dump_edit"), f"{s}{c}Z",
                         lambda: self.bench_undo(redo=True), rnote, enabled=ron),
                ]  # fmt: skip
            if self.load_help:
                show = lambda: self.say(self.load_help, 20)  # noqa: E731
                items += [sep, item(tr("app.help_loaded_program"), "", show, self.loading)]
            return items
        if kind == "machine":
            items = [
                item(tr("app.save_state"), f"{s}{c}S", self.save_state),
                item(tr("app.load_state"), f"{s}{c}L", self.load_state, self.saved_when()),
            ]
            if self.undo_state is not None:
                note = tr("app.before_loading", title=self.undo_title)
                items.append(item(tr("app.undo_program_load"), "", self.undo_loading, note))
            items.append(sep)
            for name, _y in self.sw_stops:
                key = f"{c}↑↓" if self.m.mode == name else ""
                items.append(item(switch_label(name), key, lambda n=name: self.set_mode(n)))
            return items + [sep, item(tr("app.press_reset_button"), f"{c}R", self.press_reset)]
        if kind == "view":
            if self.numpad_arrows:
                arrows = tr("app.arrow_keys_back")
            else:
                arrows = tr("app.arrow_keys_8_2")
            pads = self.pads.names()
            if pads:
                note = tr("app.connected", names=tr("common.ideographic_comma").join(pads))
            else:
                note = tr("app.no_gamepad_connected")
            lcd = tr("app.show_calculator") if self.lcd_only else tr("app.lcd_only_window_can")
            items = [
                item(tr("app.key_help"), f"{c}/", self.toggle_help),
                item(arrows, f"{c}K", self.toggle_arrows),
                item(tr("app.gamepad_mapping"), "", self.toggle_pad_panel, note),
                sep,
                item(lcd, "", self.toggle_lcd),
                item(tr("app.save_screenshot"), f"{c}S", self.screenshot),
            ]
            if self.panel.can_pack:
                if self.panel.packed:
                    gap = item(tr("app.restore_gaps_between_lcd"), "", self.toggle_packed)
                else:
                    gap = item(tr("app.remove_gaps_between_lcd"), "", self.toggle_packed,
                               tr("app.dots_evenly_spaced_not"))  # fmt: skip
                items.insert(5, gap)
            if not self.bench_only:
                if self.pane_open:
                    pane = tr("app.hide_workbench")
                else:
                    pane = tr("app.show_workbench")
                note = tr("app.not_available_while_showing") if self.lcd_only else ""
                items[3:3] = [item(pane, f"{c}D", self.toggle_pane, note, enabled=not note)]
            # 言語の切り替え。項目の名前は、切り替えた先の言語で書く
            other = "en" if i18n.language() == "ja" else "ja"
            name = LANGUAGE_NAMES[other]
            items += [sep, item(name, "", lambda: self.set_language(other))]
            paper = self.popup_items("paper")
            return items + ([sep, *paper] if paper else [])
        if kind == "rec":
            if self.rec_paused:
                pause = item(tr("app.resume_recording"), f"{s}{c}P", self.toggle_pause, icon="rec")
            else:
                pause = item(tr("app.pause_recording"), f"{s}{c}P", self.toggle_pause,
                             icon="recpause")  # fmt: skip
            stop = item(
                tr("app.stop_save_recording"), f"{s}{c}R", self.toggle_recording, icon="stop"
            )
            return [stop, pause]
        if kind == "recstart":  # 録画の形を選んで始める
            return [
                item(
                    str(REC_SHAPE_NAMES[shape]),
                    "",
                    partial(self.start_recording, shape),
                    icon="rec",
                )
                for shape in recorder.SHAPES
            ]
        if kind == "speed":
            return [item(tr("app.speed", speed=speed_label(v)), "",
                         lambda v=v: self.set_speed(v))
                    for v in self.SPEEDS]  # fmt: skip
        if kind == "bench":
            return self.bench_items()
        if kind == "paper":
            out = self.printout
            if out is None:
                return []
            items = [item(tr("app.put_paper_away"), "", self.close_paper)]
            if out.file:
                items.insert(0, item(tr("app.open_printout_folder"), "", self.reveal_printout))
            return items
        return [  # 右クリック(場所によらない、よく使うものだけ)
            pause,
            item(tr("app.program_list"), f"{c}O", self.open_menu),
            item(tr("app.save_screenshot"), f"{c}S", self.screenshot),
            item(tr("app.key_help"), f"{c}/", self.toggle_help),
        ]

    def popup_mark(self) -> str:
        """いま出しているメニューで●をつける項目(スイッチの位置か、いまの速さ)"""
        kind = self.popup.kind if self.popup is not None else ""
        if kind == "speed":
            return tr("app.speed", speed=speed_label(self.turbo))
        if kind == "recstart":  # 前に選んだ形(⇧⌘Rで始める形)
            return str(REC_SHAPE_NAMES[self.rec_shape])
        return switch_label(self.m.mode)

    def set_speed(self, speed: float) -> None:
        self.turbo = speed
        self.say(tr("app.speed", speed=speed_label(speed)), 1.5)

    def set_language(self, lang: str) -> None:
        """画面の言語を切り替えて、次に起動したときのために覚えておく"""
        i18n.set_language(lang)
        self.bench_view.flash = ""
        self._save_view(lang)
        self.say(tr("app.language_english"), 3)

    def saved_when(self) -> str:
        """保存した状態の日時(「10/22 15:30に保存」)。保存していなければ「まだ保存していません」"""
        try:
            t = os.path.getmtime(self.state_file)
        except OSError:
            return tr("app.not_saved_yet")
        when = time.strftime("%m/%d %H:%M", time.localtime(t)).lstrip("0")
        return tr("app.saved_when", when=when)

    def toggle_halt(self) -> None:
        """実行を一時停止する。止めているあいだはCPUも時計も進まない(録画の一時停止とは別)。
        ROMなしでは、作業欄の一時停止と続けるにする(止めた状態を1つにする)"""
        state = self.bench.state
        if state == "run":
            self.bench_do("pause")
            if not self.bench_only:
                self.say(tr("app.paused_p_resume_bar", c=CMD), 4)
        elif state == "pause":
            self.bench_do("resume")
            if not self.bench_only and self.bench.state == "run":
                self.say(tr("app.resumed"), 1.5)
        else:
            self.say(tr("app.not_running_g_runs", c=CMD), 3)

    @property
    def warning(self) -> str:
        """ウィンドウの左上に出す注意(いまの言語の文。なければ空)"""
        return str(self._warning)

    @warning.setter
    def warning(self, text: str | Text) -> None:
        self._warning = text

    @property
    def halted(self) -> bool:
        """ROMのある本体で、実行を一時停止しているか(作業欄の一時停止と同じ状態)。ROMなしの
        本体の実行と一時停止は作業欄が扱うので、いつもFalse"""
        return not self.bench_only and self.bench.state == "pause"

    @halted.setter
    def halted(self, on: bool) -> None:
        if not self.bench_only and on != self.halted:
            self.toggle_halt()

    def _prog_undo(self) -> tuple:
        """読み込む前に戻すために覚える、読み込んだプログラムの情報と割り当て"""
        return (
            self.last_prog, self.loading, self.load_help, self.pad_prog, self.pad_map,
            self.pad_dirty,
        )  # fmt: skip

    def undo_loading(self) -> None:
        """プログラムを読み込む直前の状態に戻す"""
        state, title = self.undo_state, self.undo_title
        if state is None:
            return
        try:
            self.m.restore(state)
        except ValueError as e:
            self.say(tr("app.cannot_undo_load", error=e), 5)
            return
        # 書き出しや説明に使う、読み込んだプログラムの情報も読み込む前のものに戻す
        self.last_prog, self.loading, self.load_help, self.pad_prog, pad_map, dirty = self.undo_prog
        self.set_pad_map(pad_map)
        self.pad_dirty = dirty
        done = tr("app.back_before_loading", title=title)
        self.bench.restore(self.undo_bench, done)
        self.undo_state = None
        self._restored(done)

    def open_bar_popup(self, kind: str) -> None:
        """操作欄のボタンのメニューを、そのボタンのすぐ上に出す"""
        i = next((i for i, b in enumerate(self.bar.buttons) if b.menu == kind), -1)
        r = self.bar.rects[i] if 0 <= i < len(self.bar.rects) else None
        if r is None or not r.width:
            r = pygame.Rect(8, self.body_size[1], 0, 0)
        self._make_room()
        ox, oy = self.origin
        self.popup = Popup((r.x + ox, r.y + oy), kind, above=True, source=i)

    def next_bar_popup(self, step: int) -> None:
        """開いている操作欄のメニューから、左右の隣のメニューのボタンへ移る(←→)"""
        popup = self.popup
        assert popup is not None
        menus = [i for i, b in enumerate(self.bar.buttons) if b.menu and self.bar.rects[i].width]
        if popup.source in menus:
            i = menus[(menus.index(popup.source) + step) % len(menus)]
            self.open_bar_popup(self.bar.buttons[i].menu)

    def open_popup(self, win) -> None:
        """右クリックのメニュー(winはウィンドウの中の位置)。作業欄の上ならクリックした番地の操作、
        プリンタの紙の上なら紙の操作、ほかはよく使う操作だけ。メニューはウィンドウ全体に描くので、
        ウィンドウを広げたぶん位置をずらす"""
        pos = self._in_content(win)
        dx, dy = self._make_room()
        win = (win[0] + dx, win[1] + dy)
        if self.pane_open and pos[0] >= self.body_size[0]:
            self.bench_menu(pos, win)
            return
        on_paper = self.paper_open and self.body_size[1] <= pos[1] < self._paper_bottom()
        if on_paper and self.popup_items("paper"):
            self.popup = Popup(win, "paper")
        else:
            self.popup = Popup(win, "context")

    def _in_content(self, win) -> tuple[int, int]:
        """ウィンドウの中の位置を中身の中の位置に直す(ウィンドウが中身より大きいとき、"
        "中身はまんなかにある)"""
        return win[0] - self.origin[0], win[1] - self.origin[1]

    def bench_menu(self, pos, win=None) -> None:
        """作業欄の右クリック(posは中身の中の位置、winはウィンドウの中の位置)。ダンプのバイトか
        逆アセンブルの行なら、その番地にカーソルを置き(ROMなしで実行中は置かない)、その番地の
        操作のメニューを出す。ほかの所ならカーソルの番地の操作"""
        b, v = self.bench, self.bench_view
        b.start_buf = b.span_buf = None
        v.focus = True
        hit = v.hit(pos)
        kind, a = hit if hit is not None else ("", 0)
        if kind in ("byte", "goto", "break", "addr", "why"):
            if b.state != "run" or b.live:
                b.place(a, v.rows)
            self.bench_at = a
        else:
            self.bench_at = b.cursor
        self.popup = Popup(pos if win is None else win, "bench")

    def bench_items(self) -> list[MenuItem]:
        """作業欄の右クリックのメニュー(App.bench_menuで選んだ番地の操作)"""
        b, item = self.bench, MenuItem
        a = self.bench_at
        here = a == b.cursor  # ショートカットは、カーソルの所に効く
        why = b.start_refusal(a)
        if a == b.start:
            why = tr("app.is_start_address")
        items = [
            item(tr("app.set_start_address", addr=a), f"{CMD}A" if here else "",
                 lambda: self.bench_start_at(a), why, enabled=not why),
        ]  # fmt: skip
        if not b.live:
            why = b.start_refusal(a) or (tr("app.running") if b.state == "run" else "")
            items.append(
                item(tr("app.run", addr=a), f"{SHIFT}{CMD}G" if here else "",
                     lambda: self.bench_run_at(a), why, enabled=not why)
            )  # fmt: skip
        ins = b.ins_at(a)
        on = ins in b.breaks
        why = "" if on or not b.blocked(ins) else tr("app.address_not_usable_without_rom")
        if on:
            label = tr("app.remove_breakpoint", addr=ins)
        else:
            label = tr("app.set_breakpoint", addr=ins)
        items.append(
            item(label, f"{CMD}B" if here and ins == b.ins_at(b.cursor) else "",
                 lambda: self.bench_break_at(ins), why, enabled=not why)
        )  # fmt: skip
        # 逆アセンブルで、その番地からをデータか命令に決める(決めなければ推定する)
        items.append(SEPARATOR)
        marks = (
            ("data", tr("app.mark_data", addr=a),
             tr("app.data_up_next_mark")),
            ("code", tr("app.mark_code", addr=a),
             tr("app.analyse_code_here")),
            (None, tr("app.clear_mark", addr=a), tr("app.back_guessing")),
        )  # fmt: skip
        for what, label, note in marks:
            why = b.mark_refusal(a, what)
            items.append(
                item(label, "", lambda w=what: self.bench_mark_at(a, w), why or note,
                     enabled=not why)
            )  # fmt: skip
        return items

    def bench_mark_at(self, addr: int, what: str | None) -> None:
        """番地addrから、逆アセンブルでデータか命令に決める(Noneなら指定を消す)"""
        b, v = self.bench, self.bench_view
        ok = not b.mark_refusal(addr, what)
        v.say(b.set_mark(addr, what), 3, ok=ok)

    def bench_run_at(self, addr: int) -> None:
        """番地addrを開始番地にして実行する"""
        b = self.bench
        if b.set_start_at(addr).ok:
            self.bench_do("run")

    def bench_break_at(self, addr: int) -> None:
        on = self.bench.toggle_break(addr)
        if on is not None:
            self.bench_view.say(break_message(addr, on), 2)

    def _paper_bottom(self) -> int:
        return self.body_size[1] + (self.paper.height if self.paper_open else 0)

    def popup_run(self, i: int) -> None:
        items = self.popup_items()
        act = items[i].action if 0 <= i < len(items) else None
        self.popup = None
        if callable(act):
            act()

    def popup_key(self, ev) -> None:
        popup = self.popup
        assert popup is not None
        if ev.key == pygame.K_ESCAPE:
            self.popup = None
        elif ev.key in (pygame.K_UP, pygame.K_DOWN):
            popup.move(-1 if ev.key == pygame.K_UP else 1, self.popup_items())
        elif ev.key in (pygame.K_LEFT, pygame.K_RIGHT) and popup.source >= 0:
            self.next_bar_popup(-1 if ev.key == pygame.K_LEFT else 1)
        elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and popup.sel >= 0:
            self.popup_run(popup.sel)

    # ---- マウス ----
    def mouse_down(self, win) -> None:
        """クリック(winはウィンドウの中の位置)。ウィンドウ全体に描く一覧とメニューはウィンドウの位置で、本体・紙・
        割り当ての欄・操作欄・作業欄は中身の中の位置で当たり判定をする"""
        pos = self._in_content(win)
        if self.menu is not None:
            self.menu_click(win)
            return
        if self.warning and self.warning_rect.collidepoint(pos):
            self.warning = ""  # 注意をクリックすると閉じる
            return
        if self.pad_panel is not None and self.popup is None and self.pad_click(pos):
            return
        if self.pane_open and self.popup is None and pos[0] >= self.body_size[0]:
            self.bench_view.focus = True  # ROMのある本体では、キーを作業欄で受ける
            self.bench_click(pos)
            return
        self.bench_view.focus = False
        self.bench.start_buf = self.bench.span_buf = None
        if self.popup is not None:
            popup = self.popup
            i = popup.hit(win)
            if i >= 0:
                self.popup_run(i)
                return
            self.popup = None
            # 操作欄のほかのボタンなら、閉じたうえでそのボタンの操作をする(同じボタンなら
            # 閉じるだけ)
            b = self.bar.hit(pos) if pos[1] >= self.body_size[1] else -1
            if b < 0 or b == popup.source:
                return
        if pos[1] >= self.body_size[1]:  # 本体の下の紙と操作欄
            i = self.bar.hit(pos)
            if i >= 0:
                self.bar.buttons[i].action()
            elif self.paper_open and self.paper.close_rect.collidepoint(pos):
                self.close_paper()
            elif self.paper_open and self.paper.where_rect.collidepoint(pos):
                self.reveal_printout()
            return
        if self.lcd_only:  # 液晶だけなので、押せるキーもスイッチもない
            return
        x = pos[0] / self.scale - display.MARGIN
        y = pos[1] / self.scale - display.MARGIN
        sx0, sy0, sx1, sy1 = self.panel.switch_area
        if sx0 <= x <= sx1 and sy0 <= y <= sy1:
            self.dragging_switch = True
            self.set_switch_from(y)
            return
        name = self.panel.key_at(x, y)
        if name is None:
            return
        self.mouse_key = name
        if name == "BRK":
            self.press_brk("mouse")
        else:
            self.typer.press_mouse(name)

    def press_brk(self, source: str) -> None:
        """BRKキーを押す。sourceはEscキー("key")か、本体の絵のBRKをマウスで("mouse")"""
        self.brk_by.add(source)
        self.m.brk = True

    def release_brk(self, source: str) -> None:
        """BRKキーを離す。もう一方の入力元でまだ押していれば、押したままにする"""
        self.brk_by.discard(source)
        self.m.brk = bool(self.brk_by)

    def mouse_up(self) -> None:
        self.dragging_switch = False
        name, self.mouse_key = self.mouse_key, None
        if name == "BRK":
            self.release_brk("mouse")
        elif name:
            self.typer.release_mouse(name)

    def set_switch_from(self, y: float) -> None:
        mode = min(self.sw_stops, key=lambda s: abs(s[1] - y))[0]
        self.set_mode(mode)

    def set_mode(self, new: str) -> None:
        """スイッチを動かす。PC-1350のスイッチは電源だけで、RUNとPROはMODEキーで切り替える"""
        m = self.m
        if self.is1350:
            if new == "OFF":
                m.power_off()
            elif new == "ON":
                m.power_on()
            elif new in ("RUN", "PRO"):
                if not m.power:
                    m.power_on()
                self.typer.add_mode(new)
            return
        # OFFにしたときはROMが自分で電源を切るので、ここでは切らない
        if new != "OFF" and (m.mode == "OFF" or not m.power):
            m.wake()
        m.mode = new

    # ---- プログラムの読み込み ----
    def _ram_line(self) -> str:
        """いまRAMを広げていれば、その範囲の# ram: の行(なければ空)"""
        base, top = self.m.ram_top(None), self.m.model.ram[1]
        return f"# ram: {base:04X}-{top - 1:04X}\n" if top > base else ""

    def open_program(self, prog: programs.Program, run: bool = False) -> None:
        """BASICがあればPROモードでNEWしてからダンプを書いてBASICを入れ、なければダンプを
        すぐ書く。runなら実行の命令も打つ。
        読めない行があるときや、RAMの外に書くダンプがあるときは、何もせずに知らせる"""
        if self.bench_only:
            self.bench_open(prog, run)
            return
        m = self.m
        problem = loading.open_problem(prog, m, self._encoded)
        if problem is not None:
            self.say(*problem)
            return
        self.undo_state, self.undo_title = m.snapshot(), prog.title or prog.name
        self.undo_prog = self._prog_undo()
        self.undo_bench = self.bench.save()
        # BASICから呼んだマシン語が動いていれば、先に止める(止めないと、書いたダンプの上で動き
        # 続け、打つCALLも届かないので、何も起きないように見える)
        stopped = self._stop_running_code()
        m.set_ram_top(prog.ram_top)
        # 読み込みを始めたら、前の書き込みは取り消せなくする(読み込みは「読み込む前に戻す」で)。
        # 前のプログラムのために決めた書き出す範囲も消す
        self.bench.forget_edits()
        self.bench.span = None
        # 開始番地は、呼び出し用のBASICの最後のCALLの番地。書いた範囲はwrite_dumpで覚える
        _pokes, call = workbench.basic_hints(f"{prog.basic}\n{prog.run}")
        self.bench.use_data(prog.data)
        self.bench.set_start(prog.blocks + prog.after, call)
        self.bench.calls = workbench.basic_calls(f"{prog.basic}\n{prog.run}")
        self.pad_prog, self.pad_note = prog, ""
        self.set_pad_map(self.pad_map_for(prog))
        if self.is1350 and not m.power:
            self.set_mode("ON")
        elif not m.power:
            self.set_mode(m.mode if m.mode != "OFF" else "RUN")
        if not loading.needs_new(prog):
            self.write_dump(prog.blocks)
        if stopped and m.basic is None:
            self.typer.add_idle()  # ROMが始め直して入力待ちになるのを待ってから打つ
        for step in loading.open_steps(prog, run, loading.back_mode(m)):
            self._add_step(step)
        if stopped:
            self.warning = Text("app.stopped_running_code")
        if prog.basic:
            self.last_prog = prog
        self.fast = self.typer.busy
        self.loading = prog.title
        self.load_help = prog.help
        self.load_total = max(1, len(self.typer.queue))
        self.load_typing = False
        if not self.fast:
            if prog.help:
                self.say_loaded(prog.help, 20)
            else:
                self.say_loaded(tr("app.loaded_bytes", name=prog.title, n=prog.size))

    def _stop_running_code(self) -> bool:
        """BASICから呼んで動いているマシン語を止め、BASICの入力待ちに戻す(プログラムと変数は
        残す)。止めたらTrue。ROMなしのBASICではCALLの最中かで、ROM使用時はマシン語を実行して
        いるか(マシン語から呼んだROMのルーチンの中も。Machine.running_ram_code)で見る。
        一時停止していれば、止めるかどうかによらず続ける状態に戻す(読み込みの打鍵が進むように)"""
        m = self.m
        if self.bench.state == "pause":
            self.bench_do("resume")
        b = m.basic
        if b is not None:
            if b.where not in ("call-run", "call-direct"):
                return False
            b.restart()
            return True
        if m.norom or not m.power or not m.running_ram_code():
            return False
        m.press_reset()  # 裏のRESETと同じに、0番地から始め直す
        m.reset_key = False
        return True

    def _add_step(self, step: loading.Step) -> None:
        t = self.typer
        if step.kind == "mode":
            t.add_mode(step.text)
        elif step.kind == "text":
            t.add_text(step.text)
        elif step.kind == "idle":
            t.add_idle()
        elif step.kind == "write":
            t.add_write(step.blocks)
        elif step.kind == "basic":
            t.add_call(lambda: self.store_basic(step.text, step.title))

    def write_dump(self, blocks: list[tuple[int, bytes]]) -> None:
        """ダンプをRAMに書き、作業欄の書いた範囲(書き出しに使う)にも0のバイトを含めて入れる。
        ダンプを書くところ(すぐ書く、# setup:のあと、# after:、--load)は、すべてここを通す"""
        for addr, data in blocks:
            for i, b in enumerate(data):
                self.m.write(addr + i, b)
        self.bench.note_written(blocks)

    def _encoded(self, text: str) -> bytes | None:
        """BASICを中間コードの行の並びにする。打ち込みで欠ける行があるなどで置けなければNone"""
        model = self.m.model.name
        if not keytype.typeable(text, model):
            return None
        typed = keytype.typed_text(text, model)
        return basictext.encode_program(
            typed, self.m.mem, pc1261_basic(self.m), basic_keywords(self.m)
        )

    def store_basic(self, text: str, title: str = "") -> None:
        """BASICのプログラムを、打ち込んだときにROMが作るのと同じ中間コードでRAMに置く。
        入りきらないときや、打ち込みでも欠ける長い行があるときは打ち込み、結果をROMに任せる。
        どちらでも、入れたあとですべての行が入ったかを確かめる(check_basic)"""
        m = self.m
        data = self._encoded(text)
        check = self.typer.call(lambda: self.check_basic(text, title))
        if data is not None and m.store_program(data):
            self.typer.queue[0:0] = [check]
        else:
            keys = keys_for_program(text, m.model.name)
            self.typer.queue[0:0] = [*keys, ["@IDLE"], check]
            self.load_total = len(self.typer.queue)  # ここからは打ち込みの進み具合を出す
            self.load_typing = True

    def check_basic(self, text: str, title: str) -> None:
        """textの行がすべて、欠けずにRAMに入ったかを確かめる。入っていない行や中身が違う行が
        あれば(RAMが足りないなど)、そのあとの実行やダンプの書き込みをやめて知らせる"""
        m = self.m
        want: set[int] = set()
        for line in keytype.typed_text(text, m.model.name).split("\n"):
            hit = re.match(r"\s*(\d+)(.*)", line)
            if hit and hit[2].strip():
                want.add(int(hit[1]))
            elif hit:  # 行番号だけの行は、その行を消す
                want.discard(int(hit[1]))
        have = {n for n, _ in basictext.program_lines(m.mem, m.program_start(), pc1261_basic(m))}
        missing = sorted(want - have)
        if missing:
            why = tr("app.did_not_fit_ram",
                     name=title, line=missing[0], n=len(missing), hint=undo_hint())  # fmt: skip
        else:
            bad = self._differs(text)
            if bad is None:
                return
            why = tr("app.line_could_not_typed",
                     name=title, line=bad, hint=undo_hint())  # fmt: skip
        self.typer.clear()
        self.fast = False
        self.say(why, 10)

    def _differs(self, text: str) -> int | None:
        """RAMのプログラムが、textを中間コードにしたものと違えば、最初に違う行の番号。
        中間コードにできないとき(行番号がおかしいなど)は比べずにNone"""
        m = self.m
        pc1261 = pc1261_basic(m)
        typed = keytype.typed_text(text, m.model.name)
        data = basictext.encode_program(typed, m.mem, pc1261, basic_keywords(m))
        if data is None:
            return None
        start = m.program_start()
        if start + 1 + len(data) >= len(m.mem):
            return None
        want = bytearray(m.mem)
        want[start + 1 : start + 1 + len(data)] = data
        want[start + 1 + len(data)] = 0xFF
        got = basictext.program_lines(m.mem, start, pc1261)
        exp = basictext.program_lines(want, start, pc1261)
        for (n, body), (en, ebody) in zip(got, exp, strict=False):
            if (n, body) != (en, ebody):
                return min(n, en)
        if len(got) != len(exp):
            return (got if len(got) > len(exp) else exp)[min(len(got), len(exp))][0]
        return None

    def insert_tape(self, path: str) -> None:
        """wavのテープをセットする。ROMがカセットの入力を読み始めたときに再生が始まる"""
        try:
            self.m.tape = tape.TapeIn(path)
        except (OSError, EOFError, wave.Error) as e:
            self.say(tr("app.cannot_read", name=os.path.basename(path), error=e), 5)
            return
        self.say(
            tr("app.tape_inserted_load_cload",
               name=os.path.basename(path)), 6
        )  # fmt: skip

    def open_file(self, path: str) -> None:
        if path.lower().endswith(".wav"):
            self.insert_tape(path)
            return
        if os.path.splitext(path)[1].lower() in programs.EXTS:
            self.open_program(programs.load_program(path))
            return
        name = os.path.basename(path)
        if path.lower().endswith(".bin"):  # 置く番地がわからない
            self.say(tr("app.load_write_bin_name", name=name), 6)
            return
        try:
            self.typer.add_text(open(path, encoding="utf-8").read())
        except (OSError, UnicodeDecodeError):
            self.say(tr("app.cannot_read_name", name=name), 4)

    def say(self, text: str, seconds: float = 3.0) -> None:
        self.status = text
        self.status_until = time.monotonic() + seconds

    def say_loaded(self, text: str, seconds: float = 3.0) -> None:
        """読み込み終わりのメッセージ。# pad: に読めない語があれば、そのメッセージも続けて出す"""
        if self.pad_note:
            text, seconds = f"{text}\n{self.pad_note}", max(seconds, 8)
            self.pad_note = ""
        self.say(text, seconds)

    def open_menu(self) -> None:
        """プログラムの一覧を開く"""
        items = programs.scan()
        if self.norom:  # ROMなしでは、ROMなしのBASICか作業欄だけで動かせるもの(読み込みと同じ)
            items = [p for p in items if p.without_rom(basic=not self.bench_only)]
        self.menu = ProgramMenu(programs.for_model(items, self.m.model.name, self.m.writable))
        self._make_room()

    def menu_key(self, ev) -> None:
        menu = self.menu
        assert menu is not None
        if menu.query is not None and ev.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            # 探しているあいだ: Escで探すのをやめ、Backspaceで1字消す
            menu.search(None if ev.key == pygame.K_ESCAPE else menu.query[:-1])
        elif ev.key in (pygame.K_ESCAPE, pygame.K_F6):
            self.menu = None
        elif ev.key in (pygame.K_UP, pygame.K_DOWN):
            menu.move(-1 if ev.key == pygame.K_UP else 1)
        elif ev.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            menu.page(-1 if ev.key == pygame.K_PAGEUP else 1)
        elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and menu.items:
            self.menu = None
            self.open_program(menu.items[menu.sel], run=not ev.mod & pygame.KMOD_SHIFT)
        elif menu.query is not None:  # 探す字はtext_inputで受ける
            return
        elif ev.key == pygame.K_o:
            self.reveal(programs.user_dir())
        elif ev.key == pygame.K_r:
            self.open_menu()

    def menu_click(self, pos) -> None:
        """行を押すと選ぶだけ(選んである行でも読み込まない)。読み込むのは下のボタンかEnter。
        一覧の外を押すと閉じる"""
        menu = self.menu
        assert menu is not None
        act = menu.button_at(pos)
        if act:
            self.menu_action(act)
            return
        i = menu.hit(pos)
        if i >= 0:
            menu.sel = i
        elif not menu.box.collidepoint(pos):
            self.menu = None

    def menu_action(self, act: str) -> None:
        """一覧の下のボタンと、上の探す欄"""
        menu = self.menu
        assert menu is not None
        if act == "search":
            if menu.query is None:
                menu.search("")
        elif act in ("run", "load") and menu.items:
            self.menu = None
            self.open_program(menu.items[menu.sel], run=act == "run")
        elif act == "folder":
            self.reveal(programs.user_dir())
        elif act == "reload":
            self.open_menu()
        elif act == "close":
            self.menu = None

    @staticmethod
    def reveal(path: str) -> None:
        """プログラムのフォルダをFinder(など)で開く"""
        cmd = {"darwin": ["open"], "win32": ["explorer"]}.get(sys.platform, ["xdg-open"])
        try:
            subprocess.Popen(cmd + [path])
        except OSError:
            pass

    def paste(self) -> None:
        self.typer.add_text(self.clipboard())

    def export_program(self) -> None:
        """RAMにあるBASICのプログラムを、プログラムのフォルダに.basのファイルとして書き出す"""
        if self.typer.scripted:
            self.say(tr("app.export_after_typing_has"))
            return
        prog = self.last_prog
        try:
            path = export_program(self.m, programs.user_dir(), prog)
        except OSError as e:
            self.say(tr("app.cannot_export", error=e), 5)
            return
        if path is None:
            self.say(tr("app.no_program_export"))
        else:
            self.say(tr("app.exported_path", path=_short(path)), 5)

    def save_tape(self, samples) -> None:
        """CSAVEの音を、プログラムのフォルダに「tape-日時.wav」として書き出す"""
        try:
            path = os.path.join(programs.user_dir(), f"tape-{time.strftime('%Y%m%d-%H%M%S')}.wav")
            tape.write_wav(path, samples)
        except OSError as e:
            self.say(tr("app.cannot_write_tape_audio", error=e), 5)
            return
        self.say(tr("app.tape_audio_written", path=_short(path)), 6)

    def save_state(self) -> None:
        """いまの状態(RAM、CPU、ポート、タイマ)を保存する"""
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            self.m.save_state(self.state_file, self._prog_info())
        except OSError as e:
            self.say(tr("app.cannot_save_state", error=e), 5)
            return
        self.say(tr("app.state_saved_l_loads", c=CMD, s=SHIFT))

    def load_state(self, path: str | None = None) -> None:
        """保存した状態に戻す。pathがなければsave_stateの保存先から"""
        try:
            extra = self.m.load_state(path or self.state_file)
        except FileNotFoundError:
            self.say(tr("app.no_saved_state"))
            return
        except (OSError, ValueError) as e:
            self.say(tr("app.cannot_load_state", error=e), 5)
            return
        self._set_prog_info(extra)
        self._restored(tr("common.state_loaded"))

    def _prog_fields(self, prog: programs.Program | None) -> dict | None:
        """状態のファイルに書く、読み込んだプログラムの情報(programs.to_state)"""
        return None if prog is None else programs.to_state(prog)

    def _prog_info(self) -> dict:
        info = {
            "program": self._prog_fields(self.last_prog),
            "loading": self.loading,
            "help": self.load_help,
        }
        info["bench"] = self.bench.save()
        # 使っている割り当て(保存していない変更も)と、その対象のプログラム
        origin = self.pad_map.origin
        info["pad"] = {
            "keys": self.pad_map.keys, "dirty": self.pad_dirty,
            # 出どころは、訳した文ではなくIDと値で書く(戻したときの言語で出す)
            "source": origin.to_state() if isinstance(origin, Text) else origin,
            "program": self._prog_fields(self.pad_prog),
        }  # fmt: skip
        return info

    def _saved_prog(self, saved) -> programs.Program | None:
        """_prog_fieldsで書いたプログラムの情報を読む。おかしければNone"""
        return programs.from_state(saved)

    def _set_prog_info(self, info: dict | None) -> None:
        """_prog_infoで書いた情報に戻す。なければ、おかしければ、前に読み込んだプログラムの
        情報は使わずに消す(書き出すファイルに、RAMと関係のない名前や# hex:が付かないように)"""
        info = info if isinstance(info, dict) else {}
        prog = self._saved_prog(info.get("program"))
        loading, load_help = info.get("loading"), info.get("help")
        self.last_prog = prog
        self.loading = loading if isinstance(loading, str) else ""
        self.load_help = load_help if isinstance(load_help, str) else ""
        self.bench.restore(info.get("bench"))
        pad = info.get("pad")
        # 前の版の状態には割り当ての対象がないので、last_progを対象にする
        if isinstance(pad, dict) and "program" in pad:
            self.pad_prog = self._saved_prog(pad["program"])
        else:
            self.pad_prog = prog
        pad_map, dirty = self._saved_pad_map(pad, self.pad_prog)
        self.set_pad_map(pad_map)
        self.pad_dirty = dirty

    def _saved_pad_map(self, saved, prog: programs.Program | None) -> tuple[gamepad.PadMap, bool]:
        """状態に書いた割り当てと、保存していない変更があったか。なければ(前の版の状態)、
        おかしければ、読み込んだときのもの"""
        if isinstance(saved, dict) and isinstance(saved.get("keys"), dict):
            keys = {
                n: k for n, k in saved["keys"].items()
                if n in gamepad.ORDER and isinstance(k, str) and k in gamepad.KEY_NAMES
            }  # fmt: skip
            source = saved.get("source")
            # 前の版の状態は、訳した文で書いてある
            origin = source if isinstance(source, str) else Text.from_state(source, PAD_SOURCES)
            pad_map = gamepad.PadMap(keys, origin or "")
            return pad_map, saved.get("dirty") is True
        return self.pad_map_for(prog), False

    def _restored(self, message: str) -> None:
        """状態を戻したあと、打ち込みの残りや音を捨てる"""
        self.typer.restored()
        self.fast = False
        self.overshoot = 0
        self.buzzer.hold(self.m.pc_out >> 4)
        if self.speaker is not None:
            self.speaker.clear()
        self.say(message)

    def screenshot(self) -> None:
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            n = 1
            while os.path.exists(os.path.join(STATE_DIR, f"shot{n:03d}.png")):
                n += 1
            path = os.path.join(STATE_DIR, f"shot{n:03d}.png")
            shot = self.panel.out
            if self.lcd_only:
                shot = shot.subsurface(self.view_box())
            pygame.image.save(opaque(shot), path)
        except (OSError, pygame.error) as e:
            self.say(tr("app.cannot_save_screenshot", error=e), 5)
            return
        self.say(tr("app.saved_path", path=_short(path)))

    # ---- 録画 ----
    def toggle_recording(self) -> None:
        """録画を始める(前に選んだ形で)。録画中なら止めて、プログラムのフォルダに
        「rec-日時.mp4」として保存する"""
        if self.recorder is None:
            self.start_recording(self.rec_shape)
            return
        rec, self.recorder = self.recorder, None
        self.rec_paused = False
        self.say(tr("app.saving_recording"), 2)
        try:
            path = rec.close()
        except OSError as e:
            self.say(tr("app.cannot_save_recording", error=e), 6)
            return
        secs = round(rec.seconds)
        self.say(tr("app.recording_saved_seconds", path=_short(path), n=secs), 6)

    @property
    def rec_shape(self) -> str:
        """録画の形(recorder.SHAPES)。前に選んだもの(なければ液晶の拡大と本体)"""
        shape = self._view_pref("rec_shape")
        return shape if isinstance(shape, str) and shape in recorder.SHAPES else "both"

    def start_recording(self, shape: str) -> None:
        """形shape(recorder.SHAPES)で録画を始め、次に⇧⌘Rで始めるときのために形を覚える"""
        if self.recorder is not None:
            return
        prog = self.last_prog
        title = prog.title if prog else self.m.model.title
        sub = f"{self.m.model.title} / sc61box {_version()}"
        path = os.path.join(programs.user_dir(), f"rec-{time.strftime('%Y%m%d-%H%M%S')}.mp4")
        try:
            size = (self.panel.out_w, self.panel.out_h)
            self.recorder = recorder.Recorder(path, title, sub, size, self.panel.lcd_box(), shape)
        except (OSError, ImportError) as e:
            self.say(tr("app.cannot_start_recording", error=e), 6)
            return
        self._save_view(rec_shape=shape)
        self.rec_buzzer = Buzzer()
        self.rec_print_sound = PrinterSound()
        self.say(
            tr("app.recording_press_r_again",
               c=CMD, s=SHIFT), 4
        )  # fmt: skip

    def toggle_pause(self) -> None:
        """録画を一時停止する。一時停止中なら続きを録る(止めているあいだは動画に入らない)"""
        if self.recorder is None:
            return
        self.rec_paused = not self.rec_paused
        if not self.rec_paused:
            self.rec_buzzer.hold(self.m.pc_out >> 4)
        self.say(tr("app.recording_paused") if self.rec_paused else tr("app.recording_resumed"), 2)

    def record_frame(self, surf, c0: int, live: bool) -> None:
        """1フレームぶんの絵と音を録画に足す。liveでないとき(読み込み中、電源が切れている
        とき)は無音にする"""
        rec = self.recorder
        assert rec is not None
        m = self.m
        if live and m.cpu.cycles != c0:
            pcm = self._render(self.rec_buzzer, c0, keep_silent=True)
            pcm = self.rec_print_sound.mix(pcm, self.paper.moved, self.print_rate)
        else:
            self.rec_buzzer.hold(m.pc_out >> 4)
            pcm = bytes(2 * recorder.SPF)
        rec.add(pygame.image.tobytes(surf, "RGB"), pcm)
        if rec.error:
            self.recorder = None
            rec.abort()
            self.say(tr("app.recording_stopped", error=rec.error), 6)

    def _font(self) -> pygame.font.Font:
        if self.font is None:
            self.font = load_help_font(17)
        return self.font

    def _small_font(self) -> pygame.font.Font:
        if self.small_font is None:
            self.small_font = load_help_font(13)
        return self.small_font

    # ---- 本体 ----
    def handle(self, ev) -> bool:
        if ev.type == pygame.QUIT:
            return False
        if self.help and ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            # キーの説明は、何か押すかクリックしたら消す(その操作もそのまま効く)
            if ev.type != pygame.KEYDOWN or ev.key not in (pygame.K_SLASH, pygame.K_F10):
                self.help = 0
        if ev.type == pygame.KEYDOWN:
            self.key_down(ev)
        elif ev.type == pygame.KEYUP:
            self.key_up(ev)
        elif ev.type == pygame.TEXTINPUT:
            self.text_input(ev.text)
        elif ev.type == pygame.MOUSEBUTTONDOWN and (
            ev.button == 3 or (ev.button == 1 and MAC and pygame.key.get_mods() & pygame.KMOD_CTRL)
        ):
            if self.menu is None:
                self.open_popup(ev.pos)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self.mouse_down(ev.pos)
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
            self.mouse_up()
        elif ev.type in PAD_EVENTS:
            self.pad_event(ev)
        elif ev.type == pygame.MOUSEWHEEL and self.menu is not None:
            self.menu.scroll(-ev.y)
        elif (
            ev.type == pygame.MOUSEWHEEL
            and self.pane_open
            and self.pane_keys()
            and pygame.mouse.get_pos()[0] - self.origin[0] >= self.body_size[0]
        ):
            self.bench.page(-ev.y, 1)  # 作業欄の上のホイールで、ダンプを1行ずつ動かす
        elif ev.type == pygame.MOUSEWHEEL and self.paper_open:
            self.scroll_paper(ev.y)
        elif ev.type == pygame.MOUSEMOTION and self.popup is not None:
            self.popup.sel = self.popup.hit(ev.pos)
        elif ev.type == pygame.MOUSEMOTION and not self.dragging_switch:
            pos = self._in_content(ev.pos)
            self.bar.hover = self.bar.hit(pos)
            if self.pane_open:
                hit = self.bench_view.hit(pos)
                self.bench_view.hover = hit[1] if hit and hit[0] == "button" else -1
                self.bench_view.why_at = hit[1] if hit and hit[0] == "why" else -1
                self.bench_view.span_hover = bool(hit and hit[0] == "span")
        elif ev.type == pygame.MOUSEMOTION and self.dragging_switch:
            self.set_switch_from(self._in_content(ev.pos)[1] / self.scale - display.MARGIN)
        elif ev.type == pygame.VIDEORESIZE:
            self.resized(ev.w, ev.h)
        elif ev.type == pygame.WINDOWSIZECHANGED:
            self.resized(ev.x, ev.y)
        elif ev.type in (pygame.WINDOWRESTORED, pygame.WINDOWMAXIMIZED):
            self.resized(*self.window.get_size())
        elif ev.type == pygame.DROPFILE:
            self.open_file(ev.file)
        elif ev.type == pygame.WINDOWLEAVE:
            self.bar.hover = -1
        elif ev.type == pygame.WINDOWFOCUSLOST:
            self.release_all()
        return True

    def release_all(self) -> None:
        """パソコンのキーとマウスで押しているものを、すべて離す。ほかのウィンドウに移ると
        キーを離したことが届かないので、押したままにならないようにする"""
        self.typer.release_physical()
        self.held_key = None
        self.mouse_up()
        self.pad_release_all()
        self.brk_by.clear()
        self.m.brk = self.m.reset_key = False

    def frame(self, poll: Callable[[], None] | None = None) -> None:
        """1フレームぶん(1/FPS秒)動かして描く。pollがあれば、本体の実行をSUBSTEPSに分けた
        合間に呼ぶ(runがキーのイベントを受け取り、時間を合わせる)"""
        m = self.m
        self._key_repeat()
        if not self.halted:
            self._count_down()
        typing = self.typer.scripted and not self.boot_frames
        speed = self.turbo * (8 if typing else 1)
        c0 = m.cpu.cycles
        m.sound_events.clear()
        if self.halted or (self.bench_only and self.bench.state != "run"):
            speed = 0
        elif self.fast and self.typer.busy and not self.boot_frames:
            # 読み込み中は時計に合わせず、1フレームの時間いっぱいまで回す
            speed = 0
            end = time.perf_counter() + 0.8 / FPS
            while time.perf_counter() < end and self.typer.busy:
                self.typer.step()
                # 打ったCALLでマシン語が動き出せば、ブレークポイントで止まる(読み込みの途中でも)
                if self._run_cpu(CLOCK // 200):
                    break
        elif self.fast:
            self.fast = False
            if self.load_help:
                self.say_loaded(self.load_help, 20)
            else:
                self.say_loaded(tr("app.loaded", name=self.loading))
        basic = m.basic
        if basic is not None and basic.notice is not None:
            self.say(
                tr("app.rom_less_basic_has",
                   addr=basic.notice), 8,
            )  # fmt: skip
            self.warning = Text("app.routine_rom_address_not", addr=basic.notice)
            basic.notice = None
        if basic is not None and basic.stalled is not None:
            r = basic.stalled
            self.say(
                tr("app.stopped_stand_kept_waiting", name=r.name, addr=r.addr,
                   file=os.path.basename(r.source) if r.source else tr("common.builtin")), 8,
            )  # fmt: skip
            self.warning = routines.Stalled(r).text
            basic.stalled = None
        speaker = self.speaker if bool(speed) and not typing else None  # 鳴らすときだけ
        adjust = speed_adjust(speaker.level()) if speaker is not None else 1
        self.paper.tick()
        if self._advance(int(speed * (CLOCK // FPS) * adjust), poll):
            # 合間に状態を復元した。音と録画は復元した所から先だけにする(復元前の時刻からの
            # 差で、何秒ぶんもの音を作らないように)
            c0 = m.cpu.cycles
            self.rush_spans = []  # 復元前のサイクルで記録した、速く回した区間も使わない
            self.buzzer.hold(m.pc_out >> 4)
            self.rec_buzzer.hold(m.pc_out >> 4)
        wav = self.tape_out.feed(m.sound_events, m.cpu.cycles, m.pc_out >> 4)
        if wav is not None:
            self.save_tape(wav)
        if speaker is not None:
            printing = self.paper.moved
            keep = speaker.keep_silent or printing or self.print_sound.active
            pcm = self._render(self.buzzer, c0, keep_silent=keep)
            speaker.push(self.print_sound.mix(pcm, printing, self.print_rate))
        elif self.speaker is not None:
            self.buzzer.hold(m.pc_out >> 4)
            self.speaker.clear()
        if m.tape is not None and m.tape.done(m.cpu.cycles):
            m.tape = None
            self.say(tr("app.end_tape"))
        pressed = set(m.held) | ({"BRK"} if m.brk else set())
        surf = self.panel.draw(
            m.columns(), m.symbols(), m.display_on() or self.lcd_any_on, m.mode, pressed,
            powered=m.power,
            duty=self.lcd_duty,
        )  # fmt: skip
        if self.recorder is not None and not self.rec_paused:
            self.record_frame(surf, c0, bool(speed) and not typing)
        self._show(surf)

    def _count_down(self) -> None:
        """起動のあとの待ちと、RESETボタンを押している時間を数える"""
        m = self.m
        if self.boot_frames:
            self.boot_frames -= 1
            if self.boot_frames == 0 and self.load_blocks is not None:
                blocks, self.load_blocks = self.load_blocks, None
                self.write_dump(blocks)
                self.bench.set_start(blocks)
            if self.boot_frames == 0 and self.pending:
                prog, run = self.pending
                self.open_program(prog, run)
                self.pending = None
        if self.reset_frames:
            self.reset_frames -= 1
            if self.reset_frames == 0:
                m.reset_key = False

    def _render(self, buzzer: Buzzer, c0: int, keep_silent: bool) -> bytes:
        """このフレーム(サイクルc0〜いま)の音。パソコンのキーを速く届けたあいだ(rush_spans)は
        RUSH倍に縮めて、実際にたった時間の長さの音にする(録画やスピーカーの音が、速く
        回したぶん長く引き延ばされないように。ほかのところの音の高さと長さは変えない)"""
        m = self.m
        out, at = [], c0
        for a, b in [*self.rush_spans, (m.cpu.cycles, m.cpu.cycles)]:
            if a > at:
                out.append(buzzer.render(m.sound_events, at, a, self.turbo, keep_silent))
            if b > a:
                out.append(buzzer.render(m.sound_events, a, b, self.turbo * RUSH, keep_silent))
            at = max(at, b)
        return b"".join(out)

    def _advance(self, cycles: int, poll: Callable[[], None] | None = None) -> bool:
        """cyclesだけ動かす。前のフレームで命令の途中まではみ出した分は差し引く
        (音のサンプルの数が再生の速さとそろうように)。pollがあればSUBSTEPSに分けて、
        合間に呼ぶ。合間に状態を復元した(サイクルが変わった)ときはTrue"""
        m = self.m
        target = m.cpu.cycles + cycles - self.overshoot
        self.overshoot = 0
        self.rush_spans = []
        # このフレームのあいだに液晶RAMに書いたものを記録する(_lcd_duty)
        start = m.cpu.cycles
        self.lcd_was_on = m.display_on()
        m.lcd_trace = []
        parts = SUBSTEPS if poll is not None else 1
        done, restored = True, False
        for k in range(parts):
            end = m.cpu.cycles + max(0, target - m.cpu.cycles) // (parts - k)
            while (left := target - m.cpu.cycles) > 0 and m.cpu.cycles < end:
                rush = False
                if not self.boot_frames:
                    self.typer.step()
                    rush = self.typer.rushing and bool(cycles)
                before = m.cpu.cycles
                if self._run_cpu(min(left, CLOCK // (1000 if rush else 200))):
                    done = False
                    break
                if rush:
                    # パソコンのキーをROMの入力待ちに届けているあいだは、RUSH倍の速さで回す
                    # (1打鍵ごとのROMの読み取りの待ちを縮めて、打ち込みのもたつきをなくす)
                    grown = (m.cpu.cycles - before) * (RUSH - 1) // RUSH
                    target += grown
                    end += grown
                    spans = self.rush_spans
                    if spans and spans[-1][1] == before:
                        spans[-1] = (spans[-1][0], m.cpu.cycles)
                    else:
                        spans.append((before, m.cpu.cycles))
                if m.cpu.cycles == before:  # 電源が切れていて時間が進まない
                    done = False
                    break
            if not done:
                break
            if poll is not None and k < parts - 1:
                mark = m.cpu.cycles
                poll()
                # 合間の操作で、一時停止、状態の復元(サイクルが変わる)、作業欄の実行の中止、
                # ウィンドウを閉じる操作があれば、復元前の目標では動かさない
                stopped = self.bench_only and self.bench.state != "run"
                restored = m.cpu.cycles != mark
                if self.closing or self.halted or stopped or restored:
                    done = False
                    break
        if done:
            self.overshoot = m.cpu.cycles - target
        self.lcd_duty = self._lcd_duty(start, m.lcd_trace or [])
        m.lcd_trace = None
        return restored

    def _lcd_duty(
        self, start: int, trace: list[tuple[int, int, int, int]]
    ) -> dict[int, list[float]]:
        """液晶RAMに書いた記録から、このフレーム(サイクルstart〜いま)のあいだに中身が
        変わった列の、各ドット(ビット0〜7)が点いていた時間の割合を求める。書き換えの
        途中の短い中身は、その短さの分だけ薄く出る。液晶を消していたあいだ(Cポートの
        ビット0。ROMはそのあいだ液晶RAMを作業に使う)は点いていないとみる。液晶を点けたり
        消したりしたフレームでは、すべての列を求める"""
        m = self.m
        end = m.cpu.cycles
        total = end - start
        self.lcd_any_on = m.display_on()
        if not trace or total <= 0:
            return {}
        cols = self.lcd_cols
        # 液晶を点けていたあいだ
        spans: list[tuple[int, int]] = []
        on_since = start if self.lcd_was_on else None
        toggled = False
        for c, a, _old, new in trace:
            if a != -1:
                continue
            toggled = True
            if new and on_since is None:
                on_since = c
            elif not new and on_since is not None:
                spans.append((on_since, c))
                on_since = None
        if on_since is not None:
            spans.append((on_since, end))
        self.lcd_any_on = bool(spans) and m.power

        def shown(c0: int, c1: int) -> int:
            return sum(max(0, min(c1, b) - max(c0, a)) for a, b in spans)

        cur: dict[int, tuple[int, int]] = {}  # 番地: (いまの値, その値になったサイクル)
        if toggled:
            mem = m.mem
            for _c, a, old, _new in reversed(trace):  # フレームの初めの値
                if a in cols:
                    cur[a] = (old, start)
            for a in cols:
                cur.setdefault(a, (mem[a], start))
        lit: dict[int, list[int]] = {}

        def add(a: int, v: int, c0: int, c1: int) -> None:
            n = shown(c0, c1)
            if v and n > 0:
                acc = lit.setdefault(a, [0] * 8)
                for b in range(8):
                    if v >> b & 1:
                        acc[b] += n

        for c, a, old, new in trace:
            if a not in cols:
                continue
            v, since = cur.get(a, (old, start))
            add(a, v, since, c)
            cur[a] = (new, c)
        duty: dict[int, list[float]] = {}
        for a, (v, since) in cur.items():
            add(a, v, since, end)
            share = [n / total for n in lit.get(a, [0] * 8)]
            for i in cols[a]:
                duty[i] = share
        return duty

    def _run_cpu(self, cycles: int) -> bool:
        """CPUを最大cyclesサイクル動かす。作業欄のブレークポイント、呼び出しの戻り先、ROMなしでは
        RAMの外と代替ROMルーチンも、ここで調べる(本体を動かすところは、すべてここを
        通す)。作業欄の実行が止まったらTrue"""
        m, bench = self.m, self.bench
        if bench.state == "run" and bench.pass_pc is not None:
            # 再帰の内側の戻り先を、止めずに1命令だけ進める。終わらないプログラムでも、
            # 1回に1命令ずつなので、フレームのサイクルを使い切れば画面に戻る
            bench.pass_step()
            stopped = bench.state != "run"
        else:
            guard = bench.guard() if bench.state == "run" and bench.needs_guard() else None
            # 作業欄を出しているあいだは、実行した番地を覚える(逆アセンブルの命令のマーク)。
            # しまっていれば覚えない(ROMのBASICを、マークをつけずに速く動かす)
            seen = bench.executed if self.pane_open else None
            # 止まっても、代替ROMルーチンを済ませただけなら(trapped)続ける
            stopped = m.run(cycles, guard, seen) and not bench.trapped()
        if stopped:
            self._bench_stopped()  # 終わったか、ブレークポイントかRAMの外で一時停止した
        return stopped

    def _bench_stopped(self) -> None:
        """作業欄の実行が止まった(終わったか、ブレークポイントなどで一時停止した)。押しているキーを
        離す。ROMのある本体で作業欄をしまっていれば、止まった所を見せるために出す"""
        self.release_all()
        if not self.bench_only and self.bench.state == "pause":
            self.toggle_pane(True)

    def _show(self, surf: pygame.Surface) -> None:
        """本体の絵をウィンドウに貼り、一覧やメッセージを重ねる"""
        self.check_printer()
        self._track_window()
        font = self._font()
        if (
            self.lcd_only
            and self.free_size is not None
            and self.body_size[0] < Bar.min_width(font, self.bar_buttons())
        ):
            # 再開・録画・言語の切り替えなどでボタンが広がったときも、全部入る幅にする。
            self._refit()
        self._open_window()  # 一覧やメニューの開け閉めで、液晶だけの細いウィンドウの高さが変わる
        win = out = self.window
        content = self._window_size()
        copy = False  # 中身を別の面に描いてウィンドウにコピーするか(ウィンドウが中身より小さいとき)
        if win.get_size() != content:  # 利用者が変えたウィンドウ。中身はまんなかに、まわりは暗く
            win.fill((20, 21, 24))
            ox, oy = self.origin
            copy = content[0] + ox > win.get_width() or content[1] + oy > win.get_height()
            out = pygame.Surface(content) if copy else win.subsurface((ox, oy, *content))
        w, h = self.body_size
        body = out.subsurface((0, 0, w, h))
        if self.lcd_only:
            surf = surf.subsurface(self.view_box())
        if self.scale == 1.0:
            body.blit(surf, (0, 0))
        else:
            # pygame 2.6.1のGENERICの縦拡大は、描画先の行の余白(pitch)を飛ばさない。
            # ウィンドウの一部へ直接書くと絵が斜めに流れるので、独立した面に拡大してから貼る。
            if self.scaled_body is None or self.scaled_body.get_size() != (w, h):
                self.scaled_body = pygame.transform.smoothscale(surf, (w, h))
                # 本体の絵は不透明。Cocoaの未使用alpha=0をsmoothscaleが透明として
                # 引き継ぐことがあるので、貼るときは透明度を使わない。
                self.scaled_body.set_alpha(None)
            else:
                pygame.transform.smoothscale(surf, (w, h), self.scaled_body)
            body.blit(self.scaled_body, (0, 0))
        top = h
        if self.printout is not None:
            rows = self.paper_rows()
            where = []
            if self.printout.file:
                folder, name = os.path.split(_short(self.printout.file))
                where = [tr("app.saved_click_open"), folder + os.sep, name]
            self.paper.draw(out, top, rows[: len(rows) - self.paper_back], where)
            top += self.paper.height
        self.bar.buttons = self.bar_buttons()
        left = out.subsurface((0, 0, w, out.get_height())) if self.pane_open else out
        if self.pad_panel is not None:
            pressed = self.pads.pressed()
            small = self._small_font()
            if not self.lcd_only:
                padmenu.draw_badges(
                    body, small, self.panel.key_rects, self.scale, display.MARGIN, self.pad_map,
                    self.pad_panel.selected, pressed,
                )  # fmt: skip
            self.pad_panel.draw(
                left, top, font, small, self.pads.names(), self.pad_map, pressed,
                *self._pad_target(), self.pad_dirty,
            )  # fmt: skip
            top += self.pad_panel.height
        self.bar.draw(left, font, top, self.bar_info())
        notice = body  # メッセージを出す場所
        if self.pane_open:
            # 作業欄は右に置き、本体と操作欄の下のあいたところにメッセージを出す
            below = top + BAR_H
            if below < out.get_height():
                out.fill((20, 21, 24), (0, below, w, out.get_height() - below))
                notice = out.subsurface((0, below, w, out.get_height() - below))
            pane = pygame.Rect(w, 0, benchview.PANE_W, out.get_height())
            self.bench_view.draw(out, pane)
        if self.fast:
            done = int(100 * min(1.0, max(0.0, 1 - len(self.typer.queue) / self.load_total)))
            if self.load_typing:
                text = tr("app.typing_esc_stops", name=self.loading, pct=done)
            else:
                text = tr("app.loading_esc_stops", name=self.loading, pct=done)
            draw_status(notice, font, text)
        elif self.status and time.monotonic() < self.status_until:
            draw_status(notice, font, self.status)
        if self.recorder is not None:
            draw_recording(out, font, self.recorder.seconds, self.rec_paused)
        self.warning_rect = pygame.Rect(0, 0, 0, 0)
        if self.halted and not self.pane_open:  # 作業欄を出していれば、作業欄に出る
            draw_halted(out, font, tr("app.paused_p_resumes", c=CMD))
        elif self.warning:
            self.warning_rect = draw_warning(out, font, self.warning)
        if copy:
            win.blit(out, self.origin)
        # キーの説明、一覧、メニューはウィンドウ全体に描く(液晶だけのウィンドウでは、中身より広い
        # 所を使う)
        if self.help:
            self.help -= 1
            draw_help(win, font, help_lines(self.bench_only, self.is1350))
        if self.menu is not None:
            self.menu.draw(win, font, self.m.model.name, _short(programs.user_dir()))
        if self.popup is not None:
            self.popup.draw(win, font, self.popup_items(), self.popup_mark())
        pygame.display.flip()

    @staticmethod
    def _view_prefs() -> dict:
        """作業欄の見え方の記録(view_file)。なければ空"""
        try:
            with open(view_file(), encoding="utf-8") as f:
                prefs = json.load(f)
        except (OSError, ValueError):
            return {}
        return prefs if isinstance(prefs, dict) else {}

    def _view_pref(self, key: str) -> object:
        return self._view_prefs().get(key)

    def _iram_shown(self) -> bool:
        """作業欄の内部RAMを開いておくか。前に開いた・閉じたものがあればそれに従う。なければ
        開いておくが、開いた作業欄が画面の高さに入らなければ閉じておく"""
        shown = self._view_pref("show_iram")
        if isinstance(shown, bool):
            return shown
        try:
            _dw, dh = pygame.display.get_desktop_sizes()[0]
        except (pygame.error, IndexError):
            return True
        return self.bench_view.min_height(True) <= dh - 120

    def _save_view(self, lang: str | None = None, rec_shape: str | None = None) -> None:
        """作業欄の内部RAMを開いたか閉じたか、ROMのある本体で作業欄を出したかを覚えておく
        (次に起動したときも同じにする)。langはメニューで選んだ画面の言語、rec_shapeは録画の形"""
        prefs = self._view_prefs()
        prefs["show_iram"] = self.bench_view.show_iram
        if self.panel.can_pack:  # PC-1350は詰めるすきまがないので、ほかの機種の設定を残す
            prefs["packed_lcd"] = self.panel.packed
        if not self.bench_only:
            # 液晶だけのあいだは作業欄を隠しているだけなので、隠す前のほうを覚える
            prefs["show_pane"] = self.pane_before_lcd if self.lcd_only else self.pane_open
        if lang:
            prefs["lang"] = lang
        if rec_shape:
            prefs["rec_shape"] = rec_shape
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(view_file(), "w", encoding="utf-8") as f:
                json.dump(prefs, f)
        except OSError:
            pass

    def pane_keys(self) -> bool:
        """パソコンのキーを、本体ではなく作業欄で受けるか。ROMなしでは実行していないあいだ。
        ROMがあれば、作業欄を出していて、作業欄をクリックしたあとか一時停止しているあいだ"""
        b = self.bench
        if self.lcd_only:
            return False
        if self.bench_only:
            return b.state != "run"
        return self.pane_open and (self.bench_view.focus or b.state == "pause")

    def toggle_pane(self, on: bool | None = None) -> None:
        """ROMのある本体で、マシン語の作業欄を出すかしまう(ウィンドウの幅が変わる)。液晶だけの
        あいだは出せない"""
        if self.bench_only:
            return
        on = not self.pane_open if on is None else on
        if on == self.pane_open or (on and self.lcd_only):
            return
        self.pane_open = on
        self.bench_view.focus = False
        self.release_all()
        self._save_view()
        self._refit()

    def _load_bench_info(self, info: object) -> None:
        """終了したときに保存した作業欄の情報を戻す。なければ(前の版のRAM)、RAMの0でない
        所を書いた範囲とする"""
        b = self.bench
        if isinstance(info, dict):
            info["state"] = "edit"  # CPUは起動し直しているので、続きからは動かせない
            b.restore(info, "")
        elif self.bench_only:  # ROMのある本体のRAMにはBASICなども入っているので、推定しない
            b.mark_nonzero()

    def close(self) -> None:
        self._finish_paper()
        if self.save_ram:
            if self.m.power and not self.norom:
                self.m.power_off()
            elif self.m.basic is not None:
                self.m.basic.mark_off()  # ROMのある本体でも、このRAMを読めるように
            # 作業欄の開始番地、ブレークポイント、書いた範囲も、RAMと一緒に覚えておく。保存
            # できなくても(プログラムのフォルダに同じ名前のファイルがあるなど)、録画の保存と
            # 後始末は続ける
            try:
                os.makedirs(STATE_DIR, exist_ok=True)
                self.m.save_ram(self.ram_file)
                with open(bench_file(self.ram_file), "w", encoding="utf-8") as f:
                    info = {**self.bench.save(), "state": "edit", "ram_top": self.m.model.ram[1]}
                    json.dump(info, f)
            except OSError as e:
                print(tr("app.cannot_save_ram", error=e), file=sys.stderr)
        if self.recorder is not None:
            self.toggle_recording()  # 録画中に閉じたら、そこまでを保存する
        if self.speaker is not None:
            self.speaker.close()
        pygame.quit()

    def run(self) -> None:
        clock = pygame.time.Clock()
        self.closing = False

        def poll() -> None:
            clock.tick(FPS * SUBSTEPS)
            self._pump()

        try:
            while not self.closing:
                self._pump()
                self.frame(poll)
                clock.tick(FPS * SUBSTEPS)
        finally:  # 予期しない例外で止まっても、RAMと印字は保存する
            self.close()

    def _pump(self) -> None:
        """たまっているイベントを本体に届ける。閉じる操作があればclosingにする"""
        try:
            events = pygame.event.get()
        except (KeyError, SystemError):  # パッドを外したときのpygameの例外(Pads.sync)
            events = []
            self.pad_sync()
        for ev in events:
            if not self.handle(ev):
                self.closing = True


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"sc61box {_version()}")
        raise typer.Exit()


def make_cli() -> typer.Typer:
    """コマンドラインの入口。オプションの説明は、作ったときの言語で書く(cliは、--langと
    SC61BOX_LANGなどで言語を決めてから作る)"""
    app = typer.Typer(add_completion=False, help=tr("app.sharp_pc_1251_pc"))

    @app.command()
    def main(
        program: str | None = typer.Argument(None, help=tr("app.program_load_path_bas")),
        run: bool = typer.Option(False, "--run", help=tr("app.run_after_loading")),
        scale: float = typer.Option(1.0, help=tr("app.window_scale")),
        type_: str | None = typer.Option(None, "--type", help=tr("app.type_contents_file_after")),
        load: str | None = typer.Option(None, help=tr("app.write_hex_dump_address")),
        fresh: bool = typer.Option(False, help=tr("app.do_not_load_saved")),
        mute: bool = typer.Option(False, help=tr("app.no_sound")),
        persist: float = typer.Option(1.0, help=tr("app.strength_lcd_afterglow_0")),
        export: str | None = typer.Option(
            None,
            help=tr("app.export_basic_program_saved"),
        ),
        model: str = typer.Option(
            "1251",
            help=tr("app.model_1250_1251_1255"),
        ),
        card: int = typer.Option(0, help=tr("app.size_pc_1350_ram")),
        overseas: bool = typer.Option(
            False,
            help=tr("app.run_pc_1350_wired"),
        ),
        numpad: bool = typer.Option(False, help=tr("app.arrow_keys_press_number")),
        lcd: bool = typer.Option(
            False,
            "--lcd",
            help=tr("app.show_only_lcd_without"),
        ),
        tape_: str | None = typer.Option(None, "--tape", help=tr("app.insert_cassette_audio_wav")),
        state: str | None = typer.Option(None, help=tr("app.start_saved_state_written")),
        norom: bool = typer.Option(
            False,
            "--norom",
            help=tr("app.run_without_rom_rom"),
        ),
        no_basic: bool = typer.Option(
            False,
            "--no-basic",
            help=tr("app.without_rom_run_only"),
        ),
        lang: str | None = typer.Option(
            None,
            "--lang",
            help=tr("app.display_language_ja_en"),
        ),
        check_routines: str | None = typer.Option(
            None,
            "--check-routines",
            help=tr("app.compare_rom_routine_stand"),
        ),
        list_routines: bool = typer.Option(
            False,
            "--list-routines",
            help=tr("app.list_rom_routine_stand"),
        ),
        new_routine: str | None = typer.Option(
            None,
            "--new-routine",
            help=tr("app.create_file_start_rom"),
        ),
        version_: bool = typer.Option(
            False,
            "--version",
            callback=_show_version,
            is_eager=True,
            help=tr("app.print_version_exit"),
        ),
    ) -> None:
        args = Options(
            model=model,
            card=card,
            overseas=overseas,
            norom=norom,
            basic=not no_basic,
            scale=scale,
            persist=persist,
            fresh=fresh,
            mute=mute,
            numpad=numpad,
            lcd=lcd,
            lang=lang,
            program=program,
            run=run,
            type=type_,
            load=load,
            tape=tape_,
            state=state,
        )
        start(args, export, check_routines, new_routine, list_routines)

    return app


def start(
    args: Options,
    export: str | None = None,
    check_routines: str | None = None,
    new_routine: str | None = None,
    list_routines: bool = False,
) -> None:
    """オプションを確かめて起動する。exportがあれば、保存したRAMのBASICを書き出して終わる。
    check_routinesとnew_routineは、代替ROMルーチンを比べるか書き始めて終わる(_routine_tool)。
    前の名前のデータのフォルダ(~/.pc1251)があれば、新しい名前(~/.sc61box)に移す"""
    global STATE_DIR
    old = paths.old_data_dir()
    if old is not None and paths.migrate():
        args.moved_data = "~/" + os.path.basename(old)
    STATE_DIR = paths.data_dir()
    if args.lang is not None and args.lang not in i18n.LANGUAGES:
        typer.echo(tr("app.language_must_ja_en"), err=True)
        raise typer.Exit(2)
    i18n.set_language(i18n.choose(args.lang, App._view_prefs().get("lang")))
    model, card = args.model, args.card
    if model not in MODELS:
        typer.echo(
            tr("app.model_must_one", models=tr("common.ideographic_comma").join(sorted(MODELS))),
            err=True,
        )
        raise typer.Exit(2)
    if card not in (0, 8, 16):
        typer.echo(tr("app.ram_card_size_must"), err=True)
        raise typer.Exit(2)
    if MODELS[model].family != "1350":
        args.card = card = 0
    for line in routines.load_user():
        typer.echo(line, err=True)
    if check_routines is not None or new_routine is not None or list_routines:
        _routine_tool(model, check_routines, new_routine, list_routines)
        return
    if export is not None:
        # 起動のときと同じにROMを使うかを決め、そのときに保存するRAMのファイルを読む
        m, norom = open_machine(model, card, args.overseas, args.norom, args.basic)
        saved = ram_file(model, card, norom)
        apply_ram_top(m, saved_info(saved))
        if not m.load_ram(saved):
            typer.echo(tr("app.does_not_exist", path=saved), err=True)
            raise typer.Exit(1)
        path = export_program(m, export)
        typer.echo(path or tr("app.no_program_export"))
        return
    try:
        App(args).run()
    except (RomNotFound, FileNotFoundError, DumpError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from e


def _routine_tool(model: str, check: str | None, new: str | None, show: bool = False) -> None:
    """--list-routinesで一覧を出すか、--new-routineでファイルを作るか、--check-routinesでROMの
    ある本体と比べる"""
    if routines.family_of(model) is None:
        typer.echo(tr("common.model_has_no_rom", model=model), err=True)
        raise typer.Exit(2)
    if show:
        typer.echo(routine_list_text(model))
        return
    if new is not None:
        at, _, name = new.partition(":")
        try:
            addr = int(at.strip().removeprefix("&").removeprefix("0x"), 16)
            path = routines.write_template(model, addr, name.strip())
        except FileExistsError as e:
            typer.echo(tr("app.already_exists", path=e.filename), err=True)
            raise typer.Exit(1) from e
        except ValueError as e:
            typer.echo(tr("app.write_address_hex_name", text=new), err=True)
            raise typer.Exit(2) from e
        typer.echo(path)
        return
    assert check is not None
    try:
        reports = routinecheck.check(model, check)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(2) from e
    except RomNotFound as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from e
    if not reports:
        typer.echo(tr("app.no_stand_ins_compare", folder=routines.user_folder()))
        return
    typer.echo(routinecheck.report_text(reports))
    if not all(r.ok for r in reports):
        raise typer.Exit(1)


def routine_list_text(model: str) -> str:
    """--list-routinesの一覧(番地、名前、使うか、書いたファイル、使わない理由)"""
    lines = []
    for r, why in routines.listing(model):
        where = tr("common.builtin") if r.builtin else r.source
        mode = f" {r.mode}" if r.mode else ""
        if why:
            lines.append(tr("app.addr_name_mode_where", addr=r.addr, name=r.name,
                            mode=mode, where=where, why=why))  # fmt: skip
        else:
            lines.append(f"OK  {r.addr:04X} {r.name}{mode} {where}")
    return "\n".join(lines)


def _asked_language(argv: list[str]) -> str | None:
    """コマンドの引数の--lang(--helpの説明の言語を決めるため、typerが読む前に見る)"""
    for i, arg in enumerate(argv):
        if arg == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--lang="):
            return arg.split("=", 1)[1]
    return None


def cli() -> None:
    asked = _asked_language(sys.argv[1:])
    i18n.set_language(i18n.choose(asked, App._view_prefs().get("lang")))
    make_cli()()


if __name__ == "__main__":
    cli()

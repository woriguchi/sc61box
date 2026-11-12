"""コマンドの入口(sc61box)。引数を読んで画面を開くか、保存したRAMのプログラムの書き出しや
代替ROMルーチンの一覧・比べ・書き始めをして終わる

uv run sc61box          # 起動
uv run sc61box --model 1245  # PC-1245として起動する
uv run sc61box --model 1261  # PC-1261として起動する(1260、1262も選べる)
uv run sc61box --model 1350 --card 16  # PC-1350として、16KBのRAMカードを差して起動する
uv run sc61box --type prog.bas # 起動後にファイルの中身をキー入力する
uv run sc61box --load dump.txt # 16進ダンプをRAMへ書き込む
uv run sc61box primes --run  # プログラムのフォルダのprimes.basを読み込んで実行する
"""

import os
import sys

import typer

from . import app as app_module
from . import i18n, paths, routinecheck, routines
from .app import (
    App,
    DumpError,
    Options,
    apply_ram_top,
    export_program,
    open_machine,
    ram_file,
    saved_info,
)
from .i18n import tr
from .machine import MODELS, RomNotFound


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"sc61box {app_module._version()}")
        raise typer.Exit()


def make_cli() -> typer.Typer:
    """コマンドラインの入口。オプションの説明は、作ったときの言語で書く(cliは、--langと
    SC61BOX_LANGなどで言語を決めてから作る)"""
    app = typer.Typer(add_completion=False, help=tr("cli.sharp_pc_1251_pc"))

    @app.command()
    def main(
        program: str | None = typer.Argument(None, help=tr("cli.program_load_path_bas")),
        run: bool = typer.Option(False, "--run", help=tr("cli.run_after_loading")),
        scale: float = typer.Option(1.0, help=tr("cli.window_scale")),
        type_: str | None = typer.Option(None, "--type", help=tr("cli.type_contents_file_after")),
        load: str | None = typer.Option(None, help=tr("cli.write_hex_dump_address")),
        fresh: bool = typer.Option(False, help=tr("cli.do_not_load_saved")),
        mute: bool = typer.Option(False, help=tr("cli.no_sound")),
        persist: float = typer.Option(1.0, help=tr("cli.strength_lcd_afterglow_0")),
        export: str | None = typer.Option(
            None,
            help=tr("cli.export_basic_program_saved"),
        ),
        model: str = typer.Option(
            "1251",
            help=tr("cli.model_1250_1251_1255"),
        ),
        card: int = typer.Option(0, help=tr("cli.size_pc_1350_ram")),
        overseas: bool = typer.Option(
            False,
            help=tr("cli.run_pc_1350_wired"),
        ),
        numpad: bool = typer.Option(False, help=tr("cli.arrow_keys_press_number")),
        lcd: bool = typer.Option(
            False,
            "--lcd",
            help=tr("cli.show_only_lcd_without"),
        ),
        tape_: str | None = typer.Option(None, "--tape", help=tr("cli.insert_cassette_audio_wav")),
        state: str | None = typer.Option(None, help=tr("cli.start_saved_state_written")),
        norom: bool = typer.Option(
            False,
            "--norom",
            help=tr("cli.run_without_rom_rom"),
        ),
        no_basic: bool = typer.Option(
            False,
            "--no-basic",
            help=tr("cli.without_rom_run_only"),
        ),
        lang: str | None = typer.Option(
            None,
            "--lang",
            help=tr("cli.display_language_ja_en"),
        ),
        check_routines: str | None = typer.Option(
            None,
            "--check-routines",
            help=tr("cli.compare_rom_routine_stand"),
        ),
        list_routines: bool = typer.Option(
            False,
            "--list-routines",
            help=tr("cli.list_rom_routine_stand"),
        ),
        new_routine: str | None = typer.Option(
            None,
            "--new-routine",
            help=tr("cli.create_file_start_rom"),
        ),
        version_: bool = typer.Option(
            False,
            "--version",
            callback=_show_version,
            is_eager=True,
            help=tr("cli.print_version_exit"),
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
    old = paths.old_data_dir()
    if old is not None and paths.migrate():
        args.moved_data = "~/" + os.path.basename(old)
    app_module.STATE_DIR = paths.data_dir()
    if args.lang is not None and args.lang not in i18n.LANGUAGES:
        typer.echo(tr("cli.language_must_ja_en"), err=True)
        raise typer.Exit(2)
    i18n.set_language(i18n.choose(args.lang, App._view_prefs().get("lang")))
    model, card = args.model, args.card
    if model not in MODELS:
        typer.echo(
            tr("cli.model_must_one", models=tr("common.ideographic_comma").join(sorted(MODELS))),
            err=True,
        )
        raise typer.Exit(2)
    if card not in (0, 8, 16):
        typer.echo(tr("cli.ram_card_size_must"), err=True)
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
            typer.echo(tr("cli.does_not_exist", path=saved), err=True)
            raise typer.Exit(1)
        path = export_program(m, export)
        typer.echo(path or tr("common.no_program_export"))
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
            typer.echo(tr("cli.already_exists", path=e.filename), err=True)
            raise typer.Exit(1) from e
        except ValueError as e:
            typer.echo(tr("cli.write_address_hex_name", text=new), err=True)
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
        typer.echo(tr("cli.no_stand_ins_compare", folder=routines.user_folder()))
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
            lines.append(tr("cli.addr_name_mode_where", addr=r.addr, name=r.name,
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

"""画面に出す文。IDごとに、言語(i18n.LANGUAGES)ごとの文を置く

文の中の{addr:04X}のような差し込みは名前で書き、どの言語の文でも同じ名前を使う。数で形の変わる文は
(1のときの形, ほかの形)の組にして、数はnの名前で渡す。ROMのルーチンの働きは rom.系統.名前 の
IDに置く(作業欄の逆アセンブルに出す)。
"""

MESSAGES: dict[str, dict[str, str | tuple[str, str]]] = {
    # ---- 2つ以上のファイルで使う文 ----
    "common.start_address_set": {
        "ja": "開始番地を{addr:04X}にしました",
        "en": "Start address set to {addr:04X}",
    },
    "common.export_range_set": {
        "ja": "書き出す範囲を{where}にしました",
        "en": "Export range set to {where}",
    },
    "common.ideographic_comma": {
        "ja": "、",
        "en": ", ",
    },
    "common.programs": {
        "ja": "プログラム",
        "en": "Programs",
    },
    "common.rec_paused": {
        "ja": "録画を一時停止中 {clock}",
        "en": "Rec paused {clock}",
    },
    "common.recording": {
        "ja": "録画中 {clock}",
        "en": "Recording {clock}",
    },
    "common.state_loaded": {
        "ja": "保存した状態に戻しました",
        "en": "State loaded",
    },
    "common.builtin": {
        "ja": "組み込み",
        "en": "built-in",
    },
    "common.model_has_no_rom": {
        "ja": "代替ROMルーチンを置けない機種です: {model}",
        "en": "This model has no ROM routine stand-ins: {model}",
    },
    "common.close_esc": {
        "ja": "閉じる(Esc)",
        "en": "Close (Esc)",
    },
    "common.katakana_middle_dot": {
        "ja": "・",
        "en": ", ",
    },
    # ---- アプリ(app.py) ----
    "app.undo_program_load_menu": {
        "ja": "メニューの「プログラムを読み込む前に戻す」で元に戻せます",
        "en": '"Undo program load" in the menu goes back',
    },
    "app.switch": {
        "ja": "スイッチ {name}",
        "en": "Switch {name}",
    },
    "app.breakpoint_set": {
        "ja": "{addr:04X}番地にブレークポイントを設定しました",
        "en": "Breakpoint set at {addr:04X}",
    },
    "app.breakpoint_removed": {
        "ja": "{addr:04X}番地のブレークポイントを解除しました",
        "en": "Breakpoint removed at {addr:04X}",
    },
    "app.workbench_without_rom_right": {
        "ja": "ROMなしの作業欄(右)",
        "en": "Workbench without ROM (on the right)",
    },
    "app.0_9_f_write": {
        "ja": (
            "0〜9・A〜F: ダンプを入力   Enter: 次の行   Space: 番地からバイトへ   Tab: "
            "番地を入力して移動"
        ),
        "en": (
            "0-9, A-F: write the dump   Enter: next line   Space: from address to bytes   Tab: "
            "type an address to jump"
        ),
    },
    "app.g_run_continue_g": {
        "ja": "{c}G: 実行・続行   {s}{c}G: カーソルから実行   {c}.: 一時停止   Esc: 編集に戻る",
        "en": (
            "{c}G: run, continue   {s}{c}G: run from the cursor   {c}.: pause   Esc: back to "
            "editing"
        ),
    },
    "app.j_step_j_step": {
        "ja": (
            "{c}J: ステップ実行   {s}{c}J: CALL単位で実行(呼び出し先から戻るまで実行)   {c}B: "
            "ブレークポイント"
        ),
        "en": "{c}J: step   {s}{c}J: step over (run a CALL until it returns)   {c}B: breakpoint",
    },
    "app.v_paste_dump_listing": {
        "ja": "{c}V: ダンプリストや.hexを貼り付け   {c}Z: 取り消す   {s}{c}Z: やり直す",
        "en": "{c}V: paste a dump listing or .hex   {c}Z: undo   {s}{c}Z: redo",
    },
    "app.pageup_pagedown_one_screen": {
        "ja": (
            "PageUp・PageDown: 1画面ずつ移動   Home・End({c}←→): 行頭・行末   {c}↑↓: 開始番地・末尾"
        ),
        "en": (
            "PageUp, PageDown: one screen   Home, End ({c}←→): start, end of line   {c}↑↓: start "
            "address, end"
        ),
    },
    "app.e_export_hex_e": {
        "ja": "{c}E: .hexに書き出す   {s}{c}E: ダンプリストの形(8バイト:チェックサム)で書き出す",
        "en": "{c}E: export to .hex   {s}{c}E: export as a dump list (8 bytes:checksum)",
    },
    "app.click_range_line_type": {
        "ja": (
            "範囲の行をクリック: 書き出す範囲を入力   {c}O: プログラムの一覧(.hexのマシン語だけを"
            "使う)"
        ),
        "en": (
            "Click the range line: type the export range   {c}O: program list (only the machine "
            "code of .hex files)"
        ),
    },
    "app.while_running_keys_go": {
        "ja": "実行中はキー入力を本体に送ります(Tab: SHIFT  Option: DEF  Delete: CL  Esc: BRK)",
        "en": (
            "While running, keys go to the machine (Tab: SHIFT  Option: DEF  Delete: CL  Esc: BRK)"
        ),
    },
    "app.keys_differ_pocket_computer": {
        "ja": "パソコンのキーとポケコンのキーの対応(ここにないキーはそのまま打てます)",
        "en": "Keys that differ from the pocket computer (other keys type as they are)",
    },
    "app.k_arrow_keys_press": {
        "ja": "{c}K: 矢印キーで数字キーの8・2・4・6を押す・元に戻す(テンキーの代わり)",
        "en": "{c}K: arrow keys press 8, 2, 4, 6 or not (for PCs without a keypad)",
    },
    "app.emulator_commands_menus_bar": {
        "ja": (
            "エミュレータの操作は下の操作欄のメニューにあります(ショートカットもメニューに表示され"
            "ます)"
        ),
        "en": "Emulator commands are in the menus of the bar below (shortcuts are shown there)",
    },
    "app.tab_shift_option_alt": {
        "ja": "Tab: SHIFT   Option(WindowsはAlt): DEF   F8: カナ   Esc: BRK(電源が切れていればON)",
        "en": "Tab: SHIFT   Option (Alt on Windows): DEF   F8: カナ   Esc: BRK (ON when off)",
    },
    "app.delete_del_insert_ins": {
        "ja": (
            "Delete: DEL   Insert: INS   Home: CLS   Backspace: 1字削除(◀とDELを押します)   \\: ¥"
        ),
        "en": (
            "Delete: DEL   Insert: INS   Home: CLS   Backspace: delete a character (◀ and DEL)   "
            "\\: ¥"
        ),
    },
    "app.f1_f2_run_pro": {
        "ja": (
            "F1・F2: MODEキーでRUN・PROに切り替え   F3・F4・{c}↑↓: 電源スイッチ   F5・{c}R: RESET"
        ),
        "en": "F1, F2: RUN, PRO with the MODE key   F3, F4, {c}↑↓: power switch   F5, {c}R: RESET",
    },
    "app.tab_shift_option_alt_windows": {
        "ja": (
            "Tab: SHIFT   Option(WindowsはAlt): DEF   Delete: CL   Esc: BRK(電源が切れていればON)"
        ),
        "en": "Tab: SHIFT   Option (Alt on Windows): DEF   Delete: CL   Esc: BRK (ON when off)",
    },
    "app.backspace_delete_character_shift": {
        "ja": "Backspace: 1字削除(◀とSHIFT+◀を押します)   \\(バックスラッシュ): ¥",
        "en": "Backspace: delete a character (◀ and SHIFT+◀)   \\ (backslash): ¥",
    },
    "app.f1_f4_mode_switch": {
        "ja": "F1〜F4・{c}↑↓: モードスイッチ   F5・{c}R: 裏のRESETボタン",
        "en": "F1-F4, {c}↑↓: mode switch   F5, {c}R: RESET button on the back",
    },
    "app.exported": {
        "ja": "{title}({when}の書き出し)",
        "en": "{title} (exported {when})",
    },
    "app.no_rom_found_so": {
        "ja": "ROMがないため、マシン語だけを実行できます(右の作業欄)",
        "en": "No ROM found, so only machine code runs (workbench on the right)",
    },
    "app.no_rom_so_running": {
        "ja": "ROMがないため、ROMなしのBASICで動かします(未対応の命令もあります)",
        "en": "No ROM, so running on the ROM-less BASIC (some commands are not made yet)",
    },
    "app.use_buttons_bar_below": {
        "ja": "操作は下の操作欄のボタンで行います。キーの説明は{c}/で表示します",
        "en": "Use the buttons in the bar below. Key help: {c}/",
    },
    "app.moved_data_folder_sc61box": {
        "ja": "データのフォルダを~/.sc61boxに移しました({old}はそこへのリンクです)",
        "en": "Moved the data folder to ~/.sc61box ({old} now links to it)",
    },
    "app.rom_routine_stand_ins": {
        "ja": "代替ROMルーチン: {text}",
        "en": "ROM routine stand-ins: {text}",
    },
    "app.not_found": {
        "ja": "{name}が見つかりません",
        "en": "{name} not found",
    },
    "app.saved": {
        "ja": "{name}用に保存したもの",
        "en": "saved for {name}",
    },
    "app.saved_default": {
        "ja": "保存した既定",
        "en": "saved default",
    },
    "app.factory_mapping": {
        "ja": "初期設定",
        "en": "factory mapping",
    },
    "app.pad": {
        "ja": "{name}の# pad:",
        "en": "# pad: of {name}",
    },
    "app.cannot_read_pad": {
        "ja": "# pad: の{text}が読めません",
        "en": "Cannot read {text} in # pad:",
    },
    "app.copied_pad_line_clipboard": {
        "ja": "# pad: の行をクリップボードにコピーしました",
        "en": "Copied the # pad: line to the clipboard",
    },
    "app.cannot_save_mapping": {
        "ja": "割り当てを保存できません: {error}",
        "en": "Cannot save the mapping: {error}",
    },
    "app.saved_mapping": {
        "ja": "割り当てを{path}に保存しました",
        "en": "Saved the mapping to {path}",
    },
    "app.not_usable_without_rom": {
        "ja": "{addr:04X}番地はROMなしでは使えないため、ブレークポイントを設定できません",
        "en": "{addr:04X} is not usable without ROM, so no breakpoint can go there",
    },
    "app.paused_continue_first_then": {
        "ja": "一時停止中です。続行してから押してください",
        "en": "Paused. Continue first, then press it",
    },
    "app.typed_call": {
        "ja": "CALL &{addr:04X}を入力しました",
        "en": "Typed CALL &{addr:04X}",
    },
    "app.press_cl_so_only": {
        "ja": "CLを押して液晶を>だけにしてから押してください",
        "en": "Press CL so that only > is on the display, then press it",
    },
    "app.press_while_basic_waiting": {
        "ja": "BASICが入力を待っているときに押してください",
        "en": "Press it while BASIC is waiting for input",
    },
    "app.type_addresses_hex_0": {
        "ja": "番地は16進表記(0〜9、A〜F)で入力してください",
        "en": "Type addresses in hex (0-9, A-F)",
    },
    "app.cannot_type_while_running": {
        "ja": "実行中は入力できません。{c}Aか右クリックで、カーソルの位置を開始番地にできます",
        "en": "Cannot type while running. {c}A or right-click sets the start address at the cursor",
    },
    "app.cannot_type_range_while": {
        "ja": "実行中は範囲を入力できません",
        "en": "Cannot type the range while running",
    },
    "app.loaded_bytes_start_address": {
        "ja": "{name}を読み込みました({n}バイト、開始番地{addr:04X})。{c}Gで実行します",
        "en": (
            "Loaded {name} ({n} byte, start address {addr:04X}). {c}G runs it",
            "Loaded {name} ({n} bytes, start address {addr:04X}). {c}G runs it",
        ),
    },
    "app.no_dump_lines_pasted": {
        "ja": "貼り付けたテキストにダンプの行がありません",
        "en": "No dump lines in the pasted text",
    },
    "app.wrote_bytes": {
        "ja": "{n}バイトを書き込みました",
        "en": ("Wrote {n} byte", "Wrote {n} bytes"),
    },
    "app.checksum_mismatch": {
        "ja": "チェックサムが合わない行: {where}",
        "en": "Checksum mismatch at {where}",
    },
    "app.bytes_outside_ram_not": {
        "ja": "RAMの外の{n}バイトは書き込めません",
        "en": ("{n} byte outside RAM not written", "{n} bytes outside RAM not written"),
    },
    "app.start_address": {
        "ja": "開始番地は{addr:04X}",
        "en": "Start address {addr:04X}",
    },
    "app.ideographic_full_stop": {
        "ja": "。",
        "en": ". ",
    },
    "app.no_dump_export": {
        "ja": "書き出すダンプがありません",
        "en": "No dump to export",
    },
    "app.exported_machine_code_workbench": {
        "ja": "{where}(マシン語の作業欄から書き出し)",
        "en": "{where} (exported from the machine-code workbench)",
    },
    "app.cannot_export": {
        "ja": "書き出せません: {error}",
        "en": "Cannot export: {error}",
    },
    "app.exported_bytes_folder": {
        "ja": "{name}を書き出しました({n}バイト)。保存先: {folder}",
        "en": (
            "Exported {name} ({n} byte). Folder: {folder}",
            "Exported {name} ({n} bytes). Folder: {folder}",
        ),
    },
    "app.speed": {
        "ja": "速度 {speed}",
        "en": "Speed {speed}",
    },
    "app.arrow_keys_number_keys": {
        "ja": "矢印キー → 数字キーの8・2・4・6",
        "en": "Arrow keys → number keys 8, 2, 4, 6",
    },
    "app.arrow_keys": {
        "ja": "矢印キー → ↑↓◀▶",
        "en": "Arrow keys → ↑↓◀▶",
    },
    "app.gaps_between_lcd_characters": {
        "ja": "液晶の文字の間を詰めました",
        "en": "Gaps between LCD characters removed",
    },
    "app.gaps_between_lcd_characters_restored": {
        "ja": "液晶の文字の間を実機と同じにしました",
        "en": "Gaps between LCD characters restored",
    },
    "app.key_help_arrow_keys": {
        "ja": "キーの説明({c}/)、矢印キー・ゲームパッドの割り当て、液晶だけ、画面の画像、印字",
        "en": "Key help ({c}/), arrow keys, gamepad, LCD only, screenshot, printout",
    },
    "app.list_export_paste_list": {
        "ja": "一覧、書き出し、貼り付け(一覧は{c}O)",
        "en": "List, export, paste (list: {c}O)",
    },
    "app.machine": {
        "ja": "本体",
        "en": "Machine",
    },
    "app.save_load_state_switch": {
        "ja": "状態の保存と復元、スイッチ、RESET",
        "en": "Save and load state, switch, RESET",
    },
    "app.view_input": {
        "ja": "表示・入力",
        "en": "View & Input",
    },
    "app.view": {
        "ja": "表示",
        "en": "View",
    },
    "app.resume_execution_p": {
        "ja": "一時停止中の実行を再開する({c}P)",
        "en": "Resume execution ({c}P)",
    },
    "app.resume": {
        "ja": "実行を再開",
        "en": "Resume",
    },
    "app.resume_short": {
        "ja": "再開",
        "en": "Resume",
    },
    "app.pause_cpu_p_recording": {
        "ja": "CPUの実行を一時停止する({c}P)。録画は続きます",
        "en": "Pause the CPU ({c}P). Recording goes on",
    },
    "app.pause": {
        "ja": "実行を一時停止",
        "en": "Pause",
    },
    "app.pause_short": {
        "ja": "一時停止",
        "en": "Pause",
    },
    "app.workbench_hide": {
        "ja": "◀ 作業欄",
        "en": "◀ Workbench",
    },
    "app.hide_machine_code_workbench": {
        "ja": "マシン語の作業欄を隠す({c}D)",
        "en": "Hide the machine-code workbench ({c}D)",
    },
    "app.workbench_show": {
        "ja": "作業欄 ▶",
        "en": "Workbench ▶",
    },
    "app.show_machine_code_workbench": {
        "ja": "マシン語の作業欄を表示({c}D)",
        "en": "Show the machine-code workbench ({c}D)",
    },
    "app.show_calculator_window_size": {
        "ja": "本体の画像を表示(ウィンドウの大きさは固定に戻ります)",
        "en": "Show the calculator (the window size is fixed again)",
    },
    "app.calculator": {
        "ja": "本体を表示",
        "en": "Calculator",
    },
    "app.choose_speed_t_faster": {
        "ja": "実行速度を選ぶ({c}Tで速く、{s}{c}Tで遅く)",
        "en": "Choose the speed ({c}T faster, {s}{c}T slower)",
    },
    "app.start_recording_r": {
        "ja": "録画の形を選んで始める({s}{c}Rは前と同じ形で始める)",
        "en": "Choose a layout and start recording ({s}{c}R uses the last layout)",
    },
    "app.rec_lcd_and_body": {
        "ja": "液晶の拡大と本体",
        "en": "Enlarged LCD and calculator",
    },
    "app.rec_body_only": {
        "ja": "本体だけ",
        "en": "Calculator only",
    },
    "app.rec_lcd_only": {
        "ja": "液晶だけ",
        "en": "LCD only",
    },
    "app.record": {
        "ja": "録画",
        "en": "Record",
    },
    "app.stop_r_pause_p": {
        "ja": "録画を停止({s}{c}R)または一時停止({s}{c}P)",
        "en": "Stop ({s}{c}R) or pause ({s}{c}P) the recording",
    },
    "app.kb_card": {
        "ja": "{n}KBカード",
        "en": "{n} KB card",
    },
    "app.arrows_8246": {
        "ja": "矢印→8246",
        "en": "Arrows→8246",
    },
    "app.tape": {
        "ja": "テープ",
        "en": "Tape",
    },
    "app.loading_stopped_partly_loaded": {
        "ja": "読み込みを中止しました(途中まで読み込まれています)。{hint}",
        "en": "Loading stopped (partly loaded). {hint}",
    },
    "app.cannot_save_printout": {
        "ja": "印字を保存できません: {error}",
        "en": "Cannot save the printout: {error}",
    },
    "app.printout_saved": {
        "ja": "印字を{path}に保存しました",
        "en": "Printout saved to {path}",
    },
    "app.resume_execution": {
        "ja": "実行を再開する",
        "en": "Resume execution",
    },
    "app.pause_execution": {
        "ja": "実行を一時停止する",
        "en": "Pause execution",
    },
    "app.export_dump_file_hex": {
        "ja": "ダンプをファイル(.hex)に書き出す",
        "en": "Export dump to file (.hex)",
    },
    "app.export_dump_list": {
        "ja": "ダンプリストの形で書き出す",
        "en": "Export as dump list",
    },
    "app.lines_8_bytes_checksum": {
        "ja": "8バイト:チェックサムの行",
        "en": "Lines of 8 bytes:checksum",
    },
    "app.paste_dump_clipboard": {
        "ja": "クリップボードからダンプを貼り付ける",
        "en": "Paste dump from clipboard",
    },
    "app.export_program_file": {
        "ja": "プログラムをファイルに書き出す",
        "en": "Export program to file",
    },
    "app.type_clipboard": {
        "ja": "クリップボードから打ち込む",
        "en": "Type in from clipboard",
    },
    "app.program_list": {
        "ja": "プログラムの一覧…",
        "en": "Program list…",
    },
    "app.open_program_folder": {
        "ja": "プログラムのフォルダを開く",
        "en": "Open program folder",
    },
    "app.undo_dump_edit": {
        "ja": "ダンプの書き込みを取り消す",
        "en": "Undo dump edit",
    },
    "app.redo_dump_edit": {
        "ja": "ダンプの書き込みをやり直す",
        "en": "Redo dump edit",
    },
    "app.help_loaded_program": {
        "ja": "読み込んだプログラムの説明",
        "en": "Help for loaded program",
    },
    "app.save_state": {
        "ja": "現在の状態を保存(どこでもセーブ)",
        "en": "Save state",
    },
    "app.load_state": {
        "ja": "保存した状態に戻す",
        "en": "Load state",
    },
    "app.before_loading": {
        "ja": "{title}を読み込む前",
        "en": "before loading {title}",
    },
    "app.undo_program_load": {
        "ja": "プログラムを読み込む前に戻す",
        "en": "Undo program load",
    },
    "app.press_reset_button": {
        "ja": "RESETボタンを押す",
        "en": "Press RESET button",
    },
    "app.arrow_keys_back": {
        "ja": "矢印キーを↑↓◀▶に戻す",
        "en": "Arrow keys back to ↑↓◀▶",
    },
    "app.arrow_keys_8_2": {
        "ja": "矢印キーを8・2・4・6にする",
        "en": "Arrow keys as 8, 2, 4, 6",
    },
    "app.connected": {
        "ja": "{names}が接続されています",
        "en": "{names} connected",
    },
    "app.no_gamepad_connected": {
        "ja": "ゲームパッドが接続されていません",
        "en": "No gamepad connected",
    },
    "app.show_calculator": {
        "ja": "本体の画像を表示",
        "en": "Show the calculator",
    },
    "app.lcd_only_window_can": {
        "ja": "液晶だけを表示(ウィンドウの大きさを変えられます)",
        "en": "LCD only (window can be resized)",
    },
    "app.key_help": {
        "ja": "キーの説明",
        "en": "Key help",
    },
    "app.gamepad_mapping": {
        "ja": "ゲームパッドの割り当て…",
        "en": "Gamepad mapping…",
    },
    "app.save_screenshot": {
        "ja": "画面を画像で保存",
        "en": "Save screenshot",
    },
    "app.restore_gaps_between_lcd": {
        "ja": "液晶の文字の間を実機と同じにする",
        "en": "Restore gaps between LCD characters",
    },
    "app.remove_gaps_between_lcd": {
        "ja": "液晶の文字の間を詰める",
        "en": "Remove gaps between LCD characters",
    },
    "app.dots_evenly_spaced_not": {
        "ja": "ドットを同じ間隔で並べます(実機にはない表示です)",
        "en": "Dots are evenly spaced (not like the real LCD)",
    },
    "app.hide_workbench": {
        "ja": "マシン語の作業欄を隠す",
        "en": "Hide workbench",
    },
    "app.show_workbench": {
        "ja": "マシン語の作業欄を表示",
        "en": "Show workbench",
    },
    "app.not_available_while_showing": {
        "ja": "液晶だけを表示しているときは使えません",
        "en": "Not available while showing only the LCD",
    },
    "app.resume_recording": {
        "ja": "録画を再開する",
        "en": "Resume recording",
    },
    "app.pause_recording": {
        "ja": "録画を一時停止する",
        "en": "Pause recording",
    },
    "app.stop_save_recording": {
        "ja": "録画を止めて保存",
        "en": "Stop and save recording",
    },
    "app.put_paper_away": {
        "ja": "プリンタの紙を隠す",
        "en": "Put the paper away",
    },
    "app.open_printout_folder": {
        "ja": "印字の保存先を開く",
        "en": "Open printout folder",
    },
    "app.language_english": {
        "ja": "表示を日本語にしました",
        "en": "Language: English",
    },
    "app.not_saved_yet": {
        "ja": "まだ保存していません",
        "en": "Not saved yet",
    },
    "app.saved_when": {
        "ja": "{when}に保存",
        "en": "Saved {when}",
    },
    "app.paused_p_resume_bar": {
        "ja": "実行を一時停止しました。{c}Pか操作欄の「実行を再開」で再開します",
        "en": 'Paused. {c}P or "Resume" in the bar continues',
    },
    "app.resumed": {
        "ja": "実行を再開しました",
        "en": "Resumed",
    },
    "app.not_running_g_runs": {
        "ja": "実行していません。{c}Gで開始番地から実行します",
        "en": "Not running. {c}G runs from the start address",
    },
    "app.cannot_undo_load": {
        "ja": "読み込む前に戻せません: {error}",
        "en": "Cannot undo the load: {error}",
    },
    "app.back_before_loading": {
        "ja": "{title}を読み込む前に戻しました",
        "en": "Back to before loading {title}",
    },
    "app.is_start_address": {
        "ja": "現在の開始番地です",
        "en": "This is the start address",
    },
    "app.set_start_address": {
        "ja": "{addr:04X}番地を開始番地にする",
        "en": "Set {addr:04X} as start address",
    },
    "app.running": {
        "ja": "実行中です",
        "en": "Running",
    },
    "app.run": {
        "ja": "{addr:04X}番地から実行する",
        "en": "Run from {addr:04X}",
    },
    "app.address_not_usable_without_rom": {
        "ja": "ROMなしでは使えない番地です",
        "en": "Not usable without ROM",
    },
    "app.remove_breakpoint": {
        "ja": "{addr:04X}番地のブレークポイントを解除",
        "en": "Remove breakpoint at {addr:04X}",
    },
    "app.set_breakpoint": {
        "ja": "{addr:04X}番地にブレークポイントを設定",
        "en": "Set breakpoint at {addr:04X}",
    },
    "app.mark_data": {
        "ja": "{addr:04X}番地からデータにする",
        "en": "Mark data from {addr:04X}",
    },
    "app.data_up_next_mark": {
        "ja": "次の指定か、実行済みの命令の手前までデータ",
        "en": "Data up to the next mark or executed instruction",
    },
    "app.mark_code": {
        "ja": "{addr:04X}番地から命令にする",
        "en": "Mark code from {addr:04X}",
    },
    "app.analyse_code_here": {
        "ja": "ここから静的解析する",
        "en": "Analyse the code from here",
    },
    "app.clear_mark": {
        "ja": "{addr:04X}番地の指定を消す",
        "en": "Clear the mark at {addr:04X}",
    },
    "app.back_guessing": {
        "ja": "推定に戻す",
        "en": "Back to guessing",
    },
    "app.loaded_bytes": {
        "ja": "{name}を読み込みました({n}バイト)",
        "en": ("Loaded {name} ({n} byte)", "Loaded {name} ({n} bytes)"),
    },
    "app.did_not_fit_ram": {
        "ja": (
            "{name}はRAMに入りきりませんでした({line}行から{n}行が入っていません)。実行と、"
            "その後の書き込みは行いませんでした。{hint}"
        ),
        "en": (
            (
                "{name} did not fit in RAM ({n} line from line {line} missing). Run and later "
                "writes skipped. {hint}"
            ),
            (
                "{name} did not fit in RAM ({n} lines from line {line} missing). Run and later "
                "writes skipped. {hint}"
            ),
        ),
    },
    "app.line_could_not_typed": {
        "ja": (
            "{name}の{line}行を正しく打ち込めませんでした。実行と、"
            "その後の書き込みは行いませんでした。{hint}"
        ),
        "en": (
            "Line {line} of {name} could not be typed in correctly. Run and later writes skipped. "
            "{hint}"
        ),
    },
    "app.cannot_read": {
        "ja": "{name}を読めません({error})",
        "en": "Cannot read {name} ({error})",
    },
    "app.tape_inserted_load_cload": {
        "ja": "テープ{name}をセットしました。CLOADかCLOAD Mで読み込みます",
        "en": "Tape {name} inserted. Load it with CLOAD or CLOAD M",
    },
    "app.load_write_bin_name": {
        "ja": "{name}を読み込むには、.basに「# bin: 名前.bin &C300」と書きます",
        "en": 'To load {name}, write "# bin: name.bin &C300" in a .bas',
    },
    "app.cannot_read_name": {
        "ja": "{name}を読めません",
        "en": "Cannot read {name}",
    },
    "app.export_after_typing_has": {
        "ja": "打ち込みが終わってから書き出してください",
        "en": "Export after typing in has finished",
    },
    "app.no_program_export": {
        "ja": "書き出すプログラムがありません",
        "en": "No program to export",
    },
    "app.exported_path": {
        "ja": "{path}に書き出しました",
        "en": "Exported to {path}",
    },
    "app.cannot_write_tape_audio": {
        "ja": "テープの音を書き出せません: {error}",
        "en": "Cannot write the tape audio: {error}",
    },
    "app.tape_audio_written": {
        "ja": "テープの音を{path}に書き出しました",
        "en": "Tape audio written to {path}",
    },
    "app.cannot_save_state": {
        "ja": "状態を保存できません: {error}",
        "en": "Cannot save state: {error}",
    },
    "app.state_saved_l_loads": {
        "ja": "状態を保存しました。{s}{c}Lで戻せます",
        "en": "State saved. {s}{c}L loads it",
    },
    "app.no_saved_state": {
        "ja": "保存した状態がありません",
        "en": "No saved state",
    },
    "app.cannot_load_state": {
        "ja": "状態を読み込めません: {error}",
        "en": "Cannot load state: {error}",
    },
    "app.cannot_save_screenshot": {
        "ja": "画面の画像を保存できません: {error}",
        "en": "Cannot save the screenshot: {error}",
    },
    "app.saved_path": {
        "ja": "{path}に保存しました",
        "en": "Saved to {path}",
    },
    "app.cannot_start_recording": {
        "ja": "録画を始められません: {error}",
        "en": "Cannot start recording: {error}",
    },
    "app.recording_press_r_again": {
        "ja": "録画を始めました。止めて保存するときは、もう一度{s}{c}Rを押します",
        "en": "Recording. Press {s}{c}R again to stop and save",
    },
    "app.saving_recording": {
        "ja": "録画を保存しています…",
        "en": "Saving the recording…",
    },
    "app.cannot_save_recording": {
        "ja": "録画を保存できません: {error}",
        "en": "Cannot save the recording: {error}",
    },
    "app.recording_saved_seconds": {
        "ja": "録画を{path}に保存しました({n}秒)",
        "en": ("Recording saved to {path} ({n} second)", "Recording saved to {path} ({n} seconds)"),
    },
    "app.recording_paused": {
        "ja": "録画を一時停止しました",
        "en": "Recording paused",
    },
    "app.recording_resumed": {
        "ja": "録画を再開しました",
        "en": "Recording resumed",
    },
    "app.recording_stopped": {
        "ja": "録画を停止しました: {error}",
        "en": "Recording stopped: {error}",
    },
    "app.loaded": {
        "ja": "{name}を読み込みました",
        "en": "Loaded {name}",
    },
    "app.rom_less_basic_has": {
        "ja": (
            "ROMなしのBASICには、CALLで呼び出したROMの{addr:04X}番地のルーチンがないため、"
            "実行を中止しました(代替ROMルーチンは--new-routine {addr:04X}で書き始められます)"
        ),
        "en": (
            "The ROM-less BASIC has no routine at ROM address {addr:04X} (called through CALL), "
            "so execution stopped (start a stand-in with --new-routine {addr:04X})"
        ),
    },
    "app.routine_rom_address_not": {
        "ja": "ROMなしでは、ROMの{addr:04X}番地のルーチンを使えません",
        "en": "The routine at ROM address {addr:04X} is not available without the ROM",
    },
    "app.stopped_stand_kept_waiting": {
        "ja": (
            "代替ROMルーチン{name}({addr:04X})が時間を進めずに待ち続けたため、"
            "実行を中止しました({file})"
        ),
        "en": (
            "Stopped: the stand-in {name} ({addr:04X}) kept waiting without advancing time ({file})"
        ),
    },
    "app.end_tape": {
        "ja": "テープが終わりました",
        "en": "End of tape",
    },
    "app.saved_click_open": {
        "ja": "保存先(クリックで開く)",
        "en": "Saved in (click to open)",
    },
    "app.typing_esc_stops": {
        "ja": "{name}を打ち込み中… {pct}%(Escで中止)",
        "en": "Typing in {name}… {pct}% (Esc stops)",
    },
    "app.loading_esc_stops": {
        "ja": "{name}を読み込み中… {pct}%(Escで中止)",
        "en": "Loading {name}… {pct}% (Esc stops)",
    },
    "app.paused_p_resumes": {
        "ja": "実行を一時停止中({c}Pで再開)",
        "en": "Paused ({c}P resumes)",
    },
    "app.cannot_save_ram": {
        "ja": "RAMを保存できません: {error}",
        "en": "Cannot save RAM: {error}",
    },
    "app.sharp_pc_1251_pc": {
        "ja": "SHARP PC-1251/PC-1245/PC-1261/PC-1350エミュレータ",
        "en": "SHARP PC-1251/PC-1245/PC-1261/PC-1350 emulator",
    },
    "app.program_load_path_bas": {
        "ja": "読み込むプログラム(.bas/.hexのパスか、プログラムのフォルダにある名前)",
        "en": "Program to load (path to a .bas/.hex, or a name in the program folder)",
    },
    "app.run_after_loading": {
        "ja": "読み込んだあと実行する",
        "en": "Run it after loading",
    },
    "app.window_scale": {
        "ja": "拡大率",
        "en": "Window scale",
    },
    "app.type_contents_file_after": {
        "ja": "起動後にこのファイルの中身をキー入力する",
        "en": "Type in the contents of this file after starting",
    },
    "app.write_hex_dump_address": {
        "ja": "16進ダンプ(番地 データ)をRAMに書き込む",
        "en": "Write a hex dump (address data) into RAM",
    },
    "app.ram_loaded": {
        "ja": "前回終了時のRAMを読み込みました(--freshで初期状態から起動できます)",
        "en": "Loaded the RAM saved on the last exit "
        "(start with --fresh to begin from a cleared RAM)",
    },
    "app.ram_loaded_locked": {
        "ja": "前回終了時のRAMを読み込みました。プログラムはパスワードで保護されています",
        "en": "Loaded the RAM saved on the last exit. The program is protected by a password",
    },
    "app.do_not_load_saved": {
        "ja": "保存したRAMを読まず、終了時にも保存しない",
        "en": "Do not load the saved RAM, and do not save it on exit",
    },
    "app.no_sound": {
        "ja": "音を出さない",
        "en": "No sound",
    },
    "app.strength_lcd_afterglow_0": {
        "ja": "液晶の残像の強さ(0で残像なし)",
        "en": "Strength of the LCD afterglow (0 for none)",
    },
    "app.export_basic_program_saved": {
        "ja": "保存したRAMのBASICのプログラムを、このフォルダに.basで書き出して終わる",
        "en": "Export the BASIC program in the saved RAM to this folder as .bas and exit",
    },
    "app.model_1250_1251_1255": {
        "ja": (
            "機種(1250、1251、1255、1245、1260、1261、1262、1350)。ROMはcpu-機種.romとbas-機種.rom"
            "(1250と1255は1251の、1260〜1262はどれも1260のROMを使う)"
        ),
        "en": (
            "Model (1250, 1251, 1255, 1245, 1260, 1261, 1262, 1350). The ROMs are cpu-MODEL.rom "
            "and bas-MODEL.rom (1250 and 1255 use the 1251 ROM, 1260 to 1262 the 1260 ROM)"
        ),
    },
    "app.size_pc_1350_ram": {
        "ja": "PC-1350に差すRAMカードの大きさ(KB)。0、8、16",
        "en": "Size of the PC-1350 RAM card in KB: 0, 8 or 16",
    },
    "app.run_pc_1350_wired": {
        "ja": "PC-1350を輸出向けの配線で動かす(カナの代わりに英小文字、¥の代わりに\\)",
        "en": (
            "Run the PC-1350 wired as the export model (lowercase instead of kana, \\ instead of ¥)"
        ),
    },
    "app.arrow_keys_press_number": {
        "ja": "矢印キーを数字キーの8・2・4・6として押す(⌘K/Ctrl+Kで切り替え)",
        "en": "Arrow keys press the number keys 8, 2, 4, 6 (toggle with ⌘K/Ctrl+K)",
    },
    "app.show_only_lcd_without": {
        "ja": "本体の画像を隠し、液晶だけを表示(ウィンドウの大きさを変えられます)",
        "en": "Show only the LCD without the calculator picture (the window can be resized)",
    },
    "app.insert_cassette_audio_wav": {
        "ja": "カセットの音(wav)をセットする。CLOAD・CLOAD Mで読み込める",
        "en": "Insert cassette audio (wav) to load with CLOAD or CLOAD M",
    },
    "app.start_saved_state_written": {
        "ja": "保存した状態(⇧⌘S/Shift+Ctrl+Sで書いたもの)から始める",
        "en": "Start from a saved state (written with ⇧⌘S/Shift+Ctrl+S)",
    },
    "app.run_without_rom_rom": {
        "ja": "ROMを使わず、ROMなしのBASICで動かす(ROMがないときは指定しなくてもこの動作)",
        "en": "Run without the ROM, on the ROM-less BASIC (automatic when the ROM is missing)",
    },
    "app.without_rom_run_only": {
        "ja": "ROMなしのとき、BASICを付けずにマシン語の作業欄だけで動かす",
        "en": "Without the ROM, run only the machine-code panel, with no BASIC",
    },
    "app.display_language_ja_en": {
        "ja": "画面の言語(jaかen)。なければSC61BOX_LANG、メニューで選んだもの、ロケールの順",
        "en": (
            "Display language (ja or en). Otherwise SC61BOX_LANG, the menu choice, then the locale"
        ),
    },
    "app.compare_rom_routine_stand": {
        "ja": (
            "代替ROMルーチンを、ROMのある本体と比べて終わる。user(データのフォルダのroutinesに書い"
            "たもの)、all、または名前をコンマで区切って書く"
        ),
        "en": (
            "compare ROM routine stand-ins with the machine with the ROM, then exit: user (those "
            "in routines in the data folder), all, or names separated by commas"
        ),
    },
    "app.list_rom_routine_stand": {
        "ja": "代替ROMルーチンの一覧(使うものと、使わないものと理由)を出して終わる",
        "en": (
            "list the ROM routine stand-ins (used ones, and unused ones with the reason), then exit"
        ),
    },
    "app.create_file_start_rom": {
        "ja": (
            "代替ROMルーチンを書き始めるファイルを、データのフォルダのroutinesに作って終わる。"
            "番地(16進)か「番地:名前」で書く"
        ),
        "en": (
            "create a file to start a ROM routine stand-in in routines in the data folder, then "
            "exit: an address (hex) or ADDRESS:NAME"
        ),
    },
    "app.print_version_exit": {
        "ja": "版を出して終わる",
        "en": "Print the version and exit",
    },
    "app.language_must_ja_en": {
        "ja": "言語はjaかenです",
        "en": "The language must be ja or en",
    },
    "app.model_must_one": {
        "ja": "機種は{models}のどれかです",
        "en": "The model must be one of {models}",
    },
    "app.ram_card_size_must": {
        "ja": "RAMカードの大きさは0、8、16のどれかです",
        "en": "The RAM card size must be 0, 8 or 16",
    },
    "app.does_not_exist": {
        "ja": "{path}がありません",
        "en": "{path} does not exist",
    },
    "app.already_exists": {
        "ja": "{path}はもうあります",
        "en": "{path} already exists",
    },
    "app.write_address_hex_name": {
        "ja": "番地は16進で、名前は英字で書きます: {text}",
        "en": "Write the address in hex and the name in letters: {text}",
    },
    "app.no_stand_ins_compare": {
        "ja": "比べる代替ROMルーチンがありません({folder})",
        "en": "No stand-ins to compare ({folder})",
    },
    "app.addr_name_mode_where": {
        "ja": "--  {addr:04X} {name}{mode} {where}: {why}",
        "en": "--  {addr:04X} {name}{mode} {where}: {why}",
    },
    # ---- マシン語の作業欄(workbench.py、benchview.py) ----
    "bench.executed_instruction": {
        "ja": "実行済みの命令",
        "en": "Executed instruction",
    },
    "bench.code_found_following_branches": {
        "ja": "分岐と呼び出しをたどり、命令と判定",
        "en": "Code found by following branches and calls",
    },
    "bench.dtc_table_row_count": {
        "ja": "DTCの表(行の数はPTCから)",
        "en": "DTC table (row count from PTC)",
    },
    "bench.dtc_table_unreferenced": {
        "ja": "DTCの表(参照されていない)",
        "en": "DTC table (unreferenced)",
    },
    "bench.unreferenced_so_unknown": {
        "ja": "参照されていないため不明",
        "en": "Unreferenced, so unknown",
    },
    "bench.guessed_text": {
        "ja": "文字列と推定",
        "en": "Guessed as text",
    },
    "bench.guessed_run_00_ff": {
        "ja": "00・FFの連続と推定",
        "en": "Guessed as a run of 00/FF",
    },
    "bench.contains_undefined_opcodes_like": {
        "ja": "未定義命令などを含むため、データと推定",
        "en": "Contains undefined opcodes or the like, so guessed as data",
    },
    "bench.does_not_end_rtn": {
        "ja": "RTNやジャンプで終わらないため、データと推定",
        "en": "Does not end in RTN or a jump, so guessed as data",
    },
    "bench.user_specified_data": {
        "ja": "ユーザ指定のデータ",
        "en": "User-specified data",
    },
    "bench.user_specified_code": {
        "ja": "ユーザ指定の命令",
        "en": "User-specified code",
    },
    "bench.breakpoint": {
        "ja": "● ブレークポイント",
        "en": "● Breakpoint",
    },
    "bench.set_breakpoint_instruction_under": {
        "ja": "カーソルの命令({addr:04X}番地)にブレークポイントを設定・解除する({c}B)",
        "en": (
            "Set a breakpoint at the instruction under the cursor ({addr:04X}), or remove it ({c}B)"
        ),
    },
    "bench.edit": {
        "ja": "編集に戻る",
        "en": "Edit",
    },
    "bench.stop_running_go_back": {
        "ja": "実行を中止して編集に戻る。書き換わったメモリはそのまま残る(Esc)",
        "en": "Stop running and go back to editing. Memory stays as it is (Esc)",
    },
    "bench.pause": {
        "ja": "■ 一時停止",
        "en": "■ Pause",
    },
    "bench.pause_before_next_instruction": {
        "ja": "次の命令の前で一時停止する({c}.)",
        "en": "Pause before the next instruction ({c}.)",
    },
    "bench.run": {
        "ja": "▶ 実行",
        "en": "▶ Run",
    },
    "bench.if_basic_waiting_input": {
        "ja": (
            "BASICが入力待ちなら、CALL &{addr:04X}を入力したときと同じように開始番地から実行する。"
            "RTNでBASICに戻る({c}G)"
        ),
        "en": (
            "If BASIC is waiting for input, run from the start address as if CALL &{addr:04X} "
            "were typed. RTN returns to BASIC ({c}G)"
        ),
    },
    "bench.run_start_address_ends": {
        "ja": "開始番地{addr:04X}から実行する。RTNで戻ると終了({c}G)",
        "en": "Run from the start address {addr:04X}. Ends at RTN ({c}G)",
    },
    "bench.step": {
        "ja": "ステップ実行",
        "en": "Step",
    },
    "bench.stop_before_first_instruction": {
        "ja": "開始番地{addr:04X}の最初の命令の前で止め、ステップ実行する({c}J)",
        "en": "Stop before the first instruction at {addr:04X}, then step one at a time ({c}J)",
    },
    "bench.cannot_continue_so_go": {
        "ja": "{addr:04X}番地からは続行できないため、編集に戻る(Esc)",
        "en": "Cannot continue from {addr:04X}, so go back to editing (Esc)",
    },
    "bench.continue": {
        "ja": "▶ 続行",
        "en": "▶ Continue",
    },
    "bench.continue_running_g": {
        "ja": "{addr:04X}番地から実行を続行する({c}G)",
        "en": "Continue running from {addr:04X} ({c}G)",
    },
    "bench.continue_basic": {
        "ja": "BASICの実行を続行する({c}G)",
        "en": "Continue running BASIC ({c}G)",
    },
    "bench.step_short": {
        "ja": "ステップ",
        "en": "Step",
    },
    "bench.run_only_next_instruction": {
        "ja": "次の命令「{ins}」({addr:04X}番地)だけを実行して止まる({c}J)",
        "en": 'Run only the next instruction "{ins}" ({addr:04X}) and stop ({c}J)',
    },
    "bench.call_run_until_rtn": {
        "ja": (
            "「{ins}」で{addr:04X}番地を呼び、RTNで戻ってくるまで実行して、"
            "次の命令で止まる({s}{c}J)"
        ),
        "en": (
            'Call {addr:04X} with "{ins}", run until RTN returns, and stop at the next '
            "instruction ({s}{c}J)"
        ),
    },
    "bench.step_over": {
        "ja": "CALL単位で実行",
        "en": "Step over",
    },
    "bench.editing": {
        "ja": "編集中",
        "en": "editing",
    },
    "bench.running": {
        "ja": "実行中",
        "en": "running",
    },
    "bench.paused": {
        "ja": "一時停止中",
        "en": "paused",
    },
    "bench.machine_code_workbench": {
        "ja": "マシン語の作業欄  {state}",
        "en": "Machine-code workbench  {state}",
    },
    "bench.keys_go_workbench": {
        "ja": "キーは作業欄へ",
        "en": "Keys go to the workbench",
    },
    "bench.keys_go_machine": {
        "ja": "キーは本体へ",
        "en": "Keys go to the machine",
    },
    "bench.machine_code_no_rom": {
        "ja": "マシン語(ROMなし)  {state}",
        "en": "Machine code (no ROM)  {state}",
    },
    "bench.stopped_not_usable_without": {
        "ja": "ROMなしでは使えない{addr:04X}番地で止まっています",
        "en": "Stopped at {addr:04X}, not usable without ROM",
    },
    "bench.run_call_basic_call": {
        "ja": "(▶ 実行、またはBASICでCALL &{addr:04X})",
        "en": "(▶ Run, or call it from BASIC with CALL &{addr:04X})",
    },
    "bench.clear_lcd_before_run": {
        "ja": "実行の前に液晶を消す",
        "en": "Clear LCD before run",
    },
    "bench.start": {
        "ja": "開始番地",
        "en": "Start",
    },
    "bench.auto": {
        "ja": "(自動)",
        "en": "(auto)",
    },
    "bench.note_key": {
        "ja": "{note}({key})",
        "en": "{note} ({key})",
    },
    "bench.undo": {
        "ja": "取り消す",
        "en": "Undo",
    },
    "bench.redo": {
        "ja": "やり直す",
        "en": "Redo",
    },
    "bench.export_hex_e": {
        "ja": ".hexに書き出す {c}E",
        "en": "Export .hex {c}E",
    },
    "bench.dump_list": {
        "ja": "ダンプリスト",
        "en": "Dump list",
    },
    "bench.no_dump_export_yet": {
        "ja": "書き出すダンプはまだありません",
        "en": "No dump to export yet",
    },
    "bench.set_range": {
        "ja": "範囲を指定する",
        "en": "Set the range",
    },
    "bench.range_set_bytes": {
        "ja": "範囲(指定、合計{n}バイト) ",
        "en": ("Range set, {n} byte: ", "Range set, {n} bytes: "),
    },
    "bench.ranges_bytes": {
        "ja": "範囲({places}か所、合計{n}バイト) ",
        "en": ("{places} ranges, {n} byte: ", "{places} ranges, {n} bytes: "),
    },
    "bench.range_bytes": {
        "ja": "範囲(合計{n}バイト) ",
        "en": ("Range, {n} byte: ", "Range, {n} bytes: "),
    },
    "bench.more": {
        "ja": "ほか{n}か所",
        "en": "and {n} more",
    },
    "bench.automatic": {
        "ja": "自動に戻す",
        "en": "Automatic",
    },
    "bench.range": {
        "ja": "範囲",
        "en": "Range",
    },
    "bench.disassembly": {
        "ja": "逆アセンブル",
        "en": "Disassembly",
    },
    "bench.click_dot_breakpoint": {
        "ja": "(左の点をクリックしてブレークポイントを設定)",
        "en": "(click a dot for a breakpoint)",
    },
    "bench.start_tag": {
        "ja": "開始",
        "en": "start",
    },
    "bench.no_rom_contents": {
        "ja": "(ROMの中身なし)",
        "en": "(no ROM contents)",
    },
    "bench.marks_right_executed_static": {
        "ja": "✓:実行済み　.:静的解析　?:推定　U:ユーザ指定",
        "en": "Marks at right  ✓: executed  .: static analysis  ?: guessed  U: user-specified",
    },
    "bench.click_type_export_range": {
        "ja": "クリックすると、書き出す範囲を入力できます",
        "en": "Click to type the export range",
    },
    "bench.registers": {
        "ja": "レジスタ",
        "en": "Registers",
    },
    "bench.cycles": {
        "ja": "サイクル {n}",
        "en": "Cycles {n}",
    },
    "bench.internal_ram": {
        "ja": "内部RAM",
        "en": "Internal RAM",
    },
    "bench.00_0b_i_j": {
        "ja": "(00〜0Bは I J A B XL XH YL YH K L M N)",
        "en": "(00-0B: I J A B XL XH YL YH K L M N)",
    },
    "bench.click_open": {
        "ja": "(クリックで開く)",
        "en": "(click to open)",
    },
    "bench.type_4_digit_hex": {
        "ja": "開始番地を16進表記4桁で入力  {c}Vで貼り付け  Escで中止",
        "en": "Type a 4-digit hex start address  {c}V pastes  Esc cancels",
    },
    "bench.type_first_last_addresses": {
        "ja": (
            "始めと終わりの番地を16進表記4桁ずつ入力  空のままEnterで自動に戻す  {c}Vで貼り付け  "
            "Escで中止"
        ),
        "en": (
            "Type the first and last addresses, 4 hex digits each  Enter alone goes back to "
            "automatic  {c}V pastes  Esc cancels"
        ),
    },
    "bench.click_workbench_write_dump": {
        "ja": "作業欄をクリックすると、キーでダンプを入力できます",
        "en": "Click the workbench to write the dump with the keys",
    },
    "bench.type_hex_pause_b": {
        "ja": (
            "16進表記で入力  {c}.で一時停止  {c}Bでブレークポイント  "
            "本体をクリックするとキー入力は本体へ"
        ),
        "en": "Type hex  {c}. pause  {c}B breakpoint  Click the machine to send keys there",
    },
    "bench.g_continue_j_step": {
        "ja": "{c}Gで続行  {c}Jでステップ実行  {s}{c}JでCALL単位の実行",
        "en": "{c}G continue  {c}J step  {s}{c}J step over CALL",
    },
    "bench.running_keys_go_esc": {
        "ja": "実行中です。キーは{model}へ(EscはBRK)。{c}.で一時停止",
        "en": "Running. Keys go to the {model} (Esc is BRK). {c}. pauses",
    },
    "bench.g_continue_j_step_c_c": {
        "ja": "{c}Gで続行  {c}Jでステップ実行  Escで編集に戻る",
        "en": "{c}G continue  {c}J step  Esc back to editing",
    },
    "bench.type_4_digit_address": {
        "ja": "番地を4桁入力してSpace、続けて8バイトを入力してEnter(ダンプリストと同じ形)",
        "en": "Type a 4-digit address and Space, then 8 bytes and Enter (as in a dump listing)",
    },
    "bench.type_hex_enter_next": {
        "ja": (
            "16進表記で入力  Enterで次の行  Tabで番地を入力して移動  {c}Gで実行  "
            "{c}Aでカーソル位置を開始番地に  {c}Vで貼り付け"
        ),
        "en": (
            "Type hex  Enter next line  Tab jumps to a typed address  {c}G run  {c}A start "
            "address at cursor  {c}V paste"
        ),
    },
    "bench.cannot_redo_while_running": {
        "ja": "実行中はやり直せません",
        "en": "Cannot redo while running",
    },
    "bench.cannot_undo_while_running": {
        "ja": "実行中は取り消せません",
        "en": "Cannot undo while running",
    },
    "bench.nothing_redo": {
        "ja": "やり直せる書き込みはありません",
        "en": "Nothing to redo",
    },
    "bench.nothing_undo": {
        "ja": "取り消せる書き込みはありません",
        "en": "Nothing to undo",
    },
    "bench.set_back": {
        "ja": "{addr:04X}番地を{new:02X}から{old:02X}に戻す",
        "en": "Set {addr:04X} back from {new:02X} to {old:02X}",
    },
    "bench.set": {
        "ja": "{addr:04X}番地を{old:02X}から{new:02X}にする",
        "en": "Set {addr:04X} from {old:02X} to {new:02X}",
    },
    "bench.undo_what": {
        "ja": "{what}を取り消す",
        "en": "Undo {what}",
    },
    "bench.redo_what": {
        "ja": "{what}をやり直す",
        "en": "Redo {what}",
    },
    "bench.undid": {
        "ja": "{what}を取り消しました",
        "en": "Undid {what}",
    },
    "bench.redid": {
        "ja": "{what}をやり直しました",
        "en": "Redid {what}",
    },
    "bench.cannot_edit_while_running": {
        "ja": "実行中は書き換えられません",
        "en": "Cannot edit while running",
    },
    "bench.end_line_enter_goes": {
        "ja": "行の終わりです。Enterで次の行へ",
        "en": "End of line. Enter goes to the next line",
    },
    "bench.outside_ram_cannot_written": {
        "ja": "{addr:04X}番地はRAMの外なので書けません",
        "en": "{addr:04X} is outside RAM and cannot be written",
    },
    "bench.typing": {
        "ja": "{addr:04X}番地への入力",
        "en": "typing at {addr:04X}",
    },
    "bench.paste": {
        "ja": "貼り付け",
        "en": "paste",
    },
    "bench.paste_bytes": {
        "ja": "貼り付け({n}バイト)",
        "en": ("paste ({n} byte)", "paste ({n} bytes)"),
    },
    "bench.outside_ram_so_without": {
        "ja": "{addr:04X}番地はRAMの外なので、ROMなしでは開始番地にできません",
        "en": "{addr:04X} is outside RAM, so without ROM it cannot be the start address",
    },
    "bench.pasted_text_not_address": {
        "ja": "貼り付けた文字は番地ではありません(16進表記の4桁で)",
        "en": "The pasted text is not an address (use 4 hex digits)",
    },
    "bench.last_address_before_first": {
        "ja": "終わりの番地が始めの番地より前にあります",
        "en": "The last address is before the first",
    },
    "bench.export_range_automatic_again": {
        "ja": "書き出す範囲を自動に戻しました",
        "en": "Export range is automatic again",
    },
    "bench.pasted_text_not_range": {
        "ja": "貼り付けたテキストは範囲ではありません(始めと終わりの番地を16進表記4桁で)",
        "en": "The pasted text is not a range (use two 4-digit hex addresses)",
    },
    "bench.more_where_n": {
        "ja": "{where}ほか{n}か所",
        "en": "{where} and {n} more",
    },
    "bench.bytes": {
        "ja": "{where}({n}バイト)",
        "en": ("{where} ({n} byte)", "{where} ({n} bytes)"),
    },
    "bench.paused_why_addr": {
        "ja": "{why}。{addr:04X}番地で一時停止しています",
        "en": "{why}. Paused at {addr:04X}",
    },
    "bench.can_continue": {
        "ja": "{why}。{addr:04X}番地から続行できます",
        "en": "{why}. You can continue from {addr:04X}",
    },
    "bench.paused_message": {
        "ja": "一時停止しました",
        "en": "Paused",
    },
    "bench.stopped_running_went_back": {
        "ja": "実行を中止して編集に戻りました(メモリはそのままです)",
        "en": "Stopped running and went back to editing (memory unchanged)",
    },
    "bench.stopped_before_first_instruction": {
        "ja": "{addr:04X}番地の最初の命令の前で止まっています",
        "en": "Stopped before the first instruction at {addr:04X}",
    },
    "bench.basic_running_now_single": {
        "ja": "BASICの実行中です。ステップ実行できるのは、マシン語の実行中だけです",
        "en": "BASIC is running now. Single-stepping works only while machine code runs",
    },
    "bench.cpu_waiting_key_timer": {
        "ja": "CPUがキーかタイマを待って停止しています(HALT)。「続行」で再開します",
        "en": 'The CPU is waiting for a key or the timer (HALT). "Continue" goes on',
    },
    "bench.returned_rtn_cycles_about": {
        "ja": "RTNで戻りました({n}サイクル、約{ms}ミリ秒)",
        "en": (
            "Returned with RTN ({n} cycle, about {ms} ms)",
            "Returned with RTN ({n} cycles, about {ms} ms)",
        ),
    },
    "bench.returned_call": {
        "ja": "呼び出しから戻りました",
        "en": "Returned from the call",
    },
    "bench.stopped_breakpoint": {
        "ja": "ブレークポイント({addr:04X})で止まりました",
        "en": "Stopped at the breakpoint at {addr:04X}",
    },
    "bench.stopped": {
        "ja": "{addr:04X}番地で止まりました",
        "en": "Stopped at {addr:04X}",
    },
    "bench.stopped_jumped_rom_routine": {
        "ja": "ROMの{name}({addr:04X})にジャンプしたため停止しました。ROMなしでは使えません",
        "en": "Stopped: jumped to the ROM routine {name} ({addr:04X}), not usable without ROM",
    },
    "bench.stopped_jumped_outside_ram": {
        "ja": (
            "RAMの外の{addr:04X}番地にジャンプしたため停止しました。"
            "ROMなしでは使えません(ROMのルーチンなら、代替ROMルーチンを--new-routine "
            "{addr:04X}で書き始められます)"
        ),
        "en": (
            "Stopped: jumped to {addr:04X} outside RAM, not usable without ROM (if it is a ROM "
            "routine, start a stand-in with --new-routine {addr:04X})"
        ),
    },
    "bench.no_mark_here": {
        "ja": "指定はありません",
        "en": "No mark here",
    },
    "bench.outside_ram": {
        "ja": "RAMの外です",
        "en": "Outside RAM",
    },
    "bench.already_marked_so": {
        "ja": "すでにこの指定です",
        "en": "Already marked so",
    },
    "bench.cleared_mark": {
        "ja": "{addr:04X}番地の指定を消しました",
        "en": "Cleared the mark at {addr:04X}",
    },
    "bench.marked_data": {
        "ja": "{addr:04X}番地からデータにしました",
        "en": "Marked data from {addr:04X}",
    },
    "bench.marked_code": {
        "ja": "{addr:04X}番地から命令にしました",
        "en": "Marked code from {addr:04X}",
    },
    "bench.name_what": {
        "ja": "{name}({what})",
        "en": "{name} ({what})",
    },
    "bench.lo_last": {
        "ja": "{lo:04X}〜{last:04X}",
        "en": "{lo:04X}-{last:04X}",
    },
    # ---- 一覧と手引き(overlay.py) ----
    "overlay.open_folder_o": {
        "ja": "フォルダを開く(O)",
        "en": "Open folder (O)",
    },
    "overlay.folder": {
        "ja": "フォルダ",
        "en": "Folder",
    },
    "overlay.reload_r": {
        "ja": "読み直す(R)",
        "en": "Reload (R)",
    },
    "overlay.reload": {
        "ja": "読み直す",
        "en": "Reload",
    },
    "overlay.close": {
        "ja": "閉じる",
        "en": "Close",
    },
    "overlay.load_only_shift_enter": {
        "ja": "読み込むだけ(Shift+Enter)",
        "en": "Load only (Shift+Enter)",
    },
    "overlay.load_only": {
        "ja": "読み込むだけ",
        "en": "Load only",
    },
    "overlay.load_run_enter": {
        "ja": "読み込んで実行(Enter)",
        "en": "Load and run (Enter)",
    },
    "overlay.load_run": {
        "ja": "読み込んで実行",
        "en": "Load and run",
    },
    "overlay.search_name": {
        "ja": "名前で検索( / )",
        "en": "Search by name ( / )",
    },
    "overlay.nothing_here_yet_put": {
        "ja": "プログラムがありません。.basか.hexのファイルをフォルダに置いてください",
        "en": "Nothing here yet. Put .bas or .hex files in the folder",
    },
    "overlay.no_match_esc_ends": {
        "ja": "一致するものがありません(Escで検索を終了)",
        "en": "No match (Esc ends the search)",
    },
    "overlay.more_above": {
        "ja": "▲ 上にあと{n}本",
        "en": "▲ {n} more above",
    },
    "overlay.more_below": {
        "ja": "▼ 下にあと{n}本",
        "en": "▼ {n} more below",
    },
    "overlay.wheel": {
        "ja": "{where}(↑↓かホイールで)",
        "en": "{where} (↑↓ or wheel)",
    },
    "overlay.esc_ends_search": {
        "ja": "Escで検索を終了",
        "en": "Esc ends the search",
    },
    "overlay.unreadable_lines": {
        "ja": "読めない行あり",
        "en": "unreadable lines",
    },
    "overlay.any_model": {
        "ja": "どの機種でも",
        "en": "any model",
    },
    "overlay.models": {
        "ja": "{models}用",
        "en": "for {models}",
    },
    # ---- ゲームパッドの割り当て(padmenu.py) ----
    "pad.save_program": {
        "ja": "このプログラム用に保存",
        "en": "Save for this program",
    },
    "pad.save_default": {
        "ja": "既定として保存",
        "en": "Save as default",
    },
    "pad.reset_factory_mapping": {
        "ja": "初期設定に戻す",
        "en": "Reset to factory mapping",
    },
    "pad.back_pad": {
        "ja": "# pad: に戻す",
        "en": "Back to # pad:",
    },
    "pad.copy_pad_line": {
        "ja": "# pad: の行をコピー",
        "en": "Copy # pad: line",
    },
    "pad.click_key_pocket_computer": {
        "ja": (
            "{name}に割り当てるキーを、本体の画像でクリックするか、"
            "パソコンのキーボードで押してください。Deleteで割り当てを解除、Escで中止します"
        ),
        "en": (
            "Click a key on the pocket computer or press one on your keyboard to map it to "
            "{name}. Delete clears the mapping, Esc cancels"
        ),
    },
    "pad.press_gamepad_button_click": {
        "ja": "ゲームパッドのボタンを押すか、下の割り当てをクリックすると変更できます",
        "en": "Press a gamepad button or click a mapping below to change it",
    },
    "pad.click_mapping_below_change": {
        "ja": "下の割り当てをクリックすると変更できます",
        "en": "Click a mapping below to change it",
    },
    "pad.button_names_follow_sdl": {
        "ja": (
            "ボタンの名前はSDLの規約によるA・B・X・Yの位置で、"
            "ゲームパッドに印字された名前と違うことがあります。違うときは、"
            "割り当てたいボタンを実際に押して選んでください"
        ),
        "en": (
            "Button names follow the SDL convention for the A/B/X/Y positions and may differ from "
            "the labels on your pad. If they do, press the button you want to map to select it"
        ),
    },
    "pad.gamepad_mapping": {
        "ja": "ゲームパッドの割り当て",
        "en": "Gamepad mapping",
    },
    "pad.no_gamepad_connected_appears": {
        "ja": "ゲームパッドが接続されていません(接続するとここに表示されます)",
        "en": "No gamepad connected (it appears here once connected)",
    },
    "pad.target_no_program_loaded": {
        "ja": "対象: (プログラムを読み込んでいません)",
        "en": "Target: (no program loaded)",
    },
    "pad.target": {
        "ja": "対象: {name}",
        "en": "Target: {name}",
    },
    "pad.current_mapping": {
        "ja": "現在の割り当て: {source}",
        "en": "Current mapping: {source}",
    },
    "pad.edited_not_saved": {
        "ja": "(変更あり・未保存)",
        "en": " (edited, not saved)",
    },
    # ---- 代替ROMルーチンの比べ(routinecheck.py) ----
    "check.went_which_has_no": {
        "ja": "代替ROMルーチンのない{addr:04X}番地へ進みました",
        "en": "went on to {addr:04X}, which has no stand-in",
    },
    "check.internal_ram_rom_stand": {
        "ja": "内部RAMの{at:02X}: ROM {rom:02X}、代替 {hle:02X}",
        "en": "internal RAM {at:02X}: ROM {rom:02X}, stand-in {hle:02X}",
    },
    "check.rom_stand": {
        "ja": "{name}: ROM {rom:X}、代替 {hle:X}",
        "en": "{name}: ROM {rom:X}, stand-in {hle:X}",
    },
    "check.rom_stand_at_hle": {
        "ja": "{at:04X}番地: ROM {rom:02X}、代替 {hle:02X}",
        "en": "{at:04X}: ROM {rom:02X}, stand-in {hle:02X}",
    },
    "check.more_bytes": {
        "ja": "ほかに{n}バイト",
        "en": ("and {n} more byte", "and {n} more bytes"),
    },
    "check.stand_stopped": {
        "ja": "代替ROMルーチンが止まりました({error})",
        "en": "the stand-in stopped ({error})",
    },
    "check.does_not_return_machine": {
        "ja": "ROMのある本体で戻りません",
        "en": "does not return on the machine with the ROM",
    },
    "check.stand_does_not_return": {
        "ja": "代替ROMルーチンが戻りません",
        "en": "the stand-in does not return",
    },
    "check.cycles_rom_stand": {
        "ja": "サイクル数: ROM {rom}、代替 {hle}",
        "en": "cycles: ROM {rom}, stand-in {hle}",
    },
    "check.no_entry_name": {
        "ja": "入口の名前がありません: {names}",
        "en": "No entry with this name: {names}",
    },
    "check.not_compared_only_reproduces": {
        "ja": "--  {name}({addr:04X}) 返す値だけをまねるので比べない {where}",
        "en": (
            "--  {name} ({addr:04X}) not compared: it only reproduces the returned values {where}"
        ),
    },
    "check.ok_calls": {
        "ja": "OK  {name}({addr:04X}) {n}回 {where}",
        "en": (
            "OK  {name} ({addr:04X}) {n} call {where}",
            "OK  {name} ({addr:04X}) {n} calls {where}",
        ),
    },
    "check.ng_calls_differ": {
        "ja": "NG  {name}({addr:04X}) {n}回のうち{bad}回が違う {where}",
        "en": (
            "NG  {name} ({addr:04X}) {bad} of {n} call differ {where}",
            "NG  {name} ({addr:04X}) {bad} of {n} calls differ {where}",
        ),
    },
    "check.more_differences": {
        "ja": "ほかに{n}か所",
        "en": ("and {n} more difference", "and {n} more differences"),
    },
    # ---- 代替ROMルーチンの登録簿(routines.py) ----
    "routines.have_more_than_one": {
        "ja": "{files}に、{addr:04X}の代替ROMルーチンがいくつもあります",
        "en": "{files} have more than one stand-in for {addr:04X}",
    },
    "routines.name_used_built": {
        "ja": "{name}という名前は、組み込みで{addr:04X}に使っています",
        "en": "the name {name} is used by the built-in at {addr:04X}",
    },
    "routines.name_used": {
        "ja": "{name}という名前が、{addrs}にあります",
        "en": "the name {name} is used at {addrs}",
    },
    "routines.replaces_built": {
        "ja": "{file}: {name}({addr:04X})が、組み込みの{old}に代わります",
        "en": "{file}: {name} ({addr:04X}) replaces the built-in {old}",
    },
    "routines.not_used": {
        "ja": "{file}: {name}({addr:04X})は使いません。{why}",
        "en": "{file}: {name} ({addr:04X}) is not used: {why}",
    },
    "routines.there_built": {
        "ja": "{addr:04X}には組み込みの{old}があります",
        "en": "there is the built-in {old} at {addr:04X}",
    },
    "routines.cannot_load": {
        "ja": "{file}:{line}: 読めません({error})",
        "en": "{file}:{line}: cannot load ({error})",
    },
    "routines.keeps_waiting_without_advancing": {
        "ja": (
            "{name}({addr:04X})が、時間を進めずに待ち続けています。待つあいだはspend()"
            "で時間を進めてください"
        ),
        "en": (
            "{name} ({addr:04X}) keeps waiting without advancing time; call spend() while waiting"
        ),
    },
    "routines.not_compared_name": {
        "ja": "比べるものの名前ではありません: {name}",
        "en": "not a name of something to compare: {name}",
    },
    "routines.not_family": {
        "ja": "代替ROMルーチンを置ける機種ではありません: {model}",
        "en": "not a model that takes stand-in ROM routines: {model}",
    },
    "routines.address_out_of_range": {
        "ja": "番地が0〜FFFFの外です: {addr:X}",
        "en": "the address is outside 0–FFFF: {addr:X}",
    },
    "routines.bad_name": {
        "ja": "名前に使えない字があります: {name}",
        "en": "the name has characters that cannot be used: {name}",
    },
    "routines.bad_mode": {
        "ja": "modeはoverrideかfallbackです: {mode}",
        "en": "mode must be override or fallback: {mode}",
    },
    "routines.no_rom_names": {
        "ja": (
            "ROMのルーチンの名前はPC-1245、PC-1250/1251/1255、PC-1260/1261/1262、"
            "PC-1350だけ: {model}"
        ),
        "en": (
            "ROM routine names exist only for the PC-1245, PC-1250/1251/1255, "
            "PC-1260/1261/1262 and PC-1350: {model}"
        ),
    },
    "routines.bad_address_or_name": {
        "ja": "番地か名前が使えません: {addr:X} {name}",
        "en": "cannot use the address or the name: {addr:X} {name}",
    },
    # ---- プログラムのファイル(programs.py) ----
    "programs.addresses_fit_no_model": {
        "ja": "{title}(番地がどの機種のRAMにも収まらない)",
        "en": "{title} (addresses fit no model's RAM)",
    },
    "programs.title_models": {
        "ja": "{title}({models}用)",
        "en": "{title} (for {models})",
    },
    "programs.line_not_hex_dump": {
        "ja": "{where}{line}行目を16進ダンプとして読めません: {text}",
        "en": "{where}line {line} is not a hex dump: {text}",
    },
    "programs.line_goes_past_ffff": {
        "ja": "{where}{line}行目の番地がFFFFを越えます: {text}",
        "en": "{where}line {line} goes past FFFF: {text}",
    },
    "programs.line_bad_checksum": {
        "ja": "{where}{line}行目の「:」のあとがチェックサム(16進表記2桁)ではありません: {text}",
        "en": "{where}line {line} has no 2-digit hex checksum after ':': {text}",
    },
    "programs.line_has_wrong_checksum": {
        "ja": "{where}{line}行目のチェックサムが合いません(計算すると{sum:02X}): {text}",
        "en": "{where}line {line} has a wrong checksum (should be {sum:02X}): {text}",
    },
    "programs.empty": {
        "ja": "{where}中身が空です",
        "en": "{where}is empty",
    },
    "programs.bytes_go_past_ffff": {
        "ja": "{where}&{addr:04X}から{n}バイトで、&FFFFを越えます",
        "en": (
            "{where}{n} byte from &{addr:04X} goes past &FFFF",
            "{where}{n} bytes from &{addr:04X} go past &FFFF",
        ),
    },
    "programs.no_address_e_g": {
        "ja": "# {key}: {name}を置く番地がありません(例:# bin: {name} &C300)",
        "en": "# {key}: no address for {name} (e.g. # bin: {name} &C300)",
    },
    "programs.not_found": {
        "ja": "# {key}: {name}が見つかりません",
        "en": "# {key}: {name} not found",
    },
    "programs.cannot_read": {
        "ja": "# {key}: {name}を読めません({error})",
        "en": "# {key}: cannot read {name} ({error})",
    },
    "programs.cannot_read_data": {
        "ja": "{file}: # data: の{text}を読めません",
        "en": "{file}: cannot read {text} in # data:",
    },
    "programs.cannot_read_ram_e": {
        "ja": "{file}: # ram: の{text}を読めません(例:# ram: 6800-7FFF)",
        "en": "{file}: cannot read {text} in # ram: (e.g. # ram: 6800-7FFF)",
    },
    "programs.cannot_read_card_8": {
        "ja": "{file}: # card: の{text}を読めません(8か16)",
        "en": "{file}: cannot read # card: {text} (8 or 16)",
    },
    # ---- プログラムの読み込み(loading.py) ----
    "load.not_loaded_outside_ram": {
        "ja": "{name}を読み込めません。{addr:04X}番地はRAMの外です",
        "en": "{name} not loaded: {addr:04X} is outside RAM",
    },
    "load.not_loaded": {
        "ja": "{name}を読み込めません。{why}",
        "en": "{name} not loaded. {why}",
    },
    "app.stopped_running_code": {
        "ja": "実行中のマシン語を止めて読み込みました",
        "en": "Stopped the running machine code and loaded the program",
    },
    "load.needs_kb_ram_card": {
        "ja": "{name}には{n}KBのRAMカードが要ります。--card {n}をつけて起動してください",
        "en": "{name} needs a {n} KB RAM card. Start sc61box with --card {n}",
    },
    "load.not_loaded_ram_overlaps": {
        "ja": "{name}を読み込めません。# ram: の{lo:04X}-{hi:04X}がROMか液晶RAMに重なっています",
        "en": "{name} not loaded: # ram: {lo:04X}-{hi:04X} overlaps ROM or LCD RAM",
    },
    "load.not_loaded_program_model": {
        "ja": "{program}のため、{model}では読み込めません",
        "en": "{program}: not loaded on the {model}",
    },
    "load.not_loaded_line_too": {
        "ja": (
            "{name}を読み込めません。{line}行が長すぎて、打ち込むと途中で切れます(行番号と中身で79"
            "字まで)"
        ),
        "en": (
            "{name} not loaded. Line {line} is too long to type in (79 characters with the line "
            "number)"
        ),
    },
    "load.not_loaded_line_too_name_text": {
        "ja": (
            "{name}を読み込めません。「{text}」の行が長すぎて、"
            "打ち込むと途中で切れます(行番号と中身で79字まで)"
        ),
        "en": (
            '{name} not loaded. The line "{text}" is too long to type in (79 characters with '
            "the line number)"
        ),
    },
    "load.not_loaded_basic_bytes": {
        "ja": (
            "{name}を読み込めません。BASICのプログラムが{size}バイトあり、"
            "RAMに入りません(空きは{room}バイト)"
        ),
        "en": (
            "{name} not loaded. The BASIC is {size} bytes and does not fit in RAM ({room} bytes "
            "free)"
        ),
    },
    "load.password_locked": {
        "ja": "プログラムがパスワードで保護されています",
        "en": "The program is protected by a password",
    },
    "load.empty": {
        "ja": "{name}は空です",
        "en": "{name}: empty",
    },
    "load.uses_basic_rom_routines": {
        "ja": "{name}はBASICとROMのルーチンを使うプログラムなので、ROMなしでは使えません",
        "en": "{name} uses BASIC and ROM routines, so it needs the ROM",
    },
    "load.basic_program_so_needs": {
        "ja": "{name}はBASICのプログラムなので、ROMなしでは使えません",
        "en": "{name} is a BASIC program, so it needs the ROM",
    },
    "load.needs_rom": {
        "ja": "{name}はROMが要るプログラムなので、ROMなしでは使えません",
        "en": "{name} needs the ROM",
    },
    # ---- 本体と状態の保存(machine.py) ----
    "machine.rom_file_not_found": {
        "ja": (
            "ROMのファイル{name}が見つかりません。実機から読み出した内部ROM(cpu-{model}.rom、8KB)"
            "とBASIC ROM(bas-{model}.rom、{kb}KB)をrom/に置くか、環境変数SC61BOX_ROMにそのフォルダ"
            "を指定してください(READMEの「ROMを置いて動かす」)。"
        ),
        "en": (
            "ROM file {name} not found. Put the internal ROM (cpu-{model}.rom, 8 KB) and the "
            "BASIC ROM (bas-{model}.rom, {kb} KB) read from a real machine in rom/, or set the "
            'environment variable SC61BOX_ROM to their folder (see "Using the ROM" in the '
            "README)."
        ),
    },
    "machine.has_only_bytes_needs": {
        "ja": "{path}は{have}バイトしかありません。{name}は{size}バイト({kb}KB)必要です。",
        "en": "{path} has only {have} bytes. {name} needs {size} bytes ({kb} KB).",
    },
    "machine.not_state_file_error": {
        "ja": "状態のファイルとして読めません({error})",
        "en": "Not a state file ({error})",
    },
    "machine.not_state_file": {
        "ja": "状態のファイルとして読めません",
        "en": "Not a state file",
    },
    "machine.state_another_model_pc": {
        "ja": "ほかの機種(PC-{model})の状態です",
        "en": "This is the state of another model (PC-{model})",
    },
    "machine.rom_not_one_used": {
        "ja": "ROMが保存したときと違います",
        "en": "The ROM is not the one used when saving",
    },
    "machine.memory_size_differs": {
        "ja": "メモリの大きさが違います",
        "en": "The memory size differs",
    },
    "machine.no_machine_state": {
        "ja": "本体の状態がありません",
        "en": "No machine state",
    },
    "machine.bad_basic_state": {
        "ja": "BASICの状態が正しくありません",
        "en": "Bad BASIC state",
    },
    "machine.bad_value_machine": {
        "ja": "本体の{name}の値が正しくありません",
        "en": "Bad value for machine {name}",
    },
    # ---- CPU(sc61860.py) ----
    "cpu.no_cpu_state": {
        "ja": "CPUの状態がありません",
        "en": "No CPU state",
    },
    "cpu.bad_value_cpu": {
        "ja": "CPUの{name}の値が正しくありません",
        "en": "Bad value for CPU {name}",
    },
    "cpu.cpu_internal_ram_size": {
        "ja": "CPUの内部RAMの大きさが違います",
        "en": "The CPU internal RAM size differs",
    },
    # ---- 録画(recorder.py) ----
    "rec.ffmpeg_not_found_install": {
        "ja": "ffmpegが見つかりません。ffmpegをインストールしてPATHに置くと録画できます",
        "en": "ffmpeg not found. Install ffmpeg on the PATH to record",
    },
    "rec.ffmpeg_stopped": {
        "ja": "ffmpegが止まりました",
        "en": "ffmpeg stopped",
    },
    "rec.wrong_picture_size_bytes": {
        "ja": "画像の大きさが違います({size}バイト。{want}バイトのはずです)",
        "en": "Wrong picture size ({size} bytes, expected {want})",
    },
    "rec.ffmpeg_exited_code": {
        "ja": "ffmpegが終了コード{code}で止まりました",
        "en": "ffmpeg exited with code {code}",
    },
    "rec.could_not_finish_video": {
        "ja": "動画を作成できませんでした",
        "en": "Could not finish the video",
    },
    # ---- 音(audio.py) ----
    "audio.sdl2_library_not_found": {
        "ja": "SDL2のライブラリが見つかりません",
        "en": "SDL2 library not found",
    },
    "audio.cannot_open_mixer": {
        "ja": "ミキサーを開けません",
        "en": "Cannot open the mixer",
    },
    "audio.mixer_opened_hz": {
        "ja": "ミキサーが{freq}Hzで開かれました",
        "en": "The mixer opened at {freq} Hz",
    },
    "audio.sdl_audio_queue_not": {
        "ja": "SDLのキューが使えないので、mixerで鳴らします({error})",
        "en": "SDL audio queue not available, using the mixer ({error})",
    },
    "audio.sound_off": {
        "ja": "音を出さずに続けます({error})",
        "en": "Sound off ({error})",
    },
    # ---- 逆アセンブル(disasm.py) ----
    "disasm.else": {
        "ja": "ほかは→{addr:04X}",
        "en": "else→{addr:04X}",
    },
    # ---- ROMなしのBASIC(basic/) ----
    "basic.not_basic_state": {
        "ja": "BASICの状態として読めません",
        "en": "Not a BASIC state",
    },
    # ---- ROMのルーチンの働き(PC-1251系) ----
    "rom.1251.fadd": {
        "ja": "Y+X",
        "en": "Y+X",
    },
    "rom.1251.fsub": {
        "ja": "Y−X",
        "en": "Y−X",
    },
    "rom.1251.fmul": {
        "ja": "Y×X",
        "en": "Y×X",
    },
    "rom.1251.fdiv": {
        "ja": "Y÷X",
        "en": "Y÷X",
    },
    "rom.1251.fpow": {
        "ja": "YのX乗",
        "en": "Y to the power X",
    },
    "rom.1251.fsin": {
        "ja": "SIN(角度の単位は液晶の記号のビットF83C・F83Dで決まる)",
        "en": "SIN (the angle unit is set by the LCD symbol bits F83C, F83D)",
    },
    "rom.1251.fcos": {
        "ja": "COS",
        "en": "COS",
    },
    "rom.1251.ftan": {
        "ja": "TAN",
        "en": "TAN",
    },
    "rom.1251.fasn": {
        "ja": "ASN",
        "en": "ASN",
    },
    "rom.1251.facs": {
        "ja": "ACS",
        "en": "ACS",
    },
    "rom.1251.fatn": {
        "ja": "ATN",
        "en": "ATN",
    },
    "rom.1251.fexp": {
        "ja": "EXP",
        "en": "EXP",
    },
    "rom.1251.fln": {
        "ja": "LN",
        "en": "LN",
    },
    "rom.1251.flog": {
        "ja": "LOG",
        "en": "LOG",
    },
    "rom.1251.fsqr": {
        "ja": "SQR",
        "en": "SQR",
    },
    "rom.1251.fabs": {
        "ja": "ABS",
        "en": "ABS",
    },
    "rom.1251.fsgn": {
        "ja": "SGN",
        "en": "SGN",
    },
    "rom.1251.fint": {
        "ja": "INT",
        "en": "INT",
    },
    "rom.1251.fdms": {
        "ja": "DMS(C6BBのビット0を立てたまま戻る。BASICへ戻る前にFROUNDを呼ぶ)",
        "en": "DMS (returns with bit 0 of C6BB set; call FROUND before going back to BASIC)",
    },
    "rom.1251.fdeg": {
        "ja": "DEG(BASIC ROM。CALLで呼ぶ)",
        "en": "DEG (BASIC ROM, use CALL)",
    },
    "rom.1251.frnd": {
        "ja": "RND(BASIC ROM。CALLで呼ぶ。F8B0〜F8B7の乱数の種を書く)",
        "en": "RND (BASIC ROM, use CALL; writes the random seed at F8B0-F8B7)",
    },
    "rom.1251.fround": {
        "ja": "演算Xを10桁に丸める",
        "en": "round X to 10 digits",
    },
    "rom.1251.feq": {
        "ja": "Y=X",
        "en": "Y=X",
    },
    "rom.1251.fne": {
        "ja": "Y<>X",
        "en": "Y<>X",
    },
    "rom.1251.flt": {
        "ja": "Y<X",
        "en": "Y<X",
    },
    "rom.1251.fgt": {
        "ja": "Y>X",
        "en": "Y>X",
    },
    "rom.1251.fle": {
        "ja": "Y<=X",
        "en": "Y<=X",
    },
    "rom.1251.fge": {
        "ja": "Y>=X",
        "en": "Y>=X",
    },
    "rom.1251.seq": {
        "ja": "Y=X(J_ONE)",
        "en": "Y=X(J_ONE)",
    },
    "rom.1251.sne": {
        "ja": "Y<>X(J_ONE)",
        "en": "Y<>X(J_ONE)",
    },
    "rom.1251.slt": {
        "ja": "Y<X",
        "en": "Y<X",
    },
    "rom.1251.sgt": {
        "ja": "Y>X",
        "en": "Y>X",
    },
    "rom.1251.sle": {
        "ja": "Y<=X",
        "en": "Y<=X",
    },
    "rom.1251.sge": {
        "ja": "Y>=X",
        "en": "Y>=X",
    },
    "rom.1251.fasc": {
        "ja": "ASC",
        "en": "ASC",
    },
    "rom.1251.fval": {
        "ja": "VAL(文字列の直後の1バイトに00を書く)",
        "en": "VAL (writes 00 to the byte after the string)",
    },
    "rom.1251.fchrs": {
        "ja": "CHR$(J_ONE)",
        "en": "CHR$(J_ONE)",
    },
    "rom.1251.fstrs": {
        "ja": "STR$(液晶RAMのF800〜F837を作業に使う)",
        "en": "STR$ (uses the LCD RAM F800-F837 as work area)",
    },
    "rom.1251.i2f": {
        "ja": "28・29番地の符号つき16ビット → 演算X",
        "en": "signed 16 bits at 28, 29 → X",
    },
    "rom.1251.u2f": {
        "ja": "28・29番地の符号なし16ビット → 演算X",
        "en": "unsigned 16 bits at 28, 29 → X",
    },
    "rom.1251.range16": {
        "ja": "F2Iの範囲を−32768〜32767にする(続けてF2Iを呼ぶ)",
        "en": "set the F2I range to −32768 to 32767 (then call F2I)",
    },
    "rom.1251.f2i": {
        "ja": "演算X → 28・29番地の16ビット(J_ONE)",
        "en": "X → 16 bits at 28, 29 (J_ONE)",
    },
    "rom.1251.keyscan": {
        "ja": "キーを1回読む。キャリー1でAに本体の文字コード(押されているときJ_ONE)",
        "en": "read the keys once; when a key is down, carry 1 and its character code in A (J_ONE)",
    },
    "rom.1251.keywait": {
        "ja": "キーを待つ。自動で電源が切れるまでの時間を戻す(J_ONE)",
        "en": "wait for a key, restarting the auto power-off time (J_ONE)",
    },
    "rom.1251.keywait2": {
        "ja": "キーを待つ。電源が切れるまでの時間を戻さない(J_ONE)",
        "en": "wait for a key, keeping the auto power-off time (J_ONE)",
    },
    "rom.1251.dispon": {
        "ja": "液晶の表示をつける(Cポート←01)",
        "en": "LCD on (port C ← 01)",
    },
    "rom.1251.dispoff": {
        "ja": "液晶の表示を消す(Cポート←00)",
        "en": "LCD off (port C ← 00)",
    },
    "rom.1251.wait2ms": {
        "ja": "2msのタイマのフラグを1回待つ",
        "en": "wait for one 2 ms timer tick",
    },
    "rom.1251.wait4ms": {
        "ja": "2msのタイマのフラグを2回待つ",
        "en": "wait for two 2 ms timer ticks",
    },
    "rom.1251.wait6ms": {
        "ja": "2msのタイマのフラグを3回待つ",
        "en": "wait for three 2 ms timer ticks",
    },
    "rom.1251.glyph": {
        "ja": "Aの文字の形の番地−1をXへ(J_ONE)",
        "en": "glyph address of A, minus 1, into X (J_ONE)",
    },
    "rom.1251.keywait0": {
        "ja": "Cポートを01にしてキーを待つ(J_ONE)",
        "en": "set port C to 01 and wait for a key (J_ONE)",
    },
    "rom.1251.swapc": {
        "ja": "AをCポートと5F番地に出し、前に5F番地にあった値をAへ",
        "en": "A → port C and 5F, previous value at 5F → A",
    },
    "rom.1251.prgtop": {
        "ja": "プログラムの頭の番地(C6E1・C6E2)をXへ",
        "en": "program start address (C6E1, C6E2) → X",
    },
    "rom.1251.showbuf": {
        "ja": "C7B0からの24バイトを内部RAMの20〜37番地にコピーし、液晶に出す",
        "en": "copy 24 bytes from C7B0 to internal RAM 20-37 and show them on the LCD",
    },
    "rom.1251.textbuf": {
        "ja": "BAにC7B0、YにC7AFを入れる",
        "en": "C7B0 → BA, C7AF → Y",
    },
    "rom.1251.ba2y": {
        "ja": "BAをYへ",
        "en": "BA → Y",
    },
    "rom.1251.ba2ym": {
        "ja": "BA−1をYへ",
        "en": "BA−1 → Y",
    },
    "rom.1251.x1c": {
        "ja": "内部RAMの1C番地からJ+1バイトをXへ",
        "en": "J+1 bytes from internal RAM 1C → X",
    },
    "rom.1251.pushx": {
        "ja": "XからJ+1バイトをスタックに積む",
        "en": "push J+1 bytes from X onto the stack",
    },
    "rom.1251.popx": {
        "ja": "PUSHXで積んだJ+1バイトをXに戻す",
        "en": "pop the J+1 bytes pushed by PUSHX back into X",
    },
    "rom.1251.ba2xm": {
        "ja": "AからJ+1バイトをXへ写し、Xから1を引く(Jが1ならBA−1)",
        "en": "copy J+1 bytes from A to X, then subtract 1 from X (BA−1 when J is 1)",
    },
    "rom.1251.lcdxm": {
        "ja": "BをF8にしてBA2XMと同じ(Jが1ならF800+A−1)",
        "en": "B ← F8, then as BA2XM (F800+A−1 when J is 1)",
    },
    "rom.1251.exbay": {
        "ja": "AからとYからのJ+1バイトを入れ替える",
        "en": "exchange J+1 bytes from A with those from Y",
    },
    "rom.1251.y2dp": {
        "ja": "DPの番地にYからJ+1バイトを書き、前の中身を0C番地からへ",
        "en": "write J+1 bytes from Y at DP, moving the previous contents to 0C",
    },
    "rom.1251.savex": {
        "ja": "XをC6B5・C6B6に置き、AにXの上位",
        "en": "X → C6B5, C6B6, high byte of X → A",
    },
    "rom.1251.loadx": {
        "ja": "Jを1、AにXの上位を入れ、C6B5・C6B6の値をXへ",
        "en": "1 → J, high byte of X → A, then C6B5, C6B6 → X",
    },
    "rom.1251.ba2x": {
        "ja": "AからJ+1バイトをXへ",
        "en": "copy J+1 bytes from A to X",
    },
    "rom.1251.exx1c": {
        "ja": "Xからと内部RAMの1C番地からのJ+1バイトを入れ替える",
        "en": "exchange J+1 bytes from X with those from internal RAM 1C",
    },
    "rom.1251.textxm": {
        "ja": "BをC7にしてBA2XMと同じ(Jが1ならC700+A−1)",
        "en": "C7 → B, then as BA2XM (C700+A−1 when J is 1)",
    },
    "rom.1251.textx": {
        "ja": "BAをC7B0にしてBA2XMと同じ(Jが1ならXがC7AF)",
        "en": "C7B0 → BA, then as BA2XM (X is C7AF when J is 1)",
    },
    "rom.1251.copyb": {
        "ja": "X+1からのBバイトをY+1からへ写す(Bが0なら256バイト)",
        "en": "copy B bytes from X+1 to Y+1 (256 bytes when B is 0)",
    },
    "rom.1251.showram": {
        "ja": "内部RAMの20番地からの字を液晶に出す(BASIC ROM。J_ONE)",
        "en": "show the characters from internal RAM 20 on the LCD (BASIC ROM, J_ONE)",
    },
    "rom.1251.printbuf": {
        "ja": "X+1からの中間コードをPRINTの字にしてC7B0から置く(BASIC ROMの00版。J_ONE)",
        "en": "turn the code from X+1 into PRINT text at C7B0 (BASIC ROM version 00, J_ONE)",
    },
    "rom.1251.noise": {
        "ja": "2msを待ち、Aを右へ回したキャリーをCポートのビット4に出す(PC-1245)",
        "en": "wait 2 ms, rotate A right and put the carry on bit 4 of port C (PC-1245)",
    },
    # ---- ROMのルーチンの働き(PC-1260/1261/1262) ----
    "rom.1261.ba2x": {
        "ja": "AからJ+1バイトをXへ",
        "en": "copy J+1 bytes from A to X",
    },
    "rom.1261.ba2y": {
        "ja": "AからJ+1バイトをYへ",
        "en": "copy J+1 bytes from A to Y",
    },
    "rom.1261.ba2xm": {
        "ja": "AからJ+1バイトをXへ写し、Xから1を引く",
        "en": "copy J+1 bytes from A to X, then subtract 1 from X",
    },
    "rom.1261.ba2ym": {
        "ja": "AからJ+1バイトをYへ写し、Yから1を引く",
        "en": "copy J+1 bytes from A to Y, then subtract 1 from Y",
    },
    "rom.1261.lcdym": {
        "ja": "Bを20にしてBA2YMと同じ(Jが1ならYが2000+A−1)",
        "en": "B ← 20, then as BA2YM (Y = 2000+A−1 when J is 1)",
    },
    "rom.1261.r382x": {
        "ja": "内部RAMの38番地からJ+1バイトをXへ",
        "en": "copy J+1 bytes from internal RAM 38 to X",
    },
    "rom.1261.x2r38": {
        "ja": "XからJ+1バイトを内部RAMの38番地へ",
        "en": "copy J+1 bytes from X to internal RAM 38",
    },
    "rom.1261.r3a2x": {
        "ja": "内部RAMの3A番地からJ+1バイトをXへ",
        "en": "copy J+1 bytes from internal RAM 3A to X",
    },
    "rom.1261.x2r3a": {
        "ja": "XからJ+1バイトを内部RAMの3A番地へ",
        "en": "copy J+1 bytes from X to internal RAM 3A",
    },
    "rom.1261.exxr38": {
        "ja": "Xからと内部RAMの38番地からのJ+1バイトを入れ替える",
        "en": "exchange J+1 bytes from X with those from internal RAM 38",
    },
    "rom.1261.exxr28": {
        "ja": "Xからと内部RAMの28番地からのJ+1バイトを入れ替える",
        "en": "exchange J+1 bytes from X with those from internal RAM 28",
    },
    "rom.1261.dp203d": {
        "ja": "DPを203Dにする",
        "en": "203D → DP",
    },
    "rom.1261.dp662b": {
        "ja": "DPを662Bにする",
        "en": "662B → DP",
    },
    "rom.1261.copyb": {
        "ja": "X+1からのBバイトをY+1からへ写す(Bが0なら256バイト)",
        "en": "copy B bytes from X+1 to Y+1 (256 bytes when B is 0)",
    },
    "rom.1261.set662e": {
        "ja": "BAをFFCEにして、662EからのJ+1バイトと入れ替える",
        "en": "FFCE → BA, then exchange it with J+1 bytes from 662E",
    },
    "rom.1261.mv6619": {
        "ja": "6619からJ+1バイトを内部RAMの0A番地へ写し、661Bからと入れ替える",
        "en": (
            "copy J+1 bytes from 6619 to internal RAM 0A, then exchange them with those from 661B"
        ),
    },
    "rom.1261.fill67b0": {
        "ja": "67B0〜67FFを0Dで埋める",
        "en": "fill 67B0-67FF with 0D",
    },
    "rom.1261.inc66e1": {
        "ja": "66E1からの値に1を足して66E3とYに置き、66D9のビット5を消す",
        "en": "add 1 to the value at 66E1, store it at 66E3 and in Y, clear bit 5 of 66D9",
    },
    "rom.1261.dispoff": {
        "ja": "Cポートを00にして液晶を消す。Aに前の5F番地の値",
        "en": "port C ← 00 (LCD off); previous value of 5F → A",
    },
    "rom.1261.dispon": {
        "ja": "Cポートを01にして液晶をつける。Aに前の5F番地の値",
        "en": "port C ← 01 (LCD on); previous value of 5F → A",
    },
    "rom.1261.glyph": {
        "ja": "Aの文字の形の、終わりの次の番地をXへ(J_ONE)",
        "en": "address just past the glyph of A into X (J_ONE)",
    },
    "rom.1261.cursor": {
        "ja": "66E9が指す液晶の桁に■を描く",
        "en": "draw ■ in the LCD cell that 66E9 points to",
    },
    "rom.1261.keynum": {
        "ja": "キーを1回読む。キャリー1でAにキーの番号",
        "en": "read the keys once; carry 1 with the key number in A",
    },
    "rom.1261.inkey": {
        "ja": "カーソルを点滅させてキーを待ち、Aに文字コード(J_ONE)",
        "en": "blink the cursor and wait for a key; character code in A (J_ONE)",
    },
    "rom.1261.modesw": {
        "ja": "モードスイッチを読む。BがRUNで08、PROで02、RSVで01、OFFで04",
        "en": "read the mode switch; B is 08 for RUN, 02 for PRO, 01 for RSV, 04 for OFF",
    },
    "rom.1261.poweroff": {
        "ja": "ONキーを押していなければ電源を切る",
        "en": "power off unless the ON key is held",
    },
    "rom.1261.b67xm": {
        "ja": "Bを67にしてBA2XMと同じ",
        "en": "B ← 67, then as BA2XM",
    },
    "rom.1261.b67ym": {
        "ja": "Bを67にしてBA2YMと同じ",
        "en": "B ← 67, then as BA2YM",
    },
    "rom.1261.y2rp": {
        "ja": "YからJ+1バイトを、Pの指す内部RAMへ",
        "en": "copy J+1 bytes from Y to the internal RAM at P",
    },
    "rom.1261.r3a2rp": {
        "ja": "内部RAMの3A番地からJ+1バイトを、Pの指す内部RAMへ",
        "en": "copy J+1 bytes from internal RAM 3A to the internal RAM at P",
    },
    "rom.1261.exxr0c": {
        "ja": "Xからと内部RAMの0C番地からのJ+1バイトを入れ替える",
        "en": "exchange J+1 bytes from X with those from internal RAM 0C",
    },
    "rom.1261.exay": {
        "ja": "AからとYからのJ+1バイトを入れ替える",
        "en": "exchange J+1 bytes from A with those from Y",
    },
    "rom.1261.exyrp": {
        "ja": "Yからと、Pの指す内部RAMからのJ+1バイトを入れ替える",
        "en": "exchange J+1 bytes from Y with those at P",
    },
    "rom.1261.yinc2r15": {
        "ja": "DPをYにし、YからJ+1バイトを内部RAMの15番地へ写して1を足す",
        "en": "Y → DP; copy J+1 bytes from Y to internal RAM 15 and add 1",
    },
    "rom.1261.popx": {
        "ja": "呼び出し元の戻り番地をXへ取り出す(呼び出し元のRTNは、もう1つ前へ戻る)",
        "en": "caller's return address → X (the caller's RTN then goes one level further back)",
    },
    "rom.1261.pushx": {
        "ja": "Xを戻り番地の下に積む(J_ONE)",
        "en": "push X under the return address (J_ONE)",
    },
    "rom.1261.suby": {
        "ja": "BAからYを引く(Jが0なら、Yの上位からBを引く)",
        "en": "BA − Y (when J is 0, B is subtracted from the high byte of Y)",
    },
    "rom.1261.ldsuby": {
        "ja": "DPからJ+1バイトをAからへ読んで、SUBYと同じ",
        "en": "read J+1 bytes from DP into A onward, then as SUBY",
    },
    "rom.1261.fill6650": {
        "ja": "6650〜667F(液晶の2行の字)をAで埋める",
        "en": "fill 6650-667F (the two lines of LCD text) with A",
    },
    "rom.1261.ldx66e1": {
        "ja": "66E1からJ+1バイトをXへ",
        "en": "copy J+1 bytes from 66E1 to X",
    },
    "rom.1261.stydp": {
        "ja": "YからJ+1バイトをDPからへ書き、もとの値を内部RAMの0C番地へ",
        "en": "write J+1 bytes from Y at DP; the old values → internal RAM 0C",
    },
    "rom.1261.skipline": {
        "ja": "X+1から0D(行の終わり)を探し、Xをその手前にする",
        "en": "search for 0D (end of line) from X+1; X ← the byte before it",
    },
    "rom.1261.peekba": {
        "ja": "BAの番地のバイトをAへ",
        "en": "byte at address BA → A",
    },
    "rom.1261.set662b": {
        "ja": "662Bのビット1が0なら1にして、SET662Eと同じ",
        "en": "if bit 1 of 662B is 0, set it and do as SET662E",
    },
    "rom.1261.wait2ms": {
        "ja": "2msのタイマの次の刻みまで待つ",
        "en": "wait for the next 2 ms timer tick",
    },
    "rom.1261.glyphx": {
        "ja": "Aの文字が表の何番目かから、Xに5×(番目+1)を足す",
        "en": "add 5 × (table index + 1) for the character in A to X",
    },
    # ---- ROMのルーチンの働き(PC-1350) ----
    "rom.1350.ba2xm": {
        "ja": "AからJ+1バイトをXへ写し、Xから1を引く",
        "en": "copy J+1 bytes from A to X, then subtract 1 from X",
    },
    "rom.1350.ba2ym": {
        "ja": "AからJ+1バイトをYへ写し、Yから1を引く",
        "en": "copy J+1 bytes from A to Y, then subtract 1 from Y",
    },
    "rom.1350.copyb": {
        "ja": "X+1からのBバイトをY+1からへ写す(Bが0なら256バイト)",
        "en": "copy B bytes from X+1 to Y+1 (256 bytes when B is 0)",
    },
    "rom.1350.fill6eb0": {
        "ja": "6EB0〜6EFFを0Dで埋める",
        "en": "fill 6EB0-6EFF with 0D",
    },
    "rom.1350.showtext": {
        "ja": "6D00〜6D5Fの96字を液晶の4行に出す(J_ONE)",
        "en": "show the 96 characters at 6D00-6D5F on the four LCD lines (J_ONE)",
    },
    "rom.1350.keynum": {
        "ja": "キーを1回読む。キャリー1でAにキーの番号",
        "en": "read the keys once; carry 1 with the key number in A",
    },
    "rom.1350.ba2y": {
        "ja": "AからJ+1バイトをYへ",
        "en": "copy J+1 bytes from A to Y",
    },
    "rom.1350.ba2x": {
        "ja": "AからJ+1バイトをXへ",
        "en": "copy J+1 bytes from A to X",
    },
    "rom.1350.swapc": {
        "ja": "AをCポートと5F番地に出し、前に5F番地にあった値をAへ",
        "en": "A → port C and 5F, previous value at 5F → A",
    },
    "rom.1350.wait6ms": {
        "ja": "2msのタイマのフラグを3回待つ",
        "en": "wait for three 2 ms timer ticks",
    },
    "rom.1350.pushx": {
        "ja": "XからJ+1バイトをスタックに積む",
        "en": "push J+1 bytes from X onto the stack",
    },
    "rom.1350.popx": {
        "ja": "PUSHXで積んだJ+1バイトをXに戻す",
        "en": "pop the J+1 bytes pushed by PUSHX back into X",
    },
    "rom.1350.r382x": {
        "ja": "内部RAMの38番地からJ+1バイトをXへ",
        "en": "copy J+1 bytes from internal RAM 38 to X",
    },
    "rom.1350.x2r38": {
        "ja": "XからJ+1バイトを内部RAMの38番地へ",
        "en": "copy J+1 bytes from X to internal RAM 38",
    },
    "rom.1350.copy5r": {
        "ja": "X−1から下へ5バイトをY+1から上へ写し、次の1バイトを0にする",
        "en": "copy 5 bytes downward from X-1 to Y+1 upward, then write 0 to the next byte",
    },
    "rom.1350.eval": {
        "ja": "Xの次からの式を計算し、数を10h〜17hに、文字列を6E60hからに置く",
        "en": "evaluate the expression after X; a number goes to 10h-17h, a string to 6E60h",
    },
    "rom.1350.numchk": {
        "ja": "10h〜17hが数ならキャリーを1、文字列ならZを1にする",
        "en": "set the carry if 10h-17h holds a number, Z if it holds a string",
    },
    "rom.1350.f2i": {
        "ja": "10h〜17hの数を0〜65535の整数にして18h・19hへ",
        "en": "convert the number at 10h-17h to an integer 0-65535 at 18h-19h",
    },
}

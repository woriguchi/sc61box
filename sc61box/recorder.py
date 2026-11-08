"""画面と音を動画(MP4)に録る

1280×720の動画にする。左上に題名を置き、その下は形(SHAPES)で選ぶ。both は上に液晶を拡大して
置き、その下に本体全体を並べる。body は本体全体だけを、lcd は液晶だけを拡大して置く(液晶は
横長なので、動画は液晶に合わせずに1280×720のままにする。Xなどは縦横の比が3:1を超える動画を
受け付けない)。フレームごとに本体の絵(display.Panelの絵、原寸)をffmpegに渡し、切り抜きと
拡大、重ね合わせはffmpegのフィルタで行う。ffmpegはPATHにあるもの、なければimageio-ffmpegの
ものを使う。

音は、鳴らす音とは別に、Cポートの書き換えの記録から作り直す(audio.Buzzer)。
フレームの数は音のサンプルの数に合わせ(1470サンプルで1フレーム)、エミュレータが1フレームで
多めに進んだときは同じ絵を続けて書く。
"""

import os
import queue
import shutil
import subprocess
import threading
import wave

from PIL import Image, ImageDraw, ImageFont

from . import display
from .audio import RATE
from .i18n import tr

W, H = 1280, 720
SHAPES = ("both", "body", "lcd")  # 液晶の拡大と本体、本体だけ、液晶だけ
FPS = 30
SPF = RATE // FPS  # 1フレームぶんのサンプル
BG = (22, 23, 26)
LCD_W = 1240  # 液晶を拡大した幅
LCD_TOP = 78
# PC-1251の本体の絵(display.Panelの絵)の中で、液晶と表示記号を囲む枠
LCD_BOX = (
    display.MARGIN + display.MAT_X - 18,
    display.MARGIN + display.ANN_Y - 8,
    display.MARGIN + display.MAT_X + display.MAT_W + 18,
    display.MARGIN + display.MAT_Y + display.MAT_H + 16,
)
FONTS = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "C:/Windows/Fonts/YuGothB.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def ffmpeg_exe() -> str:
    """使うffmpeg。PATHになければimageio-ffmpegに入っているもの。どちらもなければOSError
    (imageio-ffmpegがffmpegを含むのはWindows、macOS、Linuxのx86_64とaarch64だけ)"""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as e:
        raise OSError(tr("rec.ffmpeg_not_found_install")) from e


def _font(size: int):
    for path in FONTS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size, index=0)
            except OSError:
                continue
    return None


def header_image(path: str, title: str, sub: str) -> None:
    """動画の上の帯(題名と、機種名など)を画像にする(幅W、高さLCD_TOP)"""
    img = Image.new("RGB", (W, LCD_TOP), BG)
    d = ImageDraw.Draw(img)
    big, small = _font(30), _font(18)
    if big is not None and small is not None:
        d.text((40, 22), title, font=big, fill=(235, 235, 230))
        tw = d.textlength(title, font=big)
        d.text((40 + tw + 18, 34), sub, font=small, fill=(150, 152, 158))
    img.save(path)


def layout(lcd_box=LCD_BOX) -> tuple[int, int, int]:
    """形bothの、拡大した液晶の高さ、本体を置く高さの位置、本体の高さ"""
    x0, y0, x1, y1 = lcd_box
    lcd_h = round((y1 - y0) * LCD_W / (x1 - x0) / 2) * 2
    top = LCD_TOP + lcd_h + 14
    body_h = (H - 20 - top) // 2 * 2
    return lcd_h, top, body_h


def _even(v: float) -> int:
    return max(2, round(v / 2) * 2)


def graph(shape: str, size: tuple[int, int], lcd_box=LCD_BOX) -> str:
    """ffmpegのフィルタ。入力0は本体の絵(大きさsize)、入力1は上の帯(題名)の画像。動画の長さは
    入力0で決まる(本体の絵を1枚も渡さずに終えても、ffmpegは待ち続けない)"""
    x0, y0, x1, y1 = lcd_box
    crop = f"crop={x1 - x0}:{y1 - y0}:{x0}:{y0}"
    room = H - 20 - LCD_TOP  # 題名の下に使える高さ
    bg = "0x" + "".join(f"{v:02X}" for v in BG)

    def canvas(x: int | str, y: int) -> str:
        """絵を1280×720の地の(x, y)に置く"""
        return f"pad={W}:{H}:{x}:{y}:color={bg}"

    title = "[1:v]overlay=0:0,format=yuv420p[v]"
    if shape == "both":
        lcd_h, top, body_h = layout(lcd_box)
        return (
            f"[0:v]split[a][b];"
            f"[a]{crop},scale={LCD_W}:{lcd_h}:flags=lanczos[lcd];"
            f"[b]scale=-2:{body_h}:flags=lanczos,{canvas('(ow-iw)/2', top)}[base];"
            f"[base][lcd]overlay={(W - LCD_W) // 2}:{LCD_TOP}[t];"
            f"[t]{title}"
        )
    if shape == "body":
        w, h = size
        scale = min(LCD_W / w, room / h)
        pic_w, pic_h, src = _even(w * scale), _even(h * scale), ""
    elif shape == "lcd":
        pic_w, pic_h = LCD_W, min(room, _even((y1 - y0) * LCD_W / (x1 - x0)))
        src = f"{crop},"
    else:
        raise ValueError(f"unknown shape: {shape}")
    at = canvas((W - pic_w) // 2, LCD_TOP + (room - pic_h) // 2)
    return f"[0:v]{src}scale={pic_w}:{pic_h}:flags=lanczos,{at}[base];[base]{title}"


class Recorder:
    """録画。add()をフレームごとに呼び、close()で動画を仕上げる"""

    def __init__(
        self,
        path: str,
        title: str,
        sub: str,
        size: tuple[int, int] = (display.OUT_W, display.OUT_H),
        lcd_box: tuple[int, int, int, int] = LCD_BOX,
        shape: str = "both",
    ) -> None:
        """sizeは渡す本体の絵の大きさ、lcd_boxはその中で拡大して見せる液晶の範囲、shapeは
        動画の形(SHAPES)"""
        filters = graph(shape, size, lcd_box)  # 形を確かめてから途中のファイルを作る
        self.exe = ffmpeg_exe()  # 途中のファイルを作る前に確かめる
        self.path = path
        self.work = path + ".tmp"
        os.makedirs(self.work, exist_ok=True)
        self.video = os.path.join(self.work, "v.mp4")
        self.audio = os.path.join(self.work, "a.wav")
        header = os.path.join(self.work, "header.png")
        header_image(header, title, sub)
        self.frame_bytes = size[0] * size[1] * 3
        self.proc = subprocess.Popen(
            [
                self.exe, "-y", "-loglevel", "error",
                "-f", "rawvideo", "-pix_fmt", "rgb24",
                "-s", f"{size[0]}x{size[1]}", "-r", str(FPS), "-i", "-",
                "-i", header,
                "-filter_complex", filters, "-map", "[v]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS),
                self.video,
            ],
            stdin=subprocess.PIPE,
        )  # fmt: skip
        self.wav = wave.open(self.audio, "wb")
        self.wav.setnchannels(1)
        self.wav.setsampwidth(2)
        self.wav.setframerate(RATE)
        self.samples = 0
        self.frames = 0  # ffmpegに渡したフレームの数
        self.error = ""
        # パイプへの書き込みでフレームが止まらないよう、別のスレッドで書く
        self.q: queue.Queue[bytes | None] = queue.Queue(maxsize=FPS * 3)
        self.thread = threading.Thread(target=self._write, daemon=True)
        self.thread.start()

    def _write(self) -> None:
        stdin = self.proc.stdin
        assert stdin is not None
        while (frame := self.q.get()) is not None:
            if self.error:
                continue
            try:
                stdin.write(frame)
            except (BrokenPipeError, OSError) as e:
                self.error = str(e) or tr("rec.ffmpeg_stopped")

    @property
    def seconds(self) -> float:
        return self.samples / RATE

    def add(self, picture: bytes, pcm: bytes) -> None:
        """1フレームぶん。pictureは本体の絵(RGB、原寸)、pcmはそのあいだの音(16ビット)"""
        if len(picture) != self.frame_bytes:
            raise ValueError(
                tr("rec.wrong_picture_size_bytes",
                   size=len(picture), want=self.frame_bytes)
            )  # fmt: skip
        self.wav.writeframes(pcm)
        self.samples += len(pcm) // 2
        while self.frames < self.samples // SPF:
            self.q.put(picture)
            self.frames += 1

    def close(self) -> str:
        """録画を終えて動画を仕上げ、できたファイルのパスを返す。失敗したら例外"""
        self.q.put(None)
        self.thread.join()
        assert self.proc.stdin is not None
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        code = self.proc.wait()
        self.wav.close()
        if self.error or code != 0:
            shutil.rmtree(self.work, ignore_errors=True)
            raise OSError(self.error or tr("rec.ffmpeg_exited_code", code=code))
        done = subprocess.run(
            [
                self.exe, "-y", "-loglevel", "error", "-i", self.video, "-i", self.audio,
                "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest",
                "-movflags", "+faststart", self.path,
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )  # fmt: skip
        shutil.rmtree(self.work, ignore_errors=True)
        if done.returncode != 0:
            raise OSError(done.stderr.strip() or tr("rec.could_not_finish_video"))
        return self.path

    def abort(self) -> None:
        """録画をやめて、途中のファイルを消す"""
        self.q.put(None)
        self.thread.join()
        try:
            if self.proc.stdin is not None:
                self.proc.stdin.close()
        except OSError:
            pass
        self.proc.wait()
        self.wav.close()
        shutil.rmtree(self.work, ignore_errors=True)

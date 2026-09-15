"""Reading and writing the Wayland clipboard through wl-clipboard, within limits.

Every read has a deadline, so an application that owns the clipboard and never
answers cannot hang Readily, and a byte ceiling, so a huge copy is refused whole
instead of being saved cut off.
"""
import glob
import hashlib
import os
import selectors
import subprocess
import tempfile
import time
from dataclasses import dataclass

from .config import runtime_dir
from .errors import ReadilyError

IMAGE_TYPES = (("image/png", "png"), ("image/jpeg", "jpg"), ("image/webp", "webp"), ("image/gif", "gif"))
MIME_FOR_EXTENSION = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
                      "gif": "image/gif"}
TEXT_TYPES = ("UTF8_STRING", "STRING", "TEXT")


def _number(name, default):
    try:
        value = float(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def text_limit():
    return int(_number("READILY_MAX_TEXT_BYTES", 256 * 1024))


def image_limit():
    return int(_number("READILY_MAX_IMAGE_BYTES", 20 * 1024 * 1024))


def timeout():
    return _number("READILY_CLIP_TIMEOUT", 2.0)


def human_size(n):
    if n >= 1024 * 1024:
        return f"{n // (1024 * 1024)} MiB"
    if n >= 1024:
        return f"{n // 1024} KiB"
    return f"{n} bytes"


@dataclass
class Clip:
    state: str
    mime: str = ""
    data: bytes = b""
    message: str = ""

    @property
    def extension(self):
        return dict(IMAGE_TYPES).get(self.mime, "")

    @property
    def text(self):
        return self.data.decode("utf-8") if self.state == "text" else ""

    def hash(self):
        return hashlib.sha256(self.state.encode() + b"\0" + self.data).hexdigest()[:16]


def _read(args, cap, seconds):
    """Run a reader: ("ok" | "too-large" | "timeout" | "failed" | "unavailable", bytes)."""
    try:
        proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        return "unavailable", b""
    chunks, size, status = [], 0, "ok"
    deadline = time.monotonic() + seconds
    with selectors.DefaultSelector() as selector:
        selector.register(proc.stdout, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                status = "timeout"
                break
            if not selector.select(remaining):
                continue
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                break
            size += len(chunk)
            if size > cap:
                status = "too-large"
                break
            chunks.append(chunk)
    if status != "ok":
        proc.kill()
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    proc.stdout.close()
    if status == "ok" and proc.returncode != 0:
        status = "failed"
    return status, (b"".join(chunks) if status == "ok" else b"")


def image_bytes_match(extension, data):
    if extension == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in ("jpg", "jpeg"):
        return data.startswith(b"\xff\xd8\xff")
    if extension == "gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if extension == "webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


_TIMEOUT_MESSAGE = "The clipboard did not answer in time"
_EMPTY = "Nothing is copied"


def read_clipboard():
    seconds = timeout()
    status, out = _read(["wl-paste", "--list-types"], 64 * 1024, seconds)
    if status == "unavailable":
        return Clip("unavailable", message="wl-paste is missing; install wl-clipboard")
    if status == "timeout":
        return Clip("timeout", message=_TIMEOUT_MESSAGE)
    types = [t.strip() for t in out.decode("utf-8", "replace").splitlines() if t.strip()]
    if not types:
        return Clip("empty", message=_EMPTY)
    if "x-kde-passwordManagerHint" in types:
        return Clip("sensitive", message="This came from a password manager, so it is not saved")

    for mime, extension in IMAGE_TYPES:
        if mime not in types:
            continue
        status, data = _read(["wl-paste", "--type", mime], image_limit(), seconds)
        if status == "too-large":
            return Clip("too-large", mime, message=f"The copied image is over {human_size(image_limit())}")
        if status == "timeout":
            return Clip("timeout", message=_TIMEOUT_MESSAGE)
        if status != "ok" or not image_bytes_match(extension, data):
            return Clip("invalid", mime, message="The copied image could not be read")
        return Clip("image", mime, data)

    if any(t.startswith("text/") or t in TEXT_TYPES for t in types):
        status, data = _read(["wl-paste", "--no-newline", "--type", "text"], text_limit(), seconds)
        if status == "too-large":
            return Clip("too-large", "text/plain", message=f"The copied text is over {human_size(text_limit())}")
        if status == "timeout":
            return Clip("timeout", message=_TIMEOUT_MESSAGE)
        if status != "ok":
            return Clip("empty", message=_EMPTY)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return Clip("invalid", "text/plain", message="The copied text is not UTF-8")
        if not text.strip():
            return Clip("empty", message=_EMPTY)
        return Clip("text", "text/plain", data)
    return Clip("empty", message=_EMPTY)


def _wl_copy(mime, data):
    try:
        subprocess.run(["wl-copy", "--type", mime], input=data, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=5, check=True)
    except FileNotFoundError:
        raise ReadilyError("wl-copy is missing; install wl-clipboard")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise ReadilyError("Could not copy to the clipboard")


def copy_text(text):
    _wl_copy("text/plain;charset=utf-8", text.encode("utf-8"))


def copy_image(path):
    extension = os.path.splitext(path)[1][1:].lower()
    mime = MIME_FOR_EXTENSION.get(extension)
    try:
        if os.path.getsize(path) > image_limit():
            raise ReadilyError(f"The image is over {human_size(image_limit())}")
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        raise ReadilyError("The image is missing")
    if not mime or not image_bytes_match(extension, data):
        raise ReadilyError("The image file is damaged or not an image")
    _wl_copy(mime, data)


def write_peek_image(clip):
    """A private copy of the clipboard image for the panel's thumbnail.

    The name changes with the content because the panel caches images by path.
    """
    directory = runtime_dir()
    for old in glob.glob(os.path.join(directory, "peek-*")):
        os.unlink(old)
    path = os.path.join(directory, f"peek-{clip.hash()}.{clip.extension}")
    fd, tmp = tempfile.mkstemp(prefix=".peek-", dir=directory)
    with os.fdopen(fd, "wb") as f:
        f.write(clip.data)
    os.replace(tmp, path)
    return path

"""Shared test helpers: a throwaway environment and fake wl-clipboard tools.

Importing this module puts lib/ on sys.path, so tests can import readily.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
READILY = os.path.join(ROOT, "bin", "readily")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


def note(*lines):
    return "\n".join(lines) + "\n"


# The fakes read and write files in $FAKE_CLIP instead of the real clipboard:
#   types            what `wl-paste --list-types` prints (absent = nothing copied)
#   data.text        what `wl-paste --type text` prints
#   data.image_png   what `wl-paste --type image/png` prints (same for other mimes)
#   hang             when present, wl-paste never answers
#   copied.args / copied.data   what wl-copy received
#   opened           the argument xdg-open received
#   edited           the argument omarchy-launch-editor received
FAKE_WL_PASTE = r'''#!/usr/bin/env python3
import os, sys, time
d = os.environ["FAKE_CLIP"]
if os.path.exists(os.path.join(d, "hang")):
    time.sleep(30)
types = os.path.join(d, "types")
if not os.path.exists(types):
    sys.stderr.write("Nothing is copied\n")
    sys.exit(1)
args = sys.argv[1:]
if args == ["--list-types"]:
    sys.stdout.write(open(types).read())
    sys.exit(0)
mime = args[args.index("--type") + 1]
name = "text" if mime == "text" else mime.replace("/", "_")
path = os.path.join(d, "data." + name)
if not os.path.exists(path):
    sys.exit(1)
sys.stdout.buffer.write(open(path, "rb").read())
'''

FAKE_WL_COPY = r'''#!/usr/bin/env python3
import os, sys
d = os.environ["FAKE_CLIP"]
open(os.path.join(d, "copied.args"), "w").write(" ".join(sys.argv[1:]))
open(os.path.join(d, "copied.data"), "wb").write(sys.stdin.buffer.read())
'''

FAKE_XDG_OPEN = r'''#!/usr/bin/env python3
import os, sys
open(os.path.join(os.environ["FAKE_CLIP"], "opened"), "w").write(sys.argv[1])
'''

FAKE_LAUNCH_EDITOR = r'''#!/usr/bin/env python3
import os, sys
open(os.path.join(os.environ["FAKE_CLIP"], "edited"), "w").write(sys.argv[1])
'''


class Sandbox:
    """A temp HOME, XDG config and runtime dirs, a Readily folder and fake tools."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="readily-test-")
        self.home = self._dir("home")
        self.config = self._dir("config")
        self.runtime = self._dir("runtime")
        self.clip = self._dir("clip")
        self.bin = self._dir("bin")
        self.folder = self._dir("home/Readily")
        # omarchy-launch-editor is faked too, so no test ever opens a real editor.
        for name, body in (("wl-paste", FAKE_WL_PASTE), ("wl-copy", FAKE_WL_COPY), ("xdg-open", FAKE_XDG_OPEN),
                           ("omarchy-launch-editor", FAKE_LAUNCH_EDITOR)):
            path = os.path.join(self.bin, name)
            with open(path, "w") as f:
                f.write(body)
            os.chmod(path, 0o755)
        self.env = {
            "HOME": self.home,
            "XDG_CONFIG_HOME": self.config,
            "XDG_RUNTIME_DIR": self.runtime,
            "FAKE_CLIP": self.clip,
            "READILY_DIR": self.folder,
            "PATH": self.bin + os.pathsep + "/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "READILY_CLIP_TIMEOUT": "1",
            # Listed so apply() saves and restore() puts back what a test changes.
            "READILY_MAX_TEXT_BYTES": "",
            "READILY_MAX_IMAGE_BYTES": "",
        }
        self._saved = {}

    def _dir(self, relative):
        path = os.path.join(self.root, relative)
        os.makedirs(path, exist_ok=True)
        return path

    # In-process tests: put the sandbox environment into os.environ.
    def apply(self):
        for key, value in self.env.items():
            self._saved.setdefault(key, os.environ.get(key))
            os.environ[key] = value

    def restore(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._saved = {}

    def cleanup(self):
        self.restore()
        shutil.rmtree(self.root, ignore_errors=True)

    # Files in the Readily folder.
    def write(self, relative, text):
        path = os.path.join(self.folder, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return path

    def write_bytes(self, path, data):
        path = path if os.path.isabs(path) else os.path.join(self.folder, path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def read(self, relative):
        with open(os.path.join(self.folder, relative), encoding="utf-8", newline="") as f:
            return f.read()

    # The fake clipboard.
    def copy_text(self, text, types="text/plain;charset=utf-8\nUTF8_STRING\n"):
        data = text.encode("utf-8") if isinstance(text, str) else text
        self.write_bytes(os.path.join(self.clip, "data.text"), data)
        with open(os.path.join(self.clip, "types"), "w") as f:
            f.write(types)

    def copy_bytes(self, mime, data, extra_types=""):
        self.write_bytes(os.path.join(self.clip, "data." + mime.replace("/", "_")), data)
        with open(os.path.join(self.clip, "types"), "w") as f:
            f.write(mime + "\n" + extra_types)

    def clear_clipboard(self):
        for name in os.listdir(self.clip):
            os.unlink(os.path.join(self.clip, name))

    def copied(self):
        args = os.path.join(self.clip, "copied.args")
        if not os.path.exists(args):
            return None, None
        with open(args) as f, open(os.path.join(self.clip, "copied.data"), "rb") as g:
            return f.read(), g.read()

    # The real command, in a child process with the sandbox environment.
    def run(self, *args, stdin=None, env=None):
        full = dict(self.env)
        full.update(env or {})
        return subprocess.run([sys.executable, READILY, *args], input=stdin, capture_output=True,
                               env=full, timeout=30, text=False)

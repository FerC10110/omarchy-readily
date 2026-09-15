"""Where the Readily folder is, and helping choose it the first time."""
import json
import os
import tempfile

from .errors import USAGE, ReadilyError

EXAMPLE_NOTE = """## Find what is using a port
Replace 8080 with the port you care about.
```
ss -ltnp | grep :8080
```

## Follow a service's log
```
journalctl -fu NAME
```

## Copy a file to another machine
```
scp FILE user@host:/path/
```
"""


def config_home():
    return os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")


def config_path():
    return os.path.join(config_home(), "readily", "config.json")


def expand(path):
    return os.path.normpath(os.path.expanduser(path.strip()))


def runtime_dir():
    base = os.environ.get("XDG_RUNTIME_DIR") or os.path.join(os.path.expanduser("~"), ".cache")
    path = os.path.join(base, "readily")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def write_json_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".readily-", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def resolve_folder():
    """(folder or "", source, error). source is "env", "config" or "none"."""
    raw, source = os.environ.get("READILY_DIR", "").strip(), "env"
    if not raw:
        path = config_path()
        if not os.path.exists(path):
            return "", "none", ""
        source = "config"
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("folder") if isinstance(data, dict) else None
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("it has no folder")
        except (OSError, ValueError) as e:
            return "", source, f"{path} is not valid: {e}"
    folder = expand(raw)
    if not os.path.isabs(folder):
        return "", source, f"The folder must be an absolute path: {raw}"
    return folder, source, ""


def vault_root(folder):
    """The nearest folder, from `folder` up, that holds an Obsidian vault (.obsidian/)."""
    current = os.path.realpath(folder)
    while True:
        if os.path.isdir(os.path.join(current, ".obsidian")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return ""
        current = parent


def registered_vaults():
    """Vaults in Obsidian's own list: the open one first, then the most recent."""
    try:
        with open(os.path.join(config_home(), "obsidian", "obsidian.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    vaults = data.get("vaults") if isinstance(data, dict) else None
    out = []
    for entry in vaults.values() if isinstance(vaults, dict) else []:
        if isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry["path"]:
            ts = entry.get("ts")
            out.append({"path": entry["path"], "ts": ts if isinstance(ts, (int, float)) else 0,
                        "open": entry.get("open") is True})
    out.sort(key=lambda v: (not v["open"], -v["ts"]))
    return out


def suggestions():
    out, seen = [], set()
    for vault in registered_vaults():
        path = os.path.join(vault["path"], "Readily")
        if path not in seen:
            seen.add(path)
            out.append({"path": path, "label": "Obsidian: " + os.path.basename(vault["path"].rstrip("/")),
                        "exists": os.path.isdir(path)})
    home = os.path.join(os.path.expanduser("~"), "Readily")
    if home not in seen:
        out.append({"path": home, "label": "Home folder", "exists": os.path.isdir(home)})
    return out


def _has_sections(folder):
    return any(name.endswith(".md") and not name.startswith(".") for name in os.listdir(folder))


def init_folder(raw_path):
    """Use the folder from now on: create it, add the example if it is empty, remember it."""
    folder = expand(raw_path)
    if not os.path.isabs(folder):
        raise ReadilyError(f"The folder must be an absolute path: {raw_path}", USAGE)
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError as e:
        raise ReadilyError(f"Cannot use {folder}: {e.strerror or e}")
    if not _has_sections(folder):
        try:
            fd = os.open(os.path.join(folder, "commands.md"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            fd = None
        if fd is not None:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(EXAMPLE_NOTE)
    write_json_atomic(config_path(), {"folder": folder})
    return folder

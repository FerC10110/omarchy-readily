"""readily: keep the text and images you reach for in Markdown notes, one note per section."""
import argparse
import json
import os
import subprocess
import sys
from urllib.parse import quote

from .config import init_folder, registered_vaults, resolve_folder, suggestions, vault_root
from .errors import NO_FOLDER, USAGE, ReadilyError
from .store import list_payload, section_names, section_path
from .tags import normalize_tags


def emit(data):
    print(json.dumps(data, ensure_ascii=False))


def require_folder():
    folder, _, error = resolve_folder()
    if error:
        raise ReadilyError(error, NO_FOLDER)
    if not folder:
        raise ReadilyError("No folder chosen yet; run: readily init PATH", NO_FOLDER)
    if not os.path.isdir(folder):
        raise ReadilyError(f"Folder not found: {folder}", NO_FOLDER)
    return folder


def wanted_tags(values):
    try:
        return normalize_tags(values or [])
    except ValueError as e:
        raise ReadilyError(f"Not a valid tag: {e.args[0]}", USAGE)


def launch(target):
    """Hand a path or URL to the desktop, without waiting for the app it opens."""
    try:
        subprocess.Popen(["xdg-open", target], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except FileNotFoundError:
        raise ReadilyError("xdg-open is missing")


def cmd_where(args):
    folder, source, error = resolve_folder()
    exists = bool(folder) and os.path.isdir(folder)
    data = {"folder": folder, "source": source, "exists": exists,
            "vault": vault_root(folder) if exists else "", "error": error}
    if args.json:
        emit(data)
        return 0
    print(f"folder  {folder or '(none)'}")
    print(f"from    {source}")
    if folder and not exists:
        print("state   missing")
    if data["vault"]:
        print(f"vault   {data['vault']}")
    if error:
        print(f"error   {error}")
    return 0


def cmd_vaults(args):
    found = suggestions()
    if args.json:
        emit({"suggestions": found})
        return 0
    for s in found:
        print(f"{s['path']}  ({s['label']}{', exists' if s['exists'] else ''})")
    return 0


def cmd_init(args):
    print(init_folder(args.path))
    return 0


def cmd_list(args):
    tags = wanted_tags(args.tag)
    payload = list_payload(require_folder(), tags)
    if args.json:
        emit(payload)
        return 0
    for section in payload["sections"]:
        if tags and not section["items"]:
            continue
        print(section["name"] + (f"  ⚠ {section['error']}" if section["error"] else ""))
        for item in section["items"]:
            labels = " ".join("#" + t for t in item["tags"] + item["inheritedTags"])
            print(f"  [{item['index']}] {item['title']}" + (f"  {labels}" if labels else ""))
            if item["kind"] == "text":
                body = item["preview"]
            else:
                body = "(missing image)" if item["missing"] else item["image"]
            for line in body.split("\n"):
                print("      " + line)
    return 0


def cmd_tags(args):
    tags = list_payload(require_folder())["tags"]
    if args.json:
        emit({"tags": tags})
        return 0
    for tag in tags:
        print(f"{tag['count']:>4}  #{tag['name']}")
    return 0


def cmd_open(args):
    folder = require_folder()
    if not args.section:
        launch(folder)
        return 0
    if args.section not in section_names(folder):
        raise ReadilyError(f"There is no section named {args.section}")
    path = os.path.realpath(section_path(folder, args.section))
    vault = vault_root(folder)
    known = {os.path.realpath(v["path"]) for v in registered_vaults()}
    launch("obsidian://open?path=" + quote(path, safe="") if vault and vault in known else path)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="readily",
        description="Keep the text and images you reach for in Markdown notes, one note per section.")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = sub.add_parser("where", help="show which folder is used and why")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_where)

    p = sub.add_parser("vaults", help="suggest folders, from Obsidian's vault list")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_vaults)

    p = sub.add_parser("init", help="use PATH as the Readily folder, creating it with an example")
    p.add_argument("path", metavar="PATH")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("list", help="show sections and their items")
    p.add_argument("--json", action="store_true")
    p.add_argument("--tag", action="append", metavar="TAG", help="only items with this tag (repeatable)")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("tags", help="show every tag and how many items have it")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_tags)

    p = sub.add_parser("open", help="open a section in Obsidian (or your editor), or the folder")
    p.add_argument("section", metavar="SECTION", nargs="?")
    p.set_defaults(func=cmd_open)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ReadilyError as e:
        print(f"readily: {e}", file=sys.stderr)
        return e.code
    except KeyboardInterrupt:
        return 130

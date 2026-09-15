"""Sections on disk: listing them, resolving their images, and adding to them."""
import hashlib
import os
import re
from dataclasses import dataclass

from .config import vault_root
from .errors import ReadilyError
from .notes import parse_note
from .tags import tag_matches

MAX_SECTIONS = 200
MAX_NOTE_BYTES = 2 * 1024 * 1024
MAX_SEARCH_FILES = 5000
PREVIEW_LINES = 2
PREVIEW_CHARS = 240
SEARCH_CHARS = 4096
_SECTION_NAME = re.compile(r"[^\W_][\w -]{0,63}")


def valid_section_name(name):
    """Letters (accents too), digits, spaces, - and _; starts with a letter or digit; up to 64."""
    return bool(_SECTION_NAME.fullmatch(name)) and not name.endswith(" ")


def inside(path, root):
    real, base = os.path.realpath(path), os.path.realpath(root)
    return real == base or real.startswith(base.rstrip(os.sep) + os.sep)


def section_path(folder, name):
    return os.path.join(folder, name + ".md")


@dataclass
class Section:
    name: str
    path: str
    error: str = ""
    note: object = None


@dataclass
class Entry:
    item: object
    image: str = ""
    missing: bool = False


def section_names(folder):
    try:
        found = [e.name for e in os.scandir(folder)
                 if e.name.endswith(".md") and len(e.name) > 3 and not e.name.startswith(".") and e.is_file()]
    except OSError as e:
        raise ReadilyError(f"Cannot read {folder}: {e.strerror or e}")
    names = sorted((n[:-3] for n in found), key=lambda n: (n.casefold(), n))
    return names[:MAX_SECTIONS]


def read_section(folder, name):
    section = Section(name, section_path(folder, name))
    if not inside(section.path, folder):
        section.error = f"{name}.md points outside the folder"
        return section
    try:
        if os.path.getsize(section.path) > MAX_NOTE_BYTES:
            section.error = f"{name}.md is larger than 2 MiB"
            return section
        with open(section.path, "rb") as f:
            text = f.read().decode("utf-8")
    except UnicodeDecodeError:
        section.error = f"{name}.md is not UTF-8 text"
        return section
    except OSError as e:
        section.error = f"Cannot read {name}.md: {e.strerror or e}"
        return section
    section.note = parse_note(text)
    return section


def _find_by_name(base, name):
    seen = 0
    for current, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        if name in files:
            return os.path.join(current, name)
        seen += len(files)
        if seen > MAX_SEARCH_FILES:
            break
    return ""


def resolve_image(folder, section, item):
    """(path, missing) for an image item, or None when its link leaves the vault (or the folder)."""
    root = vault_root(folder) or folder
    if item.ref_style == "markdown":
        candidates = [os.path.join(os.path.dirname(section.path), item.ref)]
    elif "/" in item.ref:
        candidates = [os.path.join(root, item.ref), os.path.join(folder, item.ref)]
    else:
        found = _find_by_name(folder, item.ref) or _find_by_name(root, item.ref)
        candidates = [found or os.path.join(folder, item.ref)]
    confined = [os.path.normpath(c) for c in candidates if inside(c, root)]
    if not confined:
        return None
    for candidate in confined:
        if os.path.isfile(candidate):
            return candidate, False
    return confined[0], True


def entries(folder, section):
    """The items Readily shows for a section, in order. Item numbers index this list."""
    out = []
    for item in section.note.items if section.note else []:
        if item.kind == "image":
            resolved = resolve_image(folder, section, item)
            if resolved is None:
                continue
            out.append(Entry(item, resolved[0], resolved[1]))
        else:
            out.append(Entry(item))
    return out


def item_hash(item):
    value = item.content if item.kind == "text" else item.ref
    return hashlib.sha256((item.kind + "\0" + value).encode("utf-8")).hexdigest()[:16]


def _preview(item):
    if item.kind != "text":
        return "", 0
    lines = item.content.split("\n")
    return "\n".join(lines[:PREVIEW_LINES])[:PREVIEW_CHARS], len(lines)


def list_payload(folder, wanted_tags=()):
    counts, sections = {}, []
    for name in section_names(folder):
        section = read_section(folder, name)
        note_tags = section.note.tags if section.note else []
        items = []
        for index, entry in enumerate(entries(folder, section)):
            item = entry.item
            inherited = [t for t in note_tags if t not in item.tags]
            every_tag = item.tags + inherited
            for tag in every_tag:
                counts[tag] = counts.get(tag, 0) + 1
            if not all(any(tag_matches(t, w) for t in every_tag) for w in wanted_tags):
                continue
            preview, line_count = _preview(item)
            items.append({
                "index": index,
                "kind": item.kind,
                "title": item.title,
                "description": item.description,
                "tags": item.tags,
                "inheritedTags": inherited,
                "preview": preview,
                "lineCount": line_count,
                "search": item.content[:SEARCH_CHARS],
                "image": entry.image if item.kind == "image" and not entry.missing else "",
                "missing": entry.missing,
                "hash": item_hash(item),
            })
        sections.append({"name": name, "error": section.error, "tags": note_tags, "items": items})
    tags = [{"name": n, "count": c} for n, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    return {"folder": folder, "tags": tags, "sections": sections}

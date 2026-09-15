"""Reading and writing Readily notes.

A note is a section. Every fenced code block, and every image alone on its
line, is an item. The nearest heading above names it, the loose text between
them describes it, and #tags there (or in the note's frontmatter) label it.
"""
import os
import re
from dataclasses import dataclass, field
from urllib.parse import quote, unquote

from .tags import find_tags, frontmatter_tags, is_tag_line, strip_trailing_tags, unique

TITLE_MAX = 60
TITLE_WRITE_MAX = 120
DESCRIPTION_MAX = 200
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")

_FENCE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
_HEADING = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+(.*?))?[ \t]*$")
_CLOSING_HASHES = re.compile(r"(?:^|[ \t]+)#+[ \t]*$")
_MD_IMAGE = re.compile(r'^\s*!\[[^\]]*\]\(\s*<?([^)>\s]+)>?(?:\s+"[^"]*")?\s*\)\s*$')
_WIKI_IMAGE = re.compile(r"^\s*!\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]\s*$")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


@dataclass
class Item:
    kind: str            # "text" or "image"
    title: str
    description: str
    tags: list
    content: str = ""    # text items: the block, exactly
    ref: str = ""        # image items: the link target as written (decoded)
    ref_style: str = ""  # image items: "markdown" or "wiki"


@dataclass
class Note:
    tags: list = field(default_factory=list)
    items: list = field(default_factory=list)


def truncate(text, limit):
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def first_line(text):
    """The first line with something on it, with runs of spaces collapsed."""
    for line in text.split("\n"):
        if line.strip():
            return " ".join(line.split())
    return ""


def _dedent(line, indent):
    leading = len(line) - len(line.lstrip(" "))
    return line[min(leading, indent):]


def _image_ref(line):
    m = _MD_IMAGE.match(line)
    if m:
        ref, style = unquote(m.group(1)), "markdown"
        if _SCHEME.match(ref):
            return None
    else:
        m = _WIKI_IMAGE.match(line)
        if not m:
            return None
        ref, style = m.group(1).strip(), "wiki"
    if not ref.lower().endswith(IMAGE_EXTENSIONS):
        return None
    return ref, style


def _lines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _frontmatter_end(lines):
    """The index of the first line after the frontmatter, or 0 when there is none."""
    if lines and lines[0].strip() == "---":
        for end in range(1, len(lines)):
            if lines[end].strip() == "---":
                return end + 1
    return 0


def _opening_fence(line):
    """(indent, marker) when the line opens a fenced block, else None.

    A backtick fence whose info string holds a backtick is inline code, not a fence.
    """
    fence = _FENCE.match(line)
    if not fence or (fence.group(2)[0] == "`" and "`" in fence.group(3)):
        return None
    return len(fence.group(1)), fence.group(2)


def _block_end(lines, start, marker):
    """The index of the line closing the block opened at lines[start], or len(lines)."""
    closing = re.compile(r"^ {0,3}" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}[ \t]*$")
    end = start + 1
    while end < len(lines) and not closing.match(lines[end]):
        end += 1
    return end


def parse_note(text):
    lines = _lines(text)
    note = Note()
    i = _frontmatter_end(lines)
    if i:
        note.tags = frontmatter_tags(lines[1:i - 1])

    heading_title, heading_tags = "", []
    description, line_tags = [], []

    def add(kind, fallback_title, **fields):
        nonlocal description, line_tags
        note.items.append(Item(
            kind=kind,
            title=heading_title or truncate(fallback_title, TITLE_MAX),
            description=truncate(" ".join(description), DESCRIPTION_MAX),
            tags=unique(heading_tags + line_tags),
            **fields,
        ))
        description, line_tags = [], []

    while i < len(lines):
        line = lines[i]

        fence = _opening_fence(line)
        if fence:
            indent, marker = fence
            end = _block_end(lines, i, marker)
            content = "\n".join(_dedent(body_line, indent) for body_line in lines[i + 1:end])
            add("text", first_line(content), content=content)
            i = end + 1
            continue

        heading = _HEADING.match(line)
        if heading:
            raw = _CLOSING_HASHES.sub("", heading.group(1) or "")
            heading_tags = find_tags(raw)
            heading_title = strip_trailing_tags(raw)
            description, line_tags = [], []
            i += 1
            continue

        image = _image_ref(line)
        if image:
            ref, style = image
            add("image", os.path.basename(ref), ref=ref, ref_style=style)
            i += 1
            continue

        stripped = line.strip()
        if stripped:
            line_tags = unique(line_tags + find_tags(stripped))
            if not is_tag_line(stripped):
                description.append(stripped)
        i += 1
    return note


def strip_trailing_newlines(text):
    """Drop the line breaks at the end, so pasting a command does not run it."""
    return re.sub(r"[\r\n]+\Z", "", text)


def clean_title(title):
    return " ".join((title or "").split())[:TITLE_WRITE_MAX]


def fence_for(content):
    """Backticks one longer than any run inside the content, and at least three."""
    longest = max((len(run) for run in re.findall(r"`+", content)), default=0)
    return "`" * max(3, longest + 1)


def _heading_lines(title, tags):
    lines = ["## " + title]
    if tags:
        lines.append(" ".join("#" + tag for tag in tags))
    return lines


def render_text_item(title, tags, content):
    fence = fence_for(content)
    return "\n".join(_heading_lines(title, tags) + [fence, content, fence]) + "\n"


def render_image_item(title, tags, relpath):
    return "\n".join(_heading_lines(title, tags) + ["![](" + quote(relpath) + ")"]) + "\n"


def _unclosed_fence(text):
    """(indent, marker) of a block that runs to the end of the text, else None."""
    lines = _lines(text)
    i = _frontmatter_end(lines)
    while i < len(lines):
        fence = _opening_fence(lines[i])
        if fence:
            i = _block_end(lines, i, fence[1])
            if i == len(lines):
                return fence
        i += 1
    return None


def append_block(existing, block):
    """The note with the block added at the end, one blank line after what was there.

    A block left open at the end (Obsidian may have saved mid-typing) gets a
    closing fence like its opener first, so the new item does not end up inside it.
    """
    if not existing:
        return block
    if not existing.endswith("\n"):
        existing += "\n"
    fence = _unclosed_fence(existing)
    if fence:
        indent, marker = fence
        existing += " " * indent + marker + "\n"
    if not existing.endswith("\n\n"):
        existing += "\n"
    return existing + block

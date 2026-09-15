"""Tags the way Obsidian reads them.

A tag is # followed by letters, digits, _, - or /, at the start of a line or
after whitespace, with at least one character that is not a digit or a slash.
Tags compare without case and are shown lowercased. #chi/db is nested under
#chi, so a search for #chi finds it too.
"""
import re

_BODY = r"[\w/-]+"
_IN_TEXT = re.compile(r"(?:^|(?<=\s))#(" + _BODY + ")")
_TOKEN = re.compile(r"#(" + _BODY + ")")


def _clean(body):
    body = re.sub(r"/+", "/", body).strip("/").lower()
    if not body or all(c.isdigit() or c == "/" for c in body):
        return ""
    return body


def unique(values):
    seen, out = set(), []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def find_tags(text):
    """Tags in a line of Markdown text, lowercased, in order, without repeats."""
    return unique(_clean(m.group(1)) for m in _IN_TEXT.finditer(text))


def _is_tag_token(token):
    m = _TOKEN.fullmatch(token)
    return bool(m) and bool(_clean(m.group(1)))


def is_tag_line(line):
    """True when the line holds tags and nothing else."""
    tokens = line.split()
    return bool(tokens) and all(_is_tag_token(t) for t in tokens)


def strip_trailing_tags(text):
    """Heading text without the tags at its end: "Deploy #chi" -> "Deploy"."""
    tokens = text.split()
    while tokens and _is_tag_token(tokens[-1]):
        tokens.pop()
    return " ".join(tokens)


def normalize_tag(value):
    """A tag typed by a person, as Readily writes it: "#Chi Project" -> "chi-project".

    Returns "" when nothing valid is left.
    """
    v = re.sub(r"^#+", "", value.strip()).lower()
    v = re.sub(r"\s+", "-", v)
    v = re.sub(r"[^\w/-]", "", v)
    return _clean(v)


def normalize_tags(values):
    """Normalized tags without repeats. Raises ValueError(value) on the first invalid one."""
    out = []
    for value in values:
        tag = normalize_tag(value)
        if not tag:
            raise ValueError(value)
        out.append(tag)
    return unique(out)


def tag_matches(tag, wanted):
    """#chi matches chi and chi/db, never chimi."""
    tag, wanted = tag.lower(), wanted.lower().strip("/")
    return tag == wanted or tag.startswith(wanted + "/")


def frontmatter_tags(lines):
    """Tags from the `tags` key of YAML frontmatter lines (without the --- lines).

    Accepts `tags: [a, b]`, `tags: a, b` or `tags: a b`, and a block list of
    `- a` lines, each value with or without a leading #.
    """
    values = []
    i = 0
    while i < len(lines):
        m = re.match(r"^tags\s*:\s*(.*?)\s*$", lines[i])
        i += 1
        if not m:
            continue
        rest = m.group(1)
        if rest.startswith("[") and rest.endswith("]"):
            values += rest[1:-1].split(",")
        elif rest:
            values += re.split(r"[,\s]+", rest)
        else:
            while i < len(lines) and re.match(r"^\s*-(\s|$)", lines[i]):
                values.append(re.sub(r"^\s*-\s*", "", lines[i]))
                i += 1
    tags = []
    for value in values:
        value = re.sub(r"^#+", "", value.strip().strip("'\"").strip())
        if re.fullmatch(_BODY, value):
            tags.append(_clean(value))
    return unique(tags)

.pragma library

// Pure view logic for the Readily panel: filtering, tag autocomplete and the
// same validation rules the script applies. No Quickshell, no files, so it is
// tested with Node (tests/model.test.js).

var ALL = ""

var FOLD = {
  "á": "a", "à": "a", "ä": "a", "â": "a", "ã": "a", "å": "a",
  "é": "e", "è": "e", "ë": "e", "ê": "e",
  "í": "i", "ì": "i", "ï": "i", "î": "i",
  "ó": "o", "ò": "o", "ö": "o", "ô": "o", "õ": "o",
  "ú": "u", "ù": "u", "ü": "u", "û": "u",
  "ñ": "n", "ç": "c"
}

function text(value) {
  return value === undefined || value === null ? "" : String(value)
}

function normalize(value) {
  var s = text(value).toLowerCase()
  var out = ""
  for (var i = 0; i < s.length; i++) out += FOLD[s[i]] !== undefined ? FOLD[s[i]] : s[i]
  return out
}

// Characters with no letter case that are not letters or digits: Latin-1
// punctuation and symbols (keeping ª ² ³ ¹ º ¼ ½ ¾), combining marks, general
// punctuation through arrows and symbols, CJK and fullwidth punctuation,
// surrogates and private use (emoji, Nerd Font glyphs). Everything else past
// ASCII counts as a letter, so scripts without case (CJK, Arabic, Hebrew,
// Thai…) work like Python's \w; the script still validates every save.
var NON_WORD = [
  [0x0080, 0x00A9], [0x00AB, 0x00B1], [0x00B4, 0x00B4], [0x00B6, 0x00B8], [0x00BB, 0x00BB],
  [0x00BF, 0x00BF], [0x00D7, 0x00D7], [0x00F7, 0x00F7], [0x0300, 0x036F],
  [0x2000, 0x2BFF], [0x2E00, 0x2E7F], [0x3000, 0x3004], [0x3008, 0x3020],
  [0x3030, 0x3030], [0x303D, 0x303F], [0xD800, 0xF8FF], [0xFE00, 0xFE0F],
  [0xFE30, 0xFE6F], [0xFF00, 0xFF0F], [0xFF1A, 0xFF20], [0xFF3B, 0xFF40],
  [0xFF5B, 0xFF65], [0xFFF0, 0xFFFF]
]

function isLetterOrDigit(c) {
  if (/[A-Za-z0-9]/.test(c)) return true
  var code = c.charCodeAt(0)
  if (code <= 127 || /\s/.test(c)) return false
  if (c.toLowerCase() !== c.toUpperCase()) return true
  for (var i = 0; i < NON_WORD.length; i++)
    if (code >= NON_WORD[i][0] && code <= NON_WORD[i][1]) return false
  return true
}

function normalizeTag(value) {
  var v = text(value).trim().replace(/^#+/, "").toLowerCase().replace(/\s+/g, "-")
  var kept = ""
  for (var i = 0; i < v.length; i++) {
    var c = v[i]
    if (isLetterOrDigit(c) || c === "_" || c === "-" || c === "/") kept += c
  }
  kept = kept.replace(/\/+/g, "/").replace(/^\/+|\/+$/g, "")
  if (kept === "" || /^[0-9\/]+$/.test(kept)) return ""
  return kept
}

function validSectionName(name) {
  var s = text(name)
  if (s.length < 1 || s.length > 64 || !isLetterOrDigit(s[0]) || s[s.length - 1] === " ") return false
  for (var i = 1; i < s.length; i++) {
    var c = s[i]
    if (!(isLetterOrDigit(c) || c === "_" || c === " " || c === "-")) return false
  }
  return true
}

function parseQuery(query) {
  var tokens = text(query).split(/\s+/)
  var result = { tags: [], words: [] }
  for (var i = 0; i < tokens.length; i++) {
    var token = tokens[i]
    if (token === "") continue
    if (token.charAt(0) === "#") {
      var tag = normalizeTag(token)
      if (tag !== "" && result.tags.indexOf(tag) === -1) result.tags.push(tag)
    } else {
      result.words.push(normalize(token))
    }
  }
  return result
}

function tagMatches(tag, wanted) {
  var t = text(tag).toLowerCase()
  var w = text(wanted).toLowerCase().replace(/^\/+|\/+$/g, "")
  return t === w || t.indexOf(w + "/") === 0
}

function filterItems(sections, sectionKey, query) {
  var q = parseQuery(query)
  var rows = []
  var list = sections || []
  for (var s = 0; s < list.length; s++) {
    var section = list[s]
    if (sectionKey !== ALL && section.name !== sectionKey) continue
    var items = section.items || []
    for (var i = 0; i < items.length; i++) {
      var item = items[i]
      var tags = (item.tags || []).concat(item.inheritedTags || [])
      var tagsOk = q.tags.every(function(wanted) {
        return tags.some(function(tag) { return tagMatches(tag, wanted) })
      })
      if (!tagsOk) continue
      var haystack = normalize([item.title, item.description, item.search].join("\n"))
      var wordsOk = q.words.every(function(word) { return haystack.indexOf(word) !== -1 })
      if (wordsOk) rows.push({ section: section.name, item: item })
    }
  }
  return rows
}

function suggestTags(allTags, prefix, exclude, limit) {
  var p = text(prefix).replace(/^#+/, "").toLowerCase()
  var skip = exclude || []
  var max = limit || 8
  var out = []
  var list = allTags || []
  for (var i = 0; i < list.length && out.length < max; i++) {
    var tag = list[i]
    if (tag.name.indexOf(p) === 0 && skip.indexOf(tag.name) === -1) out.push(tag)
  }
  return out
}

function wordAt(value, cursor) {
  var s = text(value)
  var c = Math.max(0, Math.min(Number(cursor) || 0, s.length))
  var start = c
  while (start > 0 && !/\s/.test(s[start - 1])) start--
  var end = c
  while (end < s.length && !/\s/.test(s[end])) end++
  return { start: start, end: end, word: s.slice(start, end) }
}

function completeTag(value, cursor, tag) {
  var s = text(value)
  var w = wordAt(s, cursor)
  var insert = "#" + tag + " "
  return { text: s.slice(0, w.start) + insert + s.slice(w.end).replace(/^\s+/, ""), cursor: w.start + insert.length }
}

function rowPreview(item) {
  if (!item || item.kind !== "text") return { lines: [], more: "" }
  var lines = text(item.preview).split("\n")
  var extra = (Number(item.lineCount) || 0) - lines.length
  return { lines: lines, more: extra > 0 ? "+" + extra + (extra === 1 ? " line" : " lines") : "" }
}

function sectionTabs(sections) {
  var tabs = [{ key: ALL, label: "All", error: false }]
  var list = sections || []
  for (var i = 0; i < list.length; i++) tabs.push({ key: list[i].name, label: list[i].name, error: text(list[i].error) !== "" })
  return tabs
}

function tildePath(path, home) {
  var p = text(path)
  var h = text(home).replace(/\/+$/, "")
  if (h === "") return p
  if (p === h) return "~"
  return p.indexOf(h + "/") === 0 ? "~" + p.slice(h.length) : p
}

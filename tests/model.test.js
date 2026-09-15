const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")

const source = fs.readFileSync(path.join(__dirname, "..", "ReadilyModel.js"), "utf8").replace(/^\.pragma library\s*$/m, "")
const Model = new Function(source + "\nreturn { ALL, normalize, normalizeTag, validSectionName, parseQuery, tagMatches, filterItems, suggestTags, wordAt, completeTag, rowPreview, sectionTabs, tildePath }")()

const item = (fields) => Object.assign({ index: 0, kind: "text", title: "", description: "", tags: [], inheritedTags: [], preview: "", lineCount: 1, search: "", image: "", missing: false, hash: "0" }, fields)
const sections = [
  { name: "commands", error: "", tags: [], items: [
    item({ index: 0, title: "Ver pods", description: "Necesita la VPN", tags: ["chi/db"], search: "kubectl get pods -A" }),
    item({ index: 1, title: "Compose", tags: ["pepe"], lineCount: 4, search: "docker compose up -d" }),
  ] },
  { name: "links", error: "", tags: ["chi"], items: [
    item({ index: 0, title: "Staging", description: "Configuración", inheritedTags: ["chi"], search: "https://staging" }),
  ] },
  { name: "broken", error: "broken.md is not UTF-8 text", tags: [], items: [] },
]
const titles = (rows) => rows.map((r) => r.item.title)

test("normalize folds case and accents", () => {
  assert.equal(Model.normalize("ConfiguraCIÓN Ñandú"), "configuracion nandu")
  assert.equal(Model.normalize(null), "")
})

test("normalizeTag mirrors the script", () => {
  assert.equal(Model.normalizeTag("#Chi Project"), "chi-project")
  assert.equal(Model.normalizeTag("  ##pepe/ "), "pepe")
  assert.equal(Model.normalizeTag("chi//db"), "chi/db")
  assert.equal(Model.normalizeTag("a+b!c"), "abc")
  assert.equal(Model.normalizeTag("Configuración"), "configuración")
  for (const bad of ["", "#", "123", "1/2", "!!!"]) assert.equal(Model.normalizeTag(bad), "", bad)
  assert.equal(Model.normalizeTag("日本語"), "日本語")
  assert.equal(Model.normalizeTag("#→"), "")
  assert.equal(Model.normalizeTag(""), "")
})

test("validSectionName mirrors the script", () => {
  for (const good of ["chi", "Comandos de Pepe", "configuración_2", "a-b", "1st"]) assert.ok(Model.validSectionName(good), good)
  for (const bad of ["", " lead", "trail ", "../x", "a/b", "_x", "-x", "dot.name", "x".repeat(65)]) assert.ok(!Model.validSectionName(bad), bad)
  assert.equal(Model.validSectionName("日本語"), true)
  assert.equal(Model.validSectionName("Hello 日本"), true)
  assert.equal(Model.validSectionName("→ x"), false)
})

test("parseQuery splits tags from words", () => {
  assert.deepEqual(Model.parseQuery("  #Chi kubectl #pepe/ GET "), { tags: ["chi", "pepe"], words: ["kubectl", "get"] })
  assert.deepEqual(Model.parseQuery("# x #123"), { tags: [], words: ["x"] })
  assert.deepEqual(Model.parseQuery("#日本 x").tags, ["日本"])
})

test("tagMatches handles nesting and case", () => {
  assert.ok(Model.tagMatches("chi/db", "CHI"))
  assert.ok(Model.tagMatches("chi", "chi"))
  assert.ok(!Model.tagMatches("chimi", "chi"))
  assert.ok(!Model.tagMatches("chi", "chi/db"))
})

test("All lists every section in order and a section lists its own", () => {
  const rows = Model.filterItems(sections, Model.ALL, "")
  assert.deepEqual(rows.map((r) => r.section + ":" + r.item.title), ["commands:Ver pods", "commands:Compose", "links:Staging"])
  assert.deepEqual(titles(Model.filterItems(sections, "links", "")), ["Staging"])
})

test("tag filters use own and inherited tags, with nesting", () => {
  assert.deepEqual(titles(Model.filterItems(sections, Model.ALL, "#chi")), ["Ver pods", "Staging"])
  assert.deepEqual(titles(Model.filterItems(sections, "commands", "#chi")), ["Ver pods"])
})

test("every tag and word must match", () => {
  assert.deepEqual(titles(Model.filterItems(sections, Model.ALL, "#chi kubectl")), ["Ver pods"])
  assert.deepEqual(titles(Model.filterItems(sections, Model.ALL, "#chi #pepe")), [])
})

test("words search title, description and content without accents", () => {
  assert.deepEqual(titles(Model.filterItems(sections, Model.ALL, "configuracion")), ["Staging"])
  assert.deepEqual(titles(Model.filterItems(sections, Model.ALL, "COMPOSE UP")), ["Compose"])
  assert.deepEqual(titles(Model.filterItems(sections, Model.ALL, "zzz")), [])
})

test("suggestTags filters by prefix, skips chosen tags and stops at the limit", () => {
  const all = [{ name: "chi", count: 5 }, { name: "chi/db", count: 2 }, { name: "pepe", count: 1 }]
  assert.deepEqual(Model.suggestTags(all, "#CH", ["chi"], 8), [{ name: "chi/db", count: 2 }])
  assert.deepEqual(Model.suggestTags(all, "", [], 2), [{ name: "chi", count: 5 }, { name: "chi/db", count: 2 }])
  assert.deepEqual(Model.suggestTags(all, "#", [], 8).length, 3)
})

test("wordAt and completeTag work on the word under the cursor", () => {
  assert.deepEqual(Model.wordAt("kubectl #ch get", 11), { start: 8, end: 11, word: "#ch" })
  assert.deepEqual(Model.completeTag("kubectl #ch get", 11, "chi"), { text: "kubectl #chi get", cursor: 13 })
  assert.deepEqual(Model.completeTag("#p", 2, "pepe"), { text: "#pepe ", cursor: 6 })
})

test("rowPreview gives the first lines and how many more", () => {
  assert.deepEqual(Model.rowPreview({ kind: "text", preview: "a\nb", lineCount: 4 }), { lines: ["a", "b"], more: "+2 lines" })
  assert.deepEqual(Model.rowPreview({ kind: "text", preview: "a\nb", lineCount: 3 }), { lines: ["a", "b"], more: "+1 line" })
  assert.deepEqual(Model.rowPreview({ kind: "text", preview: "a", lineCount: 1 }), { lines: ["a"], more: "" })
  assert.deepEqual(Model.rowPreview({ kind: "image", preview: "", lineCount: 0 }), { lines: [], more: "" })
})

test("sectionTabs puts All first and marks broken sections", () => {
  assert.deepEqual(Model.sectionTabs(sections), [
    { key: "", label: "All", error: false },
    { key: "commands", label: "commands", error: false },
    { key: "links", label: "links", error: false },
    { key: "broken", label: "broken", error: true },
  ])
})

test("tildePath shortens paths under home", () => {
  assert.equal(Model.tildePath("/home/u/Vault/Readily", "/home/u"), "~/Vault/Readily")
  assert.equal(Model.tildePath("/home/user2/x", "/home/u"), "/home/user2/x")
  assert.equal(Model.tildePath("/home/u", "/home/u"), "~")
})

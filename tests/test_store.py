import os
import unittest
from unittest import mock

import support
from support import note
from readily import store
from readily.store import list_payload, section_names


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.box = support.Sandbox()
        self.box.apply()
        self.folder = self.box.folder

    def tearDown(self):
        self.box.cleanup()

    def items(self, section=0, **kw):
        return list_payload(self.folder, **kw)["sections"][section]["items"]


class Listing(StoreTest):
    def test_sections_are_md_files_sorted_without_hidden_or_nested(self):
        for rel in ("b.md", "A.md", ".hidden.md", "sub/c.md", "notes.txt"):
            self.box.write(rel, "")
        self.assertEqual(section_names(self.folder), ["A", "b"])

    def test_payload_items_tags_and_counts(self):
        self.box.write("commands.md", note("---", "tags: [chi]", "---", "## Pods", "#k8s #chi", "Needs VPN.",
                                           "```", "kubectl get pods -A", "a", "b", "```"))
        self.box.write("links.md", note("## Staging #chi/db", "```", "https://staging", "```"))
        payload = list_payload(self.folder)
        commands, links = payload["sections"]
        item = commands["items"][0]
        self.assertEqual({k: item[k] for k in ("index", "kind", "title", "description", "tags", "inheritedTags",
                                               "preview", "lineCount", "search", "image", "missing")},
                         {"index": 0, "kind": "text", "title": "Pods", "description": "Needs VPN.",
                          "tags": ["k8s", "chi"], "inheritedTags": [], "preview": "kubectl get pods -A\na",
                          "lineCount": 3, "search": "kubectl get pods -A\na\nb", "image": "", "missing": False})
        self.assertRegex(item["hash"], r"^[0-9a-f]{16}$")
        self.assertEqual((commands["tags"], commands["error"]), (["chi"], ""))
        self.assertEqual(payload["tags"], [{"name": "chi", "count": 1}, {"name": "chi/db", "count": 1},
                                           {"name": "k8s", "count": 1}])
        self.assertEqual(payload["folder"], self.folder)

    def test_inherited_tags_and_tag_filter_keep_item_numbers(self):
        self.box.write("commands.md", note("## Other", "```", "ls", "```", "## Pods", "#chi/db", "```", "kubectl", "```"))
        self.box.write("links.md", note("---", "tags: [chi]", "---", "## Staging", "```", "https://staging", "```"))
        payload = list_payload(self.folder, ["chi"])
        commands, links = payload["sections"]
        self.assertEqual([(i["index"], i["title"]) for i in commands["items"]], [(1, "Pods")])
        self.assertEqual([(i["title"], i["inheritedTags"]) for i in links["items"]], [("Staging", ["chi"])])
        self.assertEqual({t["name"]: t["count"] for t in payload["tags"]}, {"chi/db": 1, "chi": 1})

    def test_same_hash_for_same_content(self):
        self.box.write("a.md", note("## One", "```", "same", "```", "## Two", "```", "same", "```", "```", "other", "```"))
        hashes = [i["hash"] for i in self.items()]
        self.assertEqual(hashes[0], hashes[1])
        self.assertNotEqual(hashes[0], hashes[2])

    def test_bad_notes_report_errors_without_breaking_others(self):
        self.box.write("good.md", note("```", "ok", "```"))
        self.box.write_bytes("latin1.md", b"\xff\xfe bad")
        outside = self.box.write_bytes(os.path.join(self.box.root, "outside.md"), b"```\nx\n```\n")
        os.symlink(outside, os.path.join(self.folder, "link.md"))
        errors = {s["name"]: s["error"] for s in list_payload(self.folder)["sections"]}
        self.assertEqual(errors["good"], "")
        self.assertIn("not UTF-8", errors["latin1"])
        self.assertIn("outside the folder", errors["link"])

    def test_large_note_is_an_error(self):
        self.box.write("big.md", "x" * 20)
        with mock.patch.object(store, "MAX_NOTE_BYTES", 10):
            [section] = list_payload(self.folder)["sections"]
        self.assertIn("larger than", section["error"])
        self.assertEqual(section["items"], [])

    def test_section_count_is_capped(self):
        for n in range(5):
            self.box.write(f"s{n}.md", "")
        with mock.patch.object(store, "MAX_SECTIONS", 3):
            self.assertEqual(section_names(self.folder), ["s0", "s1", "s2"])


class Images(StoreTest):
    def test_markdown_image_relative_to_the_note(self):
        png = self.box.write_bytes("attachments/chi-1.png", support.PNG)
        self.box.write("shots.md", note("## Map", "![](attachments/chi-1.png)"))
        [item] = self.items()
        self.assertEqual((item["kind"], item["title"], os.path.realpath(item["image"]), item["missing"], item["search"]),
                         ("image", "Map", os.path.realpath(png), False, ""))

    def test_wiki_image_found_by_name_in_the_vault(self):
        vault = self.box.home
        os.makedirs(os.path.join(vault, ".obsidian"))
        png = self.box.write_bytes(os.path.join(vault, "assets", "Pasted image.png"), support.PNG)
        self.box.write("shots.md", note("![[Pasted image.png]]"))
        [item] = self.items()
        self.assertEqual(os.path.realpath(item["image"]), os.path.realpath(png))

    def test_missing_image_is_marked(self):
        self.box.write("shots.md", note("![](attachments/gone.png)", "![[also gone.png]]"))
        self.assertEqual([(i["image"], i["missing"]) for i in self.items()], [("", True), ("", True)])

    def test_links_leaving_the_folder_are_ignored(self):
        self.box.write_bytes(os.path.join(self.box.root, "secret.png"), support.PNG)
        self.box.write("shots.md", note("![](../../secret.png)", "![[../secret.png]]", "![](/etc/x.png)"))
        self.assertEqual(self.items(), [])


if __name__ == "__main__":
    unittest.main()

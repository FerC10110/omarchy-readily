import datetime
import os
import unittest
from unittest import mock

import support
from support import note
from readily import store
from readily.errors import ReadilyError
from readily.store import append_to_section, list_payload, section_names, valid_section_name, write_attachment


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


class Appending(StoreTest):
    def test_append_keeps_existing_content_and_mode(self):
        path = self.box.write("commands.md", "# My commands\nintro")
        os.chmod(path, 0o640)
        append_to_section(self.folder, "commands", "## B\n```\nb\n```\n")
        self.assertEqual(self.box.read("commands.md"), "# My commands\nintro\n\n## B\n```\nb\n```\n")
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o640)
        self.assertEqual([n for n in os.listdir(self.folder) if n.startswith(".readily-")], [])

    def test_missing_section_needs_create(self):
        with self.assertRaises(ReadilyError) as caught:
            append_to_section(self.folder, "chi", "x\n")
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("--create", str(caught.exception))
        append_to_section(self.folder, "chi", "## A\n```\na\n```\n", create=True)
        self.assertEqual(self.box.read("chi.md"), "## A\n```\na\n```\n")
        self.assertEqual(os.stat(os.path.join(self.folder, "chi.md")).st_mode & 0o777, 0o644)

    def test_create_on_an_existing_section_uses_it(self):
        self.box.write("chi.md", "start\n")
        append_to_section(self.folder, "chi", "x\n", create=True)
        self.assertEqual(self.box.read("chi.md"), "start\n\nx\n")

    def test_section_names_are_validated(self):
        for bad in ("", " lead", "trail ", "../x", "a/b", "_x", "-x", "dot.name", "x" * 65):
            with self.assertRaises(ReadilyError, msg=bad) as caught:
                append_to_section(self.folder, bad, "x\n", create=True)
            self.assertEqual(caught.exception.code, 2, bad)
        for good in ("chi", "Comandos de Pepe", "configuración_2", "a-b", "1st"):
            self.assertTrue(valid_section_name(good), good)

    def test_links_are_not_written_through(self):
        target = self.box.write_bytes(os.path.join(self.box.root, "elsewhere.md"), b"")
        os.symlink(target, os.path.join(self.folder, "linked.md"))
        with self.assertRaises(ReadilyError) as caught:
            append_to_section(self.folder, "linked", "x\n")
        self.assertIn("is a link", str(caught.exception))

    def test_a_note_that_keeps_changing_is_given_up(self):
        self.box.write("busy.md", "start\n")
        real_stamp = store._stamp
        calls = {"n": 0}

        def moving(path):
            calls["n"] += 1
            stamp = real_stamp(path)
            return (stamp[0] + calls["n"],) + stamp[1:] if stamp else stamp

        with mock.patch.object(store, "_stamp", side_effect=moving):
            with self.assertRaises(ReadilyError) as caught:
                append_to_section(self.folder, "busy", "x\n")
        self.assertIn("keeps changing", str(caught.exception))
        self.assertEqual(self.box.read("busy.md"), "start\n")
        self.assertEqual([n for n in os.listdir(self.folder) if n.startswith(".readily-")], [])

    def test_non_utf8_note_is_refused(self):
        self.box.write_bytes("bad.md", b"\xff")
        with self.assertRaises(ReadilyError) as caught:
            append_to_section(self.folder, "bad", "x\n")
        self.assertIn("not UTF-8", str(caught.exception))


class Attachments(StoreTest):
    def test_attachment_names_do_not_collide(self):
        when = datetime.datetime(2026, 9, 14, 18, 30, 5)
        first = write_attachment(self.folder, "Chi Links", support.PNG, "png", when)
        second = write_attachment(self.folder, "Chi Links", support.PNG, "png", when)
        self.assertEqual((first, second), ("attachments/chi-links-20260914-183005.png",
                                           "attachments/chi-links-20260914-183005-2.png"))
        with open(os.path.join(self.folder, first), "rb") as f:
            self.assertEqual(f.read(), support.PNG)


if __name__ == "__main__":
    unittest.main()

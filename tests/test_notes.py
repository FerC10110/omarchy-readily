import unittest

from support import note
from readily.notes import (append_block, clean_title, fence_for, parse_note, render_image_item,
                           render_text_item, strip_trailing_newlines)


class Reading(unittest.TestCase):
    def test_heading_description_and_block(self):
        parsed = parse_note(note("## Find a port", "Replace 8080.", "```", "ss -ltnp | grep :8080", "```"))
        [item] = parsed.items
        self.assertEqual((item.kind, item.title, item.description, item.content),
                         ("text", "Find a port", "Replace 8080.", "ss -ltnp | grep :8080"))

    def test_title_falls_back_to_first_line(self):
        [item] = parse_note(note("```", "", "  docker compose   up -d  ", "```")).items
        self.assertEqual(item.title, "docker compose up -d")

    def test_long_first_line_is_cut(self):
        [item] = parse_note(note("```", "x" * 100, "```")).items
        self.assertEqual(len(item.title), 60)
        self.assertTrue(item.title.endswith("…"))

    def test_tildes_info_string_and_longer_fences(self):
        text = note("## A", "~~~bash", "echo ```", "~~~", "## B", "````", "```", "inner", "```", "````")
        self.assertEqual([i.content for i in parse_note(text).items], ["echo ```", "```\ninner\n```"])

    def test_hashes_inside_blocks_are_not_headings_or_tags(self):
        [item] = parse_note(note("## Real", "```", "# comment #notatag", "## not a heading", "```")).items
        self.assertEqual((item.title, item.tags), ("Real", []))
        self.assertEqual(item.content, "# comment #notatag\n## not a heading")

    def test_unclosed_block_runs_to_the_end(self):
        [item] = parse_note("## A\n```\nline one\nline two").items
        self.assertEqual(item.content, "line one\nline two")

    def test_frontmatter_is_skipped_and_crlf_is_read(self):
        parsed = parse_note("---\r\ntitle: x\r\n---\r\n## A\r\n```\r\nls\r\n```\r\n")
        self.assertEqual([(i.title, i.content) for i in parsed.items], [("A", "ls")])

    def test_indented_fence_strips_its_indent(self):
        [item] = parse_note(note("  ```", "  a", "    b", "c", "  ```")).items
        self.assertEqual(item.content, "a\n  b\nc")

    def test_blocks_under_one_heading_share_it(self):
        items = parse_note(note("## Group #chi", "first", "```", "one", "```", "second #k8s", "```", "two", "```")).items
        self.assertEqual([(i.title, i.description, i.tags) for i in items],
                         [("Group", "first", ["chi"]), ("Group", "second #k8s", ["chi", "k8s"])])

    def test_closing_hashes_are_removed_from_titles(self):
        [item] = parse_note(note("### Title ###", "```", "x", "```")).items
        self.assertEqual(item.title, "Title")

    def test_text_that_is_not_a_block_is_ignored(self):
        self.assertEqual(parse_note(note("## Notes", "just text", "- a list", "Run `ls` here")).items, [])


class ReadingTags(unittest.TestCase):
    def test_tag_line_is_not_description(self):
        [item] = parse_note(note("## Pods", "#chi #kubernetes", "Needs the VPN.", "```", "kubectl get pods -A", "```")).items
        self.assertEqual((item.tags, item.description), (["chi", "kubernetes"], "Needs the VPN."))

    def test_tag_in_a_sentence_counts_and_stays(self):
        [item] = parse_note(note("## A", "Use in #chi only", "```", "x", "```")).items
        self.assertEqual((item.tags, item.description), (["chi"], "Use in #chi only"))

    def test_heading_tags_leave_the_title(self):
        [item] = parse_note(note("## Pods #chi #k8s", "```", "x", "```")).items
        self.assertEqual((item.title, item.tags), ("Pods", ["chi", "k8s"]))

    def test_frontmatter_tags_belong_to_the_note(self):
        parsed = parse_note(note("---", "tags: [chi]", "---", "## A", "#k8s", "```", "x", "```"))
        self.assertEqual((parsed.tags, parsed.items[0].tags), (["chi"], ["k8s"]))

    def test_description_and_line_tags_reset_after_each_item(self):
        items = parse_note(note("#chi", "```", "one", "```", "```", "two", "```")).items
        self.assertEqual([i.tags for i in items], [["chi"], []])


class ReadingImages(unittest.TestCase):
    def test_markdown_and_wiki_images(self):
        text = note("## Map", '![office](attachments/map%20v2.png "t")', "## Shot", "![[Pasted image 1.PNG|300]]")
        self.assertEqual([(i.kind, i.title, i.ref, i.ref_style) for i in parse_note(text).items],
                         [("image", "Map", "attachments/map v2.png", "markdown"),
                          ("image", "Shot", "Pasted image 1.PNG", "wiki")])

    def test_remote_and_non_image_links_are_ignored(self):
        self.assertEqual(parse_note(note("![x](https://site/x.png)", "![[notes.md]]", "![x](file.txt)")).items, [])

    def test_image_without_heading_takes_its_file_name(self):
        [item] = parse_note(note("![](attachments/chi-1.png)")).items
        self.assertEqual(item.title, "chi-1.png")


class Writing(unittest.TestCase):
    def test_text_item_layout(self):
        self.assertEqual(render_text_item("Pods", ["chi", "k8s"], "kubectl get pods"),
                         "## Pods\n#chi #k8s\n```\nkubectl get pods\n```\n")

    def test_no_tag_line_without_tags(self):
        self.assertEqual(render_text_item("Pods", [], "x"), "## Pods\n```\nx\n```\n")

    def test_fence_grows_past_backticks_in_content(self):
        self.assertEqual(fence_for("a ``` b"), "````")
        self.assertEqual(fence_for("plain"), "```")

    def test_image_item_layout(self):
        self.assertEqual(render_image_item("Map", ["chi"], "attachments/chi-1.png"),
                         "## Map\n#chi\n![](attachments/chi-1.png)\n")

    def test_append_keeps_one_blank_line(self):
        block = "## B\n```\nb\n```\n"
        self.assertEqual(append_block("", block), block)
        self.assertEqual(append_block("x", block), "x\n\n" + block)
        self.assertEqual(append_block("x\n", block), "x\n\n" + block)
        self.assertEqual(append_block("x\n\n", block), "x\n\n" + block)

    def test_titles_and_trailing_newlines(self):
        self.assertEqual(clean_title("  two\nlines\t here "), "two lines here")
        self.assertEqual(len(clean_title("y" * 300)), 120)
        self.assertEqual(clean_title(None), "")
        self.assertEqual(strip_trailing_newlines("ls -la\n\r\n"), "ls -la")
        self.assertEqual(strip_trailing_newlines("keep  \n"), "keep  ")


class RoundTrip(unittest.TestCase):
    SAMPLES = [
        "kubectl get pods -A",
        "echo 'año ñandú 🚀'",
        "line one\n\n\tindented with a tab\ntrailing spaces   ",
        "```\nnested block\n```",
        "~~~\ntilde lines\n~~~",
        "    four leading spaces\n# not a heading\n#notatag",
        "a ```` b ` c",
    ]

    def test_what_is_written_reads_back_the_same(self):
        text = ""
        for n, sample in enumerate(self.SAMPLES):
            text = append_block(text, render_text_item(f"Sample {n}", ["t"], sample))
        items = parse_note(text).items
        self.assertEqual([i.content for i in items], self.SAMPLES)
        self.assertEqual([i.title for i in items], [f"Sample {n}" for n in range(len(self.SAMPLES))])
        self.assertEqual([i.tags for i in items], [["t"]] * len(self.SAMPLES))


if __name__ == "__main__":
    unittest.main()

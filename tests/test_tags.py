import unittest

import support  # noqa: F401  (puts lib/ on sys.path)
from readily.tags import (find_tags, frontmatter_tags, is_tag_line, normalize_tag, normalize_tags,
                          strip_trailing_tags, tag_matches)


class FindTags(unittest.TestCase):
    def test_tags_at_line_start_and_after_spaces(self):
        self.assertEqual(find_tags("#chi uses #kubernetes"), ["chi", "kubernetes"])

    def test_numbers_only_are_not_tags(self):
        self.assertEqual(find_tags("issue #123 and #1984/5"), [])

    def test_url_anchor_is_not_a_tag(self):
        self.assertEqual(find_tags("see https://x.com/page#anchor"), [])

    def test_hex_colour_is_a_tag_like_in_obsidian(self):
        self.assertEqual(find_tags("colour #fff"), ["fff"])

    def test_accents_nested_and_case(self):
        self.assertEqual(find_tags("#Configuración #chi/DB"), ["configuración", "chi/db"])

    def test_punctuation_ends_a_tag_and_repeats_are_dropped(self):
        self.assertEqual(find_tags("#chi, #chi. (#pepe)"), ["chi"])


class TagLines(unittest.TestCase):
    def test_line_of_only_tags(self):
        self.assertTrue(is_tag_line("#chi  #kubernetes"))

    def test_sentence_with_a_tag_is_not_a_tag_line(self):
        self.assertFalse(is_tag_line("use in #chi"))

    def test_number_token_is_not_a_tag_line(self):
        self.assertFalse(is_tag_line("#chi #123"))

    def test_strip_trailing_tags_from_heading(self):
        self.assertEqual(strip_trailing_tags("Deploy #chi to prod #k8s #chi/db"), "Deploy #chi to prod")
        self.assertEqual(strip_trailing_tags("Issue #123"), "Issue #123")


class Normalize(unittest.TestCase):
    def test_typed_tags_are_normalized(self):
        self.assertEqual(normalize_tag("#Chi Project"), "chi-project")
        self.assertEqual(normalize_tag("  ##pepe/ "), "pepe")
        self.assertEqual(normalize_tag("chi//db"), "chi/db")
        self.assertEqual(normalize_tag("a+b!c"), "abc")
        self.assertEqual(normalize_tag("Configuración"), "configuración")

    def test_invalid_values_become_empty(self):
        for value in ("", "#", "123", "1/2", "!!!"):
            self.assertEqual(normalize_tag(value), "", value)

    def test_normalize_tags_drops_repeats_and_rejects_invalid(self):
        self.assertEqual(normalize_tags(["Chi", "#chi", "k8s"]), ["chi", "k8s"])
        with self.assertRaises(ValueError) as caught:
            normalize_tags(["chi", "123"])
        self.assertEqual(caught.exception.args[0], "123")


class Matching(unittest.TestCase):
    def test_nested_and_case_insensitive(self):
        self.assertTrue(tag_matches("chi", "chi"))
        self.assertTrue(tag_matches("chi/db", "CHI"))
        self.assertFalse(tag_matches("chimi", "chi"))
        self.assertFalse(tag_matches("chi", "chi/db"))


class Frontmatter(unittest.TestCase):
    def test_inline_list(self):
        self.assertEqual(frontmatter_tags(["title: x", "tags: [chi, '#K8s']"]), ["chi", "k8s"])

    def test_plain_string(self):
        self.assertEqual(frontmatter_tags(["tags: chi, pepe docker"]), ["chi", "pepe", "docker"])

    def test_block_list(self):
        self.assertEqual(frontmatter_tags(["tags:", "  - chi", '  - "#pepe/db"', "other: 1"]), ["chi", "pepe/db"])

    def test_invalid_values_are_skipped(self):
        self.assertEqual(frontmatter_tags(["tags: [123, ok tag, fine]"]), ["fine"])


if __name__ == "__main__":
    unittest.main()

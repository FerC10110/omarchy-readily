import os
import time
import unittest

import support
from readily import clipboard
from readily.errors import ReadilyError


class ClipTest(unittest.TestCase):
    def setUp(self):
        self.box = support.Sandbox()
        self.box.apply()

    def tearDown(self):
        self.box.cleanup()


class Reading(ClipTest):
    def test_text(self):
        self.box.copy_text("ls -la\n")
        clip = clipboard.read_clipboard()
        self.assertEqual((clip.state, clip.mime, clip.text), ("text", "text/plain", "ls -la\n"))

    def test_nothing_copied(self):
        clip = clipboard.read_clipboard()
        self.assertEqual((clip.state, clip.message), ("empty", "Nothing is copied"))

    def test_whitespace_only_is_empty(self):
        self.box.copy_text(" \n\t\n")
        self.assertEqual(clipboard.read_clipboard().state, "empty")

    def test_password_manager_content_is_sensitive(self):
        self.box.copy_text("hunter2", types="text/plain\nx-kde-passwordManagerHint\n")
        clip = clipboard.read_clipboard()
        self.assertEqual((clip.state, clip.data), ("sensitive", b""))

    def test_image_wins_over_text(self):
        self.box.copy_text("fallback")
        self.box.copy_bytes("image/png", support.PNG, extra_types="text/plain\n")
        clip = clipboard.read_clipboard()
        self.assertEqual((clip.state, clip.mime, clip.extension, clip.data), ("image", "image/png", "png", support.PNG))

    def test_damaged_image_is_invalid(self):
        self.box.copy_bytes("image/png", b"not a png")
        self.assertEqual(clipboard.read_clipboard().state, "invalid")

    def test_text_over_the_limit_is_dropped_whole(self):
        os.environ["READILY_MAX_TEXT_BYTES"] = "8"
        self.box.copy_text("123456789")
        clip = clipboard.read_clipboard()
        self.assertEqual((clip.state, clip.data), ("too-large", b""))
        self.assertIn("8 bytes", clip.message)

    def test_image_over_the_limit_is_dropped(self):
        os.environ["READILY_MAX_IMAGE_BYTES"] = "10"
        self.box.copy_bytes("image/png", support.PNG)
        self.assertEqual(clipboard.read_clipboard().state, "too-large")

    def test_non_utf8_text_is_invalid(self):
        self.box.copy_text(b"\xff\xfe")
        self.assertEqual(clipboard.read_clipboard().state, "invalid")

    def test_no_answer_is_a_timeout(self):
        os.environ["READILY_CLIP_TIMEOUT"] = "0.3"
        self.box.copy_text("x")
        open(os.path.join(self.box.clip, "hang"), "w").close()
        started = time.monotonic()
        self.assertEqual(clipboard.read_clipboard().state, "timeout")
        self.assertLess(time.monotonic() - started, 3)

    def test_missing_wl_paste_is_unavailable(self):
        os.environ["PATH"] = self.box.runtime
        self.assertEqual(clipboard.read_clipboard().state, "unavailable")

    def test_hash_follows_content(self):
        self.box.copy_text("one")
        first = clipboard.read_clipboard().hash()
        self.assertEqual(first, clipboard.read_clipboard().hash())
        self.box.copy_text("two")
        self.assertNotEqual(first, clipboard.read_clipboard().hash())
        self.assertRegex(first, r"^[0-9a-f]{16}$")


class Writing(ClipTest):
    def test_copy_text_goes_through_stdin(self):
        clipboard.copy_text("año")
        self.assertEqual(self.box.copied(), ("--type text/plain;charset=utf-8", "año".encode("utf-8")))

    def test_copy_image_checks_the_file(self):
        good = self.box.write_bytes("a.png", support.PNG)
        clipboard.copy_image(good)
        self.assertEqual(self.box.copied(), ("--type image/png", support.PNG))
        bad = self.box.write_bytes("b.png", b"nope")
        with self.assertRaises(ReadilyError):
            clipboard.copy_image(bad)
        with self.assertRaises(ReadilyError):
            clipboard.copy_image(os.path.join(self.box.folder, "gone.png"))

    def test_missing_wl_copy(self):
        os.environ["PATH"] = self.box.runtime
        with self.assertRaises(ReadilyError) as caught:
            clipboard.copy_text("x")
        self.assertIn("wl-copy", str(caught.exception))

    def test_peek_image_file_is_replaced(self):
        first = clipboard.write_peek_image(clipboard.Clip("image", "image/png", support.PNG))
        second = clipboard.write_peek_image(clipboard.Clip("image", "image/png", support.PNG + b"\x01"))
        self.assertNotEqual(first, second)
        self.assertFalse(os.path.exists(first))
        with open(second, "rb") as f:
            self.assertEqual(f.read(), support.PNG + b"\x01")

    def test_human_sizes(self):
        self.assertEqual(clipboard.human_size(8), "8 bytes")
        self.assertEqual(clipboard.human_size(256 * 1024), "256 KiB")
        self.assertEqual(clipboard.human_size(20 * 1024 * 1024), "20 MiB")


if __name__ == "__main__":
    unittest.main()

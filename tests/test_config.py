import json
import os
import unittest

import support
from readily import config
from readily.errors import ReadilyError


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.box = support.Sandbox()
        self.box.apply()

    def tearDown(self):
        self.box.cleanup()

    def write_config(self, data):
        path = os.path.join(self.box.config, "readily", "config.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))
        return path

    def write_obsidian(self, vaults):
        path = os.path.join(self.box.config, "obsidian", "obsidian.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"vaults": vaults}, f)


class Resolve(ConfigTest):
    def test_env_wins_over_config(self):
        self.write_config({"folder": "/somewhere/else"})
        self.assertEqual(config.resolve_folder(), (self.box.folder, "env", ""))

    def test_config_is_used_without_env(self):
        os.environ["READILY_DIR"] = ""
        self.write_config({"folder": "~/Notes/Readily"})
        self.assertEqual(config.resolve_folder(), (os.path.join(self.box.home, "Notes", "Readily"), "config", ""))

    def test_broken_config_reports_why(self):
        os.environ["READILY_DIR"] = ""
        self.write_config("{not json")
        folder, source, error = config.resolve_folder()
        self.assertEqual((folder, source), ("", "config"))
        self.assertIn("is not valid", error)

    def test_nothing_chosen_yet(self):
        os.environ["READILY_DIR"] = ""
        self.assertEqual(config.resolve_folder(), ("", "none", ""))

    def test_relative_folder_is_refused(self):
        os.environ["READILY_DIR"] = "relative/path"
        folder, source, error = config.resolve_folder()
        self.assertEqual((folder, source), ("", "env"))
        self.assertIn("absolute", error)


class Vaults(ConfigTest):
    def test_suggestions_put_the_open_vault_first_then_newest(self):
        a, b, c = (os.path.join(self.box.home, name) for name in ("a", "b", "c"))
        os.makedirs(os.path.join(c, "Readily"))
        self.write_obsidian({"1": {"path": a, "ts": 1}, "2": {"path": b, "ts": 0, "open": True}, "3": {"path": c, "ts": 5}})
        self.assertEqual(config.suggestions(), [
            {"path": os.path.join(b, "Readily"), "label": "Obsidian: b", "exists": False},
            {"path": os.path.join(c, "Readily"), "label": "Obsidian: c", "exists": True},
            {"path": os.path.join(a, "Readily"), "label": "Obsidian: a", "exists": False},
            {"path": os.path.join(self.box.home, "Readily"), "label": "Home folder", "exists": True},
        ])

    def test_no_obsidian_still_suggests_home(self):
        self.assertEqual([s["label"] for s in config.suggestions()], ["Home folder"])

    def test_vault_root_is_the_nearest_obsidian_folder(self):
        vault = os.path.join(self.box.home, "vault")
        os.makedirs(os.path.join(vault, ".obsidian"))
        os.makedirs(os.path.join(vault, "deep", "Readily"))
        self.assertEqual(config.vault_root(os.path.join(vault, "deep", "Readily")), os.path.realpath(vault))
        self.assertEqual(config.vault_root(self.box.folder), "")


class Init(ConfigTest):
    def setUp(self):
        super().setUp()
        os.environ["READILY_DIR"] = ""  # init refuses to run while it is set

    def test_init_creates_folder_example_and_config(self):
        target = os.path.join(self.box.home, "Vault", "Readily")
        self.assertEqual(config.init_folder(target), target)
        with open(os.path.join(target, "commands.md")) as f:
            self.assertEqual(f.read(), config.EXAMPLE_NOTE)
        with open(config.config_path()) as f:
            self.assertEqual(json.load(f), {"folder": target})

    def test_init_leaves_existing_sections_alone(self):
        self.box.write("mine.md", "## Mine\n")
        config.init_folder(self.box.folder)
        self.assertEqual(sorted(os.listdir(self.box.folder)), ["mine.md"])

    def test_init_never_overwrites_commands(self):
        self.box.write("commands.md", "my own\n")
        config.init_folder(self.box.folder)
        self.assertEqual(self.box.read("commands.md"), "my own\n")

    def test_init_refuses_relative_paths_and_files(self):
        with self.assertRaises(ReadilyError) as caught:
            config.init_folder("relative")
        self.assertEqual(caught.exception.code, 2)
        a_file = self.box.write("file.txt", "x")
        with self.assertRaises(ReadilyError):
            config.init_folder(a_file)

    def test_runtime_dir_is_private(self):
        path = config.runtime_dir()
        self.assertEqual(path, os.path.join(self.box.runtime, "readily"))
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o700)


if __name__ == "__main__":
    unittest.main()

import json
import os
import time
import unittest
from urllib.parse import quote

import support
from support import note


class CliTest(unittest.TestCase):
    def setUp(self):
        self.box = support.Sandbox()

    def tearDown(self):
        self.box.cleanup()

    def ok(self, *args, **kw):
        result = self.box.run(*args, **kw)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        return result.stdout.decode()

    def json(self, *args, **kw):
        return json.loads(self.ok(*args, **kw))

    def fails(self, code, *args, **kw):
        result = self.box.run(*args, **kw)
        self.assertEqual(result.returncode, code, (result.stdout, result.stderr))
        err = result.stderr.decode()
        self.assertTrue(err.startswith("readily: ") or code == 2, err)
        return err

    def wait_for(self, path, seconds=3):
        deadline = time.monotonic() + seconds
        while not os.path.exists(path) and time.monotonic() < deadline:
            time.sleep(0.05)
        with open(path) as f:
            return f.read()


class Reading(CliTest):
    def test_help_and_usage_errors(self):
        self.assertIn("readily", self.ok("-h"))
        self.fails(2, "nope")
        self.fails(2)

    def test_where_with_env_and_a_missing_folder(self):
        self.assertEqual(self.json("where", "--json"),
                         {"folder": self.box.folder, "source": "env", "exists": True, "vault": "", "error": ""})
        gone = os.path.join(self.box.root, "gone")
        self.assertFalse(self.json("where", "--json", env={"READILY_DIR": gone})["exists"])
        self.assertIn("Folder not found", self.fails(4, "list", env={"READILY_DIR": gone}))

    def test_where_without_any_folder(self):
        self.assertEqual(self.json("where", "--json", env={"READILY_DIR": ""})["source"], "none")
        self.assertIn("No folder chosen", self.fails(4, "list", env={"READILY_DIR": ""}))
        self.assertIn("from    none", self.ok("where", env={"READILY_DIR": ""}))

    def test_vaults_and_init_then_list_the_example(self):
        self.assertEqual(self.json("vaults", "--json")["suggestions"][-1]["label"], "Home folder")
        target = os.path.join(self.box.home, "Vault", "Readily")
        self.assertEqual(self.ok("init", "--", target, env={"READILY_DIR": ""}).strip(), target)
        payload = self.json("list", "--json", env={"READILY_DIR": ""})
        self.assertEqual([i["title"] for i in payload["sections"][0]["items"]],
                         ["Find what is using a port", "Follow a service's log", "Copy a file to another machine"])
        self.assertEqual(self.json("where", "--json", env={"READILY_DIR": ""})["source"], "config")

    def test_list_and_tags_for_the_terminal(self):
        self.box.write("commands.md", note("## Pods #chi", "```", "kubectl get pods", "second line", "```",
                                           "## Other", "```", "ls", "```"))
        self.box.write("links.md", note("---", "tags: chi", "---", "## Staging", "```", "https://staging", "```"))
        text = self.ok("list", "--tag", "#CHI")
        self.assertIn("commands\n  [0] Pods  #chi\n      kubectl get pods\n      second line\n", text)
        self.assertIn("links\n  [0] Staging  #chi\n      https://staging\n", text)
        self.assertNotIn("Other", text)
        self.assertEqual(self.ok("tags"), "   2  #chi\n")
        self.assertEqual(self.json("tags", "--json"), {"tags": [{"name": "chi", "count": 2}]})
        self.assertIn("Not a valid tag: 123", self.fails(2, "list", "--tag", "123"))

    def test_open_uses_obsidian_inside_a_registered_vault(self):
        os.makedirs(os.path.join(self.box.home, ".obsidian"))
        os.makedirs(os.path.join(self.box.config, "obsidian"))
        with open(os.path.join(self.box.config, "obsidian", "obsidian.json"), "w") as f:
            json.dump({"vaults": {"x": {"path": self.box.home, "ts": 1}}}, f)
        path = self.box.write("commands.md", "")
        self.ok("open", "--", "commands")
        opened = self.wait_for(os.path.join(self.box.clip, "opened"))
        self.assertEqual(opened, "obsidian://open?path=" + quote(os.path.realpath(path), safe=""))

    def test_open_without_a_vault_opens_the_note_or_folder(self):
        path = self.box.write("commands.md", "")
        self.ok("open", "commands")
        self.assertEqual(self.wait_for(os.path.join(self.box.clip, "opened")), os.path.realpath(path))
        os.unlink(os.path.join(self.box.clip, "opened"))
        self.ok("open")
        self.assertEqual(self.wait_for(os.path.join(self.box.clip, "opened")), self.box.folder)
        self.assertIn("no section named nope", self.fails(1, "open", "nope"))


if __name__ == "__main__":
    unittest.main()

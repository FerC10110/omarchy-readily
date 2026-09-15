import json
import os
import subprocess
import sys
import time
import unittest
from urllib.parse import quote

import support
from support import note


class CliTest(unittest.TestCase):
    def setUp(self):
        self.box = support.Sandbox()
        # A cleanup, not tearDown, so cleanups a test adds (like restoring a
        # folder's permissions) run before the sandbox is removed.
        self.addCleanup(self.box.cleanup)

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

    def test_init_refuses_while_readily_dir_is_set(self):
        target = os.path.join(self.box.home, "Other")
        self.assertEqual(self.fails(1, "init", "--", target),
                         "readily: READILY_DIR is set; unset it to change the folder\n")
        self.assertFalse(os.path.exists(os.path.join(self.box.config, "readily")))
        self.assertFalse(os.path.exists(target))
        self.assertEqual(self.ok("init", "--", target, env={"READILY_DIR": "  "}).strip(), target)

    def test_init_creates_the_readily_dir_folder_without_remembering_it(self):
        target = os.path.join(self.box.home, "Missing")
        self.assertEqual(self.ok("init", "--", target, env={"READILY_DIR": target}).strip(), target)
        self.assertTrue(os.path.isfile(os.path.join(target, "commands.md")))
        self.assertFalse(os.path.exists(os.path.join(self.box.config, "readily")))

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

    def test_a_note_name_that_is_not_utf8_is_skipped(self):
        self.box.write("commands.md", note("```", "ls", "```"))
        os.close(os.open(os.path.join(os.fsencode(self.box.folder), b"bad\xff.md"), os.O_CREAT | os.O_WRONLY, 0o644))
        self.assertEqual([s["name"] for s in self.json("list", "--json")["sections"]], ["commands"])
        self.assertEqual(self.ok("list"), "commands\n  [0] ls\n      ls\n")

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


class Writing(CliTest):
    def test_save_text_from_the_clipboard_then_copy_it_back(self):
        self.box.copy_text("kubectl get pods -A\n")
        peek = self.json("peek", "--json")
        self.assertEqual({k: peek[k] for k in ("state", "preview", "lineCount", "title")},
                         {"state": "text", "preview": "kubectl get pods -A", "lineCount": 1, "title": "kubectl get pods -A"})
        self.ok("save", "--title=Pods", "--tag=#Chi", "--tag=k8s", "--create", "--expect=" + peek["hash"], "--", "chi")
        self.assertEqual(self.box.read("chi.md"), "## Pods\n#chi #k8s\n```\nkubectl get pods -A\n```\n")
        item = self.json("list", "--json")["sections"][0]["items"][0]
        self.ok("copy", "--", "chi", str(item["index"]), item["hash"])
        self.assertEqual(self.box.copied(), ("--type text/plain;charset=utf-8", b"kubectl get pods -A"))

    def test_save_refuses_a_changed_clipboard(self):
        self.box.copy_text("one")
        peek = self.json("peek", "--json")
        self.box.copy_text("two")
        self.assertIn("clipboard changed", self.fails(3, "save", "--create", "--expect=" + peek["hash"], "chi"))
        self.assertFalse(os.path.exists(os.path.join(self.box.folder, "chi.md")))

    def test_save_needs_create_and_valid_tags_and_names(self):
        self.box.copy_text("x")
        self.assertIn("--create", self.fails(1, "save", "chi"))
        self.assertIn("Not a valid tag: 123", self.fails(2, "save", "--create", "--tag=123", "chi"))
        self.assertIn("Not a valid section name", self.fails(2, "save", "--create", "--", "../x"))
        self.assertEqual(os.listdir(self.box.folder), [])

    def test_save_into_existing_notes_whose_names_a_new_section_could_not_have(self):
        self.box.write("Git & GitHub.md", "start\n")
        self.box.write("k8s.prod.md", "")
        self.ok("save", "--stdin", "--", "Git & GitHub", stdin=b"git push")
        self.ok("save", "--stdin", "--", "k8s.prod", stdin=b"kubectl get pods")
        self.assertEqual(self.box.read("Git & GitHub.md"), "start\n\n## git push\n```\ngit push\n```\n")
        self.assertEqual(self.box.read("k8s.prod.md"), "## kubectl get pods\n```\nkubectl get pods\n```\n")
        self.assertIn("Not a valid section name", self.fails(2, "save", "--create", "--stdin", "--", "New & Old",
                                                             stdin=b"x"))

    def test_a_section_differing_only_in_case_is_refused(self):
        self.box.write("Commands.md", "start\n")
        self.assertEqual(self.fails(2, "save", "--create", "--stdin", "--", "commands", stdin=b"ls"),
                         "readily: A section named Commands already exists\n")
        self.assertEqual(os.listdir(self.box.folder), ["Commands.md"])
        self.ok("save", "--create", "--stdin", "--", "Commands", stdin=b"ls")
        self.assertEqual(self.box.read("Commands.md"), "start\n\n## ls\n```\nls\n```\n")

    def test_save_from_stdin_uses_the_first_line_as_title(self):
        self.ok("save", "--create", "--stdin", "commands", stdin=b"\n  docker compose up -d\nsecond\n\n")
        self.assertEqual(self.box.read("commands.md"),
                         "## docker compose up -d\n```\n\n  docker compose up -d\nsecond\n```\n")

    def test_title_starting_with_a_dash(self):
        self.ok("save", "--create", "--stdin", "--title=-la flag", "commands", stdin=b"ls -la")
        self.assertTrue(self.box.read("commands.md").startswith("## -la flag\n"))

    def test_nothing_to_save(self):
        self.assertIn("Nothing is copied", self.fails(1, "save", "--create", "commands"))
        self.assertIn("Nothing to save", self.fails(1, "save", "--create", "--stdin", "commands", stdin=b"\n\n"))
        self.box.copy_text("secret", types="text/plain\nx-kde-passwordManagerHint\n")
        self.assertIn("password manager", self.fails(1, "save", "--create", "commands"))
        self.assertEqual(self.json("peek", "--json")["state"], "sensitive")

    def test_save_image_writes_an_attachment_and_copy_returns_it(self):
        self.box.copy_bytes("image/png", support.PNG)
        peek = self.json("peek", "--json")
        self.assertEqual(peek["state"], "image")
        with open(peek["image"], "rb") as f:
            self.assertEqual(f.read(), support.PNG)
        self.ok("save", "--title=Map", "--tag=chi", "--create", "--expect=" + peek["hash"], "shots")
        [name] = os.listdir(os.path.join(self.box.folder, "attachments"))
        self.assertRegex(name, r"^shots-\d{8}-\d{6}\.png$")
        self.assertEqual(self.box.read("shots.md"), f"## Map\n#chi\n![](attachments/{name})\n")
        item = self.json("list", "--json")["sections"][0]["items"][0]
        self.assertEqual(item["kind"], "image")
        self.ok("copy", "shots", "0", item["hash"])
        self.assertEqual(self.box.copied(), ("--type image/png", support.PNG))

    def test_image_without_title_and_failed_save_leaves_no_attachment(self):
        self.box.copy_bytes("image/png", support.PNG)
        self.ok("save", "--create", "shots")
        self.assertRegex(self.box.read("shots.md"), r"^## Image \d{4}-\d{2}-\d{2} \d{2}:\d{2}\n!\[\]\(attachments/")
        self.fails(1, "save", "missing")
        self.assertEqual(len(os.listdir(os.path.join(self.box.folder, "attachments"))), 1)

    def test_copy_after_the_note_changed(self):
        self.box.write("commands.md", note("## A", "```", "one", "```"))
        item = self.json("list", "--json")["sections"][0]["items"][0]
        self.box.write("commands.md", note("## A", "```", "edited", "```"))
        self.assertIn("commands changed", self.fails(3, "copy", "commands", "0", item["hash"]))
        self.fails(3, "copy", "commands", "5", item["hash"])
        self.fails(3, "copy", "gone", "0", item["hash"])
        self.assertEqual(self.box.copied(), (None, None))

    def test_copy_a_missing_image(self):
        self.box.write("shots.md", note("![](attachments/gone.png)"))
        item = self.json("list", "--json")["sections"][0]["items"][0]
        self.assertIn("missing", self.fails(1, "copy", "shots", "0", item["hash"]))

    def test_concurrent_saves_keep_every_item(self):
        texts = [f"command number {n}" for n in range(6)]
        env = dict(self.box.env)
        procs = [subprocess.Popen([sys.executable, support.READILY, "save", "--create", "--stdin", "commands"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
                 for _ in texts]
        for proc, text in zip(procs, texts):
            proc.stdin.write(text.encode())
            proc.stdin.close()
        for proc in procs:
            self.assertEqual(proc.wait(timeout=30), 0, proc.stderr.read())
            proc.stdout.close()
            proc.stderr.close()
        saved = [i["search"] for i in self.json("list", "--json")["sections"][0]["items"]]
        self.assertEqual(sorted(saved), sorted(texts))


@unittest.skipIf(os.geteuid() == 0, "root can write into a read-only folder")
class FilesystemErrors(CliTest):
    def lock_folder(self):
        os.chmod(self.box.folder, 0o555)
        self.addCleanup(os.chmod, self.box.folder, 0o755)

    def one_line(self, err):
        self.assertEqual(len(err.splitlines()), 1, err)
        self.assertTrue(err.startswith("readily: "), err)

    def test_a_read_only_folder_is_one_error_line(self):
        self.box.write("commands.md", "start\n")
        self.lock_folder()
        err = self.fails(1, "save", "--stdin", "commands", stdin=b"ls")
        self.one_line(err)
        self.assertIn("Permission denied: " + self.box.folder, err)
        self.assertEqual(self.box.read("commands.md"), "start\n")

    def test_a_failed_append_removes_the_image_it_stored(self):
        self.box.write("shots.md", "start\n")
        attachments = os.path.join(self.box.folder, "attachments")
        os.makedirs(attachments)
        self.lock_folder()
        self.box.copy_bytes("image/png", support.PNG)
        err = self.fails(1, "save", "shots")
        self.one_line(err)
        # The image was stored; the note's temporary file is what failed.
        self.assertIn(os.path.join(self.box.folder, ".readily-"), err)
        self.assertEqual(os.listdir(attachments), [])
        self.assertEqual(self.box.read("shots.md"), "start\n")


if __name__ == "__main__":
    unittest.main()

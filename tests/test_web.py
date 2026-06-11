import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from skills_manager.web import create_server


class WebTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.library = self.root / "library"
        self.library.mkdir()
        (self.library / "project-a").mkdir()
        (self.library / "project-a" / "skills" / "writer").mkdir(parents=True)
        (self.library / "project-a" / "skills" / "writer" / "SKILL.md").write_text(
            "content",
            encoding="utf-8",
        )
        self.agent_paths = {
            "codex": self.root / "codex",
            "claude": self.root / "claude",
        }
        self.state_file = self.root / "state.json"
        self.opened_folders = []
        self.server = create_server(
            self.state_file,
            "127.0.0.1",
            0,
            self.agent_paths,
            folder_opener=self.opened_folders.append,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temporary.cleanup()

    def get(self, path):
        with urlopen(self.base_url + path) as response:
            return response.status, response.read(), response.headers["Content-Type"]

    def get_json(self, path):
        with urlopen(self.base_url + path) as response:
            return response.status, json.loads(response.read())

    def post(self, path, payload):
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            return response.status, json.loads(response.read())

    def post_error(self, path, payload):
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        return caught.exception.code, json.loads(caught.exception.read())

    def test_serves_page_and_complete_toggle_workflow(self):
        status, content, content_type = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn("Skills Manager", content.decode("utf-8"))

        status, state, _ = self.get("/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(
            json.loads(state)["state_file_path"],
            str(self.state_file.resolve()),
        )
        self.assertFalse(self.state_file.exists())

        status, state = self.post("/api/library", {"path": str(self.library)})
        self.assertEqual(status, 200)
        self.assertEqual(state["projects"][0]["name"], "project-a")

        status, state = self.post(
            "/api/tags",
            {"project": "project-a", "tags": ["写作", "常用"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(state["projects"][0]["tags"], ["写作", "常用"])
        self.assertEqual(state["tags"], ["写作", "常用"])

        status, state = self.post(
            "/api/tags/batch",
            {
                "projects": ["project-a"],
                "tags": ["批量"],
                "action": "add",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(state["projects"][0]["tags"], ["写作", "常用", "批量"])

        status, state = self.post(
            "/api/tags/batch",
            {
                "projects": ["project-a"],
                "tags": ["写作"],
                "action": "remove",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(state["projects"][0]["tags"], ["常用", "批量"])

        status, details = self.get_json(
            f"/api/project-details?project={quote('project-a')}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            details["skills"],
            [{"name": "writer", "path": "skills/writer/SKILL.md"}],
        )

        status, result = self.post(
            "/api/open-folder",
            {"project": "project-a"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            result["opened"],
            str((self.library / "project-a").resolve()),
        )

        status, result = self.post(
            "/api/open-folder",
            {"project": "project-a", "skill": "skills/writer/SKILL.md"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            result["opened"],
            str((self.library / "project-a" / "skills" / "writer").resolve()),
        )
        self.assertEqual(
            self.opened_folders,
            [
                (self.library / "project-a").resolve(),
                (self.library / "project-a" / "skills" / "writer").resolve(),
            ],
        )

        status, error = self.post_error(
            "/api/open-folder",
            {"project": "project-a", "skill": "../outside/SKILL.md"},
        )
        self.assertEqual(status, 409)
        self.assertIn("不存在 Skill", error["error"])
        self.assertEqual(len(self.opened_folders), 2)

        _, state = self.post(
            "/api/toggle",
            {"project": "project-a", "agent": "codex", "enabled": True},
        )
        self.assertEqual(state["projects"][0]["agents"]["codex"]["state"], "enabled")
        self.assertTrue((self.agent_paths["codex"] / "project-a").is_symlink())

        _, state = self.post(
            "/api/toggle",
            {"project": "project-a", "agent": "codex", "enabled": False},
        )
        self.assertEqual(state["projects"][0]["agents"]["codex"]["state"], "disabled")
        self.assertFalse((self.agent_paths["codex"] / "project-a").exists())


if __name__ == "__main__":
    unittest.main()

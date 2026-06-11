import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from skills_manager.web import create_server


class WebTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.library = self.root / "library"
        self.library.mkdir()
        (self.library / "project-a").mkdir()
        self.agent_paths = {
            "codex": self.root / "codex",
            "claude": self.root / "claude",
        }
        self.state_file = self.root / "state.json"
        self.server = create_server(
            self.state_file,
            "127.0.0.1",
            0,
            self.agent_paths,
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

    def post(self, path, payload):
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            return response.status, json.loads(response.read())

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

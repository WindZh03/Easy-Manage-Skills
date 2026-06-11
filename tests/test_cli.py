import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from skills_manager.cli import main, parser
from skills_manager.core import DEFAULT_STATE_FILE


class CliTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state = self.root / "state.json"
        self.library = self.root / "library"
        self.library.mkdir()
        (self.library / "project-a").mkdir()
        (self.library / "project-a" / "nested").mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, *arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--state-file", str(self.state), *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_state_file_defaults_for_all_commands(self):
        serve_arguments = parser().parse_args(["serve", "--no-browser"])
        list_arguments = parser().parse_args(["list"])

        self.assertEqual(serve_arguments.state_file, DEFAULT_STATE_FILE)
        self.assertEqual(list_arguments.state_file, DEFAULT_STATE_FILE)

    def test_init_and_list_only_show_first_level_project(self):
        code, _, _ = self.invoke("init", str(self.library))
        self.assertEqual(code, 0)

        code, output, _ = self.invoke("list")

        self.assertEqual(code, 0)
        self.assertEqual(output.strip(), "project-a")


if __name__ == "__main__":
    unittest.main()

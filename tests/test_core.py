import os
import tempfile
import unittest
from pathlib import Path

from skills_manager.core import (
    ConfigurationError,
    ConflictError,
    SafetyError,
    SkillsManager,
    StateStore,
)


class SkillsManagerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.library = self.root / "library"
        self.library.mkdir()
        self.agent_paths = {
            "codex": self.root / "codex",
            "claude": self.root / "claude",
        }
        self.manager = SkillsManager(
            StateStore(self.root / "state.json"),
            self.agent_paths,
        )
        self.manager.set_library(self.library)

    def tearDown(self):
        self.temporary.cleanup()

    def create_project(self, name="Idea-Copilot"):
        project = self.library / name
        (project / "skills" / "nested").mkdir(parents=True)
        (project / "skills" / "nested" / "SKILL.md").write_text(
            "content", encoding="utf-8"
        )
        return project

    def test_only_lists_first_level_folders(self):
        self.create_project()
        (self.library / "readme.txt").write_text("not a project", encoding="utf-8")

        projects = self.manager.projects()

        self.assertEqual([project.name for project in projects], ["Idea-Copilot"])
        self.assertEqual(projects[0].path, self.library.resolve() / "Idea-Copilot")

    def test_enable_and_disable_managed_link(self):
        source = self.create_project()

        target = self.manager.enable("Idea-Copilot", "codex")

        self.assertTrue(target.is_symlink())
        self.assertEqual(target.resolve(), source.resolve())
        self.assertEqual(
            self.manager.status(self.manager.project("Idea-Copilot"), "codex").state,
            "enabled",
        )

        self.manager.disable("Idea-Copilot", "codex")
        self.assertFalse(os.path.lexists(target))

    def test_enable_same_project_for_both_agents(self):
        source = self.create_project()

        codex = self.manager.enable("Idea-Copilot", "codex")
        claude = self.manager.enable("Idea-Copilot", "claude")

        self.assertEqual(codex.resolve(), source.resolve())
        self.assertEqual(claude.resolve(), source.resolve())

    def test_existing_target_is_conflict_and_is_never_overwritten(self):
        self.create_project()
        target = self.agent_paths["codex"] / "Idea-Copilot"
        target.mkdir(parents=True)
        user_file = target / "user.txt"
        user_file.write_text("keep", encoding="utf-8")

        with self.assertRaises(ConflictError):
            self.manager.enable("Idea-Copilot", "codex")

        self.assertEqual(user_file.read_text(encoding="utf-8"), "keep")

    def test_external_matching_link_is_visible_but_not_controllable(self):
        source = self.create_project()
        target = self.agent_paths["codex"] / "Idea-Copilot"
        target.parent.mkdir(parents=True)
        target.symlink_to(source, target_is_directory=True)

        status = self.manager.status(self.manager.project("Idea-Copilot"), "codex")

        self.assertEqual(status.state, "external")
        self.assertTrue(status.enabled)
        self.assertFalse(status.controllable)
        with self.assertRaises(SafetyError):
            self.manager.disable("Idea-Copilot", "codex")
        self.assertTrue(target.is_symlink())

    def test_missing_managed_link_can_be_recreated(self):
        self.create_project()
        target = self.manager.enable("Idea-Copilot", "codex")
        target.unlink()

        status = self.manager.status(self.manager.project("Idea-Copilot"), "codex")
        self.assertEqual(status.state, "missing")

        self.manager.enable("Idea-Copilot", "codex")
        self.assertTrue(target.is_symlink())

    def test_replaced_managed_link_is_not_deleted(self):
        self.create_project()
        target = self.manager.enable("Idea-Copilot", "codex")
        target.unlink()
        target.mkdir()

        with self.assertRaises(SafetyError):
            self.manager.disable("Idea-Copilot", "codex")

        self.assertTrue(target.is_dir())

    def test_cannot_switch_library_while_links_are_enabled(self):
        self.create_project()
        self.manager.enable("Idea-Copilot", "codex")
        other = self.root / "other-library"
        other.mkdir()

        with self.assertRaises(ConfigurationError):
            self.manager.set_library(other)

        self.assertEqual(self.manager.library_path(), self.library.resolve())

    def test_dashboard_contains_two_fixed_agents_and_project_statuses(self):
        self.create_project()
        self.manager.enable("Idea-Copilot", "claude")

        dashboard = self.manager.dashboard()

        self.assertEqual(
            [agent["id"] for agent in dashboard["agents"]],
            ["codex", "claude"],
        )
        self.assertEqual(dashboard["projects"][0]["agents"]["codex"]["state"], "disabled")
        self.assertEqual(dashboard["projects"][0]["agents"]["claude"]["state"], "enabled")


if __name__ == "__main__":
    unittest.main()


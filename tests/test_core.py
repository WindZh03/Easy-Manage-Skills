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

    def test_scans_skill_files_only_when_requested(self):
        project = self.create_project()
        (project / "SKILL.md").write_text("root", encoding="utf-8")
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "SKILL.md").write_text("outside", encoding="utf-8")
        (project / "linked").symlink_to(outside, target_is_directory=True)
        (project / "node_modules" / "ignored").mkdir(parents=True)
        (project / "node_modules" / "ignored" / "SKILL.md").write_text(
            "ignored",
            encoding="utf-8",
        )

        skills = self.manager.project_skills("Idea-Copilot")

        self.assertEqual(
            skills,
            [
                {"name": "Idea-Copilot", "path": "SKILL.md"},
                {"name": "nested", "path": "skills/nested/SKILL.md"},
            ],
        )

    def test_project_folder_only_allows_project_and_discovered_skills(self):
        project = self.create_project()

        self.assertEqual(self.manager.project_folder("Idea-Copilot"), project.resolve())
        self.assertEqual(
            self.manager.project_folder(
                "Idea-Copilot",
                "skills/nested/SKILL.md",
            ),
            project.resolve() / "skills" / "nested",
        )
        with self.assertRaises(ConfigurationError):
            self.manager.project_folder("Idea-Copilot", "../outside/SKILL.md")

    def test_project_tags_are_persisted_and_included_in_dashboard(self):
        self.create_project()

        tags = self.manager.set_project_tags(
            "Idea-Copilot",
            [" 研究 ", "写作", "研究", ""],
        )
        reloaded = SkillsManager(StateStore(self.root / "state.json"), self.agent_paths)

        self.assertEqual(tags, ["研究", "写作"])
        self.assertEqual(reloaded.project_tags("Idea-Copilot"), ["研究", "写作"])
        self.assertEqual(reloaded.dashboard()["tags"], ["写作", "研究"])
        self.assertEqual(
            reloaded.dashboard()["projects"][0]["tags"],
            ["研究", "写作"],
        )

    def test_batch_add_and_remove_project_tags(self):
        self.create_project()
        self.create_project("Other-Project")
        self.manager.set_project_tags("Idea-Copilot", ["研究"])
        self.manager.set_project_tags("Other-Project", ["日常"])

        added = self.manager.update_project_tags(
            ["Idea-Copilot", "Other-Project"],
            ["常用"],
            "add",
        )
        removed = self.manager.update_project_tags(
            ["Idea-Copilot", "Other-Project"],
            ["研究", "日常"],
            "remove",
        )

        self.assertEqual(added["Idea-Copilot"], ["研究", "常用"])
        self.assertEqual(added["Other-Project"], ["日常", "常用"])
        self.assertEqual(removed["Idea-Copilot"], ["常用"])
        self.assertEqual(removed["Other-Project"], ["常用"])

    def test_batch_tags_validate_all_projects_before_saving(self):
        self.create_project()
        self.manager.set_project_tags("Idea-Copilot", ["研究"])

        with self.assertRaises(ConfigurationError):
            self.manager.update_project_tags(
                ["Idea-Copilot", "Missing-Project"],
                ["常用"],
                "add",
            )

        self.assertEqual(self.manager.project_tags("Idea-Copilot"), ["研究"])

    def test_existing_state_without_project_metadata_remains_compatible(self):
        self.create_project()
        store = StateStore(self.root / "legacy-state.json")
        store.save(
            {
                "version": 2,
                "library_path": str(self.library),
                "deployments": {},
            }
        )

        manager = SkillsManager(store, self.agent_paths)
        manager.set_project_tags("Idea-Copilot", ["兼容"])

        self.assertEqual(manager.project_tags("Idea-Copilot"), ["兼容"])

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

    def test_switching_library_clears_project_tags(self):
        self.create_project()
        self.manager.set_project_tags("Idea-Copilot", ["研究"])
        other = self.root / "other-library"
        other.mkdir()

        self.manager.set_library(other)

        self.assertEqual(self.manager.state["project_metadata"], {})

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

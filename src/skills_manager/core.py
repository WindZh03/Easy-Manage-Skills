from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


STATE_VERSION = 2
DEFAULT_STATE_FILE = Path("~/skills-manager-state.json")
DEFAULT_AGENTS = {
    "codex": Path("~/.codex/skills"),
    "claude": Path("~/.claude/skills"),
}
AGENT_LABELS = {
    "codex": "Codex",
    "claude": "Claude Code",
}
SKILL_SCAN_IGNORED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


class SkillsManagerError(Exception):
    """可直接展示给用户的错误。"""


class ConfigurationError(SkillsManagerError):
    pass


class ConflictError(SkillsManagerError):
    pass


class SafetyError(SkillsManagerError):
    pass


@dataclass(frozen=True)
class Project:
    name: str
    path: Path


@dataclass(frozen=True)
class LinkStatus:
    project: str
    agent: str
    target: str
    state: str
    enabled: bool
    controllable: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def expand_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def absolute_path(value: str | Path) -> Path:
    return Path(os.path.abspath(Path(value).expanduser()))


def path_exists(path: Path) -> bool:
    return os.path.lexists(path)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_state() -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "library_path": None,
        "deployments": {},
        "project_metadata": {},
    }


class StateStore:
    def __init__(self, path: Path):
        self.path = expand_path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return default_state()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"无法读取状态文件 {self.path}: {exc}") from exc
        if data.get("version") != STATE_VERSION:
            raise ConfigurationError(
                f"状态文件版本不兼容，请移走后重试: {self.path}"
            )
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2, sort_keys=True)
                file.write("\n")
            os.replace(temporary, self.path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


class SkillsManager:
    def __init__(
        self,
        store: StateStore,
        agent_paths: Mapping[str, str | Path] | None = None,
    ):
        self.store = store
        self.state = store.load()
        self.state.setdefault("project_metadata", {})
        configured_agents = agent_paths or DEFAULT_AGENTS
        self.agents = {
            name: expand_path(configured_agents[name]) for name in DEFAULT_AGENTS
        }

    def save(self) -> None:
        self.store.save(self.state)

    def set_library(self, path: str | Path) -> Path:
        library = expand_path(path)
        if not library.is_dir():
            raise ConfigurationError(f"目录不存在或不是文件夹: {library}")
        current = self.state.get("library_path")
        if (
            current
            and expand_path(current) != library
            and self.state["deployments"]
        ):
            raise ConfigurationError("切换中央目录前，请先停用当前目录中的所有项目")
        if current and expand_path(current) != library:
            self.state["project_metadata"] = {}
        self.state["library_path"] = str(library)
        self.save()
        return library

    def library_path(self) -> Path:
        value = self.state.get("library_path")
        if not value:
            raise ConfigurationError("尚未配置 Skills 中央目录")
        return expand_path(value)

    def projects(self) -> list[Project]:
        library = self.library_path()
        if not library.is_dir():
            raise ConfigurationError(f"Skills 中央目录不存在: {library}")
        return [
            Project(path.name, path)
            for path in sorted(library.iterdir(), key=lambda item: item.name.lower())
            if path.is_dir()
        ]

    def project(self, name: str) -> Project:
        for project in self.projects():
            if project.name == name:
                return project
        raise ConfigurationError(f"中央目录中不存在一级文件夹: {name}")

    def project_tags(self, project_name: str) -> list[str]:
        metadata = self.state["project_metadata"].get(project_name, {})
        return list(metadata.get("tags", []))

    @staticmethod
    def normalize_tags(tags: list[str]) -> list[str]:
        normalized: list[str] = []
        for tag in tags:
            value = tag.strip()
            if not value or value in normalized:
                continue
            if len(value) > 30:
                raise ConfigurationError("每个标签最多 30 个字符")
            normalized.append(value)
        if len(normalized) > 12:
            raise ConfigurationError("每个项目最多设置 12 个标签")
        return normalized

    def store_project_tags(self, project_name: str, tags: list[str]) -> None:
        if tags:
            self.state["project_metadata"][project_name] = {"tags": tags}
        else:
            self.state["project_metadata"].pop(project_name, None)

    def set_project_tags(self, project_name: str, tags: list[str]) -> list[str]:
        self.project(project_name)
        normalized = self.normalize_tags(tags)
        self.store_project_tags(project_name, normalized)
        self.save()
        return normalized

    def update_project_tags(
        self,
        project_names: list[str],
        tags: list[str],
        action: str,
    ) -> dict[str, list[str]]:
        if action not in {"add", "remove"}:
            raise ConfigurationError(f"不支持的批量标签操作: {action}")
        projects = list(dict.fromkeys(project_names))
        if not projects:
            raise ConfigurationError("请至少选择一个项目")
        for project_name in projects:
            self.project(project_name)
        normalized = self.normalize_tags(tags)
        if not normalized:
            raise ConfigurationError("请至少选择一个标签")

        updated: dict[str, list[str]] = {}
        for project_name in projects:
            current = self.project_tags(project_name)
            if action == "add":
                result = self.normalize_tags([*current, *normalized])
            else:
                result = [tag for tag in current if tag not in normalized]
            updated[project_name] = result
        for project_name, result in updated.items():
            self.store_project_tags(project_name, result)
        self.save()
        return updated

    def project_skills(self, project_name: str) -> list[dict[str, str]]:
        project = self.project(project_name)
        skills = []
        for root, directories, files in os.walk(project.path, followlinks=False):
            directories[:] = sorted(
                directory
                for directory in directories
                if directory not in SKILL_SCAN_IGNORED_DIRS
                and not (Path(root) / directory).is_symlink()
            )
            if "SKILL.md" not in files:
                continue
            skill_file = Path(root) / "SKILL.md"
            relative = skill_file.relative_to(project.path)
            skills.append(
                {
                    "name": (
                        project.name
                        if relative.parent == Path(".")
                        else relative.parent.name
                    ),
                    "path": str(relative),
                }
            )
        return sorted(skills, key=lambda skill: skill["path"].lower())

    def project_folder(self, project_name: str, skill_path: str | None = None) -> Path:
        project = self.project(project_name)
        if skill_path is None:
            return project.path
        for skill in self.project_skills(project_name):
            if skill["path"] == skill_path:
                return project.path / Path(skill_path).parent
        raise ConfigurationError(f"{project_name} 中不存在 Skill: {skill_path}")

    def agent_path(self, agent: str) -> Path:
        if agent not in self.agents:
            raise ConfigurationError(f"不支持的 Agent: {agent}")
        return self.agents[agent]

    @staticmethod
    def deployment_key(project: str, agent: str) -> str:
        return f"{agent}::{project}"

    @staticmethod
    def _link_destination(target: Path) -> Path:
        return (target.parent / os.readlink(target)).resolve(strict=False)

    def status(self, project: Project, agent: str) -> LinkStatus:
        target = self.agent_path(agent) / project.name
        record = self.state["deployments"].get(
            self.deployment_key(project.name, agent)
        )
        base = {
            "project": project.name,
            "agent": agent,
            "target": str(target),
        }
        if not path_exists(target):
            if record:
                return LinkStatus(
                    **base,
                    state="missing",
                    enabled=False,
                    controllable=True,
                    detail="Manager 创建的软链接已丢失，可重新启用",
                )
            return LinkStatus(
                **base,
                state="disabled",
                enabled=False,
                controllable=True,
                detail="未启用",
            )
        if not target.is_symlink():
            return LinkStatus(
                **base,
                state="conflict",
                enabled=False,
                controllable=False,
                detail="目标位置存在同名普通文件或目录",
            )

        destination = self._link_destination(target)
        expected = project.path.resolve(strict=False)
        if destination != expected:
            return LinkStatus(
                **base,
                state="conflict",
                enabled=False,
                controllable=False,
                detail=f"同名软链接指向其他位置: {destination}",
            )
        if not record:
            return LinkStatus(
                **base,
                state="external",
                enabled=True,
                controllable=False,
                detail="软链接不是由 Manager 创建，无法在此停用",
            )
        if (
            expand_path(record["source"]) != expected
            or absolute_path(record["target"]) != absolute_path(target)
        ):
            return LinkStatus(
                **base,
                state="conflict",
                enabled=True,
                controllable=False,
                detail="Manager 记录与当前软链接不一致",
            )
        return LinkStatus(
            **base,
            state="enabled",
            enabled=True,
            controllable=True,
            detail="已启用",
        )

    def enable(self, project_name: str, agent: str) -> Path:
        project = self.project(project_name)
        target = self.agent_path(agent) / project.name
        key = self.deployment_key(project.name, agent)
        current = self.status(project, agent)
        if current.state == "enabled":
            return target
        if current.state not in {"disabled", "missing"}:
            raise ConflictError(f"无法启用 {project.name}: {current.detail}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(project.path, target_is_directory=True)
        self.state["deployments"][key] = {
            "project": project.name,
            "agent": agent,
            "source": str(project.path.resolve(strict=False)),
            "target": str(target),
            "created_at": utc_now(),
        }
        self.save()
        return target

    def disable(self, project_name: str, agent: str) -> Path:
        project = self.project(project_name)
        target = self.agent_path(agent) / project.name
        key = self.deployment_key(project.name, agent)
        record = self.state["deployments"].get(key)
        if not record:
            raise SafetyError(f"{project.name} 在 {AGENT_LABELS[agent]} 中不是 Manager 创建的")
        if not path_exists(target):
            self.state["deployments"].pop(key)
            self.save()
            return target
        current = self.status(project, agent)
        if current.state != "enabled":
            raise SafetyError(f"拒绝删除 {target}: {current.detail}")
        target.unlink()
        self.state["deployments"].pop(key)
        self.save()
        return target

    def set_enabled(self, project_name: str, agent: str, enabled: bool) -> Path:
        if enabled:
            return self.enable(project_name, agent)
        return self.disable(project_name, agent)

    def dashboard(self) -> dict[str, Any]:
        library_value = self.state.get("library_path")
        result: dict[str, Any] = {
            "library_path": library_value,
            "agents": [
                {
                    "id": agent,
                    "label": AGENT_LABELS[agent],
                    "path": str(self.agent_path(agent)),
                }
                for agent in DEFAULT_AGENTS
            ],
            "projects": [],
            "tags": [],
            "error": None,
        }
        if not library_value:
            return result
        try:
            projects = self.projects()
        except ConfigurationError as exc:
            result["error"] = str(exc)
            return result
        result["projects"] = [
            {
                "name": project.name,
                "path": str(project.path),
                "tags": self.project_tags(project.name),
                "agents": {
                    agent: self.status(project, agent).to_dict()
                    for agent in DEFAULT_AGENTS
                },
            }
            for project in projects
        ]
        result["tags"] = sorted(
            {
                tag
                for project in result["projects"]
                for tag in project["tags"]
            },
            key=str.lower,
        )
        return result

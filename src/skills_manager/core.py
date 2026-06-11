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
                "agents": {
                    agent: self.status(project, agent).to_dict()
                    for agent in DEFAULT_AGENTS
                },
            }
            for project in projects
        ]
        return result
